from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from app.api.v1.cards import get_current_invoice_period

P = '/api/v1'


def test_invoice_workspace_funding_edits_payments_and_family_isolation(client, auth_headers):
    def post(path, data):
        result = client.post(P + path, headers=auth_headers, json=data)
        assert result.status_code in (200, 201), result.text
        return result.json()

    account = post('/settings/accounts', {'name': 'Banco', 'account_type': 'CHECKING', 'initial_balance': '800'})
    post('/settings/accounts', {'name': 'Poupança', 'account_type': 'SAVINGS', 'initial_balance': '200'})
    post('/settings/accounts', {'name': 'Investimentos', 'account_type': 'INVESTMENT', 'initial_balance': '10000'})
    post('/settings/accounts', {'name': 'Conta cartão legada', 'account_type': 'CREDIT_CARD', 'initial_balance': '9999'})
    cards = [post('/cards', {'name': name, 'card_type': 'CREDIT', 'credit_limit': '5000', 'closing_day': 25,
                            'due_day': 5, 'responsible_name': 'Teste', 'account_id': account['id']}) for name in ['Cartão A', 'Cartão B']]
    year, month = get_current_invoice_period(SimpleNamespace(closing_day=25, due_day=5), date.today())
    invoice_path = f"/cards/{cards[0]['id']}/invoices/{year}/{month}"
    empty = post(invoice_path, {})
    assert empty['id'] == post(invoice_path, {})['id'], 'Registering an existing period is idempotent'
    assert empty['cycle_start_date'] <= str(date.today()) <= empty['closing_date']
    txs = [post('/transactions', {'date': str(date.today()), 'description': name, 'type': 'DESPESA',
          'amount': value, 'account_id': account['id'], 'card_id': card['id'], 'responsible_name': 'Teste'})
          for card, name, value in zip(cards, ['Mercado', 'Combustível'], ['500', '700'])]
    # A realized future receipt is not cash available today.
    post('/transactions', {'date': str(date.today() + timedelta(days=2)), 'description': 'Receita futura',
         'type': 'RECEITA', 'amount': '10000', 'account_id': account['id'], 'responsible_name': 'Teste'})
    def summary(headers=auth_headers):
        result = client.get(P + f'/cards/invoices/overview?year={year}&month={month}', headers=headers)
        assert result.status_code == 200, result.text
        return result.json()
    overview = summary()
    assert len(overview['invoices']) == 2
    assert Decimal(str(overview['bank_balance'])) == 1000
    assert Decimal(str(overview['remaining_amount'])) == 1200
    assert Decimal(str(overview['shortfall'])) == 200
    updated = client.put(P + '/transactions/' + txs[0]['id'], headers=auth_headers, json={'amount': '550'})
    assert updated.status_code == 200, updated.text
    assert Decimal(str(summary()['shortfall'])) == 250
    assert client.delete(P + '/transactions/' + txs[1]['id'], headers=auth_headers).status_code == 200
    assert Decimal(str(summary()['remaining_amount'])) == 550
    assert Decimal(str(summary()['shortfall'])) == 0
    post(invoice_path + '/pay', {'account_id': account['id'], 'amount': '200', 'payment_date': str(date.today())})
    overview = summary()
    assert Decimal(str(overview['bank_balance'])) == 800
    assert Decimal(str(overview['remaining_amount'])) == 350
    assert Decimal(str(overview['balance_after_payment'])) == 450
    # Payment locks composition; bank debit and purchase are not counted twice.
    assert client.delete(P + '/transactions/' + txs[0]['id'], headers=auth_headers).status_code == 409
    outsider = client.post(P + '/auth/register', json={'email': 'other-invoices@example.com', 'full_name': 'Other',
                                                     'password': 'strongpassword123'}).json()
    foreign_headers = {'Authorization': 'Bearer ' + outsider['access_token'], 'X-Family-Id': outsider['current_family_id']}
    assert summary(foreign_headers)['invoices'] == []
    assert client.post(P + invoice_path, headers=foreign_headers, json={}).status_code == 404
    assert client.get(P + '/cards/invoices/overview?year=2026&month=13', headers=auth_headers).status_code == 400
