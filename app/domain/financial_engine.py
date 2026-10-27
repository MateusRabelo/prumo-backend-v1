from decimal import Decimal, ROUND_FLOOR
from typing import Dict, List, Optional


class FinancialEngine:
    @staticmethod
    def calculate_cents_distribution(total_amount: Decimal, installments_count: int) -> List[Decimal]:
        """
        Splits total_amount into installments_count installments deterministically.
        Any remaining cents are distributed 1 cent per installment starting from the first.
        Ensures that sum(installments) == total_amount with exact cent precision.
        """
        if installments_count <= 0:
            raise ValueError("Installments count must be positive")
        
        # Ensure total_amount has 2 decimal places
        total = Decimal(str(total_amount)).quantize(Decimal("0.01"))
        
        # Calculate base installment using floor division
        base = (total / Decimal(installments_count)).quantize(Decimal("0.01"), rounding=ROUND_FLOOR)
        total_base = base * Decimal(installments_count)
        remainder_cents = int((total - total_base) * 100)
        
        result: List[Decimal] = []
        for i in range(installments_count):
            if i < remainder_cents:
                result.append(base + Decimal("0.01"))
            else:
                result.append(base)
                
        # Integrity check
        assert sum(result) == total, "Installment sum mismatch"
        return result

    @staticmethod
    def calculate_savings_rate(realized_income: Decimal, realized_expense: Decimal) -> Optional[Decimal]:
        """
        Calculates savings rate as ((Income - Expense) / Income) * 100.
        Returns None if income <= 0 (indicated as unavailable).
        """
        income = Decimal(str(realized_income)).quantize(Decimal("0.01"))
        expense = Decimal(str(realized_expense)).quantize(Decimal("0.01"))
        
        if income <= Decimal("0.00"):
            return None
        
        rate = ((income - expense) / income) * Decimal("100.00")
        return rate.quantize(Decimal("0.01"))

    @staticmethod
    def calculate_net_result(realized_income: Decimal, realized_expense: Decimal) -> Decimal:
        income = Decimal(str(realized_income)).quantize(Decimal("0.01"))
        expense = Decimal(str(realized_expense)).quantize(Decimal("0.01"))
        return income - expense

    @staticmethod
    def calculate_503020_breakdown(
        estimated_income: Decimal,
        needs_pct: Decimal = Decimal("50.00"),
        wants_pct: Decimal = Decimal("30.00"),
        savings_pct: Decimal = Decimal("20.00")
    ) -> Dict[str, Decimal]:
        """
        Calculates 50/30/20 budget allocations.
        Ensures exact cent distribution so needs + wants + savings == estimated_income.
        """
        income = Decimal(str(estimated_income)).quantize(Decimal("0.01"))
        needs = (income * (needs_pct / Decimal("100.00"))).quantize(Decimal("0.01"))
        wants = (income * (wants_pct / Decimal("100.00"))).quantize(Decimal("0.01"))
        savings = income - (needs + wants)
        
        return {
            "estimated_income": income,
            "needs_allocated": needs,
            "wants_allocated": wants,
            "savings_allocated": savings,
            "needs_pct": needs_pct,
            "wants_pct": wants_pct,
            "savings_pct": savings_pct
        }

    @staticmethod
    def calculate_budget_usage(limit_amount: Decimal, realized_spent: Decimal, alert_threshold: Decimal = Decimal("80.00")) -> Dict[str, any]:
        limit = Decimal(str(limit_amount)).quantize(Decimal("0.01"))
        spent = Decimal(str(realized_spent)).quantize(Decimal("0.01"))
        
        remaining = limit - spent
        percentage = Decimal("0.00")
        if limit > Decimal("0.00"):
            percentage = ((spent / limit) * Decimal("100.00")).quantize(Decimal("0.01"))
            
        is_exceeded = spent > limit
        exceeded_amount = max(Decimal("0.00"), spent - limit)
        is_warning = (percentage >= alert_threshold) and not is_exceeded
        
        return {
            "limit_amount": limit,
            "realized_spent": spent,
            "remaining_amount": remaining,
            "consumed_percentage": percentage,
            "is_warning": is_warning,
            "is_exceeded": is_exceeded,
            "exceeded_amount": exceeded_amount
        }

    @staticmethod
    def calculate_goal_progress(target_amount: Decimal, accumulated_amount: Decimal) -> Dict[str, any]:
        target = Decimal(str(target_amount)).quantize(Decimal("0.01"))
        accumulated = Decimal(str(accumulated_amount)).quantize(Decimal("0.01"))
        
        remaining = max(Decimal("0.00"), target - accumulated)
        percentage = Decimal("0.00")
        if target > Decimal("0.00"):
            percentage = min(Decimal("100.00"), ((accumulated / target) * Decimal("100.00")).quantize(Decimal("0.01")))
            
        is_completed = accumulated >= target
        
        return {
            "target_amount": target,
            "accumulated_amount": accumulated,
            "remaining_amount": remaining,
            "progress_percentage": percentage,
            "is_completed": is_completed
        }
