from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4, UUID
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.core.config import Settings
from app.models import Transaction, FamilyMembership, FamilyInvitation, BudgetRule503020
from app.core.security import get_password_hash, verify_password

P = '/api/v1'


def resources(client, headers):
    return (client.get(P+'/settings/accounts', headers=headers).json()[0]['id'],
            client.get(P+'/settings/categories', headers=headers).json()[0]['id'])


def transaction(account, **extra):
    return dict(date=str(date.today()), description='Regression', type='DESPESA', amount='100',
                account_id=account, responsible_name='Test', **extra)


def other_user(client):
    data = client.post(P+'/auth/register', json=dict(email='other@example.com', full_name='Other User', password='otherpassword123')).json()
    return {'Authorization': 'Bearer '+data['access_token'], 'X-Family-Id': data['current_family_id']}, data


def card_plan(client, headers):
    account, category = resources(client, headers)
    card = client.post(P+'/cards', headers=headers, json=dict(name='Card', closing_day=20, due_day=28, credit_limit='1000')).json()
    plan = client.post(P+'/installments/', headers=headers, json=dict(description='Plan', category_id=category,
        card_id=card['id'], responsible_name='Test', total_amount='100', installments_count=1,
        first_due_date=str(date.today()))).json()
    path = f"{P}/cards/{card['id']}/invoices/{date.today().year}/{date.today().month}"
    return account, card, plan, path


def test_cross_family_references(client, auth_headers):
    account, _ = resources(client, auth_headers)
    other_headers, _ = other_user(client)
    victim_account, victim_category = resources(client, other_headers)
    created = client.post(P+'/transactions/', headers=auth_headers, json=transaction(account)).json()
    for field, value in [('account_id', victim_account), ('category_id', victim_category), ('destination_account_id', victim_account)]:
        assert client.put(P+'/transactions/'+created['id'], headers=auth_headers, json={field: value}).status_code == 400
    assert client.post(P+'/cards', headers=auth_headers, json={'name': 'Invalid', 'account_id': victim_account}).status_code == 400
    assert Decimal(client.get(P+'/settings/accounts', headers=other_headers).json()[0]['current_balance']) == 0


def test_database_rejects_cross_family_reference(client, auth_headers, db):
    account, _ = resources(client, auth_headers)
    other_headers, _ = other_user(client)
    victim_account, _ = resources(client, other_headers)
    created = client.post(P+'/transactions/', headers=auth_headers, json=transaction(account)).json()
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(text('UPDATE transactions SET account_id=:account WHERE id=:id'), {'account': victim_account, 'id': created['id']})


def test_invites_require_recipient_and_admin(client, auth_headers, db):
    headers, data = other_user(client)
    invitation = client.post(P+'/family/invite', headers=auth_headers, json={'invited_email':'target@example.com','role':'ADMIN'}).json()
    assert client.post(P+'/family/accept-invite', headers=headers, json={'token': invitation['token']}).status_code == 403
    assert db.query(FamilyInvitation).filter_by(token=invitation['token']).first() is None
    own_invite = client.post(P+'/family/invite', headers=auth_headers, json={'invited_email':'other@example.com'}).json()
    assert client.post(P+'/family/accept-invite', headers=headers, json={'token': own_invite['token']}).status_code == 200
    shared = {**headers, 'X-Family-Id': auth_headers['X-Family-Id']}
    assert client.get(P+'/family/invitations', headers=shared).status_code == 403
    assert client.post(P+'/settings/accounts', headers=shared, json={'name':'Forbidden'}).status_code == 403
    invitations = client.get(P+'/family/invitations', headers=auth_headers).json()
    assert all('token' not in item for item in invitations)
    assert client.delete(P+'/family/invitations/'+invitation['id'], headers=auth_headers).status_code == 200


