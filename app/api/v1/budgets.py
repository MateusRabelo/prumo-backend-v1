import calendar
from datetime import date
from decimal import Decimal
from typing import Any, List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_user, get_current_family, get_admin_family
from app.domain.financial_engine import FinancialEngine
from app.models.user import User
from app.models.family import FamilySpace
from app.models.budget import BudgetRule503020, CustomBudget
from app.models.transaction import Transaction
from app.models.category import Category
from app.services.validation import validate_relations
from app.schemas.budget import (
    Budget503020Create,
    Budget503020Response,
    CustomBudgetCreate,
    CustomBudgetUpdate,
    CustomBudgetResponse,
)

router = APIRouter(prefix="/budgets", tags=["Orçamentos"])


@router.get("/503020", response_model=Budget503020Response)
def get_503020_budget(
    year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100),
    month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    budget = db.query(BudgetRule503020).filter(
        BudgetRule503020.family_id == current_family.id,
        BudgetRule503020.year == year,
        BudgetRule503020.month == month
    ).first()

    if not budget:
        # Default with 0 estimated income
        budget = BudgetRule503020(
            family_id=current_family.id,
            year=year,
            month=month,
            estimated_income=Decimal("0.00"),
            needs_percentage=Decimal("50.00"),
            wants_percentage=Decimal("30.00"),
            savings_percentage=Decimal("20.00")
        )
        from uuid import uuid4
        from datetime import datetime, timezone
        budget.id = uuid4()
        budget.created_at = budget.updated_at = datetime.now(timezone.utc)

    breakdown = FinancialEngine.calculate_503020_breakdown(
        estimated_income=budget.estimated_income,
        needs_pct=budget.needs_percentage,
        wants_pct=budget.wants_percentage,
        savings_pct=budget.savings_percentage
    )

    # Compute actual realized spending for the month
    _, last_day = calendar.monthrange(year, month)
    start_date = date(year, month, 1)
    end_date = date(year, month, last_day)

    needs_spent = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.family_id == current_family.id,
        Transaction.date >= start_date,
        Transaction.date <= end_date,
        Transaction.type == "DESPESA",
        Transaction.classification == "NECESSIDADE",
        Transaction.status == "REALIZADA",
        Transaction.is_deleted == False,
        Transaction.is_invoice_payment == False
    ).scalar()

    wants_spent = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.family_id == current_family.id,
        Transaction.date >= start_date,
        Transaction.date <= end_date,
        Transaction.type == "DESPESA",
        Transaction.classification == "DESEJO",
        Transaction.status == "REALIZADA",
        Transaction.is_deleted == False,
        Transaction.is_invoice_payment == False
    ).scalar()

    savings_spent = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.family_id == current_family.id,
        Transaction.date >= start_date,
        Transaction.date <= end_date,
        Transaction.type == "DESPESA",
        Transaction.classification == "INVESTIMENTO",
        Transaction.status == "REALIZADA",
        Transaction.is_deleted == False,
        Transaction.is_invoice_payment == False
    ).scalar()

    return Budget503020Response(
        id=budget.id,
        family_id=budget.family_id,
        year=budget.year,
        month=budget.month,
        estimated_income=budget.estimated_income,
        needs_percentage=budget.needs_percentage,
        wants_percentage=budget.wants_percentage,
        savings_percentage=budget.savings_percentage,
        needs_allocated=breakdown["needs_allocated"],
        wants_allocated=breakdown["wants_allocated"],
        savings_allocated=breakdown["savings_allocated"],
        needs_spent=Decimal(str(needs_spent)).quantize(Decimal("0.01")),
        wants_spent=Decimal(str(wants_spent)).quantize(Decimal("0.01")),
        savings_spent=Decimal(str(savings_spent)).quantize(Decimal("0.01")),
        created_at=budget.created_at,
        updated_at=budget.updated_at
    )


@router.post("/503020", response_model=Budget503020Response)
def save_503020_budget(
    data: Budget503020Create,
    current_family: FamilySpace = Depends(get_admin_family),
    db: Session = Depends(get_db)
) -> Any:
    # Validate percentages sum to 100
    total_pct = data.needs_percentage + data.wants_percentage + data.savings_percentage
    if total_pct != Decimal("100.00"):
        raise HTTPException(
            status_code=400,
            detail=f"A soma dos percentuais deve ser exatamente 100% (atualmente {total_pct}%)"
        )

    budget = db.query(BudgetRule503020).filter(
        BudgetRule503020.family_id == current_family.id,
        BudgetRule503020.year == data.year,
        BudgetRule503020.month == data.month
    ).first()

    if not budget:
        budget = BudgetRule503020(
            family_id=current_family.id,
            year=data.year,
            month=data.month,
            estimated_income=data.estimated_income,
            needs_percentage=data.needs_percentage,
            wants_percentage=data.wants_percentage,
            savings_percentage=data.savings_percentage
        )
        db.add(budget)
    else:
        budget.estimated_income = data.estimated_income
        budget.needs_percentage = data.needs_percentage
        budget.wants_percentage = data.wants_percentage
        budget.savings_percentage = data.savings_percentage

    db.commit()
    db.refresh(budget)

    return get_503020_budget(year=data.year, month=data.month, current_family=current_family, db=db)


