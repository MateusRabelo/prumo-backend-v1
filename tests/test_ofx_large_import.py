import os
from pathlib import Path
from decimal import Decimal
import pytest
from test_dynamic_card_flow import setup,P
from app.models.transaction import Transaction
from app.models.installment import InstallmentPlan


def synthetic_ofx():
    entries=[]
    for i in range(71):
        memo=f'Loja exemplo {i} - Parcela 1/3' if i<20 else f'Compra exemplo {i}'
        entries.append(f'<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20261004000000[-3:BRT]<TRNAMT>-10.00<FITID>fixture-{i}<MEMO>{memo}</STMTTRN>')
    return ('OFXHEADER:100\nDATA:OFXSGML\nVERSION:102\n\n<OFX><CREDITCARDMSGSRSV1><CCSTMTTRNRS><CCSTMTRS><CURDEF>BRL<BANKTRANLIST><DTSTART>20261004000000[-3:BRT]<DTEND>20261104000000[-3:BRT]'+''.join(entries)+'</BANKTRANLIST></CCSTMTRS></CCSTMTTRNRS></CREDITCARDMSGSRSV1></OFX>').encode()


@pytest.mark.parametrize('real_sample',[False,True])
def test_large_ofx_confirms_signed_preview_and_links_installments_to_source_invoice(client,auth_headers,db,real_sample):
    if real_sample:
        path=Path(os.getenv('NUBANK_SAMPLE_DIR','/nonexistent'))/'Nubank_2026-11-11.ofx'
        if not path.exists():pytest.skip('Private local OFX is not part of the repository')
        content=path.read_bytes()
    else:content=synthetic_ofx()
    post,account,card,category=setup(client,auth_headers)
    assert client.put(P+'/cards/'+card['id'],headers=auth_headers,json={'closing_day':4,'due_day':10}).status_code==200
    res=client.post(P+'/imports/preview',headers=auth_headers,data={'account_id':account['id'],'card_id':card['id'],'reference_month':'2026-11'},files={'file':('statement.ofx',content,'application/x-ofx')})
    assert res.status_code==200,res.text
    draft=res.json()
    assert len(draft['preview_token'])>10000
    assert draft['statement']['format']=='ofx'
    assert draft['statement']['closing_date']=='2026-11-04'
    assert draft['statement']['month']==11 and draft['statement']['due_date']=='2026-11-10'
    selected=[r for r in draft['rows'] if not r['blocked'] and not r.get('refunded_in_statement')]
    parcels=[r for r in selected if r.get('installment_info')]
    assert len(parcels)==20
    body={'preview_token':draft['preview_token'],'reviewed':True,'reconciliation_reviewed':True,'entries':[{'index':r['index'],'description':r['description'],'type':'DESPESA','category_id':category['id'],'import_installment':bool(r.get('installment_info'))} for r in selected]}
    result=post('/imports/confirm',body)
    assert result['imported']==len(selected)
    assert db.query(InstallmentPlan).filter_by(card_id=card['id']).count()==20
    invoice=client.get(P+f"/cards/{card['id']}/invoices/2026/11",headers=auth_headers).json()
    assert Decimal(str(invoice['total_amount']))==sum(Decimal(r['amount']) for r in selected)
    assert len(invoice['items'])==len(selected)
    # Installments generate plans, not duplicate stand-alone purchases.
    assert db.query(Transaction).filter_by(card_id=card['id']).count()==len(selected)-len(parcels)
    assert post('/imports/confirm',body)['skipped']==len(selected)
