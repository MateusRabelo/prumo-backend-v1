from decimal import Decimal
from test_dynamic_card_flow import setup,P
from app.models.installment import InstallmentPlan
from app.models.transaction import Transaction


def test_import_classification_overrides_category_and_remains_correct_after_payment(client,auth_headers,db):
    post,account,card,category=setup(client,auth_headers)
    r=client.post(P+'/imports/preview',headers=auth_headers,data={'account_id':account['id'],'card_id':card['id'],'reference_month':'2026-10'},files={'file':('choices.csv',b'Data;Descricao;Valor\n27/10/2026;Loja - Parcela 1/3;50,00\n27/10/2026;Outro gasto;20,00','text/csv')})
    assert r.status_code==200,r.text
    body={'preview_token':r.json()['preview_token'],'reviewed':True,'entries':[
        {'index':0,'description':'Loja','type':'DESPESA','category_id':category['id'],'classification':'DESEJO','classification_explicit':True,'import_installment':True,'remember':True},
        {'index':1,'description':'Outro gasto','type':'DESPESA','category_id':category['id'],'classification':'OUTRO','classification_explicit':True}]}
    assert post('/imports/confirm',body)['imported']==2
    assert db.query(InstallmentPlan).filter_by(card_id=card['id']).one().classification=='DESEJO'
    def budget(month):return client.get(P+f'/budgets/503020?year=2026&month={month}',headers=auth_headers).json()
    assert Decimal(str(budget(10)['other_spent']))==20
    assert Decimal(str(budget(10)['total_committed']))==20
    assert Decimal(str(budget(11)['wants_spent']))==50
    post(f"/cards/{card['id']}/invoices/2026/11/pay",{'account_id':account['id'],'payment_date':'2026-10-27'})
    assert Decimal(str(budget(10)['other_spent']))==20
    assert Decimal(str(budget(11)['wants_spent']))==50
    assert db.query(Transaction).filter(Transaction.card_id==card['id'],Transaction.installment_id.is_not(None),Transaction.is_deleted==False).one().classification=='DESEJO'
