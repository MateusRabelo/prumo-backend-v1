import asyncio
import hashlib
import json
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID
import jwt
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from app.api.deps import get_current_family, get_current_user, get_db
from app.core.config import settings
from app.models.account import FinancialAccount
from app.models.card import CreditCard
from app.models.category import Category
from app.models.family import FamilySpace
from app.models.import_rule import ImportMerchantRule
from app.models.invoice import CardInvoice
from app.models.security import RateLimitBucket
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.statement_import import ImportConfirm
from app.services.audit_service import AuditService
from app.services.statement_parser import normalize, parse_statement
from app.services.pdf_statement import statement_summary

router = APIRouter(prefix='/imports', tags=['Importação de extratos'])
_pdf_lock = asyncio.Semaphore(1)


def target(db, family_id, account_id, card_id, lock=False):
    card = None
    if card_id:
        query = db.query(CreditCard).filter_by(id=card_id, family_id=family_id, is_active=True)
        card = (query.with_for_update() if lock else query).first()
        if not card or card.card_type not in ('CREDIT', 'MULTIPLE'):
            raise HTTPException(400, detail='Selecione um cartão de crédito deste espaço.')
    query = db.query(FinancialAccount).filter_by(id=account_id, family_id=family_id, is_active=True)
    account = (query.with_for_update() if lock else query).first()
    if not account or account.account_type not in ('CHECKING', 'SAVINGS', 'WALLET'):
        raise HTTPException(400, detail='Selecione uma conta corrente, poupança ou carteira deste espaço.')
    return account, card


def dedupe_key(family_id, account_id, card_id, fingerprint):
    destination = f'card:{card_id}' if card_id else f'account:{account_id}'
    return hashlib.sha256(f'import:{family_id}:{destination}:{fingerprint}'.encode()).hexdigest()


def pdf_text(content):
    try:
        result = subprocess.run([sys.executable, '-m', 'app.services.pdf_extract'], input=content,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=18, cwd=Path(__file__).resolve().parents[3])
        if result.returncode or len(result.stdout) > 2_500_000:
            raise ValueError('Este PDF excede o limite de processamento. Divida-o ou exporte CSV/OFX.')
        data = json.loads(result.stdout)
        if data.get('error'):
            raise ValueError(data['error'])
        return data['text']
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        raise ValueError('O PDF demorou demais para ser processado. Divida-o ou exporte CSV/OFX.')


