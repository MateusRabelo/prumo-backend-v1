from decimal import Decimal
from test_dynamic_card_flow import setup,P


def test_weekly_agreement_keeps_mondays_across_months_and_pays_only_once(client,auth_headers):
    post,account,card,category=setup(client,auth_headers)
    plan=post('/installments/',{'description':'Acerto toda segunda','category_id':category['id'],'account_id':account['id'],'responsible_name':'Mateus','frequency':'WEEKLY','total_amount':'1000','installments_count':5,'purchase_date':'2026-11-01','first_due_date':'2026-11-02'})
    assert plan['frequency']=='WEEKLY'
    assert [i['due_date'] for i in plan['installments']]==['2026-11-02','2026-11-09','2026-11-16','2026-11-23','2026-11-30']
    assert all(Decimal(i['amount'])==200 for i in plan['installments'])
    first=plan['installments'][0]
    post(f"/installments/installments/{first['id']}/pay",{'account_id':account['id'],'payment_date':'2026-11-02'})
    assert client.post(P+f"/installments/installments/{first['id']}/pay",headers=auth_headers,json={'account_id':account['id'],'payment_date':'2026-11-02'}).status_code==409
    updated=client.get(P+'/installments/'+plan['id'],headers=auth_headers).json()
    assert Decimal(updated['paid_amount'])==200 and Decimal(updated['remaining_amount'])==800


def test_weekly_cent_distribution_month_boundary_and_default_monthly(client,auth_headers):
    post,account,card,category=setup(client,auth_headers)
    base={'description':'Acordo','category_id':category['id'],'account_id':account['id'],'responsible_name':'Mateus','total_amount':'100','installments_count':3,'first_due_date':'2026-11-30'}
    weekly=post('/installments/',{**base,'frequency':'WEEKLY'})
    assert [i['due_date'] for i in weekly['installments']]==['2026-11-30','2026-12-07','2026-12-14']
    assert sum(Decimal(i['amount']) for i in weekly['installments'])==100
    monthly=post('/installments/',base)
    assert monthly['frequency']=='MONTHLY'
    assert [i['due_date'] for i in monthly['installments']]==['2026-11-30','2026-12-30','2027-01-30']
    assert client.post(P+'/installments/',headers=auth_headers,json={**base,'frequency':'DAILY'}).status_code==422
