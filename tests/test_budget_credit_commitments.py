from decimal import Decimal
from test_dynamic_card_flow import setup,P


def test_credit_purchases_and_monthly_parcels_commit_budgets_before_invoice_payment(client,auth_headers):
    post,account,card,category=setup(client,auth_headers)
    wants=post('/settings/categories',{'name':'Lazer planejado','type':'DESPESA','classification':'DESEJO'})
    post('/transactions',{'date':'2026-10-27','description':'Compra crédito','type':'DESPESA','amount':'100','card_id':card['id'],'responsible_name':'Mateus','classification':'NECESSIDADE','status':'PENDENTE','category_id':category['id']})
    post('/transactions',{'date':'2026-10-27','description':'Conta paga','type':'DESPESA','amount':'18','account_id':account['id'],'responsible_name':'Mateus','status':'REALIZADA'})
    post('/transactions',{'date':'2026-10-27','description':'Conta prevista','type':'DESPESA','amount':'99','account_id':account['id'],'responsible_name':'Mateus','status':'PENDENTE'})
    post('/installments/',{'description':'Viagem','category_id':wants['id'],'card_id':card['id'],'responsible_name':'Mateus','total_amount':'300','installments_count':3,'purchase_date':'2026-10-27'})
    custom=post('/budgets/custom',{'year':2026,'month':11,'category_id':wants['id'],'limit_amount':'80'})
    def budget(month):
        r=client.get(P+f'/budgets/503020?year=2026&month={month}',headers=auth_headers);assert r.status_code==200,r.text
        return r.json()
    assert Decimal(str(budget(10)['needs_spent']))==118
    assert Decimal(str(budget(11)['wants_spent']))==100
    assert Decimal(str(budget(10)['wants_spent']))==0
    r=client.get(P+'/budgets/custom?year=2026&month=11',headers=auth_headers).json()
    assert Decimal(str(next(b for b in r if b['id']==custom['id'])['exceeded_amount']))==20
    post(f"/cards/{card['id']}/invoices/2026/11/pay",{'account_id':account['id'],'payment_date':'2026-10-27'})
    assert Decimal(str(budget(10)['needs_spent']))==118
    assert Decimal(str(budget(11)['wants_spent']))==100
