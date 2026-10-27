from fastapi import HTTPException
from app.models.card import CreditCard
from app.models.account import FinancialAccount
from app.models.invoice import CardInvoice


def resolve_card_flow(db, family_id, values):
    card_id = values.get('card_id')
    if not card_id:
        if values.get('payment_mode', 'ACCOUNT') != 'ACCOUNT' or values.get('invoice_id'):
            raise HTTPException(400, detail='Selecione um cartão para usar crédito ou débito')
        values['payment_mode'] = 'ACCOUNT'
        return None
    card = db.query(CreditCard).filter_by(id=card_id, family_id=family_id, is_active=True).with_for_update().first()
    if not card:
        raise HTTPException(400, detail='Cartão inválido para este espaço')
    mode = values.get('payment_mode') or 'ACCOUNT'
    if mode == 'ACCOUNT':
        mode = 'DEBIT' if card.card_type in ('DEBIT', 'BENEFIT') else 'CREDIT'
    if mode == 'CREDIT' and card.card_type not in ('CREDIT', 'MULTIPLE'):
        raise HTTPException(400, detail='Este cartão não oferece crédito')
    if mode == 'DEBIT' and card.card_type not in ('DEBIT', 'MULTIPLE', 'BENEFIT'):
        raise HTTPException(400, detail='Este cartão não oferece débito')
    if mode == 'DEBIT' and values.get('invoice_id'):
        raise HTTPException(400, detail='Débito sai da conta e não pode entrar em uma fatura')
    account_id = values.get('account_id')
    if card.account_id:
        if account_id and account_id != card.account_id:
            raise HTTPException(400, detail='A conta do lançamento deve ser a conta vinculada ao cartão')
        values['account_id'] = card.account_id
    else:
        if not account_id:
            accounts = db.query(FinancialAccount).filter_by(family_id=family_id, is_active=True).all()
            if len(accounts) == 1:
                account_id = accounts[0].id
        if not account_id:
            raise HTTPException(400, detail='Vincule uma conta ao cartão antes de registrar a compra')
        account = db.query(FinancialAccount).filter_by(id=account_id, family_id=family_id, is_active=True).first()
        if not account or account.account_type == 'CREDIT_CARD':
            raise HTTPException(400, detail='Conta vinculada ao cartão inválida')
        card.account_id = account_id
        values['account_id'] = account_id
    values['payment_mode'] = mode
    return card


def ensure_invoice(db, family_id, card, purchase_date):
    from app.api.v1.cards import get_current_invoice_period, get_invoice_cycle_dates
    year, month = get_current_invoice_period(card, purchase_date)
    if not 2000 <= year <= 2100:
        raise HTTPException(400, detail='O vencimento deve estar entre 2000 e 2100')
    invoice = db.query(CardInvoice).filter_by(card_id=card.id, year=year, month=month).first()
    if not invoice:
        _, closing, due = get_invoice_cycle_dates(card, year, month)
        invoice = CardInvoice(family_id=family_id, card_id=card.id, year=year, month=month,
                              closing_date=closing, due_date=due, total_amount=0, paid_amount=0, status='ABERTA')
        db.add(invoice); db.flush()
    return invoice
