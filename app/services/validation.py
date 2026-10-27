"""Authorization and invariants shared by financial write operations."""
from fastapi import HTTPException
from app.models.account import FinancialAccount
from app.models.category import Category
from app.models.card import CreditCard
from app.models.payment_method import PaymentMethod
from app.models.responsible import ResponsiblePerson

RELATIONS = {
    'account_id': FinancialAccount, 'destination_account_id': FinancialAccount,
    'category_id': Category, 'card_id': CreditCard,
    'payment_method_id': PaymentMethod, 'responsible_id': ResponsiblePerson,
}


def validate_relations(db, family_id, values):
    for field, model in RELATIONS.items():
        identifier = values.get(field)
        if identifier is None:
            continue
        obj = db.query(model).filter(model.id == identifier, model.family_id == family_id).first()
        if obj is None or not obj.is_active:
            raise HTTPException(400, detail=f'Referência inválida ou inativa: {field}')


def validate_transaction(values):
    if values.get('type') == 'TRANSFERENCIA':
        if not values.get('destination_account_id') or values['destination_account_id'] == values.get('account_id'):
            raise HTTPException(400, detail='Transferência exige contas de origem e destino diferentes')
        if values.get('card_id'):
            raise HTTPException(400, detail='Transferência não pode usar cartão')
    elif values.get('destination_account_id'):
        raise HTTPException(400, detail='Conta de destino é exclusiva de transferências')
    if values.get('card_id') and values.get('type') != 'DESPESA':
        raise HTTPException(400, detail='Cartão só pode ser vinculado a despesas')


def protect_linked_transaction(db, transaction):
    from app.models.goal import GoalContribution
    linked_goal = db.query(GoalContribution.id).filter(GoalContribution.transaction_id == transaction.id).first()
    from app.models.invoice import CardInvoice
    invoice = db.get(CardInvoice, transaction.invoice_id) if transaction.invoice_id else None
    if transaction.is_invoice_payment or transaction.installment_id or (invoice and invoice.paid_amount > 0) or linked_goal:
        raise HTTPException(409, detail='Movimentação vinculada: utilize o fluxo de pagamento ou estorno correspondente')


def validate_card_periods(db, family_id, values):
    """Freeze invoice composition after the first payment; serialize with payment."""
    card_id = values.get('card_id')
    from app.models.invoice import CardInvoice
    assigned = db.query(CardInvoice).filter_by(id=values['invoice_id'], family_id=family_id).first() if values.get('invoice_id') else None
    if values.get('invoice_id') and not assigned:
        raise HTTPException(400, detail='Fatura inválida para este espaço')
    if assigned and assigned.card_id != card_id:
        raise HTTPException(409, detail='Compra vinculada a uma fatura não permite trocar o cartão')
    if not card_id:
        return
    from app.api.v1.cards import get_current_invoice_period
    from app.domain.recurrence_engine import RecurrenceEngine
    card = db.query(CreditCard).filter_by(id=card_id, family_id=family_id).with_for_update().first()
    if not card:
        raise HTTPException(400, detail='Cartão inválido')
    if assigned:
        db.refresh(assigned)  # Re-read after the card lock; a concurrent payment may have completed.
        periods = {(assigned.year, assigned.month)}
    elif values.get('first_due_date'):
        dates = RecurrenceEngine.generate_due_dates(values['first_due_date'], 'MONTHLY', values['installments_count'], values['first_due_date'].day)
        periods = {(d.year, d.month) for d in dates}
    else:
        periods = {get_current_invoice_period(card, values['date'])}
    for year, month in periods:
        invoice = db.query(CardInvoice).filter_by(card_id=card.id, year=year, month=month).first()
        if invoice and invoice.paid_amount > 0:
            raise HTTPException(409, detail='Fatura com pagamento não permite alterar sua composição')


def lock_transaction_context(db, transaction, new_card_id=None):
    """Same lock order as settlement: cards first, transaction second."""
    card_ids = sorted({identifier for identifier in (transaction.card_id, new_card_id) if identifier}, key=str)
    for identifier in card_ids:
        db.query(CreditCard).filter_by(id=identifier, family_id=transaction.family_id).with_for_update().first()
    db.refresh(transaction, with_for_update=True)
    if transaction.card_id and transaction.card_id not in card_ids:
        raise HTTPException(409, detail='Movimentação alterada simultaneamente. Atualize e tente novamente.')
