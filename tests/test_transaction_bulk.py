from test_dynamic_card_flow import setup,P


def test_bulk_atomic_update_and_stale_selection(client,auth_headers):
    post,account,card,category=setup(client,auth_headers)
    person=post('/settings/responsibles',{'name':'Outro responsável','is_shared':True})
    def create(name):
        return post('/transactions/',{'date':'2026-10-27','description':name,'type':'DESPESA','amount':'10','account_id':account['id'],'responsible_name':'Mateus','status':'PENDENTE'})
    a,b=create('Primeira'),create('Segunda')
    items=[{'id':t['id'],'updated_at':t['updated_at']} for t in [a,b]]
    r=client.post(P+'/transactions/bulk',headers=auth_headers,json={'items':items,'status':'REALIZADA','responsible_name':person['name']})
    assert r.status_code==200,r.text
    assert r.json()['updated']==2
    for t in [a,b]:
        actual=client.get(P+'/transactions/'+t['id'],headers=auth_headers).json()
        assert actual['status']=='REALIZADA' and actual['responsible_name']==person['name'] and actual['is_shared']
    balances=client.get(P+'/settings/accounts',headers=auth_headers).json()
    assert next(a for a in balances if a['id']==account['id'])['current_balance']=='980.00'
    fresh=create('Sem alteração')
    r=client.post(P+'/transactions/bulk',headers=auth_headers,json={'items':[items[0],{'id':fresh['id'],'updated_at':fresh['updated_at']}],'status':'VENCIDA'})
    assert r.status_code==409,r.text
    assert client.get(P+'/transactions/'+fresh['id'],headers=auth_headers).json()['status']=='PENDENTE'


def test_bulk_rejects_foreign_ids_invalid_responsible_and_protected_invoice(client,auth_headers):
    from uuid import uuid4
    post,account,card,category=setup(client,auth_headers)
    a=post('/transactions/',{'date':'2026-10-27','description':'Crédito protegido','type':'DESPESA','amount':'10','card_id':card['id'],'responsible_name':'Mateus','status':'PENDENTE'})
    item={'id':a['id'],'updated_at':a['updated_at']}
    def bulk(items,**kwargs): return client.post(P+'/transactions/bulk',headers=auth_headers,json={'items':items,**kwargs})
    assert bulk([item],responsible_name='Pessoa de outro espaço').status_code==400
    assert bulk([item,{**item,'id':str(uuid4())}],status='REALIZADA').status_code==404
    assert bulk([item,item],status='REALIZADA').status_code==400
    assert bulk([item]).status_code==400
    post(f"/cards/{card['id']}/invoices/2026/11/pay",{'account_id':account['id'],'payment_date':'2026-10-27'})
    refreshed=client.get(P+'/transactions/'+a['id'],headers=auth_headers).json()
    assert bulk([{'id':a['id'],'updated_at':refreshed['updated_at']}],status='PENDENTE').status_code==409
