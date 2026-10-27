from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID
from app.schemas.base import BaseModel
from pydantic import ConfigDict, Field, model_validator


class InstallmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    installment_plan_id: UUID
    installment_number: int
    amount: Decimal
    due_date: date
    status: str
    payment_date: Optional[date] = None
    transaction_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class InstallmentPlanCreate(BaseModel):
    @model_validator(mode="after")
    def minimum_parcel(self):
        if self.total_amount < Decimal(self.installments_count) / 100:
            raise ValueError("Cada parcela deve ter pelo menos um centavo")
        return self

    description: str = Field(..., min_length=1, max_length=255)
    category_id: UUID
    account_id: Optional[UUID] = None
    card_id: Optional[UUID] = None
    payment_method_id: Optional[UUID] = None
    responsible_name: str = Field(..., min_length=1, max_length=100)
    is_shared: bool = False
    total_amount: Decimal = Field(..., gt=Decimal("0.00"))
    installments_count: int = Field(..., ge=1, le=120)
    purchase_date: date = Field(default_factory=date.today)
    first_due_date: date
    notes: Optional[str] = None


class InstallmentPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    family_id: UUID
    description: str
    category_id: UUID
    category_name: Optional[str] = None
    account_id: Optional[UUID] = None
    account_name: Optional[str] = None
    card_id: Optional[UUID] = None
    card_name: Optional[str] = None
    payment_method_id: Optional[UUID] = None
    payment_method_name: Optional[str] = None
    responsible_name: str
    is_shared: bool
    total_amount: Decimal
    installments_count: int
    purchase_date: date
    first_due_date: date
    notes: Optional[str] = None
    status: str
    paid_amount: Decimal
    remaining_amount: Decimal
    installments: List[InstallmentResponse] = []
    created_at: datetime
    updated_at: datetime


class InstallmentPayRequest(BaseModel):
    account_id: Optional[UUID] = None
    payment_date: date = Field(default_factory=date.today)


class InstallmentCalendarItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    installment_id: UUID
    plan_id: UUID
    description: str
    category_name: Optional[str] = None
    responsible_name: str
    installment_number: int
    installments_count: int
    amount: Decimal
    due_date: date
    status: str


class InstallmentCalendarMonth(BaseModel):
    year: int
    month: int
    total_due: Decimal
    total_paid: Decimal
    total_pending: Decimal
    items: List[InstallmentCalendarItem] = []
