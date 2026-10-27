import calendar
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_family, get_current_user, get_admin_family
from app.models.card import CreditCard
from app.models.family import FamilySpace
from app.models.installment import Installment, InstallmentPlan
from app.models.invoice import CardInvoice
from app.models.account import FinancialAccount
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.settings import CreditCardCreate, CreditCardResponse, CreditCardUpdate
from app.schemas.invoice import CardInvoiceResponse, CardInvoiceItem, InvoicePayRequest

from app.services.validation import validate_relations
from app.services.audit_service import AuditService

router = APIRouter(prefix="/cards", tags=["Cartões de Crédito e Benefício"])

MONTH_NAMES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
]


def get_invoice_cycle_dates(card: CreditCard, year: int, month: int):
    _, last_day_of_month = calendar.monthrange(year, month)
    due_day = min(card.due_day, last_day_of_month)
    due_date = date(year, month, due_day)

    closing_day = card.closing_day

    if card.due_day <= card.closing_day:
        # Closing date in previous month
        if month == 1:
            prev_year = year - 1
            prev_month = 12
        else:
            prev_year = year
            prev_month = month - 1
        _, last_day_prev = calendar.monthrange(prev_year, prev_month)
        closing_date = date(prev_year, prev_month, min(closing_day, last_day_prev))
    else:
        # Closing date in the same month
        closing_date = date(year, month, min(closing_day, last_day_of_month))

    # Cycle start date is day after previous cycle's closing date
    if closing_date.month == 1:
        cycle_prev_year = closing_date.year - 1
        cycle_prev_month = 12
    else:
        cycle_prev_year = closing_date.year
        cycle_prev_month = closing_date.month - 1
    _, last_day_cycle_prev = calendar.monthrange(cycle_prev_year, cycle_prev_month)
    prev_closing = date(cycle_prev_year, cycle_prev_month, min(closing_day, last_day_cycle_prev))
    start_date = prev_closing + timedelta(days=1)

    return start_date, closing_date, due_date


def get_current_invoice_period(card: CreditCard, ref_date: Optional[date] = None) -> tuple[int, int]:
    if not ref_date:
        ref_date = date.today()

    if ref_date.day <= card.closing_day:
        if card.due_day <= card.closing_day:
            target_year = ref_date.year if ref_date.month < 12 else ref_date.year + 1
            target_month = ref_date.month + 1 if ref_date.month < 12 else 1
            return target_year, target_month
        else:
            return ref_date.year, ref_date.month
    else:
        if card.due_day <= card.closing_day:
            m = ref_date.month + 2
            y = ref_date.year
            if m > 12:
                m -= 12
                y += 1
            return y, m
        else:
            m = ref_date.month + 1
            y = ref_date.year
            if m > 12:
                m -= 12
                y += 1
            return y, m


def compute_card_limits(db: Session, card: CreditCard):
    # Pending installments for this card
    pending_installments = db.query(func.coalesce(func.sum(Installment.amount), 0)).join(
        InstallmentPlan, Installment.installment_plan_id == InstallmentPlan.id
    ).filter(
        InstallmentPlan.card_id == card.id,
        Installment.status == "PENDENTE"
    ).scalar()

    # Expenses made on this card not from installments, excluding already paid invoices
    direct_card_expenses = db.query(func.coalesce(func.sum(Transaction.amount), 0)).outerjoin(
        CardInvoice, Transaction.invoice_id == CardInvoice.id
    ).filter(
        Transaction.card_id == card.id,
        Transaction.type == "DESPESA",
        Transaction.status.in_(["PENDENTE", "REALIZADA", "VENCIDA"]),
        Transaction.installment_id.is_(None),
        Transaction.is_invoice_payment == False,
        Transaction.is_deleted == False,
        (Transaction.invoice_id.is_(None) | (CardInvoice.status != "PAGA"))
    ).scalar()

    partial_paid = db.query(func.coalesce(func.sum(CardInvoice.paid_amount), 0)).filter(
        CardInvoice.card_id == card.id, CardInvoice.status != "PAGA"
    ).scalar()
    used = max(Decimal("0"), Decimal(str(pending_installments)) + Decimal(str(direct_card_expenses)) - Decimal(str(partial_paid))).quantize(Decimal("0.01"))
    credit_limit = Decimal(str(card.credit_limit or "0.00")).quantize(Decimal("0.01"))
    avail = max(Decimal("0.00"), credit_limit - used).quantize(Decimal("0.01"))
    
    today = date.today()
    cur_year, cur_month = get_current_invoice_period(card, today)
    start_date, closing_date, due_date = get_invoice_cycle_dates(card, cur_year, cur_month)
    cur_txs = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.card_id == card.id,
        Transaction.date >= start_date,
        Transaction.date <= closing_date,
        Transaction.type == "DESPESA",
        Transaction.is_deleted == False,
        Transaction.is_invoice_payment == False,
        Transaction.installment_id.is_(None)
    ).scalar()
    cur_insts = db.query(func.coalesce(func.sum(Installment.amount), 0)).join(InstallmentPlan).filter(
        InstallmentPlan.card_id == card.id,
        Installment.due_date >= date(cur_year, cur_month, 1),
        Installment.due_date <= date(cur_year, cur_month, calendar.monthrange(cur_year, cur_month)[1]),
        Installment.status != "CANCELADA"
    ).scalar()
    current_invoice = (Decimal(str(cur_txs)) + Decimal(str(cur_insts))).quantize(Decimal("0.01"))

    return used, avail, current_invoice


