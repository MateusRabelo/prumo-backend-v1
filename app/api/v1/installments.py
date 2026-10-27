from datetime import date
from decimal import Decimal
from typing import Any, List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_user, get_current_family, get_admin_family
from app.domain.financial_engine import FinancialEngine
from app.domain.recurrence_engine import RecurrenceEngine
from app.models.user import User
from app.models.family import FamilySpace
from app.models.installment import InstallmentPlan, Installment
from app.models.transaction import Transaction
from app.models.category import Category
from app.models.account import FinancialAccount
from app.models.payment_method import PaymentMethod
from app.schemas.installment import (
    InstallmentPlanCreate,
    InstallmentPlanResponse,
    InstallmentResponse,
    InstallmentPayRequest,
    InstallmentCalendarItem,
    InstallmentCalendarMonth,
)
from app.services.audit_service import AuditService
from app.services.validation import validate_card_periods, validate_relations

router = APIRouter(prefix="/installments", tags=["Parcelamentos"])


def plan_to_schema(plan: InstallmentPlan) -> InstallmentPlanResponse:
    paid = sum((Decimal(str(i.amount)) for i in plan.installments if i.status == "PAGA"), Decimal("0.00"))
    remaining = Decimal(str(plan.total_amount)) - paid
    
    installments_resps = [
        InstallmentResponse(
            id=i.id,
            installment_plan_id=i.installment_plan_id,
            installment_number=i.installment_number,
            amount=i.amount,
            due_date=i.due_date,
            status=i.status,
            payment_date=i.payment_date,
            transaction_id=i.transaction_id,
            created_at=i.created_at,
            updated_at=i.updated_at
        )
        for i in plan.installments
    ]

    return InstallmentPlanResponse(
        imported_from_number=plan.imported_from_number,
        id=plan.id,
        family_id=plan.family_id,
        description=plan.description,
        category_id=plan.category_id,
        category_name=plan.category.name if plan.category else None,
        account_id=plan.account_id,
        account_name=plan.account.name if plan.account else None,
        card_id=plan.card_id,
        card_name=plan.card.name if plan.card else None,
        payment_method_id=plan.payment_method_id,
        payment_method_name=plan.payment_method.name if plan.payment_method else None,
        responsible_name=plan.responsible_name,
        is_shared=plan.is_shared,
        total_amount=plan.total_amount,
        installments_count=plan.installments_count,
        purchase_date=plan.purchase_date,
        first_due_date=plan.first_due_date,
        notes=plan.notes,
        status=plan.status,
        paid_amount=paid.quantize(Decimal("0.01")),
        remaining_amount=remaining.quantize(Decimal("0.01")),
        installments=installments_resps,
        created_at=plan.created_at,
        updated_at=plan.updated_at
    )


