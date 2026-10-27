from decimal import Decimal
import pytest
from app.domain.financial_engine import FinancialEngine


def test_calculate_cents_distribution():
    # R$ 100,00 into 3 installments -> 33.34, 33.33, 33.33
    amounts = FinancialEngine.calculate_cents_distribution(Decimal("100.00"), 3)
    assert len(amounts) == 3
    assert amounts == [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")]
    assert sum(amounts) == Decimal("100.00")

    # R$ 10,00 into 4 installments -> 2.50, 2.50, 2.50, 2.50
    amounts2 = FinancialEngine.calculate_cents_distribution(Decimal("10.00"), 4)
    assert len(amounts2) == 4
    assert amounts2 == [Decimal("2.50"), Decimal("2.50"), Decimal("2.50"), Decimal("2.50")]
    assert sum(amounts2) == Decimal("10.00")

    # R$ 1000.01 into 7 installments
    amounts3 = FinancialEngine.calculate_cents_distribution(Decimal("1000.01"), 7)
    assert len(amounts3) == 7
    assert sum(amounts3) == Decimal("1000.01")


def test_calculate_savings_rate():
    # Normal positive rate: income 5000, expense 3500 -> (1500 / 5000) * 100 = 30.00%
    rate = FinancialEngine.calculate_savings_rate(Decimal("5000.00"), Decimal("3500.00"))
    assert rate == Decimal("30.00")

    # Zero income -> None (unavailable)
    assert FinancialEngine.calculate_savings_rate(Decimal("0.00"), Decimal("500.00")) is None

    # Negative income -> None
    assert FinancialEngine.calculate_savings_rate(Decimal("-100.00"), Decimal("200.00")) is None

    # Expense greater than income -> negative rate: income 1000, expense 1500 -> -50.00%
    rate_neg = FinancialEngine.calculate_savings_rate(Decimal("1000.00"), Decimal("1500.00"))
    assert rate_neg == Decimal("-50.00")


def test_503020_breakdown():
    breakdown = FinancialEngine.calculate_503020_breakdown(Decimal("5000.00"))
    assert breakdown["needs_allocated"] == Decimal("2500.00")
    assert breakdown["wants_allocated"] == Decimal("1500.00")
    assert breakdown["savings_allocated"] == Decimal("1000.00")
    assert (
        breakdown["needs_allocated"] + breakdown["wants_allocated"] + breakdown["savings_allocated"]
        == Decimal("5000.00")
    )


def test_budget_usage():
    # Normal usage: limit 1000, spent 700
    usage = FinancialEngine.calculate_budget_usage(Decimal("1000.00"), Decimal("700.00"))
    assert usage["consumed_percentage"] == Decimal("70.00")
    assert usage["remaining_amount"] == Decimal("300.00")
    assert not usage["is_warning"]
    assert not usage["is_exceeded"]

    # Warning usage: limit 1000, spent 850 (alert threshold 80%)
    usage_warn = FinancialEngine.calculate_budget_usage(Decimal("1000.00"), Decimal("850.00"))
    assert usage_warn["is_warning"]
    assert not usage_warn["is_exceeded"]

    # Exceeded usage: limit 1000, spent 1200
    usage_exc = FinancialEngine.calculate_budget_usage(Decimal("1000.00"), Decimal("1200.00"))
    assert usage_exc["is_exceeded"]
    assert usage_exc["exceeded_amount"] == Decimal("200.00")