def build_invoice_response(db: Session, card: CreditCard, year: int, month: int) -> CardInvoiceResponse:
    start_date, closing_date, due_date = get_invoice_cycle_dates(card, year, month)
    period_label = f"{MONTH_NAMES[month - 1]} / {year}"

    # Query saved invoice if exists
    saved_invoice = db.query(CardInvoice).filter(
        CardInvoice.card_id == card.id,
        CardInvoice.year == year,
        CardInvoice.month == month
    ).first()

    # Transactions in this invoice cycle
    txs = db.query(Transaction).filter(
        Transaction.card_id == card.id,
        Transaction.date >= start_date,
        Transaction.date <= closing_date,
        Transaction.type == "DESPESA",
        Transaction.is_deleted == False,
        Transaction.is_invoice_payment == False,
        Transaction.installment_id.is_(None)
    ).order_by(Transaction.date.asc()).all()

    # Installment parcels falling into this invoice
    insts = db.query(Installment).join(InstallmentPlan).filter(
        InstallmentPlan.card_id == card.id,
        Installment.due_date >= date(year, month, 1),
        Installment.due_date <= date(year, month, calendar.monthrange(year, month)[1]),
        Installment.status != "CANCELADA"
    ).order_by(Installment.due_date.asc()).all()

    items: List[CardInvoiceItem] = []
    for t in txs:
        items.append(CardInvoiceItem(
            id=t.id,
            date=t.date,
            description=t.description,
            category_name=t.category.name if t.category else None,
            category_color=t.category.color if t.category else None,
            responsible_name=t.responsible_name,
            amount=Decimal(str(t.amount)).quantize(Decimal("0.01")),
            is_installment=False,
            installment_text=None,
            status=t.status
        ))

    for i in insts:
        items.append(CardInvoiceItem(
            id=i.id,
            date=i.due_date,
            description=i.plan.description,
            category_name=i.plan.category.name if i.plan.category else None,
            category_color=i.plan.category.color if i.plan.category else None,
            responsible_name=i.plan.responsible_name,
            amount=Decimal(str(i.amount)).quantize(Decimal("0.01")),
            is_installment=True,
            installment_text=f"Parcela {i.installment_number}/{i.plan.installments_count}",
            status=i.status
        ))

    total_amount = sum((it.amount for it in items), Decimal("0.00")).quantize(Decimal("0.01"))
    today = date.today()
    cur_year, cur_month = get_current_invoice_period(card, today)
    is_current = (year == cur_year and month == cur_month)

    if saved_invoice:
        paid_amount = Decimal(str(saved_invoice.paid_amount)).quantize(Decimal("0.01"))
        remaining_amount = max(Decimal("0.00"), total_amount - paid_amount).quantize(Decimal("0.01"))
        inv_status = saved_invoice.status
        if inv_status != "PAGA":
            if today > due_date:
                inv_status = "VENCIDA"
            elif today > closing_date:
                inv_status = "FECHADA"
            else:
                inv_status = "ABERTA"

        payment_account_name = saved_invoice.payment_account.name if saved_invoice.payment_account else None
        return CardInvoiceResponse(
            id=saved_invoice.id,
            card_id=card.id,
            year=year,
            month=month,
            period_label=period_label,
            closing_date=closing_date,
            due_date=due_date,
            total_amount=total_amount,
            paid_amount=paid_amount,
            remaining_amount=remaining_amount,
            status=inv_status,
            items_count=len(items),
            is_current=is_current,
            payment_date=saved_invoice.payment_date,
            payment_account_id=saved_invoice.payment_account_id,
            payment_account_name=payment_account_name,
            items=items,
            created_at=saved_invoice.created_at
        )

    # Dynamic invoice calculation when not yet persisted
    paid_amount = Decimal("0.00")
    remaining_amount = total_amount
    if today > due_date:
        inv_status = "VENCIDA" if total_amount > 0 else "ABERTA"
    elif today > closing_date:
        inv_status = "FECHADA"
    else:
        inv_status = "ABERTA"

    return CardInvoiceResponse(
        id=None,
        card_id=card.id,
        year=year,
        month=month,
        period_label=period_label,
        closing_date=closing_date,
        due_date=due_date,
        total_amount=total_amount,
        paid_amount=paid_amount,
        remaining_amount=remaining_amount,
        status=inv_status,
        items_count=len(items),
        is_current=is_current,
        items=items
    )


