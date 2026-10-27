from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID
from app.schemas.base import BaseModel
from pydantic import ConfigDict, Field


class CardInvoiceItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    date: date
    description: str
    category_name: Optional[str] = None
    category_color: Optional[str] = None
    responsible_name: str
    amount: Decimal
    is_installment: bool = False
    installment_text: Optional[str] = None
    status: str = "REALIZADA"


class CardInvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[UUID] = None
    card_id: UUID
    year: int
    month: int
    period_label: str
    cycle_start_date: date
    closing_date: date
    due_date: date
    total_amount: Decimal
    paid_amount: Decimal = Decimal("0.00")
    remaining_amount: Decimal = Decimal("0.00")
    status: str  # ABERTA, FECHADA, PAGA, VENCIDA
    items_count: int = 0
    is_current: bool = False
    payment_date: Optional[date] = None
    payment_account_id: Optional[UUID] = None
    payment_account_name: Optional[str] = None
    items: List[CardInvoiceItem] = []
    created_at: Optional[datetime] = None


class InvoicePayRequest(BaseModel):
    account_id: UUID
    payment_date: date = Field(default_factory=date.today)
    amount: Optional[Decimal] = Field(None, gt=Decimal("0"))
    notes: Optional[str] = None


class InvoiceOverviewItem(BaseModel):
    card_name: str
    invoice: CardInvoiceResponse


class InvoiceOverview(BaseModel):
    year: int
    month: int
    bank_balance: Decimal
    available_for_payment: Decimal
    total_amount: Decimal
    paid_amount: Decimal
    remaining_amount: Decimal
    shortfall: Decimal
    balance_after_payment: Decimal
    invoices: List[InvoiceOverviewItem]
