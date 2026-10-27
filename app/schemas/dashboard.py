from datetime import date as dt_date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel


class CategorySpendingItem(BaseModel):
    category_id: Optional[UUID] = None
    category_name: str
    color: str
    amount: Decimal
    percentage: Decimal


class ResponsibleSpendingItem(BaseModel):
    responsible_name: str
    is_shared: bool
    amount: Decimal
    income: Decimal = Decimal("0.00")
    percentage: Decimal


class ClassificationSpendingItem(BaseModel):
    classification: str  # NECESSIDADE, DESEJO, INVESTIMENTO
    amount: Decimal
    percentage: Decimal


class MonthlyCashFlowItem(BaseModel):
    period: str  # e.g. "2026-05"
    label: str   # e.g. "Mai/26"
    realized_income: Decimal
    realized_expense: Decimal
    net_result: Decimal


class TopExpenseItem(BaseModel):
    id: UUID
    description: str
    category_name: Optional[str] = None
    responsible_name: str
    amount: Decimal
    date: dt_date


class FutureInstallmentCommitment(BaseModel):
    period: str
    label: str
    amount: Decimal
    count: int


class DashboardMetricsResponse(BaseModel):
    start_date: dt_date
    end_date: dt_date
    period_label: str
    
    # Realized Flow
    realized_income: Decimal
    realized_expense: Decimal
    net_result: Decimal
    
    # Pending Flow
    pending_income: Decimal
    pending_expense: Decimal
    projected_net: Decimal
    
    # Indicators
    future_installments_total: Decimal
    savings_rate: Optional[Decimal] = None  # None if income <= 0
    total_account_balance: Decimal
    
    # Breakdowns
    category_spending: List[CategorySpendingItem]
    responsible_spending: List[ResponsibleSpendingItem]
    classification_spending: List[ClassificationSpendingItem]
    cash_flow_timeline: List[MonthlyCashFlowItem]
    top_expenses: List[TopExpenseItem]
    future_commitments: List[FutureInstallmentCommitment]
