import calendar
from datetime import date
from decimal import Decimal
from typing import Any, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_family
from app.domain.financial_engine import FinancialEngine
from app.models.family import FamilySpace
from app.models.transaction import Transaction
from app.models.category import Category
from app.schemas.dashboard import CategorySpendingItem, ResponsibleSpendingItem, ClassificationSpendingItem
from app.schemas.report import MonthlyReportResponse, AnnualReportResponse, AnnualMonthSummary

router = APIRouter(prefix="/reports", tags=["Relatórios"])


@router.get("/monthly", response_model=MonthlyReportResponse)
def get_monthly_report(
    year: int = Query(default_factory=lambda: date.today().year),
    month: int = Query(default_factory=lambda: date.today().month),
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    _, last_day = calendar.monthrange(year, month)
    start_date = date(year, month, 1)
    end_date = date(year, month, last_day)

    month_names = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    period_label = f"{month_names[month - 1]} de {year}"

    # Income and Expenses
    realized_income = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.family_id == current_family.id,
        Transaction.date >= start_date,
        Transaction.date <= end_date,
        Transaction.type == "RECEITA",
        Transaction.status == "REALIZADA",
        Transaction.is_deleted == False
    ).scalar()

    realized_expense = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.family_id == current_family.id,
        Transaction.date >= start_date,
        Transaction.date <= end_date,
        Transaction.type == "DESPESA",
        Transaction.status == "REALIZADA",
        Transaction.is_invoice_payment == False,
        Transaction.is_deleted == False
    ).scalar()

    income_dec = Decimal(str(realized_income)).quantize(Decimal("0.01"))
    expense_dec = Decimal(str(realized_expense)).quantize(Decimal("0.01"))
    net_dec = FinancialEngine.calculate_net_result(income_dec, expense_dec)
    savings_rate = FinancialEngine.calculate_savings_rate(income_dec, expense_dec)

    total_count = db.query(Transaction).filter(
        Transaction.family_id == current_family.id,
        Transaction.date >= start_date,
        Transaction.date <= end_date,
        Transaction.is_deleted == False
    ).count()

    # Category breakdown
    cat_spend_query = db.query(
        Transaction.category_id,
        Category.name,
        Category.color,
        func.sum(Transaction.amount)
    ).join(Category, Transaction.category_id == Category.id, isouter=True).filter(
        Transaction.family_id == current_family.id,
        Transaction.date >= start_date,
        Transaction.date <= end_date,
        Transaction.type == "DESPESA",
        Transaction.status == "REALIZADA",
        Transaction.is_invoice_payment == False,
        Transaction.is_deleted == False
    ).group_by(Transaction.category_id, Category.name, Category.color).order_by(func.sum(Transaction.amount).desc()).all()

    categories: List[CategorySpendingItem] = []
    for cat_id, cat_name, cat_color, total_spent in cat_spend_query:
        spent_amt = Decimal(str(total_spent)).quantize(Decimal("0.01"))
        pct = Decimal("0.00")
        if expense_dec > Decimal("0.00"):
            pct = ((spent_amt / expense_dec) * Decimal("100.00")).quantize(Decimal("0.01"))
        categories.append(CategorySpendingItem(
            category_id=cat_id,
            category_name=cat_name or "Sem categoria",
            color=cat_color or "#6B7280",
            amount=spent_amt,
            percentage=pct
        ))

    # Responsible breakdown
    resp_query = db.query(
        Transaction.responsible_name,
        Transaction.is_shared,
        func.sum(Transaction.amount)
    ).filter(
        Transaction.family_id == current_family.id,
        Transaction.date >= start_date,
        Transaction.date <= end_date,
        Transaction.type == "DESPESA",
        Transaction.status == "REALIZADA",
        Transaction.is_invoice_payment == False,
        Transaction.is_deleted == False
    ).group_by(Transaction.responsible_name, Transaction.is_shared).all()

    responsibles: List[ResponsibleSpendingItem] = []
    for resp_name, is_shared, total_spent in resp_query:
        spent_amt = Decimal(str(total_spent)).quantize(Decimal("0.01"))
        pct = Decimal("0.00")
        if expense_dec > Decimal("0.00"):
            pct = ((spent_amt / expense_dec) * Decimal("100.00")).quantize(Decimal("0.01"))

        resp_income = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.family_id == current_family.id,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            Transaction.type == "RECEITA",
            Transaction.status == "REALIZADA",
            Transaction.responsible_name == resp_name,
            Transaction.is_deleted == False
        ).scalar()

        responsibles.append(ResponsibleSpendingItem(
            responsible_name=resp_name,
            is_shared=is_shared,
            amount=spent_amt,
            income=Decimal(str(resp_income)).quantize(Decimal("0.01")),
            percentage=pct
        ))

    # Classification breakdown
    classif_query = db.query(
        Transaction.classification,
        func.sum(Transaction.amount)
    ).filter(
        Transaction.family_id == current_family.id,
        Transaction.date >= start_date,
        Transaction.date <= end_date,
        Transaction.type == "DESPESA",
        Transaction.status == "REALIZADA",
        Transaction.is_invoice_payment == False,
        Transaction.is_deleted == False
    ).group_by(Transaction.classification).all()

    classifications: List[ClassificationSpendingItem] = []
    for classif, total_spent in classif_query:
        spent_amt = Decimal(str(total_spent)).quantize(Decimal("0.01"))
        pct = Decimal("0.00")
        if expense_dec > Decimal("0.00"):
            pct = ((spent_amt / expense_dec) * Decimal("100.00")).quantize(Decimal("0.01"))
        classifications.append(ClassificationSpendingItem(
            classification=classif,
            amount=spent_amt,
            percentage=pct
        ))

    return MonthlyReportResponse(
        year=year,
        month=month,
        period_label=period_label,
        realized_income=income_dec,
        realized_expense=expense_dec,
        net_result=net_dec,
        savings_rate=savings_rate,
        categories=categories,
        responsibles=responsibles,
        classifications=classifications,
        total_transactions_count=total_count
    )


