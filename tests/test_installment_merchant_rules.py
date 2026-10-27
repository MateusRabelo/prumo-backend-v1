from test_dynamic_card_flow import setup,P
from app.services.import_installments import merchant_name,merchant_key
from app.services.statement_parser import parse_statement
from datetime import date


def test_installment_patterns_are_generic_without_changing_real_numbers():
    for suffix in ['Parcela 1/5','Parcela 2/5','Parcelas 1/10','Parcela 1/*','Parcela */*']:
        assert merchant_name('Loja - '+suffix)=='Loja'
        assert merchant_key('Loja - '+suffix)=='loja'
    assert merchant_name('Produto 1/5')=='Produto 1/5'
    rows,_=parse_statement('Data;Descricao;Valor\n27/10/2026;Loja - Parcelas 2/5;50,00','csv',date(2026,10,1),card=True)
    assert rows[0]['installment_info']['number']==2 and rows[0]['installment_info']['count']==5


def test_learned_name_and_category_apply_to_any_installment_number_or_total(client,auth_headers):
    post,account,card,category=setup(client,auth_headers)
    def preview(number,total,day='27/10/2026'):
        r=client.post(P+'/imports/preview',headers=auth_headers,data={'account_id':account['id'],'card_id':card['id'],'reference_month':'2026-10'},files={'file':('test.csv',f'Data;Descricao;Valor\n{day};R N Doces - Parcela {number}/{total};50,00'.encode(),'text/csv')})
        assert r.status_code==200,r.text
        return r.json()
    draft=preview(1,5)
    result=post('/imports/confirm',{'preview_token':draft['preview_token'],'reviewed':True,'entries':[{'index':0,'description':'Cantina faculdade - Parcela 1/*','type':'DESPESA','category_id':category['id'],'remember':True,'import_installment':True}]})
    assert result['imported']==1
    rules=client.get(P+'/imports/rules',headers=auth_headers).json()
    assert rules[0]['description']=='Cantina faculdade' and rules[0]['merchant']=='r n doces'
    for number,total in [(2,5),(1,10)]:
        row=preview(number,total,'27/11/2026')['rows'][0]
        assert row['description']=='Cantina faculdade'
        assert row['category_id']==category['id']
        assert row['installment_info']['number']==number and row['installment_info']['count']==total
