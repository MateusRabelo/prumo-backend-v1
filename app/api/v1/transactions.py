import csv
import io
from datetime import date
from decimal import Decimal
from typing import Any, List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, case
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_user, get_current_family
from app.domain.financial_engine import FinancialEngine
from app.models.user import User
from app.models.family import FamilySpace
from app.models.transaction import Transaction
from app.models.category import Category
from app.models.account import FinancialAccount
from app.models.payment_method import PaymentMethod
from app.schemas.transaction import (
    TransactionCreate,
    TransactionUpdate,
    TransactionResponse,
    TransactionSummary,
    TransactionListResponse,
)
from app.services.audit_service import AuditService
from app.services.validation import lock_transaction_context, validate_card_periods, validate_relations, validate_transaction, protect_linked_transaction

def transaction_snapshot(transaction):
    return {column.name: (value if value is None or isinstance(value, (str, int, bool, float)) else str(value))
            for column in Transaction.__table__.columns
            for value in [getattr(transaction, column.name)]}


router = APIRouter(prefix="/transactions", tags=["Transações"])


def transaction_to_schema(t: Transaction) -> TransactionResponse:
    from app.api.v1.cards import MONTH_NAMES
    return TransactionResponse(
        invoice_id=t.invoice_id,
        invoice_label=f"{MONTH_NAMES[t.invoice.month - 1]} / {t.invoice.year}" if t.invoice else None,
        id=t.id,
        family_id=t.family_id,
        created_by_id=t.created_by_id,
        date=t.date,
        description=t.description,
        type=t.type,
        amount=t.amount,
        category_id=t.category_id,
        category_name=t.category.name if t.category else None,
        category_color=t.category.color if t.category else None,
        account_id=t.account_id,
        account_name=t.account.name if t.account else None,
        destination_account_id=t.destination_account_id,
        destination_account_name=t.destination_account.name if t.destination_account else None,
        payment_mode=t.payment_mode,
        card_id=t.card_id,
        card_name=t.card.name if t.card else None,
        responsible_name=t.responsible_name,
        is_shared=t.is_shared,
        classification=t.classification,
        payment_method_id=t.payment_method_id,
        payment_method_name=t.payment_method.name if t.payment_method else None,
        status=t.status,
        notes=t.notes,
        installment_id=t.installment_id,
        recurrence_id=t.recurrence_id,
        is_deleted=t.is_deleted,
        created_at=t.created_at,
        updated_at=t.updated_at
    )


@router.get("/", response_model=TransactionListResponse)
def list_transactions(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    type: Optional[str] = None,
    category_id: Optional[UUID] = None,
    account_id: Optional[UUID] = None,
    responsible_name: Optional[str] = None,
    classification: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    query = db.query(Transaction).filter(
        Transaction.family_id == current_family.id,
        Transaction.is_deleted == False
    )

    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)
    if type:
        query = query.filter(Transaction.type == type)
    if category_id:
        query = query.filter(Transaction.category_id == category_id)
    if account_id:
        query = query.filter(or_(Transaction.account_id == account_id, Transaction.destination_account_id == account_id))
    if responsible_name:
        query = query.filter(Transaction.responsible_name == responsible_name)
    if classification:
        query = query.filter(Transaction.classification == classification)
    if status_filter:
        query = query.filter(Transaction.status == status_filter)
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            or_(
                Transaction.description.ilike(search_filter),
                Transaction.notes.ilike(search_filter)
            )
        )

    # Calculate summary metrics based on the exact same filtered query
    total_count = query.count()

    def total(kind, statuses):
        return query.with_entities(func.coalesce(func.sum(case(
            ((Transaction.type == kind) & Transaction.status.in_(statuses) & (Transaction.is_invoice_payment == False), Transaction.amount),
            else_=0)), 0)).scalar()

    realized_income = total("RECEITA", ["REALIZADA"])
    realized_expense = total("DESPESA", ["REALIZADA"])
    pending_income = total("RECEITA", ["PENDENTE", "VENCIDA"])
    pending_expense = total("DESPESA", ["PENDENTE", "VENCIDA"])

    realized_net = FinancialEngine.calculate_net_result(realized_income, realized_expense)

    summary = TransactionSummary(
        total_realized_income=realized_income,
        total_realized_expense=realized_expense,
        realized_net=realized_net,
        total_pending_income=pending_income,
        total_pending_expense=pending_expense,
        count=total_count
    )

    items = query.order_by(Transaction.date.desc(), Transaction.created_at.desc()).offset(skip).limit(limit).all()
    item_responses = [transaction_to_schema(t) for t in items]

    return TransactionListResponse(
        items=item_responses,
        total=total_count,
        skip=skip,
        limit=limit,
        summary=summary
    )


