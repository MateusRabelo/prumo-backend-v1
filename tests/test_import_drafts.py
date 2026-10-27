import jwt
from datetime import datetime,timedelta,timezone
from app.core.config import settings
from app.models.transaction import Transaction
from app.models.family import FamilyMembership
from uuid import UUID
from test_dynamic_card_flow import setup,P


def preview(client,headers,account):
    r=client.post(P+'/imports/preview',headers=headers,data={'account_id':account['id'],'reference_month':'2026-10'},files={'file':('rascunho.csv',b'Data;Descricao;Valor\n27/10/2026;Loja exemplo;-50,00','text/csv')})
    assert r.status_code==200,r.text
    return r.json()


def test_drafts_resume_expired_preview_preserve_edits_and_complete_without_duplication(client,auth_headers,db):
    post,account,card,category=setup(client,auth_headers)
    before=db.query(Transaction).count()
    draft=preview(client,auth_headers,account)
    path=P+'/imports/drafts/'+draft['draft_id']
    assert db.query(Transaction).count()==before
    state={'revision':draft['revision'],'entries':[{'index':0,'description':'Nome revisado','type':'DESPESA','category_id':category['id'],'selected':True,'remember':True}],'bulk_category':category['id'],'group_open':{category['id']:False}}
    saved=client.put(path,headers=auth_headers,json=state)
    assert saved.status_code==200,saved.text
    assert client.put(path,headers=auth_headers,json=state).status_code==409
    assert client.put(path,headers=auth_headers,json={**state,'revision':saved.json()['revision'],'entries':[{**state['entries'][0],'amount':'99999'}]}).status_code==422
    claims=jwt.decode(draft['preview_token'],settings.SECRET_KEY,algorithms=['HS256'])
    claims['exp']=datetime.now(timezone.utc)-timedelta(seconds=1)
    expired=jwt.encode(claims,settings.SECRET_KEY,algorithm='HS256')
    body={'preview_token':expired,'reviewed':True,'entries':[{'index':0,'description':'Nome revisado','type':'DESPESA','category_id':category['id']}]}
    assert client.post(P+'/imports/confirm',headers=auth_headers,json=body).status_code==400
    restored=client.get(path,headers=auth_headers)
    assert restored.status_code==200,restored.text
    data=restored.json()
    assert data['review_state']['entries'][0]['description']=='Nome revisado'
    assert data['rows'][0]['amount']=='50.00'
    assert data['review_state']['group_open'][category['id']] is False
    body.update(preview_token=data['preview_token'],draft_id=draft['draft_id'],draft_revision=data['revision'])
    assert client.post(P+'/imports/confirm',headers=auth_headers,json=body).json()=={'imported':1,'skipped':0}
    assert client.post(P+'/imports/confirm',headers=auth_headers,json=body).json()=={'imported':0,'skipped':1}
    assert db.query(Transaction).count()==before+1
    assert client.get(P+'/imports/drafts',headers=auth_headers).json()==[]
    assert client.get(path,headers=auth_headers).status_code==404


def test_drafts_are_private_even_from_another_member_of_the_same_family(client,auth_headers,test_user,db):
    post,account,card,category=setup(client,auth_headers)
    draft=preview(client,auth_headers,account)
    other=client.post(P+'/auth/register',json={'email':'draft-other@example.com','full_name':'Other','password':'securepassword123'}).json()
    db.add(FamilyMembership(family_id=test_user['family'].id,user_id=UUID(other['user']['id']),role='MEMBER',alias_name='Other'));db.flush()
    headers={'Authorization':'Bearer '+other['access_token'],'X-Family-Id':auth_headers['X-Family-Id']}
    path=P+'/imports/drafts/'+draft['draft_id']
    assert client.get(P+'/imports/drafts',headers=headers).json()==[]
    assert client.get(path,headers=headers).status_code==404
    assert client.put(path,headers=headers,json={'revision':1,'entries':[]}).status_code==404
    assert client.delete(path,headers=headers).status_code==404
    assert client.delete(path,headers=auth_headers).status_code==200
    assert client.get(path,headers=auth_headers).status_code==404
    body={'preview_token':draft['preview_token'],'reviewed':True,'entries':[{'index':0,'description':'Loja','type':'DESPESA'}]}
    assert client.post(P+'/imports/confirm',headers=auth_headers,json=body).status_code==404


def test_draft_limit_can_be_freed_without_touching_finances(client,auth_headers):
    post,account,card,category=setup(client,auth_headers)
    drafts=[preview(client,auth_headers,account) for _ in range(10)]
    assert len(client.get(P+'/imports/drafts',headers=auth_headers).json())==10
    r=client.post(P+'/imports/preview',headers=auth_headers,data={'account_id':account['id'],'reference_month':'2026-10'},files={'file':('new.csv',b'Data;Descricao;Valor\n27/10/2026;Loja;-10,00','text/csv')})
    assert r.status_code==409
    assert client.delete(P+'/imports/drafts/'+drafts[0]['draft_id'],headers=auth_headers).status_code==200
    assert preview(client,auth_headers,account)['draft_id']
