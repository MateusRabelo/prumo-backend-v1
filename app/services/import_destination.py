"""Resolve the final, explicitly reviewed destination from trusted preview facts."""
from datetime import date
from fastapi import HTTPException
from app.api.v1.cards import get_invoice_cycle_dates


def resolve_destination(db, family_id, payload, destination):
    from app.api.v1.imports import target
    account_id = destination.account_id
    card_id = destination.card_id
    account, card = target(db, family_id, account_id, card_id, lock=True)
    if card and card.account_id and card.account_id != account_id:
        raise HTTPException(400, detail='Escolha a conta vinculada ao cartão selecionado.')
    statement = dict(payload['statement']) if payload.get('statement') else None
    digits = statement.get('card_last_digits', []) if statement else []
    if card and digits and card.last_digits and card.last_digits not in digits:
        raise HTTPException(400, detail='O final do cartão escolhido difere do arquivo. Revise o cartão de destino.')
    if not card:
        if statement or payload.get('credit_statement'):
            raise HTTPException(400, detail='O arquivo é uma fatura. Escolha um cartão de crédito na confirmação final.')
        return account_id, None, None
    if not destination.invoice_month:
        raise HTTPException(400, detail='Informe o mês de referência da fatura.')
    year, month = map(int, destination.invoice_month.split('-'))
    if statement:
        statement.update(year=year, month=month)
        if statement.get('format') == 'ofx' and statement.get('closing_date'):
            closing = date.fromisoformat(statement['closing_date'])
            due_year, due_month = closing.year, closing.month
            if card.due_day <= closing.day:
                due_year, due_month = due_year + (due_month == 12), due_month % 12 + 1
            _, _, due = get_invoice_cycle_dates(card, *divmod_reference(due_year, due_month, getattr(card, 'billing_month_offset', 0) or 0))
            statement['due_date'] = str(due)
    else:
        closing_raw = payload.get('source_closing_date')
        if closing_raw:
            closing = date.fromisoformat(closing_raw)
            due_year, due_month = closing.year, closing.month
            if card.due_day <= closing.day:
                due_year, due_month = due_year + (due_month == 12), due_month % 12 + 1
            _, _, due = get_invoice_cycle_dates(card, *divmod_reference(due_year, due_month, getattr(card, 'billing_month_offset', 0) or 0))
        else:
            _, closing, due = get_invoice_cycle_dates(card, year, month)
        statement = {'year': year, 'month': month, 'closing_date': str(closing), 'due_date': str(due),
                     'totals_match': None, 'requires_reconciliation': False}
    return account_id, card, statement


def divmod_reference(year, month, offset):
    year, month0 = divmod(year * 12 + month - 1 + offset, 12)
    return year, month0 + 1
