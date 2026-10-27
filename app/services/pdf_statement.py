"""Statement layout support; never interpret summaries as purchases."""
import re
from datetime import date

MONTHS = {name: i + 1 for i, name in enumerate('JAN FEV MAR ABR MAI JUN JUL AGO SET OUT NOV DEZ'.split())}
MONTH = '|'.join(MONTHS)
NAMED_DATE = re.compile(r'^\s*(\d{1,2})\s+(' + MONTH + r')\.?\s+(?:(\d{4})\s+)?(.*)$', re.I)
BILL_DATE = re.compile(r'\bFATURA\s+(\d{1,2})\s+(' + MONTH + r')\s+(\d{4})', re.I)
SIGNS = str.maketrans({'−': '-', '–': '-', '﹣': '-', '－': '-', '\u00a0': ' '})


def clean_pdf_text(text):
    return text.translate(SIGNS)


def bill_reference(text, fallback):
    match = BILL_DATE.search(text)
    return date(int(match[3]), MONTHS[match[2].upper()], int(match[1])) if match else fallback


def named_pdf_candidates(text, reference, money_pattern):
    """Nubank's DD MMM table, including wrapped descriptions and page breaks."""
    reference = bill_reference(text, reference)
    candidates, warnings = [], []
    pending = None
    table_only = bool(BILL_DATE.search(text) and re.search(r'TRANSA[ÇC][ÕO]ES', text, re.I))
    in_table = not table_only
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if re.search(r'^TRANSA[ÇC][ÕO]ES\b', line, re.I):
            in_table = True
            continue
        if not in_table or not line:
            continue
        match = NAMED_DATE.match(line)
        if match:
            if pending:
                warnings.append(f'Linha {pending[2]}: compra sem valor reconhecido; confira no arquivo original.')
            day, month_name, year, description = match.groups()
            month = MONTHS[month_name.upper()]
            inferred_year = int(year) if year else reference.year - (1 if month - reference.month >= 6 else 0)
            try:
                parsed = date(inferred_year, month, int(day))
            except ValueError:
                warnings.append(f'Linha {number}: data inválida no arquivo.')
                pending = None
                continue
            pending = [parsed.isoformat(), description, number, 0]
        elif pending:
            # Do not join headers or sections to unfinished transaction descriptions.
            if BILL_DATE.search(line) or re.search(r'^(RESUMO|PR[ÓO]XIMAS|PAGAMENTOS|TOTAL|EM CUMPRIMENTO)', line, re.I):
                warnings.append(f'Linha {pending[2]}: compra incompleta; confira no arquivo original.')
                pending = None
                continue
            pending[1] += ' ' + line
            pending[3] += 1
        if not pending:
            continue
        amounts = list(money_pattern.finditer(pending[1]))
        if amounts and not pending[1][amounts[-1].end():].strip():
            amount = amounts[-1]
            description = pending[1][:amount.start()].strip()
            description = re.sub(r'^(?:[•●*xX]{4}\s*\d{4}\s*)', '', description).strip()
            if description:
                token = amount.group().strip()
                direction = 'DESPESA' if '-' in token else 'RECEITA' if '+' in token else None
                candidates.append((pending[0], description, token, direction, None, f'Linha {pending[2]}'))
            pending = None
        elif pending[3] >= 3:
            warnings.append(f'Linha {pending[2]}: descrição ou valor quebrado; confira no arquivo original.')
            pending = None
    if pending:
        warnings.append(f'Linha {pending[2]}: compra incompleta; confira no arquivo original.')
    return candidates, warnings


def statement_summary(text, rows):
    from app.services.statement_parser import money
    from decimal import Decimal
    text = clean_pdf_text(text)
    reference = BILL_DATE.search(text)
    if not reference or not re.search('RESUMO DA FATURA ATUAL', text, re.I):
        return None
    cycle = re.search(r'TRANSA[ÇC][ÕO]ES\s+DE\s+(\d{1,2})\s+(' + MONTH + r')\s+A\s+(\d{1,2})\s+(' + MONTH + r')', text, re.I)
    cycle_start, cycle_end = None, None
    if cycle:
        end_month = MONTHS[cycle[4].upper()]
        end_year = int(reference[3]) - (1 if end_month - MONTHS[reference[2].upper()] >= 6 else 0)
        start_month = MONTHS[cycle[2].upper()]
        cycle_end = date(end_year, end_month, int(cycle[3])).isoformat()
        cycle_start = date(end_year - (1 if start_month > end_month else 0), start_month, int(cycle[1])).isoformat()
    full_text = text
    section = re.search(r'RESUMO DA FATURA ATUAL(.*?)(?:PR[ÓO]XIMAS FATURAS|LIMITES DISPON[ÍI]VEIS|$)', text, re.S | re.I)
    text = section[1] if section else text
    currency = r'([-+]?\s*R\$\s*[-+]?\s*[\d.]+,\d{2})'
    fields = {}
    for key, label in [('previous_balance', 'Fatura anterior'), ('payments_received', 'Pagamento recebido'),
                       ('purchases', 'Total de compras de todos os cart[õo]es[^\n]*?'),
                       ('other_entries', 'Outros lan[çc]amentos'), ('amount_due', 'Total a pagar')]:
        match = re.search(label + r'\s+' + currency, text, re.I)
        fields[key] = str(money(match[1])) if match else None
    charges = sum((Decimal(r['amount']) for r in rows if r.get('entry_kind') == 'purchase'), Decimal('0'))
    credits = sum((Decimal(r['amount']) for r in rows if r.get('entry_kind') in ('refund', 'credit')), Decimal('0'))
    payments = sum((Decimal(r['amount']) for r in rows if r.get('entry_kind') == 'payment'), Decimal('0'))
    checked = []
    if fields['purchases'] is not None:
        checked.append(charges == Decimal(fields['purchases']))
    if fields['payments_received'] is not None:
        checked.append(payments == abs(Decimal(fields['payments_received'])))
    if fields['other_entries'] is not None and Decimal(fields['other_entries']) < 0:
        checked.append(credits == abs(Decimal(fields['other_entries'])))
    if fields['amount_due'] is not None and fields['previous_balance'] is not None:
        checked.append(max(Decimal('0'), Decimal(fields['previous_balance']) + charges - credits - payments) == Decimal(fields['amount_due']))
    return {'issuer': 'Nubank', 'card_last_digits': sorted(set(re.findall(r'[•●*]{4}\s*(\d{4})', full_text))), 'cycle_start_date': cycle_start, 'closing_date': cycle_end, 'due_date': date(int(reference[3]), MONTHS[reference[2].upper()], int(reference[1])).isoformat(), 'year': int(reference[3]), 'month': MONTHS[reference[2].upper()],
            **fields, 'recognized_purchases': str(charges), 'recognized_credits': str(credits),
            'recognized_payments': str(payments), 'totals_match': all(checked) if checked else None,
            'requires_reconciliation': bool(credits or payments or Decimal(fields['previous_balance'] or '0'))}
