import io
from datetime import date
from decimal import Decimal
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from app.models.transaction import Transaction
from app.services.statement_parser import parse_statement

P = '/api/v1'


def sample_pdf(text):
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(('BT /F1 12 Tf 40 750 Td (' + text + ') Tj ET').encode())
    page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO(); writer.write(output)
    return output.getvalue()


def test_pdf_preview_learning_deduplication_and_token_isolation(client, auth_headers, db):
    account = client.post(P+'/settings/accounts', headers=auth_headers, json={'name': 'Banco Import', 'account_type': 'CHECKING', 'initial_balance': '100'}).json()
    def preview(day='26/10/2026'):
        res = client.post(P+'/imports/preview', headers=auth_headers,
                          data={'account_id': account['id'], 'reference_month': '2026-10'},
                          files={'file': ('extrato.pdf', sample_pdf(day+' R N Doces 12,50'), 'application/pdf')})
        assert res.status_code == 200, res.text
        return res.json()
    initial_count = db.query(Transaction).count()
    draft = preview()
    assert db.query(Transaction).count() == initial_count
    assert len(draft['rows']) == 1
    assert draft['rows'][0]['type'] is None, 'Unsigned bank value must be classified by the user'
    assert draft['rows'][0]['amount'] == '12.50'
    body = {'preview_token': draft['preview_token'], 'reviewed': True,
            'entries': [{'index': 0, 'description': 'Cantina faculdade', 'type': 'DESPESA', 'remember': True}]}
    result = client.post(P+'/imports/confirm', headers=auth_headers, json=body)
    assert result.status_code == 200, result.text
    assert result.json() == {'imported': 1, 'skipped': 0}
    assert client.post(P+'/imports/confirm', headers=auth_headers, json=body).json()['skipped'] == 1
    assert db.query(Transaction).count() == initial_count + 1
    again = preview()
    assert again['rows'][0]['duplicate'] is True
    assert again['rows'][0]['description'] == 'Cantina faculdade'
    assert again['rows'][0]['learned'] is True
    next_time = preview('27/10/2026')
    assert next_time['rows'][0]['description'] == 'Cantina faculdade'
    assert next_time['rows'][0]['duplicate'] is False
    other = client.post(P+'/auth/register', json={'full_name': 'Other import', 'email': 'other-import@example.com', 'password': 'securepassword123'}).json()
    foreign = {'Authorization': 'Bearer '+other['access_token'], 'X-Family-Id': other['current_family_id']}
    assert client.post(P+'/imports/confirm', headers=foreign, json=body).status_code == 403
    assert client.get(P+'/imports/rules', headers=foreign).json() == []
    body['preview_token'] = 'tampered'
    assert client.post(P+'/imports/confirm', headers=auth_headers, json=body).status_code == 400
    rule = client.get(P+'/imports/rules', headers=auth_headers).json()[0]
    assert client.delete(P+'/imports/rules/'+rule['id'], headers=foreign).status_code == 404
    assert client.delete(P+'/imports/rules/'+rule['id'], headers=auth_headers).status_code == 200