@router.post('/preview')
async def preview_statement(file: UploadFile = File(...), account_id: UUID = Form(...),
                            reference_month: str = Form(...), card_id: UUID | None = Form(None),
                            family: FamilySpace = Depends(get_current_family),
                            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    target(db, family.id, account_id, card_id)
    now = datetime.now(timezone.utc)
    rate_key = hashlib.sha256(f'import:{user.id}:{int(time.time() // 3600)}'.encode()).hexdigest()
    count = db.execute(insert(RateLimitBucket).values(key=rate_key, count=1, expires_at=now + timedelta(hours=2))
        .on_conflict_do_update(index_elements=['key'], set_={'count': RateLimitBucket.count + 1})
        .returning(RateLimitBucket.count)).scalar_one()
    db.commit()
    if count > 30:
        raise HTTPException(429, detail='Limite de 30 prévias por hora. Tente novamente mais tarde.')
    content = await file.read(4 * 1024 * 1024 + 1)
    await file.close()
    if len(content) > 4 * 1024 * 1024:
        raise HTTPException(413, detail='Envie um arquivo de até 4 MB.')
    extension = Path(file.filename or '').suffix.lower().lstrip('.')
    if extension not in ('pdf', 'csv', 'ofx'):
        raise HTTPException(400, detail='Use PDF com texto selecionável, CSV ou OFX.')
    try:
        reference = date.fromisoformat(reference_month + '-01')
        if not 2000 <= reference.year <= 2100:
            raise ValueError('Mês de referência inválido.')
        if extension == 'pdf':
            if not content.startswith(b'%PDF-'):
                raise ValueError('O conteúdo não corresponde a um PDF.')
            if _pdf_lock.locked():
                raise HTTPException(429, detail='Um PDF está sendo processado. Tente novamente em alguns segundos.')
            async with _pdf_lock:
                text = await run_in_threadpool(pdf_text, content)
        else:
            try:
                text = content.decode('utf-8-sig')
            except UnicodeDecodeError:
                text = content.decode('cp1252')
        rows, warnings = parse_statement(text, extension, reference, card=bool(card_id))
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc))
    statement = statement_summary(text, rows) if extension == 'pdf' else None
    if statement and not card_id:
        raise HTTPException(422, detail='Este PDF é uma fatura de cartão. Selecione Fatura de cartão de crédito e o cartão correspondente.')
    if statement and statement['totals_match'] is False:
        warnings.append('Os valores reconhecidos não fecham com o resumo do PDF. A confirmação ficará bloqueada para evitar uma importação incompleta.')
    rules = {rule.merchant_key: rule for rule in db.query(ImportMerchantRule).filter_by(family_id=family.id).all()}
    keys = [dedupe_key(family.id, account_id, card_id, row['fingerprint']) for row in rows]
    existing = {value for (value,) in db.query(Transaction.idempotency_key).filter(Transaction.idempotency_key.in_(keys)).all()}
    # Existing manual entries can only be suggested as duplicates, never silently discarded.
    dates = [date.fromisoformat(row['date']) for row in rows]
    prior = db.query(Transaction).filter(Transaction.family_id == family.id, Transaction.account_id == account_id if not card_id else True,
        Transaction.card_id == card_id, Transaction.date.between(min(dates), max(dates)), Transaction.is_deleted == False).all()
    prior_values = {(str(tx.date), str(Decimal(tx.amount).quantize(Decimal('.01'))), normalize(tx.description)) for tx in prior}
    paid_periods = {(i.year, i.month) for i in db.query(CardInvoice).filter(CardInvoice.card_id == card_id, CardInvoice.paid_amount > 0).all()} if card_id else set()
    _, card = target(db, family.id, account_id, card_id)
    from app.api.v1.cards import get_current_invoice_period
    output = []
    for row, key in zip(rows, keys):
        rule = rules.get(normalize(row['original_description']))
        description = rule.display_name if rule else row['original_description']
        if card and ((statement['year'], statement['month']) if statement else get_current_invoice_period(card, date.fromisoformat(row['date']))) in paid_periods:
            row['blocked'], row['warning'] = True, 'Fatura com pagamento: composição protegida. Faça o ajuste pelo fluxo de estorno.'
        output.append({**row, 'description': description, 'category_id': str(rule.category_id) if rule and rule.category_id else None,
                       'learned': bool(rule), 'duplicate': key in existing,
                       'possible_duplicate': (row['date'], row['amount'], normalize(description)) in prior_values})
    token = jwt.encode({'purpose': 'statement_preview', 'sub': str(user.id), 'family': str(family.id),
        'account': str(account_id), 'card': str(card_id) if card_id else None, 'rows': rows, 'statement': statement,
        'iat': now, 'exp': now + timedelta(minutes=30)}, settings.SECRET_KEY, algorithm='HS256')
    return {'preview_token': token, 'rows': output, 'warnings': warnings, 'statement': statement,
            'notice': 'Confira com o arquivo original. Saldos, totais e linhas não reconhecidas não são importados. Nenhum lançamento foi salvo.'}


