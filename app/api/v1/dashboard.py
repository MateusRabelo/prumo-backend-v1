import calendar
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_family
from app.api.v1.settings import compute_account_balance
from app.domain.financial_engine import FinancialEngine
from app.models.family import FamilySpace
from app.models.transaction import Transaction
from app.models.category import Category
from app.models.account import FinancialAccount
from app.models.installment import Installment, InstallmentPlan
from app.schemas.dashboard import (
    DashboardMetricsResponse,
    CategorySpendingItem,
    ResponsibleSpendingItem,
    ClassificationSpendingItem,
    MonthlyCashFlowItem,
    TopExpenseItem,
    FutureInstallmentCommitment,
)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def get_date_range_for_period(period: str, custom_start: Optional[date], custom_end: Optional[date]) -> tuple[date, date, str]:
    today = date.today()
    if period == "last_month":
        # First day of previous month
        first_current = date(today.year, today.month, 1)
        last_prev = first_current - timedelta(days=1)
        first_prev = date(last_prev.year, last_prev.month, 1)
        return first_prev, last_prev, "Mês anterior"
    elif period == "last_3_months":
        start = today - timedelta(days=90)
        return start, today, "Últimos 3 meses"
    elif period == "last_6_months":
        start = today - timedelta(days=180)
        return start, today, "Últimos 6 meses"
    elif period == "this_year":
        return date(today.year, 1, 1), date(today.year, 12, 31), f"Ano {today.year}"
    elif period == "custom" and custom_start and custom_end:
        return custom_start, custom_end, "Período personalizado"
    else:
        # Default: this_month
        _, last_day = calendar.monthrange(today.year, today.month)
        return date(today.year, today.month, 1), date(today.year, today.month, last_day), "Este mês"


