from datetime import date
from decimal import Decimal
from app.models.installment import InstallmentPlan
from app.models.transaction import Transaction
from app.models.family import FamilyMembership
from app.services.responsibles import sync_responsibles

P = '/api/v1'


def setup(client, headers):
    def post(path, data):
        r = client.post(P+path, headers=headers, json=data)
        assert r.status_code in (200,201), r.text
        return r.json()
    account = post('/settings/accounts', {'name':'Nubank', 'account_type':'CHECKING', 'initial_balance':'1000','initial_balance_date':'2026-10-01'})
    card = post('/cards', {'name':'Nu', 'card_type':'MULTIPLE','account_id':account['id'],'closing_day':20,'due_day':28,'credit_limit':'5000'})
    category = client.get(P+'/settings/categories',headers=headers).json()[0]
    return post, account, card, category


def test_credit_debit_and_installments_share_correct_account_and_invoice(client,auth_headers):
    post, account, card, category = setup(client,auth_headers)
    base = {'date':'2026-10-27','description':'Compra','type':'DESPESA','amount':'100','card_id':card['id'],'responsible_name':'Mateus'}
    credit = post('/transactions',{**base,'payment_mode':'CREDIT'})
    assert credit['account_id'] == account['id'] and credit['invoice_id']
    assert 'Novembro' in credit['invoice_label']
    assert credit['invoice_year']==2026 and credit['invoice_month']==11
    assert not credit['is_invoice_payment']
    assert credit['card_name']=='Nu'
    debit = post('/transactions',{**base,'payment_mode':'DEBIT'})
    assert debit['invoice_id'] is None
    accounts = client.get(P+'/settings/accounts',headers=auth_headers).json()
    assert Decimal(str(next(a for a in accounts if a['id']==account['id'])['current_balance'])) == 900
    plan = post('/installments/',{'description':'Notebook','category_id':category['id'],'card_id':card['id'],'responsible_name':'Mateus','total_amount':'300','installments_count':3,'purchase_date':'2026-10-27'})
    assert plan['first_due_date'] == '2026-11-28'
    invoice = client.get(P+f"/cards/{card['id']}/invoices/2026/11",headers=auth_headers).json()
    assert Decimal(str(invoice['total_amount'])) == 200
    assert len(invoice['items']) == 2
    moved = client.put(P+'/transactions/'+credit['id'],headers=auth_headers,json={'date':'2026-11-27'})
    assert moved.status_code==200,moved.text
    assert 'Dezembro' in moved.json()['invoice_label']
    november=client.get(P+f"/cards/{card['id']}/invoices/2026/11",headers=auth_headers).json()
    assert Decimal(str(november['total_amount']))==100
    switched=client.put(P+'/transactions/'+credit['id'],headers=auth_headers,json={'payment_mode':'DEBIT'})
    assert switched.status_code==200,switched.text
    assert switched.json()['invoice_id'] is None
    december=client.get(P+f"/cards/{card['id']}/invoices/2026/12",headers=auth_headers).json()
    assert Decimal(str(december['total_amount']))==100
    assert len(december['items'])==1 and december['items'][0]['is_installment']
    other = post('/settings/accounts',{'name':'Outro','account_type':'CHECKING'})
    assert client.post(P+'/transactions',headers=auth_headers,json={**base,'account_id':other['id']}).status_code==400


def test_import_installments_tracks_only_observed_and_future_and_deduplicates(client,auth_headers,db):
    post, account, card, category = setup(client,auth_headers)
    def preview(number):
        r=client.post(P+'/imports/preview',headers=auth_headers,data={'account_id':account['id'],'card_id':card['id'],'reference_month':'2026-10'},files={'file':('test.csv',f'Data;Descrição;Valor\n27/10/2026;Loja - Parcela {number}/6;50,00'.encode(),'text/csv')})
        assert r.status_code==200,r.text
        return r.json()
    draft=preview(6)
    assert draft['rows'][0]['installment_info']['number']==6
    body={'preview_token':draft['preview_token'],'reviewed':True,'entries':[{'index':0,'description':'Loja - Parcela 6/6','type':'DESPESA','category_id':category['id'],'import_installment':True}]}
    assert post('/imports/confirm',body)=={'imported':1,'skipped':0}
    plan=db.query(InstallmentPlan).filter_by(description='Loja').one()
    assert plan.imported_from_number==6 and len(plan.installments)==1
    assert plan.installments[0].installment_number==6
    assert db.query(Transaction).filter_by(card_id=card['id']).count()==0
    assert post('/imports/confirm',body)=={'imported':0,'skipped':1}
    assert preview(6)['rows'][0]['duplicate']
    invoice=client.get(P+f"/cards/{card['id']}/invoices/2026/11",headers=auth_headers).json()
    assert Decimal(str(invoice['total_amount']))==50


def test_responsibles_follow_members_without_fake_default_people(client,auth_headers,test_user,db):
    persons=client.get(P+'/settings/responsibles',headers=auth_headers).json()
    active=[p for p in persons if p['is_active']]
    assert len(active)==1 and active[0]['is_current_user'] and not active[0]['is_shared']
    other=client.post(P+'/auth/register',json={'email':'new-member@example.com','full_name':'Nova Pessoa','password':'securepassword123'}).json()
    from uuid import UUID
    db.add(FamilyMembership(family_id=test_user['family'].id,user_id=UUID(other['user']['id']) if 'user' in other else UUID(other['user_id']),role='MEMBER',alias_name='Nova'))
    db.flush()
    sync_responsibles(db,test_user['family'].id)
    active=[p for p in client.get(P+'/settings/responsibles',headers=auth_headers).json() if p['is_active']]
    assert {p['name'] for p in active}=={'Mateus','Nova','Conjunto'}


def test_import_matches_existing_plan_and_observed_value_without_second_purchase(client,auth_headers,db):
    post, account, card, category=setup(client,auth_headers)
    plan=post('/installments/',{'description':'Loja','category_id':category['id'],'card_id':card['id'],'responsible_name':'Mateus','total_amount':'150','installments_count':3,'purchase_date':'2026-10-27'})
    r=client.post(P+'/imports/preview',headers=auth_headers,data={'account_id':account['id'],'card_id':card['id'],'reference_month':'2026-10'},files={'file':('test.csv',b'Data;Descricao;Valor\n27/10/2026;Loja - Parcela 1/3;50,00','text/csv')})
    assert r.status_code==200,r.text
    draft=r.json()
    assert draft['rows'][0]['installment_info']['matching_plan_id']==plan['id']
    result=post('/imports/confirm',{'preview_token':draft['preview_token'],'reviewed':True,'entries':[{'index':0,'description':'Loja','type':'DESPESA','category_id':category['id'],'import_installment':True,'remember':True}]})
    assert result['imported']==1
    assert db.query(InstallmentPlan).filter_by(card_id=card['id']).count()==1
    invoice=client.get(P+f"/cards/{card['id']}/invoices/2026/11",headers=auth_headers).json()
    assert Decimal(str(invoice['total_amount']))==50
    assert len(invoice['items'])==1
