import calendar
import re
from datetime import date,timedelta
from decimal import Decimal
from fastapi import HTTPException
from app.models.recurrence import RecurrenceRule
from app.models.transaction import Transaction
from app.services.statement_parser import normalize

VENDORS={
    'netflix':r'netflix', 'spotify':r'spotify', 'disney plus':r'disney(?:\s*plus|\+)',
    'amazon prime':r'amazon\s*prime|prime\s*video', 'youtube premium':r'youtube\s*premium',
    'google one':r'google\s*one', 'icloud':r'icloud', 'microsoft 365':r'microsoft\s*365',
    'adobe':r'adobe', 'chatgpt':r'chatgpt|openai', 'max streaming':r'hbo\s*max',
}

def merchant(description):
    text=normalize(description)
    return next((key for key,pattern in VENDORS.items() if re.search(pattern,text)),text)


def next_date(observed,frequency,preferred_day=None):
    if frequency=='WEEKLY':return observed+timedelta(days=7)
    y,m=(observed.year+1,observed.month) if frequency=='YEARLY' else (observed.year+(observed.month==12),observed.month%12+1)
    if y>2100:raise HTTPException(400,detail='A próxima cobrança excede o ano 2100')
    return date(y,m,min(preferred_day or observed.day,calendar.monthrange(y,m)[1]))


def match_rule(db,family_id,card_id,description):
    rules=db.query(RecurrenceRule).filter_by(family_id=family_id,card_id=card_id,is_subscription=True,is_active=True,merchant_key=merchant(description)).all()
    if len(rules)>1:raise HTTPException(409,detail='Mais de uma assinatura corresponde a esta cobrança. Revise os cadastros.')
    return rules[0] if rules else None


def detect(db,family_id,card_id,row,description):
    if not card_id or row.get('blocked') or row.get('installment_info'):return None
    rule=match_rule(db,family_id,card_id,row['original_description'])
    if rule:
        observed=date.fromisoformat(row['date'])
        previous=db.query(Transaction.id).filter(Transaction.recurrence_id==rule.id,Transaction.is_deleted==False,
            Transaction.date.between(observed-timedelta(days=3),observed+timedelta(days=3)),Transaction.amount==Decimal(row['amount'])).first()
        return {'matching_id':str(rule.id),'category_id':str(rule.category_id),'frequency':rule.frequency,'already_recorded':bool(previous),'reason':'Assinatura já acompanhada neste cartão'}
    key=merchant(row['original_description'])
    if key in VENDORS:return {'matching_id':None,'frequency':'MONTHLY','reason':'Serviço possivelmente recorrente; confirme a frequência'}
    day=date.fromisoformat(row['date'])
    history=db.query(Transaction).filter(Transaction.family_id==family_id,Transaction.card_id==card_id,
        Transaction.is_deleted==False,Transaction.is_invoice_payment==False,Transaction.date.between(day-timedelta(days=35),day-timedelta(days=25)),Transaction.amount==Decimal(row['amount'])).all()
    if any(merchant(t.description) in (key,merchant(description)) for t in history):
        return {'matching_id':None,'frequency':'MONTHLY','reason':'Mesmo estabelecimento e valor em um ciclo mensal anterior; confirme se é assinatura'}
    return None


def observe(db,family,user,card,row,entry,category,actor):
    if not category:raise HTTPException(400,detail='Escolha uma categoria para acompanhar a assinatura')
    rule=match_rule(db,family.id,card.id,row['original_description'])
    observed=date.fromisoformat(row['date'])
    if rule:
        previous=db.query(Transaction).filter(Transaction.recurrence_id==rule.id,Transaction.is_deleted==False,
            Transaction.date.between(observed-timedelta(days=3),observed+timedelta(days=3)),Transaction.amount==Decimal(row['amount'])).first()
        if previous:return rule,previous
    else:
        rule=RecurrenceRule(family_id=family.id,created_by_id=user.id,is_subscription=True,card_id=card.id,
            merchant_key=merchant(row['original_description']),type='DESPESA',start_date=observed,day_of_month=observed.day,
            responsible_name=card.responsible_name or actor,is_shared=card.responsible_name=='Conjunto',classification=category.classification)
        db.add(rule)
    if not rule.last_generated_date or observed>=rule.last_generated_date:
        rule.description=entry.description;rule.amount=Decimal(row['amount']);rule.category_id=category.id
        rule.account_id=card.account_id;rule.frequency=entry.subscription_frequency
        rule.last_generated_date=observed;rule.next_due_date=next_date(observed,rule.frequency,rule.day_of_month)
    db.flush()
    return rule,None