def test_partial_invoice_and_linked_transaction_protection(client, auth_headers, db):
    account, card, plan, path = card_plan(client, auth_headers)
    payload = {'account_id':account, 'amount':'1'}
    headers = {**auth_headers, 'Idempotency-Key':str(uuid4())}
    response = client.post(path+'/pay', headers=headers, json=payload)
    assert response.status_code == 200, response.text
    assert Decimal(response.json()['remaining_amount']) == 99
    assert client.get(P+'/installments/'+plan['id'], headers=auth_headers).json()['installments'][0]['status'] == 'PENDENTE'
    assert Decimal(client.get(P+'/cards/'+card['id'], headers=auth_headers).json()['used_limit']) == 99
    assert client.post(path+'/pay', headers=headers, json=payload).status_code == 200
    assert Decimal(client.get(path, headers=auth_headers).json()['paid_amount']) == 1
    assert client.post(path+'/pay', headers=headers, json={**payload,'amount':'2'}).status_code == 409
    for value in ['-1','0','0.001','10000000000']:
        assert client.post(path+'/pay', headers=auth_headers, json={'account_id':account,'amount':value}).status_code == 422
    assert client.post(path+'/pay', headers=auth_headers, json={'account_id':account,'amount':'100'}).status_code == 400
    payment = db.query(Transaction).filter_by(is_invoice_payment=True).one()
    for method in ['put','delete']:
        response = getattr(client, method)(P+'/transactions/'+str(payment.id), headers=auth_headers, **({'json':{'amount':'2'}} if method=='put' else {}))
        assert response.status_code == 409
    assert client.post(path+'/pay', headers=auth_headers, json={'account_id':account}).status_code == 200
    assert client.get(P+'/installments/'+plan['id'], headers=auth_headers).json()['installments'][0]['status'] == 'PAGA'
    summary = client.get(P+'/transactions/', headers=auth_headers).json()['summary']
    assert Decimal(summary['total_realized_expense']) == 100


def test_installment_only_in_one_invoice(client, auth_headers):
    account, card, plan, path = card_plan(client, auth_headers)
    today = date.today()
    next_month = today.replace(day=28) + timedelta(days=4)
    next_path = f"{P}/cards/{card['id']}/invoices/{next_month.year}/{next_month.month}"
    assert len(client.get(path, headers=auth_headers).json()['items']) == 1
    assert len(client.get(next_path, headers=auth_headers).json()['items']) == 0
    installment_id = plan['installments'][0]['id']
    assert client.post(P+f'/installments/installments/{installment_id}/pay', headers=auth_headers, json={}).status_code == 409


def test_tokens_revoked_on_password_change_and_logout(client, auth_headers):
    assert client.post(P+'/auth/change-password', headers=auth_headers,
        json={'current_password':'secretpassword123','new_password':'newpassword123'}).status_code == 200
    assert client.get(P+'/auth/me', headers=auth_headers).status_code == 401
    result = client.post(P+'/auth/login', json={'email':'testuser@example.com','password':'newpassword123'}).json()
    headers = {'Authorization':'Bearer '+result['access_token']}
    assert client.post(P+'/auth/logout', headers=headers).status_code == 200
    assert client.get(P+'/auth/me', headers=headers).status_code == 401


def test_validation_and_csv(client, auth_headers):
    account, _ = resources(client, auth_headers)
    assert client.post(P+'/transactions/', headers=auth_headers, json={**transaction(account), 'type':'TRANSFERENCIA'}).status_code == 400
    data = client.post(P+'/transactions/', headers=auth_headers, json={**transaction(account), 'description':'=1+1'}).json()
    assert client.put(P+'/transactions/'+data['id'], headers=auth_headers, json={'amount':None}).status_code == 422
    assert "'=1+1" in client.get(P+'/transactions/export/csv', headers=auth_headers).text
    assert client.post(P+'/auth/register', json={'full_name':'  ','email':'blank@example.com','password':'password123'}).status_code == 422
    assert client.post(P+'/auth/register', json={'full_name':'Long Password','email':'long@example.com','password':'a'*100}).status_code == 201
    password = '  spaces matter  '
    assert verify_password(password, get_password_hash(password))


