from decimal import Decimal
from typing import Any, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_user, get_current_family, get_admin_family
from app.domain.financial_engine import FinancialEngine
from app.models.user import User
from app.models.family import FamilySpace
from app.models.goal import FinancialGoal, GoalContribution
from app.models.transaction import Transaction
from app.models.account import FinancialAccount
from app.models.category import Category
from app.schemas.goal import (
    FinancialGoalCreate,
    FinancialGoalUpdate,
    FinancialGoalResponse,
    GoalContributionCreate,
    GoalContributionResponse,
)
from app.services.audit_service import AuditService

router = APIRouter(prefix="/goals", tags=["Metas Financeiras"])


def compute_goal_stats(goal: FinancialGoal) -> dict:
    accumulated = Decimal("0.00")
    for c in goal.contributions:
        if c.is_reversed:
            continue
        amt = Decimal(str(c.amount))
        if c.type in ("CONTRIBUICAO", "AJUSTE"):
            accumulated += amt
        elif c.type == "RETIRADA":
            accumulated -= amt

    stats = FinancialEngine.calculate_goal_progress(
        target_amount=goal.target_amount,
        accumulated_amount=accumulated
    )
    return stats


def goal_to_schema(goal: FinancialGoal) -> FinancialGoalResponse:
    stats = compute_goal_stats(goal)
    contributions_resp = [
        GoalContributionResponse(
            id=c.id,
            is_reversed=c.is_reversed,
            goal_id=c.goal_id,
            created_by_id=c.created_by_id,
            date=c.date,
            type=c.type,
            amount=c.amount,
            notes=c.notes,
            account_id=c.account_id,
            account_name=c.account.name if c.account else None,
            created_at=c.created_at
        )
        for c in goal.contributions
    ]

    return FinancialGoalResponse(
        id=goal.id,
        family_id=goal.family_id,
        created_by_id=goal.created_by_id,
        name=goal.name,
        description=goal.description,
        target_amount=goal.target_amount,
        accumulated_amount=stats["accumulated_amount"],
        remaining_amount=stats["remaining_amount"],
        progress_percentage=stats["progress_percentage"],
        target_date=goal.target_date,
        responsible_name=goal.responsible_name,
        is_shared=goal.is_shared,
        status=goal.status,
        contributions=contributions_resp,
        created_at=goal.created_at,
        updated_at=goal.updated_at
    )


