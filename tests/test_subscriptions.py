from datetime import date
from decimal import Decimal
from test_dynamic_card_flow import setup,P
from app.models.transaction import Transaction
from app.models.recurrence import RecurrenceRule
from app.services.subscriptions import next_date


def test_subscription_card_charge_is_atomic_bound_and_not_a_second_cash_debit(client,auth_headers,db):
    post,account,card,category=setup(client,auth_headers)
    body={'description':'Netflix','amount':'49.90','account_id':account['id'],'card_id':card['id'],'category_id':category['id'],'next_due_date':str(date.today())}
    before=db.query(Transaction).count()
    sub=post('/subscriptions',body)
    assert db.query(Transaction).count()==before
    assert client.post(P+'/subscriptions',headers=auth_headers,json=body).status_code==409
    charge={'expected_date':sub['next_due_date'],'date':str(date.today())}
    result=post('/subscriptions/'+sub['id']+'/charge',charge)
    assert result['next_due_date']>sub['next_due_date']
    assert client.post(P+'/subscriptions/'+sub['id']+'/charge',headers=auth_headers,json=charge).status_code==409
    tx=db.query(Transaction).filter_by(recurrence_id=sub['id']).one()
    assert str(tx.card_id)==card['id']
    assert tx.payment_mode=='CREDIT' and tx.invoice_id
    preview=client.post(P+'/imports/preview',headers=auth_headers,data={'account_id':account['id'],'card_id':card['id'],'reference_month':str(date.today())[:7]},files={'file':('sub.csv',f'Data;Descricao;Valor\n{date.today():%d/%m/%Y};Netflix.com;49,90'.encode(),'text/csv')})
    assert preview.status_code==200,preview.text
    assert preview.json()['rows'][0]['duplicate'] is True
    accounts=client.get(P+'/settings/accounts',headers=auth_headers).json()
    assert Decimal(str(next(a for a in accounts if a['id']==account['id'])['current_balance']))==1000
    foreign=client.post(P+'/auth/register',json={'email':'foreign-sub@example.com','full_name':'Other','password':'securepassword123'}).json()
    headers={'Authorization':'Bearer '+foreign['access_token'],'X-Family-Id':foreign['current_family_id']}
    assert client.get(P+'/subscriptions',headers=headers).json()==[]
    assert client.put(P+'/subscriptions/'+sub['id'],headers=headers,json=body).status_code==404
    assert client.post(P+'/subscriptions/'+sub['id']+'/charge',headers=headers,json=charge).status_code==404


def test_import_subscription_suggestion_requires_review_and_links_one_observed_charge(client,auth_headers,db):
    post,account,card,category=setup(client,auth_headers)
    def preview(day='27/10/2026'):
        r=client.post(P+'/imports/preview',headers=auth_headers,data={'account_id':account['id'],'card_id':card['id'],'reference_month':'2026-10'},files={'file':('sub.csv',f'Data;Descricao;Valor\n{day};Netflix.com;39,90'.encode(),'text/csv')})
        assert r.status_code==200,r.text
        return r.json()
    draft=preview()
    assert draft['rows'][0]['subscription_info']['matching_id'] is None
    assert db.query(RecurrenceRule).filter_by(is_subscription=True).count()==0
    body={'preview_token':draft['preview_token'],'reviewed':True,'entries':[{'index':0,'description':'Streaming da casa','type':'DESPESA','import_subscription':True}]}
    assert client.post(P+'/imports/confirm',headers=auth_headers,json=body).status_code==400
    body['entries'][0]['category_id']=category['id']
    assert post('/imports/confirm',body)['imported']==1
    rule=db.query(RecurrenceRule).filter_by(is_subscription=True).one()
    assert rule.next_due_date==date(2026,11,27)
    assert db.query(Transaction).filter_by(recurrence_id=rule.id).count()==1
    assert post('/imports/confirm',body)['skipped']==1
    next_draft=preview('27/11/2026')
    assert next_draft['rows'][0]['subscription_info']['matching_id']==str(rule.id)
    body['preview_token']=next_draft['preview_token']
    assert post('/imports/confirm',body)['imported']==1
    assert db.query(RecurrenceRule).filter_by(is_subscription=True).count()==1
    assert rule.next_due_date==date(2026,12,27)


def test_subscription_cash_charge_pause_and_month_end_dates(client,auth_headers):
    post,account,card,category=setup(client,auth_headers)
    body={'description':'Academia','amount':'100','account_id':account['id'],'category_id':category['id'],'next_due_date':str(date.today())}
    rule=post('/subscriptions',body)
    paused=client.put(P+'/subscriptions/'+rule['id'],headers=auth_headers,json={**body,'is_active':False})
    assert paused.status_code==200
    charge={'expected_date':rule['next_due_date'],'date':str(date.today())}
    assert client.post(P+'/subscriptions/'+rule['id']+'/charge',headers=auth_headers,json=charge).status_code==409
    assert client.put(P+'/subscriptions/'+rule['id'],headers=auth_headers,json=body).status_code==200
    post('/subscriptions/'+rule['id']+'/charge',charge)
    accounts=client.get(P+'/settings/accounts',headers=auth_headers).json()
    assert Decimal(str(next(a for a in accounts if a['id']==account['id'])['current_balance']))==900
    assert next_date(date(2027,1,31),'MONTHLY',31)==date(2027,2,28)
    assert next_date(date(2027,2,28),'MONTHLY',31)==date(2027,3,31)
    assert next_date(date(2026,12,31),'YEARLY')==date(2027,12,31)
