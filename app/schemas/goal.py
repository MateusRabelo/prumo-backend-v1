from datetime import date as dt_date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID
from app.schemas.base import BaseModel
from pydantic import ConfigDict, Field


class GoalContributionCreate(BaseModel):
    date: dt_date = Field(default_factory=dt_date.today)
    type: str = Field(default="CONTRIBUICAO", pattern="^(CONTRIBUICAO|RETIRADA|AJUSTE)$")
    amount: Decimal = Field(..., gt=Decimal("0.00"))
    notes: Optional[str] = None
    account_id: Optional[UUID] = None


class GoalContributionResponse(BaseModel):
    is_reversed: bool = False
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    goal_id: UUID
    created_by_id: Optional[UUID] = None
    date: dt_date
    type: str
    amount: Decimal
    notes: Optional[str] = None
    account_id: Optional[UUID] = None
    account_name: Optional[str] = None
    created_at: datetime


class FinancialGoalCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    description: Optional[str] = None
    target_amount: Decimal = Field(..., gt=Decimal("0.00"))
    target_date: Optional[dt_date] = None
    responsible_name: str = Field(..., min_length=1, max_length=100)
    is_shared: bool = False


class FinancialGoalUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    description: Optional[str] = None
    target_amount: Optional[Decimal] = Field(None, gt=Decimal("0.00"))
    target_date: Optional[dt_date] = None
    responsible_name: Optional[str] = None
    is_shared: Optional[bool] = None
    status: Optional[str] = Field(None, pattern="^(EM_ANDAMENTO|CONCLUIDA|CANCELADA)$")


class FinancialGoalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    family_id: UUID
    created_by_id: Optional[UUID] = None
    name: str
    description: Optional[str] = None
    target_amount: Decimal
    accumulated_amount: Decimal = Decimal("0.00")
    remaining_amount: Decimal = Decimal("0.00")
    progress_percentage: Decimal = Decimal("0.00")
    target_date: Optional[dt_date] = None
    responsible_name: str
    is_shared: bool
    status: str
    contributions: List[GoalContributionResponse] = []
    created_at: datetime
    updated_at: datetime
