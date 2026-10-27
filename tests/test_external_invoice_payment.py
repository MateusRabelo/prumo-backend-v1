from decimal import Decimal
from app.models.transaction import Transaction
from app.models.audit import AuditLog
from test_dynamic_card_flow import setup, P


def test_external_payment_checks_password_preserves_cash_and_can_be_reversed(client,auth_headers,db):
    post,account,card,category=setup(client,auth_headers)
    post('/transactions',{'date':'2026-10-27','description':'Compra','type':'DESPESA','amount':'100','card_id':card['id'],'responsible_name':'Mateus'})
    plan=post('/installments/',{'description':'Loja','category_id':category['id'],'card_id':card['id'],'responsible_name':'Mateus','total_amount':'60','installments_count':2,'purchase_date':'2026-10-27'})
    path=f"/cards/{card['id']}/invoices/2026/11"
    body={'password':'wrong-password','expected_total':'130','payment_date':'2026-10-27'}
    assert client.post(P+path+'/external-payment',headers=auth_headers,json=body).status_code==400
    assert client.get(P+path,headers=auth_headers).json()['status']!='PAGA'
    body['password']='secretpassword123'
    body['expected_total']='129'
    assert client.post(P+path+'/external-payment',headers=auth_headers,json=body).status_code==409
    body['expected_total']='130'
    confirmed=post(path+'/external-payment',body)
    assert confirmed['external_settled'] and confirmed['status']=='PAGA'
    assert Decimal(str(confirmed['external_paid_amount']))==130
    assert Decimal(str(confirmed['remaining_amount']))==0
    assert db.query(Transaction).filter_by(is_invoice_payment=True).count()==0
    assert client.get(P+'/installments/'+plan['id'],headers=auth_headers).json()['installments'][0]['status']=='PAGA'
    accounts=client.get(P+'/settings/accounts',headers=auth_headers).json()
    assert Decimal(str(next(a for a in accounts if a['id']==account['id'])['current_balance']))==1000
    assert post(path+'/external-payment',body)['status']=='PAGA'
    reopened=post(path+'/external-payment/reverse',body)
    assert not reopened['external_settled'] and Decimal(str(reopened['remaining_amount']))==130
    assert client.get(P+'/installments/'+plan['id'],headers=auth_headers).json()['installments'][0]['status']=='PENDENTE'
    # Ordinary payment remains a bank debit.
    paid=post(path+'/pay',{'account_id':account['id'],'payment_date':'2026-10-27'})
    assert paid['status']=='PAGA' and not paid['external_settled']
    accounts=client.get(P+'/settings/accounts',headers=auth_headers).json()
    assert Decimal(str(next(a for a in accounts if a['id']==account['id'])['current_balance']))==870
    audit=str([(a.action,a.new_values) for a in db.query(AuditLog).all()])
    assert 'secretpassword123' not in audit and 'wrong-password' not in audit


def test_empty_invoice_is_not_overdue_and_external_closure_is_frozen(client,auth_headers):
    post,account,card,category=setup(client,auth_headers)
    path=f"/cards/{card['id']}/invoices/2026/10"
    empty=post(path,{})
    assert empty['status']=='ABERTA' and empty['items_count']==0
    body={'password':'secretpassword123','expected_total':'0','payment_date':'2026-10-10'}
    closed=post(path+'/external-payment',body)
    assert closed['status']=='PAGA' and closed['external_settled']
    assert Decimal(str(closed['paid_amount']))==0
    r=client.post(P+'/transactions',headers=auth_headers,json={'date':'2026-10-01','description':'Compra tardia','type':'DESPESA','amount':'1','card_id':card['id'],'responsible_name':'Mateus'})
    assert r.status_code==409,r.text
    assert post(path+'/external-payment/reverse',body)['status']=='ABERTA'


def test_external_payment_requires_family_admin_and_cannot_use_other_users_password(client,auth_headers):
    post,account,card,category=setup(client,auth_headers)
    other=client.post(P+'/auth/register',json={'email':'external-other@example.com','full_name':'Other User','password':'different-password123'}).json()
    foreign={'Authorization':'Bearer '+other['access_token'],'X-Family-Id':other['current_family_id']}
    path=f"/cards/{card['id']}/invoices/2026/10/external-payment"
    assert client.post(P+path,headers=foreign,json={'password':'different-password123','expected_total':'0'}).status_code==404
    assert client.post(P+path,headers=auth_headers,json={'password':'different-password123','expected_total':'0'}).status_code==400
