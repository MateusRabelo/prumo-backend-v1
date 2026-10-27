from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID
from app.schemas.base import BaseModel
from pydantic import ConfigDict, Field


class Budget503020Create(BaseModel):
    year: int = Field(..., ge=2000, le=2100)
    month: int = Field(..., ge=1, le=12)
    estimated_income: Decimal = Field(..., ge=Decimal("0.00"))
    needs_percentage: Decimal = Field(default=Decimal("50.00"), ge=Decimal("0.00"), le=Decimal("100.00"))
    wants_percentage: Decimal = Field(default=Decimal("30.00"), ge=Decimal("0.00"), le=Decimal("100.00"))
    savings_percentage: Decimal = Field(default=Decimal("20.00"), ge=Decimal("0.00"), le=Decimal("100.00"))


class Budget503020Response(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    family_id: UUID
    year: int
    month: int
    estimated_income: Decimal
    needs_percentage: Decimal
    wants_percentage: Decimal
    savings_percentage: Decimal
    needs_allocated: Decimal
    wants_allocated: Decimal
    savings_allocated: Decimal
    needs_spent: Decimal = Decimal("0.00")
    wants_spent: Decimal = Decimal("0.00")
    savings_spent: Decimal = Decimal("0.00")
    created_at: datetime
    updated_at: datetime


class CustomBudgetCreate(BaseModel):
    year: int = Field(..., ge=2000, le=2100)
    month: int = Field(..., ge=1, le=12)
    category_id: Optional[UUID] = None
    responsible_name: Optional[str] = None
    classification: Optional[str] = Field(None, pattern="^(NECESSIDADE|DESEJO|INVESTIMENTO)$")
    limit_amount: Decimal = Field(..., gt=Decimal("0.00"))
    alert_threshold_percentage: Decimal = Field(default=Decimal("80.00"), ge=Decimal("1.00"), le=Decimal("100.00"))


class CustomBudgetUpdate(BaseModel):
    limit_amount: Optional[Decimal] = Field(None, gt=Decimal("0.00"))
    alert_threshold_percentage: Optional[Decimal] = Field(None, ge=Decimal("1.00"), le=Decimal("100.00"))


class CustomBudgetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    family_id: UUID
    year: int
    month: int
    category_id: Optional[UUID] = None
    category_name: Optional[str] = None
    responsible_name: Optional[str] = None
    classification: Optional[str] = None
    limit_amount: Decimal
    alert_threshold_percentage: Decimal
    realized_spent: Decimal = Decimal("0.00")
    remaining_amount: Decimal = Decimal("0.00")
    consumed_percentage: Decimal = Decimal("0.00")
    is_warning: bool = False
    is_exceeded: bool = False
    exceeded_amount: Decimal = Decimal("0.00")
    created_at: datetime
    updated_at: datetime
