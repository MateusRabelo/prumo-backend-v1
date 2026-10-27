import calendar
import re
from datetime import date
from decimal import Decimal
from fastapi import HTTPException
from app.models.installment import InstallmentPlan, Installment
from app.models.import_rule import StatementImportLink
from app.services.statement_parser import normalize


def merchant_name(description):
    return re.sub(r'\s*(?:[-·]\s*)?Parcelas?\s+(?:\d+|\*)\s*/\s*(?:\d+|\*)\s*$', '', description, flags=re.I).strip()


def merchant_key(description):
    return normalize(merchant_name(description))

def find_plan(db, family_id, card_id, row, display_name):
    info = row.get('installment_info')
    if not info:
        return None
    names = {merchant_key(info['description']), merchant_key(display_name)}
    candidates = db.query(InstallmentPlan).filter(InstallmentPlan.family_id == family_id,
        InstallmentPlan.card_id == card_id, InstallmentPlan.status != 'CANCELLED',
        InstallmentPlan.installments_count == info['count']).all()
    matches = [plan for plan in candidates if merchant_key(plan.description) in names and any(
        i.installment_number == info['number'] and abs(Decimal(i.amount) - Decimal(row['amount'])) <= Decimal('.01')
        for i in plan.installments)]
    if len(matches) > 1:
        raise HTTPException(409, detail='Há mais de um parcelamento compatível. Confira os planos antes de importar esta parcela.')
    return matches[0] if matches else None


def monthly_due(first, offset, due_day):
    index = first.year * 12 + first.month - 1 + offset
    year, month_index = divmod(index, 12)
    return date(year, month_index + 1, min(due_day, calendar.monthrange(year, month_index + 1)[1]))


def apply_parcel(db, family, user, account_id, card, row, entry, category, invoice):
    info = row.get('installment_info')
    if not info:
        raise HTTPException(400, detail='Esta linha não contém uma parcela identificada')
    plan = find_plan(db, family.id, card.id, row, entry.description)
    first = invoice.due_date
    from app.models.invoice import CardInvoice
    # Never move an installment into or out of an invoice that has received payment.
    dates = {monthly_due(first, offset, card.due_day) for offset in range(info['count'] - info['number'] + 1)}
    if plan:
        dates |= {i.due_date for i in plan.installments if i.installment_number >= info['number'] and i.status == 'PENDENTE'}
    periods = {(d.year, d.month) for d in dates}
    if any((i.year, i.month) in periods for i in db.query(CardInvoice).filter_by(card_id=card.id).filter(((CardInvoice.paid_amount > 0) | (CardInvoice.external_settled == True))).all()):
        raise HTTPException(409, detail='Uma das parcelas pertence a uma fatura com pagamento. Revise o plano sem alterar o histórico pago.')
    if plan:
        parcel = next(i for i in plan.installments if i.installment_number == info['number'])
        if parcel.status != 'PENDENTE':
            return parcel, False
        # Only unobserved future dates are aligned. Paid/historical entries are untouched.
        for item in plan.installments:
            if item.installment_number >= info['number'] and item.status == 'PENDENTE':
                item.due_date = monthly_due(first, item.installment_number - info['number'], card.due_day)
        parcel.due_date = first
        difference = Decimal(row['amount']) - Decimal(parcel.amount)
        parcel.amount = Decimal(row['amount'])
        plan.total_amount = Decimal(plan.total_amount) + difference
        plan.account_id = account_id
        if category:
            plan.category_id = category.id
        plan.description = merchant_name(entry.description)
        return parcel, True
    if not category:
        raise HTTPException(400, detail='Escolha uma categoria para criar o parcelamento identificado')
    remaining = info['count'] - info['number'] + 1
    amount = Decimal(row['amount'])
    total = amount * remaining
    if total > Decimal('9999999999.99'):
        raise HTTPException(400, detail='O valor do parcelamento excede o limite permitido')
    from app.models.family import FamilyMembership
    member = db.query(FamilyMembership).filter_by(family_id=family.id, user_id=user.id).one()
    name = merchant_name(entry.description)
    plan = InstallmentPlan(family_id=family.id, created_by_id=user.id, description=name,
        category_id=category.id, account_id=account_id, card_id=card.id,
        responsible_name=card.responsible_name or member.alias_name, is_shared=card.responsible_name == 'Conjunto',
        total_amount=total, installments_count=info['count'], imported_from_number=info['number'],
        purchase_date=date.fromisoformat(row['date']), first_due_date=first, status='ACTIVE',
        notes='Criado do extrato a partir da parcela observada. Parcelas anteriores não foram recriadas; futuras são estimadas pelo valor informado.')
    db.add(plan); db.flush()
    current = None
    for offset in range(remaining):
        parcel = Installment(installment_plan_id=plan.id, installment_number=info['number'] + offset,
            amount=amount, due_date=first if offset == 0 else monthly_due(first, offset, card.due_day), status='PENDENTE')
        db.add(parcel)
        if offset == 0:
            current = parcel
    db.flush()
    return current, True
