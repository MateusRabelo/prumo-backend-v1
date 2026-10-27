import hashlib
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException
from pydantic import Field
from sqlalchemy.orm import Session
from app.schemas.base import BaseModel
from app.api.deps import get_db,get_current_family,get_current_user
from app.models.recurrence import RecurrenceRule
from app.models.family import FamilyMembership,FamilySpace
from app.models.transaction import Transaction
from app.models.category import Category
from app.services.card_flow import resolve_card_flow,ensure_invoice
from app.services.validation import validate_relations,validate_card_periods
from app.services.subscriptions import merchant,next_date
from app.services.audit_service import AuditService

router=APIRouter(prefix='/subscriptions',tags=['Assinaturas'])

class SubscriptionInput(BaseModel):
    description:str=Field(min_length=1,max_length=255)
    amount:Decimal=Field(gt=0,max_digits=12,decimal_places=2)
    account_id:UUID
    card_id:UUID|None=None
    category_id:UUID
    frequency:Literal['MONTHLY','YEARLY','WEEKLY']='MONTHLY'
    next_due_date:date
    is_active:bool=True

class ChargeInput(BaseModel):
    expected_date:date
    date:date


def serialize(rule):
    return {k:getattr(rule,k) for k in ['id','description','amount','account_id','card_id','category_id','frequency','next_due_date','is_active','last_generated_date']}|{'card_name':rule.card.name if rule.card else None,'account_name':rule.account.name,'category_name':rule.category.name}

@router.get('')
def listing(family=Depends(get_current_family),db:Session=Depends(get_db)):
    return [serialize(r) for r in db.query(RecurrenceRule).filter_by(family_id=family.id,is_subscription=True).order_by(RecurrenceRule.is_active.desc(),RecurrenceRule.next_due_date).all()]

@router.post('',status_code=201)
def create(data:SubscriptionInput,family=Depends(get_current_family),user=Depends(get_current_user),db:Session=Depends(get_db)):
    return save(None,data,family,user,db)

@router.put('/{rule_id}')
def update(rule_id:UUID,data:SubscriptionInput,family=Depends(get_current_family),user=Depends(get_current_user),db:Session=Depends(get_db)):
    return save(rule_id,data,family,user,db)

def save(rule_id,data,family,user,db):
    db.query(FamilySpace).filter_by(id=family.id).with_for_update().one()
    rule=db.query(RecurrenceRule).filter_by(id=rule_id,family_id=family.id,is_subscription=True).first() if rule_id else None
    if rule_id and not rule:raise HTTPException(404,detail='Assinatura não encontrada')
    values=data.model_dump();card=resolve_card_flow(db,family.id,{**values,'payment_mode':'CREDIT'}) if data.card_id else None
    if card:values['account_id']=card.account_id
    validate_relations(db,family.id,values)
    from app.models.account import FinancialAccount
    if db.get(FinancialAccount,values['account_id']).account_type not in ('CHECKING','SAVINGS','WALLET'):
        raise HTTPException(400,detail='Selecione uma conta corrente, poupança ou carteira')
    category=db.get(Category,data.category_id)
    if category.type not in ('DESPESA','AMBOS'):raise HTTPException(400,detail='Selecione uma categoria de despesa')
    if not 2000<=data.next_due_date.year<=2100:raise HTTPException(400,detail='Data de cobrança inválida')
    duplicate=db.query(RecurrenceRule).filter_by(family_id=family.id,is_subscription=True,is_active=True,card_id=data.card_id,merchant_key=merchant(data.description)).first()
    if data.is_active and duplicate and duplicate.id!=rule_id:raise HTTPException(409,detail='Esta assinatura já está ativa neste cartão ou conta')
    if not rule:
        alias=db.query(FamilyMembership).filter_by(family_id=family.id,user_id=user.id).one().alias_name
        rule=RecurrenceRule(family_id=family.id,created_by_id=user.id,is_subscription=True,type='DESPESA',responsible_name=alias,start_date=data.next_due_date)
        db.add(rule)
    for k,v in values.items():setattr(rule,k,v)
    rule.merchant_key=merchant(data.description);rule.day_of_month=data.next_due_date.day;rule.classification=category.classification
    db.flush();AuditService.log(db,family.id,user.id,'SAVE_SUBSCRIPTION','RECURRENCE',str(rule.id))
    db.commit();return serialize(rule)

@router.post('/{rule_id}/charge')
def charge(rule_id:UUID,data:ChargeInput,family=Depends(get_current_family),user=Depends(get_current_user),db:Session=Depends(get_db)):
    rule=db.query(RecurrenceRule).filter_by(id=rule_id,family_id=family.id,is_subscription=True).first()
    if not rule:raise HTTPException(404,detail='Assinatura não encontrada')
    values={'card_id':rule.card_id,'account_id':None if rule.card_id else rule.account_id,'payment_mode':'CREDIT' if rule.card_id else 'ACCOUNT'}
    card=resolve_card_flow(db,family.id,values)
    db.refresh(rule,with_for_update=True)
    if rule.card_id != values['card_id'] or (not card and rule.account_id != values['account_id']):raise HTTPException(409,detail='Assinatura alterada simultaneamente. Atualize a lista.')
    if not rule.is_active or rule.next_due_date!=data.expected_date:raise HTTPException(409,detail='Assinatura alterada ou cobrança já registrada. Atualize a lista.')
    if data.expected_date>date.today():raise HTTPException(400,detail='A próxima cobrança ainda está no futuro. Ajuste o cadastro se o ciclo mudou.')
    if data.date>date.today():raise HTTPException(400,detail='Confirme apenas cobranças já realizadas')
    validate_relations(db,family.id,{'account_id':values['account_id'],'category_id':rule.category_id})
    if card:validate_card_periods(db,family.id,{**values,'date':data.date})
    rule.account_id=values['account_id']
    invoice=ensure_invoice(db,family.id,card,data.date) if card else None
    tx=Transaction(family_id=family.id,created_by_id=user.id,date=data.date,description=rule.description,type='DESPESA',amount=rule.amount,
        account_id=values['account_id'],card_id=rule.card_id,payment_mode=values['payment_mode'],invoice_id=invoice.id if invoice else None,
        category_id=rule.category_id,responsible_name=rule.responsible_name,is_shared=rule.is_shared,classification=rule.classification,status='REALIZADA',recurrence_id=rule.id,
        idempotency_key=hashlib.sha256(f'subscription:{rule.id}:{data.expected_date}'.encode()).hexdigest())
    db.add(tx);rule.last_generated_date=data.date;rule.next_due_date=next_date(data.expected_date,rule.frequency,rule.day_of_month)
    AuditService.log(db,family.id,user.id,'CHARGE_SUBSCRIPTION','RECURRENCE',str(rule.id),new_values={'date':str(data.date),'amount':str(rule.amount)})
    db.commit();return serialize(rule)
