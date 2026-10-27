import json
from datetime import datetime,timezone
from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field,field_validator
from sqlalchemy.orm import Session
from app.api.deps import get_current_family,get_current_user,get_db
from app.models.import_draft import ImportDraft
from app.services.import_drafts import owned_draft,draft_token,metadata

router=APIRouter(prefix='/imports/drafts',tags=['Rascunhos de importação'])

class DraftEntry(BaseModel):
    model_config=ConfigDict(extra='forbid')
    index:int=Field(ge=0,le=499)
    description:str=Field(max_length=255)
    type:Literal['','RECEITA','DESPESA']=''
    category_id:UUID|None=None
    selected:bool=True
    classification:Literal["NECESSIDADE","DESEJO","INVESTIMENTO","OUTRO"]|None=None
    classification_explicit:bool=False
    remember:bool=False
    import_installment:bool=False
    import_subscription:bool=False
    subscription_frequency:Literal['MONTHLY','YEARLY','WEEKLY']='MONTHLY'

class DraftSave(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:int=Field(ge=1)
    entries:list[DraftEntry]=Field(max_length=500)
    bulk_category:UUID|None=None
    bulk_scope:Literal['installments','uncategorized','selected']='uncategorized'
    bulk_classification:Literal["","NECESSIDADE","DESEJO","INVESTIMENTO","OUTRO"]=""
    bulk_remember:bool=True
    group_open:dict[str,bool]=Field(default_factory=dict,max_length=501)

    @field_validator('group_open')
    @classmethod
    def valid_groups(cls,value):
        for key in value:
            if key:UUID(key)
        return value

@router.get('')
def listing(family=Depends(get_current_family),user=Depends(get_current_user),db:Session=Depends(get_db)):
    return [metadata(d) for d in db.query(ImportDraft).filter_by(user_id=user.id,family_id=family.id,completed_at=None).filter(ImportDraft.expires_at>datetime.now(timezone.utc)).order_by(ImportDraft.updated_at.desc()).all()]

@router.get('/{draft_id}')
def load(draft_id:UUID,family=Depends(get_current_family),user=Depends(get_current_user),db:Session=Depends(get_db)):
    draft=owned_draft(db,user.id,family.id,draft_id)
    import copy
    from app.api.v1.imports import dedupe_key
    from app.models.transaction import Transaction
    from app.models.import_rule import StatementImportLink
    from app.models.invoice import CardInvoice
    from app.models.card import CreditCard
    from app.api.v1.cards import get_current_invoice_period
    from datetime import date
    preview=copy.deepcopy(draft.preview_data)
    payload=draft.preview_payload
    keys=[dedupe_key(family.id,payload['account'],payload['card'],row['fingerprint']) for row in payload['rows']]
    existing={v for (v,) in db.query(Transaction.idempotency_key).filter(Transaction.idempotency_key.in_(keys)).all()}
    existing|={v for (v,) in db.query(StatementImportLink.key).filter(StatementImportLink.key.in_(keys)).all()}
    card=db.get(CreditCard,UUID(payload['card'])) if payload['card'] else None
    paid={(i.year,i.month) for i in db.query(CardInvoice).filter_by(card_id=card.id).filter((CardInvoice.paid_amount>0)|(CardInvoice.external_settled==True)).all()} if card else set()
    for row,key in zip(preview['rows'],keys):
        row['duplicate']=row['duplicate'] or key in existing
        period=(payload['statement']['year'],payload['statement']['month']) if payload.get('statement') else get_current_invoice_period(card,date.fromisoformat(row['date'])) if card else None
        if period in paid:
            row['blocked']=True;row['warning']='Esta fatura recebeu pagamento. Sua composição está protegida.'
    return {**preview,**metadata(draft),'draft_id':str(draft.id),'preview_token':draft_token(draft),'review_state':draft.review_state}

@router.put('/{draft_id}')
def save(draft_id:UUID,data:DraftSave,family=Depends(get_current_family),user=Depends(get_current_user),db:Session=Depends(get_db)):
    draft=owned_draft(db,user.id,family.id,draft_id,lock=True)
    if draft.revision!=data.revision:raise HTTPException(409,detail='Este rascunho foi alterado em outra aba. Reabra-o para conferir as duas versões.')
    indices=[entry.index for entry in data.entries]
    if len(indices)!=len(set(indices)) or any(i>=len(draft.preview_payload['rows']) for i in indices):
        raise HTTPException(400,detail='A revisão contém linhas inválidas ou repetidas.')
    state=data.model_dump(mode='json',exclude={'revision'})
    if len(json.dumps(state).encode())>600_000:raise HTTPException(413,detail='O rascunho excede o limite de revisão.')
    draft.review_state=state;draft.revision+=1;draft.updated_at=datetime.now(timezone.utc)
    db.commit()
    return {**metadata(draft),'preview_token':draft_token(draft)}

@router.delete('/{draft_id}')
def discard(draft_id:UUID,family=Depends(get_current_family),user=Depends(get_current_user),db:Session=Depends(get_db)):
    draft=owned_draft(db,user.id,family.id,draft_id,lock=True);db.delete(draft);db.commit()
    return {'removed':True}