@router.get("/custom", response_model=List[CustomBudgetResponse])
def get_custom_budgets(
    year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100),
    month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    budgets = db.query(CustomBudget).filter(
        CustomBudget.family_id == current_family.id,
        CustomBudget.year == year,
        CustomBudget.month == month
    ).all()

    _, last_day = calendar.monthrange(year, month)
    start_date = date(year, month, 1)
    end_date = date(year, month, last_day)

    result = []
    for b in budgets:
        # Calculate actual spent for this budget scope
        q = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.family_id == current_family.id,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            Transaction.type == "DESPESA",
            Transaction.status == "REALIZADA",
            Transaction.is_deleted == False,
        Transaction.is_invoice_payment == False
        )
        if b.category_id:
            q = q.filter(Transaction.category_id == b.category_id)
        if b.responsible_name:
            q = q.filter(Transaction.responsible_name == b.responsible_name)
        if b.classification:
            q = q.filter(Transaction.classification == b.classification)

        spent = Decimal(str(q.scalar())).quantize(Decimal("0.01"))
        stats = FinancialEngine.calculate_budget_usage(
            limit_amount=b.limit_amount,
            realized_spent=spent,
            alert_threshold=b.alert_threshold_percentage
        )

        resp = CustomBudgetResponse(
            id=b.id,
            family_id=b.family_id,
            year=b.year,
            month=b.month,
            category_id=b.category_id,
            category_name=b.category.name if b.category else None,
            responsible_name=b.responsible_name,
            classification=b.classification,
            limit_amount=b.limit_amount,
            alert_threshold_percentage=b.alert_threshold_percentage,
            realized_spent=stats["realized_spent"],
            remaining_amount=stats["remaining_amount"],
            consumed_percentage=stats["consumed_percentage"],
            is_warning=stats["is_warning"],
            is_exceeded=stats["is_exceeded"],
            exceeded_amount=stats["exceeded_amount"],
            created_at=b.created_at,
            updated_at=b.updated_at
        )
        result.append(resp)

    return result


@router.post("/custom", response_model=CustomBudgetResponse, status_code=status.HTTP_201_CREATED)
def create_custom_budget(
    data: CustomBudgetCreate,
    current_family: FamilySpace = Depends(get_admin_family),
    db: Session = Depends(get_db)
) -> Any:
    validate_relations(db, current_family.id, data.model_dump())
    budget = CustomBudget(
        family_id=current_family.id,
        year=data.year,
        month=data.month,
        category_id=data.category_id,
        responsible_name=data.responsible_name,
        classification=data.classification,
        limit_amount=data.limit_amount,
        alert_threshold_percentage=data.alert_threshold_percentage
    )
    db.add(budget)
    db.commit()
    db.refresh(budget)

    # Return with computed stats
    all_budgets = get_custom_budgets(year=data.year, month=data.month, current_family=current_family, db=db)
    for b in all_budgets:
        if b.id == budget.id:
            return b
    return budget


@router.put("/custom/{budget_id}", response_model=CustomBudgetResponse)
def update_custom_budget(
    budget_id: UUID,
    data: CustomBudgetUpdate,
    current_family: FamilySpace = Depends(get_admin_family),
    db: Session = Depends(get_db)
) -> Any:
    budget = db.query(CustomBudget).filter(
        CustomBudget.id == budget_id,
        CustomBudget.family_id == current_family.id
    ).first()
    if not budget:
        raise HTTPException(status_code=404, detail="Orçamento não encontrado")

    update_dict = data.model_dump(exclude_unset=True)
    for key, val in update_dict.items():
        setattr(budget, key, val)

    db.commit()
    db.refresh(budget)

    all_budgets = get_custom_budgets(year=budget.year, month=budget.month, current_family=current_family, db=db)
    for b in all_budgets:
        if b.id == budget.id:
            return b
    return budget


@router.delete("/custom/{budget_id}", status_code=status.HTTP_200_OK)
def delete_custom_budget(
    budget_id: UUID,
    current_family: FamilySpace = Depends(get_admin_family),
    db: Session = Depends(get_db)
) -> Any:
    budget = db.query(CustomBudget).filter(
        CustomBudget.id == budget_id,
        CustomBudget.family_id == current_family.id
    ).first()
    if not budget:
        raise HTTPException(status_code=404, detail="Orçamento não encontrado")

    db.delete(budget)
    db.commit()
    return {"message": "Orçamento excluído com sucesso"}
