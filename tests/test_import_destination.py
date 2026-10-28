from datetime import date
from decimal import Decimal
from uuid import uuid4
from test_dynamic_card_flow import setup,P
from app.models.card import CreditCard
from app.models.transaction import Transaction
from app.models.installment import InstallmentPlan,Installment
from app.api.v1.cards import get_current_invoice_period,get_invoice_cycle_dates


def test_final_destination_from_bank_preview_creates_parcels_in_explicit_reference(client,auth_headers,db):
    post,account,card,category=setup(client,auth_headers)
    model=db.get(CreditCard,card['id']);model.closing_day=4;model.due_day=10;model.billing_month_offset=-1;db.commit()
    assert get_current_invoice_period(model,date(2026,10,27))==(2026,10)
    assert get_current_invoice_period(model,date(2026,11,4))==(2026,10)
    assert get_current_invoice_period(model,date(2026,11,5))==(2026,11)
    assert get_invoice_cycle_dates(model,2026,10)[1:]==(date(2026,11,4),date(2026,11,10))
    ofx='<OFX><CCSTMTRS><BANKTRANLIST><DTSTART>20261004<DTEND>20261104<STMTTRN><DTPOSTED>20261004<TRNAMT>-50.00<FITID>parcel-reference-test<MEMO>Loja - Parcela 3/6</STMTTRN></BANKTRANLIST></CCSTMTRS></OFX>'
    r=client.post(P+'/imports/preview',headers=auth_headers,data={'account_id':account['id'],'reference_month':'2026-10'},files={'file':('fatura.ofx',ofx.encode(),'application/x-ofx')})
    assert r.status_code==200,r.text
    preview=r.json();assert preview['credit_statement'] and preview['rows'][0]['installment_info']['number']==3
    body={'preview_token':preview['preview_token'],'reviewed':True,'entries':[{'index':0,'description':'Loja - Parcela 3/6','type':'DESPESA','category_id':category['id'],'import_installment':True}], 'destination':{'account_id':account['id'],'card_id':card['id'],'invoice_month':'2026-10'}}
    invalid={**body,'destination':{'account_id':account['id']}}
    assert client.post(P+'/imports/confirm',headers=auth_headers,json=invalid).status_code==400
    assert client.post(P+'/imports/confirm',headers=auth_headers,json={**body,'destination':{**body['destination'],'card_id':str(uuid4())}}).status_code==400
    result=post('/imports/confirm',body);assert result['imported']==1
    plan=db.query(InstallmentPlan).filter_by(card_id=model.id).one()
    assert plan.imported_from_number==3 and len(plan.installments)==4
    october=client.get(P+f"/cards/{card['id']}/invoices/2026/10",headers=auth_headers).json()
    november=client.get(P+f"/cards/{card['id']}/invoices/2026/11",headers=auth_headers).json()
    assert len(october['items'])==1 and october['items'][0]['is_installment']
    assert october['due_date']=='2026-11-10'
    assert len(november['items'])==1 and november['items'][0]['installment_text']=='Parcela 4/6'
    assert november['due_date']=='2026-12-10'
    # Invoice settlement must find the explicitly assigned parcel, not the month of its due date.
    post(f"/cards/{card['id']}/invoices/2026/10/pay",{'account_id':account['id'],'payment_date':'2026-10-27'})
    assert plan.installments[0].status=='PAGA' and plan.installments[1].status=='PENDENTE'
    assert client.post(P+'/imports/confirm',headers=auth_headers,json=body).status_code==409
