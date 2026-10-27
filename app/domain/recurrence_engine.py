import calendar
from datetime import date, timedelta
from typing import List


class RecurrenceEngine:
    @staticmethod
    def get_valid_date_for_month(year: int, month: int, preferred_day: int) -> date:
        """
        Returns a date for the specified year and month.
        If preferred_day exceeds the number of days in the month, adjusts to the last day of that month.
        """
        _, last_day = calendar.monthrange(year, month)
        actual_day = min(preferred_day, last_day)
        return date(year, month, actual_day)

    @staticmethod
    def generate_due_dates(
        start_date: date,
        frequency: str,
        installments_or_periods: int,
        day_of_month: int = None
    ) -> List[date]:
        """
        Generates a deterministic sequence of dates.
        """
        dates: List[date] = []
        preferred_day = day_of_month or start_date.day
        
        current_year = start_date.year
        current_month = start_date.month

        for i in range(installments_or_periods):
            if frequency == "MONTHLY":
                month_offset = current_month + i
                year = current_year + (month_offset - 1) // 12
                month = ((month_offset - 1) % 12) + 1
                dates.append(RecurrenceEngine.get_valid_date_for_month(year, month, preferred_day))
            elif frequency == "WEEKLY":
                dates.append(start_date + timedelta(weeks=i))
            elif frequency == "DAILY":
                dates.append(start_date + timedelta(days=i))
            elif frequency == "YEARLY":
                dates.append(date(start_date.year + i, start_date.month, min(start_date.day, 28 if start_date.month == 2 else 30)))
            else:
                # Default monthly
                month_offset = current_month + i
                year = current_year + (month_offset - 1) // 12
                month = ((month_offset - 1) % 12) + 1
                dates.append(RecurrenceEngine.get_valid_date_for_month(year, month, preferred_day))
                
        return dates