# --- CARD CRUD ---

@router.get("", response_model=List[CreditCardResponse])
def get_cards(
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    cards = db.query(CreditCard).filter(
        CreditCard.family_id == current_family.id,
        CreditCard.is_active == True
    ).order_by(CreditCard.name.asc()).all()

    result = []
    for c in cards:
        used, avail, cur_inv = compute_card_limits(db, c)
        resp = CreditCardResponse(
            id=c.id,
            family_id=c.family_id,
            name=c.name,
            card_type=c.card_type,
            brand=c.brand,
            bank_name=c.bank_name,
            last_digits=c.last_digits,
            credit_limit=c.credit_limit,
            closing_day=c.closing_day,
            due_day=c.due_day,
            color=c.color,
            responsible_name=c.responsible_name,
            responsible_id=c.responsible_id,
            account_id=c.account_id,
            is_active=c.is_active,
            used_limit=used,
            available_limit=avail,
            current_invoice_total=cur_inv,
            created_at=c.created_at,
            updated_at=c.updated_at
        )
        result.append(resp)
    return result


@router.post("", response_model=CreditCardResponse, status_code=status.HTTP_201_CREATED)
def create_card(
    data: CreditCardCreate,
    current_family: FamilySpace = Depends(get_admin_family),
    db: Session = Depends(get_db)
) -> Any:
    validate_relations(db, current_family.id, data.model_dump())
    card = CreditCard(
        family_id=current_family.id,
        name=data.name,
        card_type=data.card_type,
        brand=data.brand,
        bank_name=data.bank_name,
        last_digits=data.last_digits,
        credit_limit=data.credit_limit,
        closing_day=data.closing_day,
        due_day=data.due_day,
        color=data.color,
        responsible_name=data.responsible_name,
        responsible_id=data.responsible_id,
        account_id=data.account_id,
        is_active=True
    )
    db.add(card)
    db.commit()
    db.refresh(card)

    return CreditCardResponse(
        id=card.id,
        family_id=card.family_id,
        name=card.name,
        card_type=card.card_type,
        brand=card.brand,
        bank_name=card.bank_name,
        last_digits=card.last_digits,
        credit_limit=card.credit_limit,
        closing_day=card.closing_day,
        due_day=card.due_day,
        color=card.color,
        responsible_name=card.responsible_name,
        responsible_id=card.responsible_id,
        account_id=card.account_id,
        is_active=card.is_active,
        used_limit=Decimal("0.00"),
        available_limit=card.credit_limit,
        current_invoice_total=Decimal("0.00"),
        created_at=card.created_at,
        updated_at=card.updated_at
    )


@router.get("/{card_id}", response_model=CreditCardResponse)
def get_card_by_id(
    card_id: UUID,
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    card = db.query(CreditCard).filter(
        CreditCard.id == card_id,
        CreditCard.family_id == current_family.id,
        CreditCard.is_active == True
    ).first()
    if not card:
        raise HTTPException(status_code=404, detail="Cartão não encontrado")

    used, avail, cur_inv = compute_card_limits(db, card)
    return CreditCardResponse(
        id=card.id,
        family_id=card.family_id,
        name=card.name,
        card_type=card.card_type,
        brand=card.brand,
        bank_name=card.bank_name,
        last_digits=card.last_digits,
        credit_limit=card.credit_limit,
        closing_day=card.closing_day,
        due_day=card.due_day,
        color=card.color,
        responsible_name=card.responsible_name,
        responsible_id=card.responsible_id,
        account_id=card.account_id,
        is_active=card.is_active,
        used_limit=used,
        available_limit=avail,
        current_invoice_total=cur_inv,
        created_at=card.created_at,
        updated_at=card.updated_at
    )


@router.put("/{card_id}", response_model=CreditCardResponse)
def update_card(
    card_id: UUID,
    data: CreditCardUpdate,
    current_family: FamilySpace = Depends(get_admin_family),
    db: Session = Depends(get_db)
) -> Any:
    card = db.query(CreditCard).filter(
        CreditCard.id == card_id,
        CreditCard.family_id == current_family.id
    ).first()
    if not card:
        raise HTTPException(status_code=404, detail="Cartão não encontrado")

    validate_relations(db, current_family.id, data.model_dump(exclude_unset=True))
    if ({"closing_day", "due_day"} & data.model_fields_set) and (
        db.query(Transaction.id).filter(Transaction.card_id == card.id, Transaction.is_deleted == False).first()
        or db.query(InstallmentPlan.id).filter(InstallmentPlan.card_id == card.id).first()
    ):
        raise HTTPException(409, detail="Não é possível alterar o ciclo de cartão com movimentações")
    update_data = data.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(card, field, val)

    db.commit()
    db.refresh(card)

    used, avail, cur_inv = compute_card_limits(db, card)
    return CreditCardResponse(
        id=card.id,
        family_id=card.family_id,
        name=card.name,
        card_type=card.card_type,
        brand=card.brand,
        bank_name=card.bank_name,
        last_digits=card.last_digits,
        credit_limit=card.credit_limit,
        closing_day=card.closing_day,
        due_day=card.due_day,
        color=card.color,
        responsible_name=card.responsible_name,
        responsible_id=card.responsible_id,
        account_id=card.account_id,
        is_active=card.is_active,
        used_limit=used,
        available_limit=avail,
        current_invoice_total=cur_inv,
        created_at=card.created_at,
        updated_at=card.updated_at
    )


@router.delete("/{card_id}", status_code=status.HTTP_200_OK)
def delete_card(
    card_id: UUID,
    current_family: FamilySpace = Depends(get_admin_family),
    db: Session = Depends(get_db)
) -> Any:
    card = db.query(CreditCard).filter(
        CreditCard.id == card_id,
        CreditCard.family_id == current_family.id
    ).first()
    if not card:
        raise HTTPException(status_code=404, detail="Cartão não encontrado")

    card.is_active = False
    db.commit()
    return {"message": "Cartão desativado com sucesso"}


# --- INVOICE ENDPOINTS ---

@router.get("/{card_id}/invoices", response_model=List[CardInvoiceResponse])
def get_card_invoices(
    card_id: UUID,
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    card = db.query(CreditCard).filter(
        CreditCard.id == card_id,
        CreditCard.family_id == current_family.id,
        CreditCard.is_active == True
    ).first()
    if not card:
        raise HTTPException(status_code=404, detail="Cartão não encontrado")

    today = date.today()
    # Generate range: 3 previous months, current month, next 4 months
    invoices = []
    for offset in range(-3, 5):
        target_month = today.month + offset
        target_year = today.year
        while target_month < 1:
            target_month += 12
            target_year -= 1
        while target_month > 12:
            target_month -= 12
            target_year += 1

        inv = build_invoice_response(db, card, target_year, target_month)
        invoices.append(inv)

    return invoices


@router.get("/{card_id}/invoices/{year}/{month}", response_model=CardInvoiceResponse)
def get_card_invoice_by_period(
    card_id: UUID,
    year: int,
    month: int,
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    if month < 1 or month > 12 or not 2000 <= year <= 2100:
        raise HTTPException(status_code=400, detail="Mês inválido (1-12)")

    card = db.query(CreditCard).filter(
        CreditCard.id == card_id,
        CreditCard.family_id == current_family.id,
        CreditCard.is_active == True
    ).first()
    if not card:
        raise HTTPException(status_code=404, detail="Cartão não encontrado")

    return build_invoice_response(db, card, year, month)


@router.post("/{card_id}/invoices/{year}/{month}/pay", response_model=CardInvoiceResponse)
def pay_card_invoice(
    card_id: UUID,
    year: int,
    month: int,
    data: InvoicePayRequest,
    idempotency_key: Optional[UUID] = Header(None),
    current_user: User = Depends(get_current_user),
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    if not 1 <= month <= 12 or not 2000 <= year <= 2100:
        raise HTTPException(400, detail="Competência inválida")
    card = db.query(CreditCard).filter(
        CreditCard.id == card_id,
        CreditCard.family_id == current_family.id,
        CreditCard.is_active == True
    ).with_for_update().first()
    if not card:
        raise HTTPException(status_code=404, detail="Cartão não encontrado")

    fingerprint = hashlib.sha256(json.dumps({"card": str(card_id), "year": year, "month": month,
        "data": data.model_dump(mode="json")}, sort_keys=True).encode()).hexdigest()
    request_key = hashlib.sha256(f"{current_family.id}:{idempotency_key}".encode()).hexdigest() if idempotency_key else None
    if request_key:
        previous = db.query(Transaction).filter_by(idempotency_key=request_key).first()
        if previous:
            if previous.is_deleted:
                raise HTTPException(409, detail="Pagamento estornado: utilize uma nova chave")
            if previous.request_fingerprint != fingerprint:
                raise HTTPException(409, detail="Chave de idempotência já utilizada para outra requisição")
            return build_invoice_response(db, card, year, month)

    # Validate payment account
    account = db.query(FinancialAccount).filter(
        FinancialAccount.id == data.account_id,
        FinancialAccount.family_id == current_family.id,
        FinancialAccount.is_active == True
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="Conta bancária de pagamento não encontrada")

    # Current invoice calculation
    inv_resp = build_invoice_response(db, card, year, month)
    if inv_resp.status == "PAGA":
        raise HTTPException(status_code=400, detail="Esta fatura já foi totalmente paga")

    pay_amount = data.amount if data.amount is not None else inv_resp.remaining_amount
    if pay_amount > inv_resp.remaining_amount:
        raise HTTPException(400, detail="Pagamento excede o saldo da fatura")
    if pay_amount <= 0:
        raise HTTPException(status_code=400, detail="Valor de pagamento deve ser positivo")

    start_date, closing_date, due_date = get_invoice_cycle_dates(card, year, month)
    period_label = f"{MONTH_NAMES[month - 1]} / {year}"

    # Get or create CardInvoice in DB
    invoice_record = db.query(CardInvoice).filter(
        CardInvoice.card_id == card.id,
        CardInvoice.year == year,
        CardInvoice.month == month
    ).first()

    if not invoice_record:
        invoice_record = CardInvoice(
            family_id=current_family.id,
            card_id=card.id,
            year=year,
            month=month,
            closing_date=closing_date,
            due_date=due_date,
            total_amount=inv_resp.total_amount,
            paid_amount=Decimal("0.00"),
            status="ABERTA"
        )
        db.add(invoice_record)
        db.flush()

    # 1. Create cash outflow Transaction from checking account
    pay_tx = Transaction(
        family_id=current_family.id,
        idempotency_key=request_key,
        request_fingerprint=fingerprint,
        created_by_id=current_user.id,
        date=data.payment_date,
        description=f"Pagamento Fatura {card.name} ({period_label})",
        type="DESPESA",
        amount=pay_amount,
        category_id=None,
        account_id=data.account_id,
        destination_account_id=None,
        card_id=card.id,
        responsible_name=card.responsible_name or "Família",
        is_shared=True,
        classification="NECESSIDADE",
        status="REALIZADA",
        is_invoice_payment=True,
        invoice_id=invoice_record.id,
        notes=data.notes or f"Quitação da fatura de {period_label} do cartão {card.name}"
    )
    db.add(pay_tx)
    db.flush()

    fully_paid = inv_resp.paid_amount + pay_amount >= inv_resp.total_amount

    # 2. Settle installments only when the invoice is fully paid
    insts = db.query(Installment).join(InstallmentPlan).filter(
        InstallmentPlan.card_id == card.id,
        Installment.due_date >= date(year, month, 1),
        Installment.due_date <= date(year, month, calendar.monthrange(year, month)[1]),
        Installment.status == "PENDENTE"
    ).all()

    for inst in insts if fully_paid else []:
        inst.status = "PAGA"
        inst.payment_date = data.payment_date
        # Recognize the installment expense without a second cash outflow.
        tx = Transaction(family_id=current_family.id, created_by_id=current_user.id,
            date=inst.due_date, description=f"{inst.plan.description} ({inst.installment_number}/{inst.plan.installments_count})",
            type="DESPESA", amount=inst.amount, category_id=inst.plan.category_id,
            account_id=data.account_id, card_id=card.id, responsible_name=inst.plan.responsible_name,
            is_shared=inst.plan.is_shared, classification="NECESSIDADE", status="REALIZADA",
            installment_id=inst.id, invoice_id=invoice_record.id)
        db.add(tx)
        db.flush()
        inst.transaction_id = tx.id
        if all(i.status in ("PAGA", "CANCELADA") for i in inst.plan.installments):
            inst.plan.status = "COMPLETED"

    # 3. Link card expenses in this cycle to this invoice
    cycle_txs = db.query(Transaction).filter(
        Transaction.card_id == card.id,
        Transaction.date >= start_date,
        Transaction.date <= closing_date,
        Transaction.type == "DESPESA",
        Transaction.is_deleted == False,
        Transaction.is_invoice_payment == False,
        Transaction.installment_id.is_(None)
    ).all()
    for t in cycle_txs:
        t.invoice_id = invoice_record.id

    invoice_record.total_amount = inv_resp.total_amount
    # 4. Update Invoice Record
    new_paid = (Decimal(str(invoice_record.paid_amount)) + pay_amount).quantize(Decimal("0.01"))
    invoice_record.paid_amount = new_paid
    invoice_record.payment_date = data.payment_date
    invoice_record.payment_account_id = data.account_id
    invoice_record.payment_transaction_id = pay_tx.id
    if new_paid >= invoice_record.total_amount:
        invoice_record.status = "PAGA"
    else:
        invoice_record.status = "FECHADA"

    AuditService.log(db, current_family.id, current_user.id, "PAY_INVOICE", "INVOICE", str(invoice_record.id),
                     new_values={"amount": str(pay_amount), "payment_transaction_id": str(pay_tx.id)})
    db.commit()
    db.refresh(invoice_record)

    return build_invoice_response(db, card, year, month)


@router.post('/{card_id}/invoices/{year}/{month}/payments/{payment_id}/reverse', response_model=CardInvoiceResponse)
def reverse_invoice_payment(card_id: UUID, year: int, month: int, payment_id: UUID,
                            current_family: FamilySpace = Depends(get_admin_family),
                            current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    card = db.query(CreditCard).filter_by(id=card_id, family_id=current_family.id).with_for_update().first()
    if not card:
        raise HTTPException(404, detail='Cartão não encontrado')
    invoice = db.query(CardInvoice).filter_by(card_id=card.id, year=year, month=month).first()
    payment = db.query(Transaction).filter_by(id=payment_id, family_id=current_family.id,
        invoice_id=invoice.id if invoice else None, is_invoice_payment=True, is_deleted=False).first() if invoice else None
    if not payment:
        raise HTTPException(404, detail='Pagamento não encontrado ou já estornado')
    if invoice.status == 'PAGA':
        recognized = db.query(Transaction).filter(Transaction.invoice_id == invoice.id,
            Transaction.installment_id.is_not(None), Transaction.is_deleted == False).all()
        for tx in recognized:
            parcel = db.query(Installment).filter_by(id=tx.installment_id).one()
            parcel.status = 'PENDENTE'
            parcel.payment_date = None
            parcel.transaction_id = None
            parcel.plan.status = 'ACTIVE'
            tx.is_deleted = True
    payment.is_deleted = True
    invoice.paid_amount = (Decimal(str(invoice.paid_amount)) - Decimal(str(payment.amount))).quantize(Decimal('.01'))
    invoice.status = 'FECHADA' if invoice.paid_amount else 'ABERTA'
    latest = db.query(Transaction).filter(Transaction.invoice_id == invoice.id,
        Transaction.is_invoice_payment == True, Transaction.is_deleted == False,
        Transaction.id != payment.id).order_by(Transaction.created_at.desc()).first()
    invoice.payment_transaction_id = latest.id if latest else None
    invoice.payment_account_id = latest.account_id if latest else None
    invoice.payment_date = latest.date if latest else None
    AuditService.log(db, current_family.id, current_user.id, 'REVERSE_PAYMENT', 'INVOICE', str(invoice.id),
                     new_values={'payment_id': str(payment.id), 'amount': str(payment.amount)})
    db.commit()
    return build_invoice_response(db, card, year, month)
