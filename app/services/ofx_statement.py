"""Billing period metadata for credit-card OFX; never infer it from a filename."""
import calendar
import re
from datetime import date
from decimal import Decimal


def statement_summary(text,rows,card):
    if not card or not re.search(r'<CCSTMTRS>',text,re.I):return None
    def tagged_date(tag):
        value=re.search(r'<'+tag+r'>\s*(\d{8})',text,re.I)
        if not value:return None
        raw=value[1]
        try:
            parsed=date(int(raw[:4]),int(raw[4:6]),int(raw[6:8]))
            return parsed if 2000<=parsed.year<=2100 else None
        except ValueError:return None
    closing=tagged_date('DTEND')
    if not closing:return None
    start=tagged_date('DTSTART')
    if start and start>closing:return None
    year,month=closing.year,closing.month
    if card.due_day<=closing.day:
        year,month=year+(month==12),month%12+1
    if year>2100:return None
    due=date(year,month,min(card.due_day,calendar.monthrange(year,month)[1]))
    sums={kind:sum((Decimal(r['amount']) for r in rows if r.get('entry_kind')==kind),Decimal('0')) for kind in ['purchase','payment','refund','credit']}
    credits=sums['refund']+sums['credit']
    return {'format':'ofx','issuer':'OFX do cartão','year':year,'month':month,'card_last_digits':[],
        'cycle_start_date':str(start) if start else None,'closing_date':str(closing),'due_date':str(due),
        'purchases':str(sums['purchase']),'recognized_purchases':str(sums['purchase']),
        'previous_balance':None,'payments_received':None,'amount_due':None,'other_entries':None,
        'recognized_credits':str(credits),'recognized_payments':str(sums['payment']),
        'totals_match':None,'requires_reconciliation':bool(credits or sums['payment'])}
