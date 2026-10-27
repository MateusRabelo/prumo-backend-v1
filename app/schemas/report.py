from datetime import date
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel
from app.schemas.dashboard import CategorySpendingItem, ResponsibleSpendingItem, ClassificationSpendingItem


class MonthlyReportResponse(BaseModel):
    year: int
    month: int
    period_label: str
    realized_income: Decimal
    realized_expense: Decimal
    net_result: Decimal
    savings_rate: Optional[Decimal] = None
    categories: List[CategorySpendingItem]
    responsibles: List[ResponsibleSpendingItem]
    classifications: List[ClassificationSpendingItem]
    total_transactions_count: int


class AnnualMonthSummary(BaseModel):
    month: int
    month_name: str
    income: Decimal
    expense: Decimal
    net: Decimal
    savings_rate: Optional[Decimal] = None


class AnnualReportResponse(BaseModel):
    year: int
    total_income: Decimal
    total_expense: Decimal
    net_result: Decimal
    average_monthly_income: Decimal
    average_monthly_expense: Decimal
    months: List[AnnualMonthSummary]
    top_categories: List[CategorySpendingItem]