def test_read_budget_does_not_write(client, auth_headers, db):
    before = db.query(BudgetRule503020).count()
    assert client.get(P+'/budgets/503020', headers=auth_headers).status_code == 200
    assert db.query(BudgetRule503020).count() == before
    assert client.get(P+'/budgets/503020?month=13', headers=auth_headers).status_code == 422


def test_production_secret_required():
    for secret in ['', 'change-this-in-production-super-secret-key-msfinancas-2026']:
        with pytest.raises(ValueError):
            Settings(_env_file=None, ENVIRONMENT='production', SECRET_KEY=secret)


def test_auth_rate_limit(client, monkeypatch):
    from types import SimpleNamespace
    from app.api import rate_limit
    monkeypatch.setattr(rate_limit, "time", SimpleNamespace(time=lambda: 1800000000))
    for _ in range(20):
        assert client.post(P+'/auth/login', json={'email':'missing@example.com','password':'invalid'}).status_code == 401
    response = client.post(P+'/auth/login', json={'email':'missing@example.com','password':'invalid'})
    assert response.status_code == 429
    assert response.headers['Retry-After'] == '60'


def test_password_reset_single_use(client, auth_headers, monkeypatch):
    from app.core.config import settings
    from app.services import password_reset
    monkeypatch.setattr(settings, 'SMTP_HOST', 'smtp.example.com')
    monkeypatch.setattr(settings, 'SMTP_FROM', 'sender@example.com')
    monkeypatch.setattr(settings, 'PASSWORD_RESET_URL', 'https://example.com/reset')
    delivered = []
    monkeypatch.setattr(password_reset, 'send_reset_email', lambda email, token: delivered.append(token))
    assert client.post(P+'/auth/recover-password', json={'email':'testuser@example.com'}).status_code == 200
    payload = {'token':delivered[0], 'new_password':'resetpassword123'}
    assert client.post(P+'/auth/reset-password', json=payload).status_code == 200
    assert client.post(P+'/auth/reset-password', json=payload).status_code == 400
    assert client.get(P+'/auth/me', headers=auth_headers).status_code == 401
    assert client.post(P+'/auth/login', json={'email':'testuser@example.com','password':'resetpassword123'}).status_code == 200


def test_invoice_reversal_restores_debt_and_balance(client, auth_headers, db):
    account, card, plan, path = card_plan(client, auth_headers)
    assert client.post(path+'/pay', headers=auth_headers, json={'account_id':account}).status_code == 200
    payment = db.query(Transaction).filter_by(is_invoice_payment=True).one()
    response = client.post(path+f'/payments/{payment.id}/reverse', headers=auth_headers)
    assert response.status_code == 200, response.text
    assert Decimal(response.json()['remaining_amount']) == 100
    assert Decimal(client.get(P+'/cards/'+card['id'], headers=auth_headers).json()['used_limit']) == 100
    balance = next(a for a in client.get(P+'/settings/accounts', headers=auth_headers).json() if a['id']==account)
    assert Decimal(balance['current_balance']) == 0
    assert client.post(path+f'/payments/{payment.id}/reverse', headers=auth_headers).status_code == 404
    assert client.post(path+'/pay', headers=auth_headers, json={'account_id':account}).status_code == 200
    assert Decimal(client.get(P+'/transactions/', headers=auth_headers).json()['summary']['total_realized_expense']) == 100