@router.post("/", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
def create_transaction(
    data: TransactionCreate,
    current_user: User = Depends(get_current_user),
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    from app.services.card_flow import resolve_card_flow, ensure_invoice
    values = data.model_dump()
    card = resolve_card_flow(db, current_family.id, values)
    data = data.model_copy(update=values)
    validate_relations(db, current_family.id, values)
    validate_card_periods(db, current_family.id, data.model_dump())
    validate_transaction(data.model_dump())
    # Validate account belongs to current family
    account = db.query(FinancialAccount).filter(
        FinancialAccount.id == data.account_id,
        FinancialAccount.family_id == current_family.id
    ).first()
    if not account:
        raise HTTPException(status_code=400, detail="Conta financeira inválida")

    if data.destination_account_id:
        dest_account = db.query(FinancialAccount).filter(
            FinancialAccount.id == data.destination_account_id,
            FinancialAccount.family_id == current_family.id
        ).first()
        if not dest_account:
            raise HTTPException(status_code=400, detail="Conta de destino inválida")

    if data.category_id:
        category = db.query(Category).filter(
            Category.id == data.category_id,
            Category.family_id == current_family.id
        ).first()
        if not category:
            raise HTTPException(status_code=400, detail="Categoria inválida")

    if card and data.payment_mode == 'CREDIT' and not data.invoice_id:
        data = data.model_copy(update={'invoice_id': ensure_invoice(db, current_family.id, card, data.date).id})
    transaction = Transaction(
        payment_mode=data.payment_mode,
        family_id=current_family.id,
        created_by_id=current_user.id,
        date=data.date,
        description=data.description,
        type=data.type,
        amount=data.amount,
        category_id=data.category_id,
        account_id=data.account_id,
        destination_account_id=data.destination_account_id,
        card_id=data.card_id,
        invoice_id=data.invoice_id,
        responsible_name=data.responsible_name,
        is_shared=data.is_shared,
        classification=data.classification,
        payment_method_id=data.payment_method_id,
        status=data.status,
        notes=data.notes,
        is_deleted=False
    )
    db.add(transaction)
    db.flush()

    # Log audit entry
    AuditService.log(
        db=db,
        family_id=current_family.id,
        user_id=current_user.id,
        action="CREATE",
        entity_type="TRANSACTION",
        entity_id=str(transaction.id),
        new_values={
            "description": transaction.description,
            "type": transaction.type,
            "amount": str(transaction.amount),
            "status": transaction.status,
            "date": str(transaction.date)
        }
    )

    db.commit()
    db.refresh(transaction)
    return transaction_to_schema(transaction)


@router.get("/{transaction_id}", response_model=TransactionResponse)
def get_transaction(
    transaction_id: UUID,
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.family_id == current_family.id,
        Transaction.is_deleted == False
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transação não encontrada")
    return transaction_to_schema(transaction)


@router.put("/{transaction_id}", response_model=TransactionResponse)
def update_transaction(
    transaction_id: UUID,
    data: TransactionUpdate,
    current_user: User = Depends(get_current_user),
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.family_id == current_family.id,
        Transaction.is_deleted == False
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transação não encontrada")

    lock_transaction_context(db, transaction, data.card_id)
    protect_linked_transaction(db, transaction)
    merged = {column.name: getattr(transaction, column.name) for column in Transaction.__table__.columns}
    merged.update(data.model_dump(exclude_unset=True))
    from app.services.card_flow import resolve_card_flow, ensure_invoice
    if transaction.invoice_id and data.payment_mode == 'DEBIT':
        raise HTTPException(409, detail='Uma compra já vinculada à fatura não pode virar débito')
    card = resolve_card_flow(db, current_family.id, merged)
    validate_relations(db, current_family.id, merged)
    validate_transaction(merged)
    validate_card_periods(db, current_family.id, merged)

    old_values = transaction_snapshot(transaction)

    update_dict = data.model_dump(exclude_unset=True)
    update_dict.update({'account_id': merged['account_id'], 'payment_mode': merged['payment_mode']})
    if card and merged['payment_mode'] == 'CREDIT' and not merged.get('invoice_id'):
        update_dict['invoice_id'] = ensure_invoice(db, current_family.id, card, merged['date']).id
    for key, value in update_dict.items():
        setattr(transaction, key, value)

    AuditService.log(
        db=db,
        family_id=current_family.id,
        user_id=current_user.id,
        action="UPDATE",
        entity_type="TRANSACTION",
        entity_id=str(transaction.id),
        old_values=old_values,
        new_values=transaction_snapshot(transaction)
    )

    db.commit()
    db.refresh(transaction)
    return transaction_to_schema(transaction)


@router.delete("/{transaction_id}", status_code=status.HTTP_200_OK)
def delete_transaction(
    transaction_id: UUID,
    current_user: User = Depends(get_current_user),
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.family_id == current_family.id,
        Transaction.is_deleted == False
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transação não encontrada")

    lock_transaction_context(db, transaction)
    protect_linked_transaction(db, transaction)
    # Soft delete with audit log
    transaction.is_deleted = True

    AuditService.log(
        db=db,
        family_id=current_family.id,
        user_id=current_user.id,
        action="DELETE",
        entity_type="TRANSACTION",
        entity_id=str(transaction.id),
        old_values={
            "description": transaction.description,
            "amount": str(transaction.amount),
            "status": transaction.status
        }
    )

    db.commit()
    return {"message": "Transação excluída com sucesso"}


@router.post("/{transaction_id}/duplicate", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
def duplicate_transaction(
    transaction_id: UUID,
    current_user: User = Depends(get_current_user),
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    original = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.family_id == current_family.id,
        Transaction.is_deleted == False
    ).first()
    if not original:
        raise HTTPException(status_code=404, detail="Transação original não encontrada")

    lock_transaction_context(db, original)
    protect_linked_transaction(db, original)
    validate_card_periods(db, current_family.id, {"card_id": original.card_id, "date": date.today()})
    duplicated = Transaction(
        family_id=current_family.id,
        created_by_id=current_user.id,
        date=date.today(),
        description=f"{original.description} (Cópia)",
        type=original.type,
        amount=original.amount,
        category_id=original.category_id,
        account_id=original.account_id,
        destination_account_id=original.destination_account_id,
        card_id=original.card_id,
        payment_mode=original.payment_mode,
        responsible_name=original.responsible_name,
        is_shared=original.is_shared,
        classification=original.classification,
        payment_method_id=original.payment_method_id,
        status="PENDENTE" if original.type == "DESPESA" else "REALIZADA",
        notes=original.notes,
        is_deleted=False
    )
    db.add(duplicated)
    db.flush()

    AuditService.log(
        db=db,
        family_id=current_family.id,
        user_id=current_user.id,
        action="CREATE",
        entity_type="TRANSACTION",
        entity_id=str(duplicated.id),
        new_values={"duplicated_from": str(original.id)}
    )

    db.commit()
    db.refresh(duplicated)
    return transaction_to_schema(duplicated)


@router.get("/export/csv")
def export_transactions_csv(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    type: Optional[str] = None,
    category_id: Optional[UUID] = None,
    account_id: Optional[UUID] = None,
    responsible_name: Optional[str] = None,
    classification: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
):
    query = db.query(Transaction).filter(
        Transaction.family_id == current_family.id,
        Transaction.is_deleted == False
    )
    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)
    if type:
        query = query.filter(Transaction.type == type)
    if category_id:
        query = query.filter(Transaction.category_id == category_id)
    if account_id:
        query = query.filter(or_(Transaction.account_id == account_id, Transaction.destination_account_id == account_id))
    if responsible_name:
        query = query.filter(Transaction.responsible_name == responsible_name)
    if classification:
        query = query.filter(Transaction.classification == classification)
    if status_filter:
        query = query.filter(Transaction.status == status_filter)

    if query.count() > 10000:
        raise HTTPException(400, detail="Exportação limitada a 10000 registros. Reduza o período.")
    transactions = query.order_by(Transaction.date.desc()).all()

    output = io.StringIO()
    # Write UTF-8 BOM so Excel opens it with accents correctly
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';')
    writer.writerow([
        "Data", "Descrição", "Tipo", "Valor (R$)", "Categoria", "Conta",
        "Responsável", "Conjunto/Individual", "Classificação", "Forma Pagamento", "Status", "Observações"
    ])

    def safe_cell(value):
        if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
            return "'" + value
        return value

    for t in transactions:
        writer.writerow([safe_cell(value) for value in [
            t.date.strftime("%d/%m/%Y"),
            t.description,
            t.type,
            f"{t.amount:.2f}".replace('.', ','),
            t.category.name if t.category else "",
            t.account.name if t.account else "",
            t.responsible_name,
            "Conjunto" if t.is_shared else "Individual",
            t.classification,
            t.payment_method.name if t.payment_method else "",
            t.status,
            t.notes or ""
        ]])

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=msfinancas_transacoes_{date.today()}.csv"}
    )
