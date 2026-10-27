"""Budget commitments: credit purchases and monthly parcels, never invoice settlement twice."""
import calendar
from datetime import date
from decimal import Decimal
from sqlalchemy import and_,or_
from app.models.transaction import Transaction
from app.models.installment import Installment,InstallmentPlan


def expenses_for_month(db,family_id,year,month):
    start=date(year,month,1);end=date(year,month,calendar.monthrange(year,month)[1])
    direct=db.query(Transaction).filter(Transaction.family_id==family_id,Transaction.date.between(start,end),
        Transaction.type=='DESPESA',Transaction.is_deleted==False,Transaction.is_invoice_payment==False,Transaction.installment_id.is_(None),
        or_(and_(Transaction.payment_mode=='CREDIT',Transaction.status.in_(['REALIZADA','PENDENTE','VENCIDA'])),
            and_(Transaction.payment_mode!='CREDIT',Transaction.status=='REALIZADA'))).all()
    result=[{'amount':Decimal(t.amount),'category_id':t.category_id,'classification':t.classification,'responsible_name':t.responsible_name} for t in direct]
    parcels=db.query(Installment).join(InstallmentPlan).filter(InstallmentPlan.family_id==family_id,
        Installment.due_date.between(start,end),Installment.status.in_(['PENDENTE','PAGA'])).all()
    for i in parcels:
        result.append({'amount':Decimal(i.amount),'category_id':i.plan.category_id,
            'classification':i.plan.classification or i.plan.category.classification,'responsible_name':i.plan.responsible_name})
    return result
