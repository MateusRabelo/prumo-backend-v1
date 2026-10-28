from datetime import date as dt_date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID
from app.schemas.base import BaseModel
from pydantic import ConfigDict, Field


class TransactionCreate(BaseModel):
    date: dt_date = Field(default_factory=dt_date.today)
    description: str = Field(..., min_length=1, max_length=255)
    type: str = Field(..., pattern="^(RECEITA|DESPESA|TRANSFERENCIA)$")
    amount: Decimal = Field(..., gt=Decimal("0.00"))
    category_id: Optional[UUID] = None
    account_id: Optional[UUID] = None
    destination_account_id: Optional[UUID] = None
    payment_mode: str = Field(default="ACCOUNT", pattern="^(ACCOUNT|CREDIT|DEBIT)$")
    card_id: Optional[UUID] = None
    invoice_id: Optional[UUID] = None
    responsible_name: str = Field(..., min_length=1, max_length=100)
    is_shared: bool = False
    classification: str = Field(default="NECESSIDADE", pattern="^(NECESSIDADE|DESEJO|INVESTIMENTO|OUTRO)$")
    payment_method_id: Optional[UUID] = None
    status: str = Field(default="REALIZADA", pattern="^(REALIZADA|PENDENTE|VENCIDA)$")
    notes: Optional[str] = None


class TransactionUpdate(BaseModel):
    date: Optional[dt_date] = None
    description: Optional[str] = Field(None, min_length=1, max_length=255)
    type: Optional[str] = Field(None, pattern="^(RECEITA|DESPESA|TRANSFERENCIA)$")
    amount: Optional[Decimal] = Field(None, gt=Decimal("0.00"))
    category_id: Optional[UUID] = None
    account_id: Optional[UUID] = None
    destination_account_id: Optional[UUID] = None
    payment_mode: Optional[str] = Field(None, pattern="^(ACCOUNT|CREDIT|DEBIT)$")
    card_id: Optional[UUID] = None
    responsible_name: Optional[str] = None
    is_shared: Optional[bool] = None
    classification: Optional[str] = Field(None, pattern="^(NECESSIDADE|DESEJO|INVESTIMENTO|OUTRO)$")
    payment_method_id: Optional[UUID] = None
    status: Optional[str] = Field(None, pattern="^(REALIZADA|PENDENTE|VENCIDA)$")
    notes: Optional[str] = None


class TransactionResponse(BaseModel):
    is_invoice_payment: bool = False
    card_last_digits: Optional[str] = None
    card_bank_name: Optional[str] = None
    account_bank_name: Optional[str] = None
    invoice_year: Optional[int] = None
    invoice_month: Optional[int] = None
    invoice_id: Optional[UUID] = None
    invoice_label: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    family_id: UUID
    created_by_id: Optional[UUID] = None
    date: dt_date
    description: str
    type: str
    amount: Decimal
    category_id: Optional[UUID] = None
    category_name: Optional[str] = None
    category_color: Optional[str] = None
    account_id: UUID
    account_name: Optional[str] = None
    destination_account_id: Optional[UUID] = None
    destination_account_name: Optional[str] = None
    payment_mode: str = "ACCOUNT"
    card_id: Optional[UUID] = None
    card_name: Optional[str] = None
    responsible_name: str
    is_shared: bool
    classification: str
    payment_method_id: Optional[UUID] = None
    payment_method_name: Optional[str] = None
    status: str
    notes: Optional[str] = None
    installment_id: Optional[UUID] = None
    recurrence_id: Optional[UUID] = None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class TransactionSummary(BaseModel):
    total_realized_income: Decimal
    total_realized_expense: Decimal
    realized_net: Decimal
    total_pending_income: Decimal
    total_pending_expense: Decimal
    count: int


class TransactionListResponse(BaseModel):
    items: List[TransactionResponse]
    total: int
    skip: int
    limit: int
    summary: TransactionSummary


class BulkTransactionItem(BaseModel):
    id: UUID
    updated_at: datetime


class TransactionBulkUpdate(BaseModel):
    items: List[BulkTransactionItem] = Field(min_length=1, max_length=100)
    responsible_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    status: Optional[str] = Field(default=None, pattern="^(REALIZADA|PENDENTE|VENCIDA)$")
