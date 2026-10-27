from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID
from app.schemas.base import BaseModel
from pydantic import ConfigDict, Field


# --- CATEGORY ---
class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color: str = Field(default="#10B981", max_length=20)
    icon: str = Field(default="tag", max_length=50)
    classification: str = Field(default="NECESSIDADE", pattern="^(NECESSIDADE|DESEJO|INVESTIMENTO)$")
    type: str = Field(default="DESPESA", pattern="^(DESPESA|RECEITA|AMBOS)$")
    order_index: int = 0


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    color: Optional[str] = None
    icon: Optional[str] = None
    classification: Optional[str] = Field(None, pattern="^(NECESSIDADE|DESEJO|INVESTIMENTO)$")
    type: Optional[str] = Field(None, pattern="^(DESPESA|RECEITA|AMBOS)$")
    order_index: Optional[int] = None
    is_active: Optional[bool] = None


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    family_id: UUID
    name: str
    color: str
    icon: str
    classification: str
    type: str
    order_index: int
    is_active: bool
    created_at: datetime


# --- FINANCIAL ACCOUNT ---
class AccountCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    account_type: str = Field(default="CHECKING", pattern="^(CHECKING|SAVINGS|WALLET|CREDIT_CARD|INVESTMENT)$")
    bank_name: Optional[str] = Field(None, max_length=100)
    agency: Optional[str] = Field(None, max_length=20)
    account_number: Optional[str] = Field(None, max_length=30)
    initial_balance: Decimal = Decimal("0.00")
    initial_balance_date: date = Field(default_factory=date.today)
    color: str = Field(default="#3B82F6", max_length=20)


class AccountUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    account_type: Optional[str] = Field(None, pattern="^(CHECKING|SAVINGS|WALLET|CREDIT_CARD|INVESTMENT)$")
    bank_name: Optional[str] = None
    agency: Optional[str] = None
    account_number: Optional[str] = None
    initial_balance: Optional[Decimal] = None
    initial_balance_date: Optional[date] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    family_id: UUID
    name: str
    account_type: str
    bank_name: Optional[str] = None
    agency: Optional[str] = None
    account_number: Optional[str] = None
    initial_balance: Decimal
    initial_balance_date: date
    color: str
    is_active: bool
    current_balance: Optional[Decimal] = None
    created_at: datetime


# --- CREDIT CARD ---
class CreditCardCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    card_type: str = Field(default="CREDIT", pattern="^(CREDIT|DEBIT|MULTIPLE|BENEFIT)$")
    brand: str = Field(default="Mastercard", max_length=50)
    bank_name: Optional[str] = Field(None, max_length=100)
    last_digits: Optional[str] = Field(None, max_length=4)
    credit_limit: Decimal = Field(default=Decimal("0.00"), ge=0)
    closing_day: int = Field(default=1, ge=1, le=31)
    due_day: int = Field(default=10, ge=1, le=31)
    color: str = Field(default="#6366F1", max_length=20)
    responsible_name: Optional[str] = None
    responsible_id: Optional[UUID] = None
    account_id: Optional[UUID] = None


class CreditCardUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    card_type: Optional[str] = Field(None, pattern="^(CREDIT|DEBIT|MULTIPLE|BENEFIT)$")
    brand: Optional[str] = None
    bank_name: Optional[str] = None
    last_digits: Optional[str] = None
    credit_limit: Optional[Decimal] = Field(None, ge=0)
    closing_day: Optional[int] = Field(None, ge=1, le=31)
    due_day: Optional[int] = Field(None, ge=1, le=31)
    color: Optional[str] = None
    responsible_name: Optional[str] = None
    responsible_id: Optional[UUID] = None
    account_id: Optional[UUID] = None
    is_active: Optional[bool] = None


class CreditCardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    family_id: UUID
    name: str
    card_type: str
    brand: str
    bank_name: Optional[str] = None
    last_digits: Optional[str] = None
    credit_limit: Decimal
    closing_day: int
    due_day: int
    color: str
    responsible_name: Optional[str] = None
    responsible_id: Optional[UUID] = None
    account_id: Optional[UUID] = None
    is_active: bool
    used_limit: Optional[Decimal] = Decimal("0.00")
    available_limit: Optional[Decimal] = Decimal("0.00")
    current_invoice_total: Optional[Decimal] = Decimal("0.00")
    created_at: datetime
    updated_at: datetime


# --- PAYMENT METHOD ---
class PaymentMethodCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class PaymentMethodUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    is_active: Optional[bool] = None


class PaymentMethodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    family_id: UUID
    name: str
    is_active: bool
    created_at: datetime


# --- RESPONSIBLE PERSON ---
class ResponsibleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    is_shared: bool = False


class ResponsibleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    is_shared: Optional[bool] = None
    is_active: Optional[bool] = None


class ResponsibleResponse(BaseModel):
    user_id: Optional[UUID] = None
    is_system: bool = False
    is_current_user: bool = False
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    family_id: UUID
    name: str
    is_shared: bool
    is_active: bool
    created_at: datetime