@router.get("/", response_model=List[FinancialGoalResponse])
def list_goals(
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    goals = db.query(FinancialGoal).filter(
        FinancialGoal.family_id == current_family.id
    ).order_by(FinancialGoal.created_at.desc()).all()
    return [goal_to_schema(g) for g in goals]


@router.post("/", response_model=FinancialGoalResponse, status_code=status.HTTP_201_CREATED)
def create_goal(
    data: FinancialGoalCreate,
    current_user: User = Depends(get_current_user),
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    goal = FinancialGoal(
        family_id=current_family.id,
        created_by_id=current_user.id,
        name=data.name,
        description=data.description,
        target_amount=data.target_amount,
        target_date=data.target_date,
        responsible_name=data.responsible_name,
        is_shared=data.is_shared,
        status="EM_ANDAMENTO"
    )
    db.add(goal)
    db.flush()

    AuditService.log(
        db=db,
        family_id=current_family.id,
        user_id=current_user.id,
        action="CREATE",
        entity_type="GOAL",
        entity_id=str(goal.id),
        new_values={"name": goal.name, "target_amount": str(goal.target_amount)}
    )

    db.commit()
    db.refresh(goal)
    return goal_to_schema(goal)


@router.get("/{goal_id}", response_model=FinancialGoalResponse)
def get_goal(
    goal_id: UUID,
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    goal = db.query(FinancialGoal).filter(
        FinancialGoal.id == goal_id,
        FinancialGoal.family_id == current_family.id
    ).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Meta financeira não encontrada")
    return goal_to_schema(goal)


@router.put("/{goal_id}", response_model=FinancialGoalResponse)
def update_goal(
    goal_id: UUID,
    data: FinancialGoalUpdate,
    current_user: User = Depends(get_current_user),
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    goal = db.query(FinancialGoal).filter(
        FinancialGoal.id == goal_id,
        FinancialGoal.family_id == current_family.id
    ).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Meta financeira não encontrada")

    update_dict = data.model_dump(exclude_unset=True)
    for key, val in update_dict.items():
        setattr(goal, key, val)

    stats = compute_goal_stats(goal)
    if data.status == "CONCLUIDA" and not stats["is_completed"]:
        raise HTTPException(400, detail="Meta só pode ser concluída ao atingir o valor alvo")
    if goal.status != "CANCELADA":
        goal.status = "CONCLUIDA" if stats["is_completed"] else "EM_ANDAMENTO"

    AuditService.log(
        db=db,
        family_id=current_family.id,
        user_id=current_user.id,
        action="UPDATE",
        entity_type="GOAL",
        entity_id=str(goal.id),
        new_values={"name": goal.name, "status": goal.status}
    )

    db.commit()
    db.refresh(goal)
    return goal_to_schema(goal)


@router.delete("/{goal_id}", status_code=status.HTTP_200_OK)
def delete_goal(
    goal_id: UUID,
    current_user: User = Depends(get_current_user),
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    goal = db.query(FinancialGoal).filter(
        FinancialGoal.id == goal_id,
        FinancialGoal.family_id == current_family.id
    ).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Meta financeira não encontrada")

    if goal.contributions:
        raise HTTPException(409, detail="Meta com contribuições deve ser cancelada para preservar o histórico")
    db.delete(goal)
    AuditService.log(
        db=db,
        family_id=current_family.id,
        user_id=current_user.id,
        action="DELETE",
        entity_type="GOAL",
        entity_id=str(goal_id)
    )
    db.commit()
    return {"message": "Meta excluída com sucesso"}


@router.post("/{goal_id}/contributions", response_model=GoalContributionResponse, status_code=status.HTTP_201_CREATED)
def add_contribution(
    goal_id: UUID,
    data: GoalContributionCreate,
    current_user: User = Depends(get_current_user),
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    goal = db.query(FinancialGoal).filter(
        FinancialGoal.id == goal_id,
        FinancialGoal.family_id == current_family.id
    ).with_for_update().first()
    if not goal:
        raise HTTPException(status_code=404, detail="Meta financeira não encontrada")

    if goal.status == "CANCELADA":
        raise HTTPException(409, detail="Meta cancelada não aceita movimentações")
    if data.type == "RETIRADA" and data.amount > compute_goal_stats(goal)["accumulated_amount"]:
        raise HTTPException(400, detail="Retirada excede o saldo da meta")
    if data.type == "AJUSTE" and data.account_id:
        raise HTTPException(400, detail="Ajuste de meta não movimenta conta bancária")
    linked_tx_id = None
    if data.account_id:
        account = db.query(FinancialAccount).filter(
            FinancialAccount.id == data.account_id,
            FinancialAccount.family_id == current_family.id,
            FinancialAccount.is_active == True
        ).first()
        if not account:
            raise HTTPException(status_code=400, detail="Conta financeira inválida")

        # Find or use an investment category
        invest_cat = db.query(Category).filter(
            Category.family_id == current_family.id,
            Category.classification == "INVESTIMENTO"
        ).first()

        tx_type = "DESPESA" if data.type == "CONTRIBUICAO" else "RECEITA"
        tx_desc = f"{'Contribuição' if data.type == 'CONTRIBUICAO' else 'Retirada'} meta: {goal.name}"
        
        tx = Transaction(
            family_id=current_family.id,
            created_by_id=current_user.id,
            date=data.date,
            description=tx_desc,
            type=tx_type,
            amount=data.amount,
            category_id=invest_cat.id if invest_cat else None,
            account_id=account.id,
            responsible_name=goal.responsible_name,
            is_shared=goal.is_shared,
            classification="INVESTIMENTO",
            status="REALIZADA",
            notes=data.notes,
            is_deleted=False
        )
        db.add(tx)
        db.flush()
        linked_tx_id = tx.id

    contribution = GoalContribution(
        goal_id=goal.id,
        created_by_id=current_user.id,
        date=data.date,
        type=data.type,
        amount=data.amount,
        notes=data.notes,
        account_id=data.account_id,
        transaction_id=linked_tx_id
    )
    db.add(contribution)
    db.flush()

    # Re-evaluate goal status
    db.refresh(goal)
    stats = compute_goal_stats(goal)
    goal.status = "CONCLUIDA" if stats["is_completed"] else "EM_ANDAMENTO"

    AuditService.log(
        db=db,
        family_id=current_family.id,
        user_id=current_user.id,
        action="CONTRIBUTE_GOAL",
        entity_type="GOAL",
        entity_id=str(goal.id),
        new_values={
            "type": contribution.type,
            "amount": str(contribution.amount),
            "accumulated": str(stats["accumulated_amount"])
        }
    )

    db.commit()
    db.refresh(contribution)

    return GoalContributionResponse(
        id=contribution.id,
        goal_id=contribution.goal_id,
        created_by_id=contribution.created_by_id,
        date=contribution.date,
        type=contribution.type,
        amount=contribution.amount,
        notes=contribution.notes,
        account_id=contribution.account_id,
        account_name=contribution.account.name if contribution.account else None,
        created_at=contribution.created_at
    )


@router.post('/{goal_id}/contributions/{contribution_id}/reverse', response_model=GoalContributionResponse)
def reverse_contribution(goal_id: UUID, contribution_id: UUID,
                         current_family: FamilySpace = Depends(get_admin_family),
                         current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    goal = db.query(FinancialGoal).filter_by(id=goal_id, family_id=current_family.id).with_for_update().first()
    if not goal:
        raise HTTPException(404, detail='Meta não encontrada')
    contribution = db.query(GoalContribution).filter_by(id=contribution_id, goal_id=goal.id).first()
    if not contribution or contribution.is_reversed:
        raise HTTPException(409, detail='Contribuição não encontrada ou já estornada')
    if contribution.type != 'RETIRADA' and contribution.amount > compute_goal_stats(goal)['accumulated_amount']:
        raise HTTPException(409, detail='Estorno deixaria a meta com saldo negativo')
    contribution.is_reversed = True
    if contribution.transaction_id:
        tx = db.query(Transaction).filter_by(id=contribution.transaction_id, family_id=current_family.id).one()
        tx.is_deleted = True
    if goal.status != 'CANCELADA':
        goal.status = 'CONCLUIDA' if compute_goal_stats(goal)['is_completed'] else 'EM_ANDAMENTO'
    AuditService.log(db, current_family.id, current_user.id, 'REVERSE_CONTRIBUTION', 'GOAL', str(goal.id),
                     new_values={'contribution_id':str(contribution.id), 'amount':str(contribution.amount)})
    db.commit()
    db.refresh(contribution)
    return contribution


@router.get('/{goal_id}/contributions', response_model=List[GoalContributionResponse])
def list_contributions(goal_id: UUID, current_family: FamilySpace = Depends(get_current_family),
                       db: Session = Depends(get_db)):
    goal = db.query(FinancialGoal).filter_by(id=goal_id, family_id=current_family.id).first()
    if not goal:
        raise HTTPException(404, detail='Meta não encontrada')
    return goal_to_schema(goal).contributions