@router.get("/", response_model=List[InstallmentPlanResponse])
def list_plans(
    status_filter: Optional[str] = Query(None, alias="status"),
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    query = db.query(InstallmentPlan).filter(InstallmentPlan.family_id == current_family.id)
    if status_filter:
        query = query.filter(InstallmentPlan.status == status_filter)
    plans = query.order_by(InstallmentPlan.created_at.desc()).all()
    return [plan_to_schema(p) for p in plans]


@router.post("/", response_model=InstallmentPlanResponse, status_code=status.HTTP_201_CREATED)
def create_installment_plan(
    data: InstallmentPlanCreate,
    current_user: User = Depends(get_current_user),
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    from app.services.card_flow import resolve_card_flow
    from app.api.v1.cards import get_current_invoice_period, get_invoice_cycle_dates
    values = data.model_dump()
    card = resolve_card_flow(db, current_family.id, {**values, 'payment_mode': 'CREDIT'}) if data.card_id else None
    if card:
        values['account_id'] = card.account_id
        if not values.get('first_due_date'):
            year, month = get_current_invoice_period(card, data.purchase_date)
            values['first_due_date'] = get_invoice_cycle_dates(card, year, month)[2]
    elif not values.get('first_due_date'):
        values['first_due_date'] = data.purchase_date
    data = data.model_copy(update=values)
    validate_relations(db, current_family.id, values)
    validate_card_periods(db, current_family.id, data.model_dump())
    # Validate category
    category = db.query(Category).filter(
        Category.id == data.category_id,
        Category.family_id == current_family.id
    ).first()
    if not category:
        raise HTTPException(status_code=400, detail="Categoria inválida")

    # 1. Create Plan
    plan = InstallmentPlan(
        family_id=current_family.id,
        created_by_id=current_user.id,
        description=data.description,
        category_id=data.category_id,
        account_id=data.account_id,
        card_id=data.card_id,
        payment_method_id=data.payment_method_id,
        responsible_name=data.responsible_name,
        is_shared=data.is_shared,
        total_amount=data.total_amount,
        installments_count=data.installments_count,
        purchase_date=data.purchase_date,
        first_due_date=data.first_due_date,
        notes=data.notes,
        status="ACTIVE"
    )
    db.add(plan)
    db.flush()

    # 2. Compute exact cent distribution and monthly due dates
    amounts = FinancialEngine.calculate_cents_distribution(data.total_amount, data.installments_count)
    due_dates = RecurrenceEngine.generate_due_dates(
        start_date=data.first_due_date,
        frequency="MONTHLY",
        installments_or_periods=data.installments_count,
        day_of_month=data.first_due_date.day
    )

    # 3. Create all individual installments
    for idx, (amt, due) in enumerate(zip(amounts, due_dates), start=1):
        installment = Installment(
            installment_plan_id=plan.id,
            installment_number=idx,
            amount=amt,
            due_date=due,
            status="PENDENTE"
        )
        db.add(installment)

    AuditService.log(
        db=db,
        family_id=current_family.id,
        user_id=current_user.id,
        action="CREATE",
        entity_type="INSTALLMENT_PLAN",
        entity_id=str(plan.id),
        new_values={
            "description": plan.description,
            "total_amount": str(plan.total_amount),
            "installments_count": plan.installments_count
        }
    )

    db.commit()
    db.refresh(plan)
    return plan_to_schema(plan)


@router.get("/{plan_id}", response_model=InstallmentPlanResponse)
def get_installment_plan(
    plan_id: UUID,
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    plan = db.query(InstallmentPlan).filter(
        InstallmentPlan.id == plan_id,
        InstallmentPlan.family_id == current_family.id
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Parcelamento não encontrado")
    return plan_to_schema(plan)


@router.post("/installments/{installment_id}/pay", response_model=InstallmentResponse)
def pay_installment(
    installment_id: UUID,
    data: InstallmentPayRequest,
    current_user: User = Depends(get_current_user),
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    locked_plan = db.query(InstallmentPlan).join(Installment).filter(
        Installment.id == installment_id, InstallmentPlan.family_id == current_family.id
    ).with_for_update(of=InstallmentPlan).first()
    if not locked_plan:
        raise HTTPException(404, detail="Parcela não encontrada")
    installment = db.query(Installment).join(InstallmentPlan).filter(
        Installment.id == installment_id,
        InstallmentPlan.family_id == current_family.id
    ).with_for_update(of=Installment).first()
    if not installment:
        raise HTTPException(status_code=404, detail="Parcela não encontrada")

    if installment.status != "PENDENTE" or installment.plan.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Somente parcelas pendentes de planos ativos podem ser pagas")
    if installment.plan.card_id:
        raise HTTPException(409, detail="Parcela de cartão deve ser paga pela fatura")

    plan = installment.plan
    pay_account_id = data.account_id or plan.account_id
    if not pay_account_id:
        # Fallback to family's first account
        first_acc = db.query(FinancialAccount).filter(
            FinancialAccount.family_id == current_family.id,
            FinancialAccount.is_active == True
        ).first()
        if not first_acc:
            raise HTTPException(status_code=400, detail="Nenhuma conta financeira disponível para registrar o pagamento")
        pay_account_id = first_acc.id

    validate_relations(db, current_family.id, {"account_id": pay_account_id})
    # Create Realized Expense Transaction for this installment
    desc = f"{plan.description} ({installment.installment_number}/{plan.installments_count})"
    transaction = Transaction(
        family_id=current_family.id,
        created_by_id=current_user.id,
        date=data.payment_date,
        description=desc,
        type="DESPESA",
        amount=installment.amount,
        category_id=plan.category_id,
        account_id=pay_account_id,
        card_id=plan.card_id,
        responsible_name=plan.responsible_name,
        is_shared=plan.is_shared,
        classification="NECESSIDADE",
        payment_method_id=plan.payment_method_id,
        status="REALIZADA",
        notes=f"Pagamento da parcela {installment.installment_number}/{plan.installments_count}",
        installment_id=installment.id,
        is_deleted=False
    )
    db.add(transaction)
    db.flush()

    # Link installment
    installment.status = "PAGA"
    installment.payment_date = data.payment_date
    installment.transaction_id = transaction.id

    # Check if all installments in plan are now paid
    remaining_pending = db.query(Installment).filter(
        Installment.installment_plan_id == plan.id,
        Installment.id != installment.id,
        Installment.status == "PENDENTE"
    ).count()

    if remaining_pending == 0:
        plan.status = "COMPLETED"

    AuditService.log(
        db=db,
        family_id=current_family.id,
        user_id=current_user.id,
        action="PAY_INSTALLMENT",
        entity_type="INSTALLMENT",
        entity_id=str(installment.id),
        new_values={
            "plan": plan.description,
            "installment": f"{installment.installment_number}/{plan.installments_count}",
            "amount": str(installment.amount),
            "transaction_id": str(transaction.id)
        }
    )

    db.commit()
    db.refresh(installment)
    return InstallmentResponse(
        id=installment.id,
        installment_plan_id=installment.installment_plan_id,
        installment_number=installment.installment_number,
        amount=installment.amount,
        due_date=installment.due_date,
        status=installment.status,
        payment_date=installment.payment_date,
        transaction_id=installment.transaction_id,
        created_at=installment.created_at,
        updated_at=installment.updated_at
    )


@router.post("/{plan_id}/cancel", status_code=status.HTTP_200_OK)
def cancel_installment_plan(
    plan_id: UUID,
    current_user: User = Depends(get_current_user),
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    plan = db.query(InstallmentPlan).filter(
        InstallmentPlan.id == plan_id,
        InstallmentPlan.family_id == current_family.id
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Parcelamento não encontrado")

    if plan.card_id:
        validate_card_periods(db, current_family.id, {
            "card_id": plan.card_id, "first_due_date": plan.first_due_date,
            "installments_count": plan.installments_count})
    db.query(InstallmentPlan).filter_by(id=plan.id).with_for_update().one()
    # Serialize cancellation with standalone installment payments.
    pending = db.query(Installment).filter_by(installment_plan_id=plan.id).order_by(Installment.id).with_for_update().all()
    db.refresh(plan)
    # Cancel only pending installments
    db.query(Installment).filter(
        Installment.installment_plan_id == plan.id,
        Installment.status == "PENDENTE"
    ).update({"status": "CANCELADA"})

    plan.status = "CANCELLED"

    AuditService.log(
        db=db,
        family_id=current_family.id,
        user_id=current_user.id,
        action="CANCEL",
        entity_type="INSTALLMENT_PLAN",
        entity_id=str(plan.id)
    )

    db.commit()
    return {"message": "Parcelamento cancelado com sucesso. Parcelas já pagas foram preservadas."}


@router.get("/calendar/overview", response_model=List[InstallmentCalendarMonth])
def get_installment_calendar(
    months_ahead: int = Query(6, ge=1, le=24),
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    today = date.today()
    start_date = date(today.year, today.month, 1)
    
    # Calculate end date
    end_month_offset = today.month + months_ahead
    end_year = today.year + (end_month_offset - 1) // 12
    end_month = ((end_month_offset - 1) % 12) + 1
    
    installments = db.query(Installment).join(InstallmentPlan).filter(
        InstallmentPlan.family_id == current_family.id,
        Installment.due_date >= start_date,
        Installment.status != "CANCELADA"
    ).order_by(Installment.due_date.asc()).all()

    # Group by (year, month)
    monthly_data: dict[tuple[int, int], list[InstallmentCalendarItem]] = {}
    for i in range(months_ahead):
        m_offset = today.month + i
        y = today.year + (m_offset - 1) // 12
        m = ((m_offset - 1) % 12) + 1
        monthly_data[(y, m)] = []

    for inst in installments:
        key = (inst.due_date.year, inst.due_date.month)
        if key in monthly_data:
            item = InstallmentCalendarItem(
                installment_id=inst.id,
                plan_id=inst.installment_plan_id,
                description=inst.plan.description,
                category_name=inst.plan.category.name if inst.plan.category else None,
                responsible_name=inst.plan.responsible_name,
                installment_number=inst.installment_number,
                installments_count=inst.plan.installments_count,
                amount=inst.amount,
                due_date=inst.due_date,
                status=inst.status
            )
            monthly_data[key].append(item)

    result = []
    for (y, m), items in sorted(monthly_data.items()):
        total_due = sum((Decimal(str(item.amount)) for item in items), Decimal("0.00"))
        total_paid = sum((Decimal(str(item.amount)) for item in items if item.status == "PAGA"), Decimal("0.00"))
        total_pending = sum((Decimal(str(item.amount)) for item in items if item.status == "PENDENTE"), Decimal("0.00"))
        
        result.append(InstallmentCalendarMonth(
            year=y,
            month=m,
            total_due=total_due,
            total_paid=total_paid,
            total_pending=total_pending,
            items=items
        ))

    return result


@router.post('/installments/{installment_id}/reverse', response_model=InstallmentResponse)
def reverse_installment_payment(installment_id: UUID,
                                current_family: FamilySpace = Depends(get_admin_family),
                                current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = db.query(InstallmentPlan).join(Installment).filter(Installment.id == installment_id,
        InstallmentPlan.family_id == current_family.id).with_for_update(of=InstallmentPlan).first()
    if not plan:
        raise HTTPException(404, detail='Parcela não encontrada')
    parcel = db.query(Installment).join(InstallmentPlan).filter(Installment.id == installment_id,
        InstallmentPlan.family_id == current_family.id).with_for_update(of=Installment).first()
    if not parcel:
        raise HTTPException(404, detail='Parcela não encontrada')
    if parcel.plan.card_id:
        raise HTTPException(409, detail='Pagamento de cartão deve ser estornado na fatura')
    if parcel.status != 'PAGA' or not parcel.transaction_id:
        raise HTTPException(409, detail='Parcela não possui pagamento para estornar')
    tx = db.query(Transaction).filter_by(id=parcel.transaction_id, family_id=current_family.id).one()
    tx.is_deleted = True
    parcel.status = 'CANCELADA' if parcel.plan.status == 'CANCELLED' else 'PENDENTE'
    parcel.payment_date = None
    parcel.transaction_id = None
    if parcel.plan.status == 'COMPLETED':
        parcel.plan.status = 'ACTIVE'
    AuditService.log(db, current_family.id, current_user.id, 'REVERSE_PAYMENT', 'INSTALLMENT', str(parcel.id),
                     new_values={'transaction_id': str(tx.id), 'amount': str(tx.amount)})
    db.commit()
    db.refresh(parcel)
    return parcel