@router.get("/metrics", response_model=DashboardMetricsResponse)
def get_dashboard_metrics(
    period: str = Query("this_month", pattern="^(this_month|last_month|last_3_months|last_6_months|this_year|custom)$"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    range_start, range_end, period_label = get_date_range_for_period(period, start_date, end_date)

    # 1. Realized Cash Flow in Period
    realized_income = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.family_id == current_family.id,
        Transaction.date >= range_start,
        Transaction.date <= range_end,
        Transaction.type == "RECEITA",
        Transaction.status == "REALIZADA",
        Transaction.is_deleted == False
    ).scalar()

    realized_expense = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.family_id == current_family.id,
        Transaction.date >= range_start,
        Transaction.date <= range_end,
        Transaction.type == "DESPESA",
        Transaction.status == "REALIZADA",
        Transaction.is_invoice_payment == False,
        Transaction.is_deleted == False
    ).scalar()

    income_dec = Decimal(str(realized_income)).quantize(Decimal("0.01"))
    expense_dec = Decimal(str(realized_expense)).quantize(Decimal("0.01"))
    net_dec = FinancialEngine.calculate_net_result(income_dec, expense_dec)

    # 2. Pending Cash Flow in Period
    pending_income = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.family_id == current_family.id,
        Transaction.date >= range_start,
        Transaction.date <= range_end,
        Transaction.type == "RECEITA",
        Transaction.status == "PENDENTE",
        Transaction.is_deleted == False
    ).scalar()

    pending_expense = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.family_id == current_family.id,
        Transaction.date >= range_start,
        Transaction.date <= range_end,
        Transaction.type == "DESPESA",
        Transaction.status.in_(["PENDENTE", "VENCIDA"]),
        Transaction.is_deleted == False
    ).scalar()

    pending_inc_dec = Decimal(str(pending_income)).quantize(Decimal("0.01"))
    pending_exp_dec = Decimal(str(pending_expense)).quantize(Decimal("0.01"))
    projected_net_dec = (income_dec + pending_inc_dec) - (expense_dec + pending_exp_dec)

    # 3. Future Installments in Period
    future_installments = db.query(func.coalesce(func.sum(Installment.amount), 0)).join(InstallmentPlan).filter(
        InstallmentPlan.family_id == current_family.id,
        Installment.due_date >= range_start,
        Installment.due_date <= range_end,
        Installment.status == "PENDENTE"
    ).scalar()
    future_inst_dec = Decimal(str(future_installments)).quantize(Decimal("0.01"))

    # 4. Savings Rate
    savings_rate = FinancialEngine.calculate_savings_rate(income_dec, expense_dec)

    # 5. Total Consolidated Bank Balance
    accounts = db.query(FinancialAccount).filter(
        FinancialAccount.family_id == current_family.id,
        FinancialAccount.is_active == True
    ).all()
    total_balance = sum((compute_account_balance(db, acc) for acc in accounts), Decimal("0.00")).quantize(Decimal("0.01"))

    # 6. Category Spending
    cat_spend_query = db.query(
        Transaction.category_id,
        Category.name,
        Category.color,
        func.sum(Transaction.amount)
    ).join(Category, Transaction.category_id == Category.id, isouter=True).filter(
        Transaction.family_id == current_family.id,
        Transaction.date >= range_start,
        Transaction.date <= range_end,
        Transaction.type == "DESPESA",
        Transaction.status == "REALIZADA",
        Transaction.is_invoice_payment == False,
        Transaction.is_deleted == False
    ).group_by(Transaction.category_id, Category.name, Category.color).order_by(func.sum(Transaction.amount).desc()).all()

    category_spending: List[CategorySpendingItem] = []
    for cat_id, cat_name, cat_color, total_spent in cat_spend_query:
        spent_amt = Decimal(str(total_spent)).quantize(Decimal("0.01"))
        pct = Decimal("0.00")
        if expense_dec > Decimal("0.00"):
            pct = ((spent_amt / expense_dec) * Decimal("100.00")).quantize(Decimal("0.01"))
        category_spending.append(CategorySpendingItem(
            category_id=cat_id,
            category_name=cat_name or "Sem categoria",
            color=cat_color or "#6B7280",
            amount=spent_amt,
            percentage=pct
        ))

    # 7. Responsible Spending & Income
    resp_query = db.query(
        Transaction.responsible_name,
        Transaction.is_shared,
        func.sum(Transaction.amount)
    ).filter(
        Transaction.family_id == current_family.id,
        Transaction.date >= range_start,
        Transaction.date <= range_end,
        Transaction.type == "DESPESA",
        Transaction.status == "REALIZADA",
        Transaction.is_invoice_payment == False,
        Transaction.is_deleted == False
    ).group_by(Transaction.responsible_name, Transaction.is_shared).all()

    responsible_spending: List[ResponsibleSpendingItem] = []
    for resp_name, is_shared, total_spent in resp_query:
        spent_amt = Decimal(str(total_spent)).quantize(Decimal("0.01"))
        pct = Decimal("0.00")
        if expense_dec > Decimal("0.00"):
            pct = ((spent_amt / expense_dec) * Decimal("100.00")).quantize(Decimal("0.01"))

        # Fetch income for this responsible
        resp_income = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.family_id == current_family.id,
            Transaction.date >= range_start,
            Transaction.date <= range_end,
            Transaction.type == "RECEITA",
            Transaction.status == "REALIZADA",
            Transaction.responsible_name == resp_name,
            Transaction.is_deleted == False
        ).scalar()

        responsible_spending.append(ResponsibleSpendingItem(
            responsible_name=resp_name,
            is_shared=is_shared,
            amount=spent_amt,
            income=Decimal(str(resp_income)).quantize(Decimal("0.01")),
            percentage=pct
        ))

    # 8. Classification Spending (Necessidade vs Desejo vs Investimento)
    classif_query = db.query(
        Transaction.classification,
        func.sum(Transaction.amount)
    ).filter(
        Transaction.family_id == current_family.id,
        Transaction.date >= range_start,
        Transaction.date <= range_end,
        Transaction.type == "DESPESA",
        Transaction.status == "REALIZADA",
        Transaction.is_invoice_payment == False,
        Transaction.is_deleted == False
    ).group_by(Transaction.classification).all()

    classification_spending: List[ClassificationSpendingItem] = []
    for classif, total_spent in classif_query:
        spent_amt = Decimal(str(total_spent)).quantize(Decimal("0.01"))
        pct = Decimal("0.00")
        if expense_dec > Decimal("0.00"):
            pct = ((spent_amt / expense_dec) * Decimal("100.00")).quantize(Decimal("0.01"))
        classification_spending.append(ClassificationSpendingItem(
            classification=classif,
            amount=spent_amt,
            percentage=pct
        ))

    # 9. Cash Flow Timeline (Past 6 Months)
    timeline: List[MonthlyCashFlowItem] = []
    today = date.today()
    for i in range(5, -1, -1):
        # Calculate year and month
        m_offset = today.month - i
        y = today.year + (m_offset - 1) // 12
        m = ((m_offset - 1) % 12) + 1
        _, m_last_day = calendar.monthrange(y, m)
        m_start = date(y, m, 1)
        m_end = date(y, m, m_last_day)

        m_inc = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.family_id == current_family.id,
            Transaction.date >= m_start,
            Transaction.date <= m_end,
            Transaction.type == "RECEITA",
            Transaction.status == "REALIZADA",
            Transaction.is_deleted == False
        ).scalar()

        m_exp = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.family_id == current_family.id,
            Transaction.date >= m_start,
            Transaction.date <= m_end,
            Transaction.type == "DESPESA",
            Transaction.status == "REALIZADA",
            Transaction.is_invoice_payment == False,
            Transaction.is_deleted == False
        ).scalar()

        m_inc_dec = Decimal(str(m_inc)).quantize(Decimal("0.01"))
        m_exp_dec = Decimal(str(m_exp)).quantize(Decimal("0.01"))

        month_names = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
        label = f"{month_names[m - 1]}/{str(y)[2:]}"
        period_str = f"{y}-{m:02d}"

        timeline.append(MonthlyCashFlowItem(
            period=period_str,
            label=label,
            realized_income=m_inc_dec,
            realized_expense=m_exp_dec,
            net_result=m_inc_dec - m_exp_dec
        ))

    # 10. Top 5 Expenses
    top_expenses_q = db.query(Transaction).filter(
        Transaction.family_id == current_family.id,
        Transaction.date >= range_start,
        Transaction.date <= range_end,
        Transaction.type == "DESPESA",
        Transaction.status == "REALIZADA",
        Transaction.is_invoice_payment == False,
        Transaction.is_deleted == False
    ).order_by(Transaction.amount.desc()).limit(5).all()

    top_expenses = [
        TopExpenseItem(
            id=t.id,
            description=t.description,
            category_name=t.category.name if t.category else "Sem categoria",
            responsible_name=t.responsible_name,
            amount=t.amount,
            date=t.date
        )
        for t in top_expenses_q
    ]

    # 11. Future Commitments (Next 6 Months)
    future_commitments: List[FutureInstallmentCommitment] = []
    month_names = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
    for i in range(1, 7):
        m_offset = today.month + i
        y = today.year + (m_offset - 1) // 12
        m = ((m_offset - 1) % 12) + 1
        _, m_last_day = calendar.monthrange(y, m)
        m_start = date(y, m, 1)
        m_end = date(y, m, m_last_day)

        inst_sum, inst_count = db.query(
            func.coalesce(func.sum(Installment.amount), 0),
            func.count(Installment.id)
        ).join(InstallmentPlan).filter(
            InstallmentPlan.family_id == current_family.id,
            Installment.due_date >= m_start,
            Installment.due_date <= m_end,
            Installment.status == "PENDENTE"
        ).first()

        future_commitments.append(FutureInstallmentCommitment(
            period=f"{y}-{m:02d}",
            label=f"{month_names[m - 1]}/{str(y)[2:]}",
            amount=Decimal(str(inst_sum)).quantize(Decimal("0.01")),
            count=inst_count or 0
        ))

    return DashboardMetricsResponse(
        start_date=range_start,
        end_date=range_end,
        period_label=period_label,
        realized_income=income_dec,
        realized_expense=expense_dec,
        net_result=net_dec,
        pending_income=pending_inc_dec,
        pending_expense=pending_exp_dec,
        projected_net=projected_net_dec,
        future_installments_total=future_inst_dec,
        savings_rate=savings_rate,
        total_account_balance=total_balance,
        category_spending=category_spending,
        responsible_spending=responsible_spending,
        classification_spending=classification_spending,
        cash_flow_timeline=timeline,
        top_expenses=top_expenses,
        future_commitments=future_commitments
    )