@router.post('/confirm')
def confirm_statement(data: ImportConfirm, family: FamilySpace = Depends(get_current_family),
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(data.preview_token, settings.SECRET_KEY, algorithms=['HS256'], options={'require': ['exp', 'sub', 'purpose']})
    except jwt.PyJWTError:
        raise HTTPException(400, detail='A prévia expirou ou é inválida. Envie o arquivo novamente.')
    if payload.get('purpose') != 'statement_preview' or payload.get('sub') != str(user.id) or payload.get('family') != str(family.id):
        raise HTTPException(403, detail='Esta prévia pertence a outra conta ou espaço.')
    statement = payload.get('statement')
    if statement and statement['totals_match'] is False:
        raise HTTPException(409, detail='A leitura não fecha com o resumo do PDF. Nenhum lançamento foi salvo. Precisamos revisar este layout.')
    if statement and statement['requires_reconciliation'] and not data.reconciliation_reviewed:
        raise HTTPException(400, detail='Confira o resumo e reconheça que pagamentos e estornos precisam ser conciliados separadamente.')
    account_id = UUID(payload['account'])
    card_id = UUID(payload['card']) if payload['card'] else None
    _, card = target(db, family.id, account_id, card_id, lock=True)
    indices = [entry.index for entry in data.entries]
    if len(indices) != len(set(indices)):
        raise HTTPException(400, detail='A seleção contém linhas repetidas.')
    rows = payload['rows']
    categories = {str(c.id): c for c in db.query(Category).filter_by(family_id=family.id, is_active=True).all()}
    from app.api.v1.cards import get_current_invoice_period
    paid_periods = {(i.year, i.month) for i in db.query(CardInvoice).filter(CardInvoice.card_id == card_id, CardInvoice.paid_amount > 0).all()} if card_id else set()
    existing = {key for (key,) in db.query(Transaction.idempotency_key).filter(Transaction.idempotency_key.in_(
        [dedupe_key(family.id, account_id, card_id, row['fingerprint']) for row in rows])).all()}
    imported, skipped = 0, 0
    statement_invoice = None
    if statement and card:
        statement_invoice = db.query(CardInvoice).filter_by(card_id=card.id, year=statement['year'], month=statement['month']).first()
    for entry in data.entries:
        if entry.index >= len(rows):
            raise HTTPException(400, detail='Linha fora da prévia original.')
        row = rows[entry.index]
        if row['blocked']:
            raise HTTPException(400, detail='A seleção contém uma linha que exige tratamento manual.')
        if card and (entry.type != 'DESPESA' or ((statement['year'], statement['month']) if statement else get_current_invoice_period(card, date.fromisoformat(row['date']))) in paid_periods):
            raise HTTPException(409, detail='Cartão exige despesa e fatura sem pagamento. Atualize a prévia.')
        if row['type'] and row['type'] != entry.type:
            raise HTTPException(400, detail='O tipo difere do sinal identificado no arquivo.')
        category = categories.get(str(entry.category_id)) if entry.category_id else None
        if entry.category_id and (not category or category.type not in ('AMBOS', entry.type)):
            raise HTTPException(400, detail='Categoria inválida para este espaço ou tipo de lançamento.')
        key = dedupe_key(family.id, account_id, card_id, row['fingerprint'])
        if key in existing:
            skipped += 1
            continue
        if statement and card and statement_invoice is None:
            from app.api.v1.cards import get_invoice_cycle_dates
            _, closing, _ = get_invoice_cycle_dates(card, statement['year'], statement['month'])
            if statement.get('closing_date'):
                closing = date.fromisoformat(statement['closing_date'])
            statement_invoice = CardInvoice(family_id=family.id, card_id=card.id, year=statement['year'], month=statement['month'],
                closing_date=closing, due_date=date.fromisoformat(statement['due_date']), total_amount=Decimal('0.00'), paid_amount=Decimal('0.00'), status='ABERTA')
            db.add(statement_invoice)
            db.flush()
        if statement and statement_invoice:
            if statement.get('closing_date'):
                statement_invoice.closing_date = date.fromisoformat(statement['closing_date'])
            statement_invoice.due_date = date.fromisoformat(statement['due_date'])
        transaction = Transaction(family_id=family.id, created_by_id=user.id, date=date.fromisoformat(row['date']),
            description=entry.description, type=entry.type, amount=Decimal(row['amount']), account_id=account_id,
            card_id=card_id, invoice_id=statement_invoice.id if statement_invoice else None, category_id=entry.category_id, classification=category.classification if category else 'NECESSIDADE',
            responsible_name=card.responsible_name or 'Família' if card else 'Família', is_shared=True,
            status='REALIZADA', idempotency_key=key, notes='Importado de extrato. Descrição original: ' + row['original_description'])
        db.add(transaction)
        existing.add(key)
        imported += 1
        if entry.remember and normalize(row['original_description']):
            db.execute(insert(ImportMerchantRule).values(family_id=family.id, merchant_key=normalize(row['original_description']),
                display_name=entry.description, category_id=entry.category_id, updated_at=datetime.now(timezone.utc))
                .on_conflict_do_update(constraint='uq_import_merchant_family', set_={
                    'display_name': entry.description, 'category_id': entry.category_id, 'updated_at': datetime.now(timezone.utc)}))
    AuditService.log(db, family.id, user.id, 'IMPORT_STATEMENT', 'ACCOUNT', str(account_id),
                     new_values={'imported': imported, 'skipped': skipped, 'card_id': str(card_id) if card_id else None})
    db.commit()
    return {'imported': imported, 'skipped': skipped}


@router.get('/rules')
def merchant_rules(family: FamilySpace = Depends(get_current_family), db: Session = Depends(get_db)):
    return [{'id': str(r.id), 'merchant': r.merchant_key, 'description': r.display_name, 'category_id': str(r.category_id) if r.category_id else None}
            for r in db.query(ImportMerchantRule).filter_by(family_id=family.id).order_by(ImportMerchantRule.display_name).all()]


@router.delete('/rules/{rule_id}')
def remove_rule(rule_id: UUID, family: FamilySpace = Depends(get_current_family), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rule = db.query(ImportMerchantRule).filter_by(id=rule_id, family_id=family.id).first()
    if not rule:
        raise HTTPException(404, detail='Regra não encontrada.')
    db.delete(rule)
    AuditService.log(db, family.id, user.id, 'DELETE', 'IMPORT_RULE', str(rule_id))
    db.commit()
    return {'removed': True}