def test_concurrent_invoice_payments_are_idempotent(db):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import Session
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.database import get_db
    engine = db.get_bind().engine
    def independent_session():
        with Session(engine) as session:
            yield session
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = independent_session
    try:
        with TestClient(app) as client:
            result = client.post(P+'/auth/register', json={'email':f'concurrent-{uuid4()}@example.com',
                'full_name':'Concurrent User','password':'concurrentpassword123'}).json()
            headers = {'Authorization':'Bearer '+result['access_token'], 'X-Family-Id': result['current_family_id']}
            account, card, plan, path = card_plan(client, headers)
            headers['Idempotency-Key'] = str(uuid4())
            barrier = Barrier(2)
            def pay():
                barrier.wait(timeout=10)
                return client.post(path+'/pay', headers=headers, json={'account_id':account,'amount':'1'})
            with ThreadPoolExecutor(max_workers=2) as executor:
                responses = list(executor.map(lambda _:pay(), range(2)))
            assert [r.status_code for r in responses] == [200,200], [r.text for r in responses]
            invoice = client.get(path, headers=headers).json()
            assert Decimal(invoice['paid_amount']) == 1
            with Session(engine) as session:
                assert session.query(Transaction).filter_by(card_id=UUID(card['id']), is_invoice_payment=True).count() == 1
    finally:
        if previous:
            app.dependency_overrides[get_db] = previous
        else:
            app.dependency_overrides.pop(get_db, None)


def test_standalone_installment_reversal_and_cancelled_payment(client, auth_headers):
    account, category = resources(client, auth_headers)
    plan = client.post(P+'/installments/', headers=auth_headers, json={'description':'Standalone',
        'category_id':category,'account_id':account,'responsible_name':'Test','total_amount':'100',
        'installments_count':1,'first_due_date':str(date.today())}).json()
    path = P+'/installments/installments/'+plan['installments'][0]['id']
    assert client.post(path+'/pay', headers=auth_headers, json={}).status_code == 200
    assert client.post(path+'/reverse', headers=auth_headers).status_code == 200
    assert client.get(P+'/installments/'+plan['id'], headers=auth_headers).json()['status'] == 'ACTIVE'
    assert client.post(P+'/installments/'+plan['id']+'/cancel', headers=auth_headers).status_code == 200
    assert client.post(path+'/pay', headers=auth_headers, json={}).status_code == 409


def test_goal_adjustment_and_reversal(client, auth_headers):
    account, _ = resources(client, auth_headers)
    goal = client.post(P+'/goals/', headers=auth_headers, json={'name':'Goal','target_amount':'100','responsible_name':'Test'}).json()
    path = P+'/goals/'+goal['id']
    assert client.post(path+'/contributions', headers=auth_headers, json={'type':'AJUSTE','amount':'10','account_id':account}).status_code == 400
    contribution = client.post(path+'/contributions', headers=auth_headers, json={'amount':'100','account_id':account}).json()
    assert client.get(path, headers=auth_headers).json()['status'] == 'CONCLUIDA'
    assert client.delete(path, headers=auth_headers).status_code == 409
    reverse = client.post(path+'/contributions/'+contribution['id']+'/reverse', headers=auth_headers)
    assert reverse.status_code == 200, reverse.text
    assert reverse.json()['is_reversed'] is True
    assert Decimal(client.get(path, headers=auth_headers).json()['accumulated_amount']) == 0
    assert client.get(path, headers=auth_headers).json()['status'] == 'EM_ANDAMENTO'
    assert Decimal(client.get(P+'/settings/accounts', headers=auth_headers).json()[0]['current_balance']) == 0


def test_frozen_invoice_and_goal_history(client, auth_headers):
    account, card, plan, path = card_plan(client, auth_headers)
    assert client.post(path+'/pay', headers=auth_headers, json={'account_id':account,'amount':'1'}).status_code == 200
    category = resources(client, auth_headers)[1]
    response = client.post(P+'/installments/', headers=auth_headers, json={'description':'Blocked',
        'card_id':card['id'],'category_id':category,'responsible_name':'Test','total_amount':'10',
        'installments_count':1,'first_due_date':str(date.today())})
    assert response.status_code == 409
    goal = client.post(P+'/goals/', headers=auth_headers, json={'name':'History','target_amount':'100','responsible_name':'Test'}).json()
    contribution = client.post(P+'/goals/'+goal['id']+'/contributions', headers=auth_headers, json={'amount':'10'}).json()
    history = client.get(P+'/goals/'+goal['id']+'/contributions', headers=auth_headers)
    assert history.status_code == 200
    assert history.json()[0]['id'] == contribution['id']