def test_parsers_handle_signs_repeated_purchases_and_card_payments():
    from app.api.v1.imports import dedupe_key
    assert dedupe_key('family', 'account1', 'card', 'row') == dedupe_key('family', 'account2', 'card', 'row')
    rows, warnings = parse_statement('Data;Descrição;Valor\n26/10/2026;R N Doces;-12,50\n26/10/2026;R N Doces;-12,50', 'csv', date(2026,10,1))
    assert len(rows) == 2 and rows[0]['fingerprint'] != rows[1]['fingerprint']
    assert rows[0]['type'] == 'DESPESA'
    rows, _ = parse_statement('26/10/2026 PAGAMENTO FATURA -100,00\n26/10/2026 Mercado 100,00', 'pdf', date(2026,10,1), card=True)
    assert rows[0]['blocked'] is True and rows[1]['blocked'] is False
    rows, _ = parse_statement('26/10/2026 PIX 12,50 D 820,00\n27/10/2026 Salário 3.000,00 C 3.820,00', 'pdf', date(2026,10,1))
    assert rows[0]['type'] == 'DESPESA' and rows[0]['amount'] == '12.50'
    assert rows[1]['type'] == 'RECEITA' and rows[1]['amount'] == '3000.00'
    rows, _ = parse_statement('31/12 Mercado 5,00', 'pdf', date(2027,1,1), card=True)
    assert rows[0]['date'] == '2026-12-31'
    rows, _ = parse_statement('<OFX><BANKTRANLIST><STMTTRN><DTPOSTED>20261026<TRNAMT>-12.50<FITID>123<MEMO>R N Doces</STMTTRN></BANKTRANLIST></OFX>', 'ofx', date(2026,10,1))
    assert rows[0]['amount'] == '12.50' and rows[0]['type'] == 'DESPESA'
    rows, _ = parse_statement('<OFX><BANKTRANLIST><STMTTRN><DTPOSTED>20261026<TRNAMT>-12.50<FITID>123<MEMO>R N Doces</STMTTRN></BANKTRANLIST></OFX>', 'ofx', date(2026,10,1), card=True)
    assert rows[0]['blocked'] is False
    rows, _ = parse_statement('26/10/2026 Bonus 12,50 C', 'pdf', date(2026,10,1), card=True)
    assert rows[0]['blocked'] is True


def test_import_preview_rejects_foreign_account_and_payment_freezes_old_preview(client, auth_headers):
    account = client.post(P+'/settings/accounts', headers=auth_headers, json={'name': 'Card bank', 'account_type': 'CHECKING', 'initial_balance': '1000'}).json()
    card = client.post(P+'/cards', headers=auth_headers, json={'name': 'Card import', 'card_type': 'CREDIT', 'closing_day': 25, 'due_day': 5, 'credit_limit': '5000'}).json()
    today = date.today()
    data = {'account_id': account['id'], 'card_id': card['id'], 'reference_month': str(today)[:7]}
    content = f'Data;Descrição;Valor\n{today:%d/%m/%Y};Compra nova;50,00'
    res = client.post(P+'/imports/preview', headers=auth_headers, data=data, files={'file': ('test.csv', content.encode(), 'text/csv')})
    assert res.status_code == 200, res.text
    preview = res.json()
    body = {'preview_token': preview['preview_token'], 'reviewed': True, 'entries': [{'index': 0, 'description': 'Nova compra', 'type': 'DESPESA'}]}
    tx = client.post(P+'/transactions', headers=auth_headers, json={'description': 'Compra antes do pagamento', 'type': 'DESPESA', 'amount': '100', 'date': str(today), 'account_id': account['id'], 'card_id': card['id'], 'responsible_name': 'Família'})
    assert tx.status_code == 201, tx.text
    from app.api.v1.cards import get_current_invoice_period
    from types import SimpleNamespace
    year, month = get_current_invoice_period(SimpleNamespace(closing_day=25, due_day=5), today)
    res = client.post(P+f"/cards/{card['id']}/invoices/{year}/{month}/pay", headers=auth_headers, json={'account_id': account['id'], 'amount': '10'})
    assert res.status_code == 200, res.text
    assert client.post(P+'/imports/confirm', headers=auth_headers, json=body).status_code == 409
    other = client.post(P+'/auth/register', json={'full_name': 'Foreign', 'email': 'foreign-statement@example.com', 'password': 'securepassword123'}).json()
    foreign = {'Authorization': 'Bearer '+other['access_token'], 'X-Family-Id': other['current_family_id']}
    res = client.post(P+'/imports/preview', headers=foreign, data=data, files={'file': ('test.csv', content.encode(), 'text/csv')})
    assert res.status_code == 400
