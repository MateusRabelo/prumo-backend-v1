"""Synthetic fixtures preserve layout, never the customer's private statements."""
import os
from pathlib import Path
from datetime import date
from decimal import Decimal
import pytest
from app.services.statement_parser import parse_statement
from app.services.pdf_statement import statement_summary

SYNTHETIC = '''Nubank
FATURA 14 SET 2026 EMISSÃO E ENVIO 06 SET 2026
Simulação de parcelamento: Total a pagar R$ 999,99
RESUMO DA FATURA ATUAL
Fatura anterior R$ 10,00
Pagamento recebido −R$ 15,00
Total de compras de todos os cartões, 06 AGO a 06 SET R$ 25,00
Total a pagar R$ 20,00
PRÓXIMAS FATURAS
Saldo em aberto da próxima fatura R$ 300,00
TRANSAÇÕES DE 06 AGO A 06 SET
Pessoa de exemplo R$ 25,00
06 AGO •••• 0000 R N Doces
R$ 12,50
01 SET •••• 0000 Loja Exemplo - Parcela 1/3 R$ 12,50
Pagamentos -R$ 15,00
06 AGO Pagamento em 06 AGO −R$ 15,00
'''


def test_nubank_named_month_wrapping_signs_summary_and_sanitization():
    rows, warnings = parse_statement(SYNTHETIC, 'pdf', date(2030, 1, 1), card=True)
    assert len(rows) == 3 and warnings == []
    assert rows[0]['date'] == '2026-08-06', 'Explicit document year overrides the UI month'
    assert rows[0]['original_description'] == 'R N Doces'
    assert rows[0]['amount'] == '12.50'
    assert rows[1]['possible_installment'] is True
    assert rows[2]['entry_kind'] == 'payment' and rows[2]['blocked'] is True
    summary = statement_summary(SYNTHETIC, rows)
    assert summary['amount_due'] == '20.00', 'Must ignore financing simulations and next-invoice balances'
    assert summary['totals_match'] is True
    assert summary['requires_reconciliation'] is True
    incomplete = statement_summary(SYNTHETIC, rows[1:])
    assert incomplete['totals_match'] is False


def test_nubank_refunds_and_year_boundary():
    sample = '''FATURA 10 JAN 2027
TRANSAÇÕES DE 01 DEZ A 01 JAN
31 DEZ •••• 0000 Loja R$ 12,50
31 DEZ Estorno de "Loja" −R$ 12,50
Estorno referente a compra de valor R$ 12,50, realizada em
30 de Dezembro de 2026
'''
    rows, _ = parse_statement(sample, 'pdf', date(2028, 7, 1), card=True)
    assert len(rows) == 2
    assert all(r['date'] == '2026-12-31' for r in rows)
    assert rows[1]['entry_kind'] == 'refund' and rows[1]['blocked'] is True
    assert rows[0]['refunded_in_statement'] is True


@pytest.mark.skipif(not os.environ.get('NUBANK_SAMPLE_DIR'), reason='Private PDFs are never committed')
def test_actual_customer_pdfs_reconcile_without_saving_records():
    from app.api.v1.imports import pdf_text
    files = [Path(os.environ['NUBANK_SAMPLE_DIR']) / name for name in ('Setembro 2026.pdf', 'Outubro 2026.pdf')]
    assert len(files) >= 2
    for path in files:
        text = pdf_text(path.read_bytes())
        rows, warnings = parse_statement(text, 'pdf', date(2030, 1, 1), card=True)
        summary = statement_summary(text, rows)
        assert summary and summary['totals_match'] is True, 'Extracted rows must close with all stated totals'
        assert all('••••' not in row['original_description'] for row in rows)
        assert warnings == []
        assert sum(Decimal(row['amount']) for row in rows if row['entry_kind'] == 'purchase') == Decimal(summary['purchases'])