@router.get("/annual", response_model=AnnualReportResponse)
def get_annual_report(
    year: int = Query(default_factory=lambda: date.today().year),
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    month_names = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    months_summary: List[AnnualMonthSummary] = []
    total_income = Decimal("0.00")
    total_expense = Decimal("0.00")

    for m in range(1, 13):
        _, last_day = calendar.monthrange(year, m)
        start_date = date(year, m, 1)
        end_date = date(year, m, last_day)

        m_inc = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.family_id == current_family.id,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            Transaction.type == "RECEITA",
            Transaction.status == "REALIZADA",
            Transaction.is_deleted == False
        ).scalar()

        m_exp = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.family_id == current_family.id,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            Transaction.type == "DESPESA",
            Transaction.status == "REALIZADA",
            Transaction.is_deleted == False
        ).scalar()

        inc_dec = Decimal(str(m_inc)).quantize(Decimal("0.01"))
        exp_dec = Decimal(str(m_exp)).quantize(Decimal("0.01"))
        net_dec = inc_dec - exp_dec
        rate = FinancialEngine.calculate_savings_rate(inc_dec, exp_dec)

        total_income += inc_dec
        total_expense += exp_dec

        months_summary.append(AnnualMonthSummary(
            month=m,
            month_name=month_names[m - 1],
            income=inc_dec,
            expense=exp_dec,
            net=net_dec,
            savings_rate=rate
        ))

    avg_income = (total_income / Decimal("12")).quantize(Decimal("0.01"))
    avg_expense = (total_expense / Decimal("12")).quantize(Decimal("0.01"))

    # Top categories for the year
    cat_spend_query = db.query(
        Transaction.category_id,
        Category.name,
        Category.color,
        func.sum(Transaction.amount)
    ).join(Category, Transaction.category_id == Category.id, isouter=True).filter(
        Transaction.family_id == current_family.id,
        Transaction.date >= date(year, 1, 1),
        Transaction.date <= date(year, 12, 31),
        Transaction.type == "DESPESA",
        Transaction.status == "REALIZADA",
        Transaction.is_invoice_payment == False,
        Transaction.is_deleted == False
    ).group_by(Transaction.category_id, Category.name, Category.color).order_by(func.sum(Transaction.amount).desc()).limit(10).all()

    top_categories: List[CategorySpendingItem] = []
    for cat_id, cat_name, cat_color, total_spent in cat_spend_query:
        spent_amt = Decimal(str(total_spent)).quantize(Decimal("0.01"))
        pct = Decimal("0.00")
        if total_expense > Decimal("0.00"):
            pct = ((spent_amt / total_expense) * Decimal("100.00")).quantize(Decimal("0.01"))
        top_categories.append(CategorySpendingItem(
            category_id=cat_id,
            category_name=cat_name or "Sem categoria",
            color=cat_color or "#6B7280",
            amount=spent_amt,
            percentage=pct
        ))

    return AnnualReportResponse(
        year=year,
        total_income=total_income,
        total_expense=total_expense,
        net_result=total_income - total_expense,
        average_monthly_income=avg_income,
        average_monthly_expense=avg_expense,
        months=months_summary,
        top_categories=top_categories
    )
