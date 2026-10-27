"""Conservative local parsing: uncertain bank directions always require user review."""
import csv
import hashlib
import io
import re
import unicodedata
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

MAX_ROWS = 500
DATE = re.compile(r'^\s*(\d{2}/\d{2}(?:/\d{2,4})?|\d{4}-\d{2}-\d{2})\s+(.+)$')
MONEY = re.compile(r'(?<![\w/])(?:[-+]\s*)?(?:R\$\s*)?[-+]?\s*(?:\d{1,3}(?:\.\d{3})+|\d+)[,.]\d{2}(?:\s*[DC-])?(?![\d/])', re.I)


def normalize(value):
    value = ''.join(c for c in unicodedata.normalize('NFKD', value) if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', value.lower()).split())[:255]


def money(value):
    raw = re.sub(r'[^0-9,.+-]', '', str(value))
    if raw.endswith('-'):
        raw = '-' + raw[:-1].lstrip('+-')
    if ',' in raw and '.' in raw and raw.rfind('.') > raw.rfind(','):
        raw = raw.replace(',', '')
    elif ',' in raw:
        raw = raw.replace('.', '').replace(',', '.')
    elif raw.count('.') > 1:
        raise ValueError('Valor ambíguo')
    amount = Decimal(raw)
    if not amount.is_finite() or abs(amount) > Decimal('9999999999.99'):
        raise ValueError('Valor fora do limite')
    return amount.quantize(Decimal('.01'))


def parse_date(raw, reference):
    raw = raw.strip()
    if re.fullmatch(r'\d{2}/\d{2}', raw):
        day, month = map(int, raw.split('/'))
        year = reference.year - (1 if month - reference.month >= 6 else 0)
        return date(year, month, day)
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d/%m/%y', '%Y%m%d'):
        try:
            result = datetime.strptime(raw, fmt).date()
            if not 2000 <= result.year <= 2100:
                raise ValueError('Ano inválido')
            return result
        except ValueError:
            continue
    raise ValueError('Data inválida')


def parse_statement(text, kind, reference, card=False):
    candidates, warnings = [], []
    if kind == 'pdf':
        from app.services.pdf_statement import clean_pdf_text, named_pdf_candidates
        text = clean_pdf_text(text)
        named, notices = named_pdf_candidates(text, reference, MONEY)
        candidates.extend(named)
        warnings.extend(notices)
        for line_number, line in enumerate(text.splitlines(), 1):
            match = DATE.match(line)
            if not match:
                continue
            day, rest = match.groups()
            amounts = list(MONEY.finditer(rest))
            if not amounts:
                warnings.append(f'Linha {line_number}: data encontrada sem valor claro; confira no PDF.')
                continue
            amount = amounts[0]
            description = rest[:amount.start()].strip()
            if not description or normalize(description).startswith(('saldo anterior', 'saldo do dia', 'saldo final', 'saldo disponivel')):
                continue
            if len(amounts) > 1:
                warnings.append(f'Linha {line_number}: há várias colunas monetárias; usamos a primeira. Confira o valor na prévia.')
            token = amount.group().strip()
            direction = 'DESPESA' if '-' in token or re.search(r'D\s*$', token, re.I) else 'RECEITA' if '+' in token or re.search(r'C\s*$', token, re.I) else None
            candidates.append((day, description, token, direction, None, f'Linha {line_number}'))
    elif kind == 'ofx':
        for block in re.findall(r'<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>|</BANKTRANLIST>))', text, re.S | re.I):
            def tag(name):
                found = re.search(r'<' + name + r'>([^<\r\n]+)', block, re.I)
                return found.group(1).strip() if found else ''
            amount = tag('TRNAMT')
            candidates.append((tag('DTPOSTED')[:8], tag('MEMO') or tag('NAME'), amount, 'DESPESA' if amount.startswith('-') else 'RECEITA', tag('FITID') or None, 'OFX'))
    else:
        try:
            dialect = csv.Sniffer().sniff(text[:20000], delimiters=';,\t')
        except csv.Error:
            raise ValueError('CSV deve ter colunas de data, descrição e valor, separadas por vírgula, ponto e vírgula ou tabulação.')
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        fields = {normalize(h): h for h in reader.fieldnames or []}
        def column(*names):
            return next((fields[n] for n in names if n in fields), None)
        day_key = column('data', 'date', 'data da compra', 'data lancamento')
        name_key = column('descricao', 'description', 'historico', 'title', 'estabelecimento')
        amount_key = column('valor', 'amount', 'valor r')
        type_key = column('tipo', 'type', 'entrada saida')
        if not all([day_key, name_key, amount_key]):
            raise ValueError('Colunas não reconhecidas. Use Data, Descrição e Valor; opcionalmente Tipo (entrada/saída).')
        for line_number, row in enumerate(reader, 2):
            if line_number > MAX_ROWS + 2:
                raise ValueError('Importe no máximo 500 lançamentos por arquivo.')
            raw = row.get(amount_key, '') or ''
            label = normalize(row.get(type_key, '') or '')
            direction = 'DESPESA' if label in ('d', 'debito', 'saida', 'despesa') or '-' in raw else 'RECEITA' if label in ('c', 'credito', 'entrada', 'receita') or '+' in raw else None
            candidates.append((row.get(day_key, '') or '', row.get(name_key, '') or '', raw, direction, None, f'Linha {line_number}'))
    if len(candidates) > MAX_ROWS:
        raise ValueError('Importe no máximo 500 lançamentos por arquivo.')
    rows, occurrence = [], Counter()
    for raw_date, description, raw_amount, direction, external_id, location in candidates:
        try:
            amount = money(raw_amount)
            parsed_date = parse_date(raw_date, reference)
            description = ' '.join(description.split())[:255]
            if not description or amount == 0:
                continue
            warning, blocked = '', False
            if card:
                credit = direction == 'RECEITA' if kind == 'ofx' else amount < 0 or direction == 'RECEITA'
                direction = 'DESPESA'
                if credit or re.search(r'\b(pagamento|estorno|credito recebido)\b', normalize(description)):
                    warning, blocked = 'Pagamento ou crédito de cartão: revise pelo fluxo da fatura ou estorno, para não duplicar despesas.', True
            elif re.search(r'\b(pagamento (?:de )?fatura|pagto fatura|pag fatura)\b', normalize(description)):
                warning, blocked = 'Pagamento de fatura: registre em Faturas, escolhendo a conta bancária.', True
            elif direction is None:
                warning = 'Confirme se este valor é uma entrada ou saída. O arquivo não informa o sinal com clareza.'
            entry_kind = 'purchase' if card else 'transaction'
            if card and blocked:
                entry_kind = 'payment' if re.search(r'\bpagamento\b', normalize(description)) else 'refund' if 'estorno' in normalize(description) else 'credit'
            parcel = re.search(r'\s*(?:[-·]\s*)?Parcelas?\s+(\d{1,3})\s*/\s*(\d{1,3})\s*$', description, re.I) if card else None
            installment_info = None
            if parcel and 1 <= int(parcel[1]) <= int(parcel[2]) <= 120:
                installment_info = {'number': int(parcel[1]), 'count': int(parcel[2]), 'description': description[:parcel.start()].strip()}
            installment_hint = bool(installment_info)
            if installment_hint and not blocked:
                warning = 'Possível parcela: se o parcelamento já existe no Prumo, não importe esta linha novamente.'
            identity = external_id or f'{parsed_date}|{normalize(description)}|{abs(amount)}|{direction}'
            occurrence[identity] += 1
            # FITID is already a bank-provided unique ID; repeated FITID must deduplicate.
            key = identity if external_id else f'{identity}|{occurrence[identity]}'
            rows.append(dict(index=len(rows), date=str(parsed_date), original_description=description, amount=str(abs(amount)),
                             type=direction, entry_kind=entry_kind, warning=warning, blocked=blocked, possible_installment=bool(installment_hint),
                             installment_info=installment_info, fingerprint=hashlib.sha256(key.encode()).hexdigest()))
        except (ValueError, InvalidOperation):
            warnings.append(f'{location}: não foi possível interpretar data ou valor. Confira esse lançamento manualmente.')
    if card:
        for refund in rows:
            if refund['entry_kind'] != 'refund':
                continue
            merchant = re.sub(r'^estorno\s+de\s+', '', refund['original_description'], flags=re.I).strip(' \"“”')
            matches = [r for r in rows if r['entry_kind'] == 'purchase' and r['amount'] == refund['amount']
                       and normalize(r['original_description']) == normalize(merchant)]
            if len(matches) == 1 and not matches[0].get('refunded_in_statement'):
                matches[0]['refunded_in_statement'] = True
                matches[0]['warning'] = 'Compra com estorno integral identificado neste PDF. Vem desmarcada para não somar uma despesa cancelada.'
    if not rows:
        raise ValueError('Não foi possível reconhecer os lançamentos deste arquivo. Nenhum dado foi salvo. Confira se o PDF contém texto selecionável; se persistir, envie um exemplo para ajustarmos o leitor.')
    return rows, warnings[:100]