@pytest.mark.parametrize('pre_registered', [False, True])
def test_nubank_http_preview_binds_statement_month_and_requires_reconciliation(client, auth_headers, db, monkeypatch, pre_registered):
    from app.models.transaction import Transaction
    from app.models.invoice import CardInvoice
    import app.api.v1.imports as api
    monkeypatch.setattr(api, 'pdf_text', lambda content: SYNTHETIC)
    account = client.post('/api/v1/settings/accounts', headers=auth_headers, json={'name': 'Banco sintético', 'account_type': 'CHECKING', 'initial_balance': '1000'}).json()
    card = client.post('/api/v1/cards', headers=auth_headers, json={'name': 'Cartão sintético', 'card_type': 'CREDIT', 'closing_day': 25, 'due_day': 5, 'credit_limit': '5000'}).json()
    if pre_registered:
        registered = client.post(f"/api/v1/cards/{card['id']}/invoices/2026/9", headers=auth_headers, json={})
        assert registered.status_code == 200
    initial = db.query(Transaction).count()
    res = client.post('/api/v1/imports/preview', headers=auth_headers,
        data={'account_id': account['id'], 'card_id': card['id'], 'reference_month': '2030-01'},
        files={'file': ('example.pdf', b'%PDF-example', 'application/pdf')})
    assert res.status_code == 200, res.text
    preview = res.json()
    assert preview['statement']['totals_match'] is True
    assert db.query(Transaction).count() == initial
    payload = {'preview_token': preview['preview_token'], 'reviewed': True, 'entries': [
        {'index': 0, 'description': 'Cantina faculdade', 'type': 'DESPESA'},
        {'index': 1, 'description': 'Loja exemplo', 'type': 'DESPESA'},
    ]}
    assert client.post('/api/v1/imports/confirm', headers=auth_headers, json=payload).status_code == 400
    # An incomplete extraction remains visible but can never be confirmed.
    monkeypatch.setattr(api, 'pdf_text', lambda content: SYNTHETIC.replace('01 SET •••• 0000 Loja Exemplo - Parcela 1/3 R$ 12,50', ''))
    incomplete = client.post('/api/v1/imports/preview', headers=auth_headers,
        data={'account_id': account['id'], 'card_id': card['id'], 'reference_month': '2030-01'},
        files={'file': ('example.pdf', b'%PDF-example', 'application/pdf')}).json()
    assert incomplete['statement']['totals_match'] is False
    denied = client.post('/api/v1/imports/confirm', headers=auth_headers, json={
        'preview_token': incomplete['preview_token'], 'reviewed': True, 'reconciliation_reviewed': True,
        'entries': [{'index': 0, 'description': 'Cantina', 'type': 'DESPESA'}]})
    assert denied.status_code == 409 and db.query(Transaction).count() == initial
    payload['reconciliation_reviewed'] = True
    res = client.post('/api/v1/imports/confirm', headers=auth_headers, json=payload)
    assert res.status_code == 200, res.text
    assert res.json()['imported'] == 2
    path = f"/api/v1/cards/{card['id']}/invoices/2026/9"
    september = client.get(path, headers=auth_headers).json()
    august = client.get(f"/api/v1/cards/{card['id']}/invoices/2026/8", headers=auth_headers).json()
    assert Decimal(str(september['total_amount'])) == 25
    assert Decimal(str(august['total_amount'])) == 0, 'Boundary-date purchases belong to the PDF statement, not a guessed cycle'
    assert september['due_date'] == '2026-09-14'
    assert september['closing_date'] == '2026-09-06'
    assert september['cycle_start_date'] == '2026-08-06'
    # New purchases from the invoice editor also keep the explicit period.
    addition = client.post('/api/v1/transactions', headers=auth_headers, json={
        'description': 'Compra adicionada à fatura', 'date': '2026-09-02', 'type': 'DESPESA', 'amount': '2.00',
        'account_id': account['id'], 'card_id': card['id'], 'invoice_id': september['id'], 'responsible_name': 'Exemplo'})
    assert addition.status_code == 201, addition.text
    assert Decimal(str(client.get(f"/api/v1/cards/{card['id']}/invoices/2026/10", headers=auth_headers).json()['total_amount'])) == 0
    purchase = db.query(Transaction).filter_by(description='Cantina faculdade').one()
    result = client.put('/api/v1/transactions/'+str(purchase.id), headers=auth_headers, json={'amount': '13.50'})
    assert result.status_code == 200, result.text
    assert Decimal(str(client.get(path, headers=auth_headers).json()['total_amount'])) == 28
    result = client.post(path+'/pay', headers=auth_headers, json={'account_id': account['id'], 'amount': '28'})
    assert result.status_code == 200, result.text
    assert client.delete('/api/v1/transactions/'+str(purchase.id), headers=auth_headers).status_code == 409
    assert client.post('/api/v1/imports/confirm', headers=auth_headers, json=payload).status_code == 409
