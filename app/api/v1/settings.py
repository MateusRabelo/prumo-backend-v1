from decimal import Decimal
from datetime import date
from typing import Any, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_user, get_current_family, get_admin_family
from app.models.user import User
from app.models.family import FamilySpace
from app.models.category import Category
from app.models.account import FinancialAccount
from app.models.payment_method import PaymentMethod
from app.models.responsible import ResponsiblePerson
from app.models.transaction import Transaction
from app.schemas.settings import (
    CategoryCreate,
    CategoryUpdate,
    CategoryResponse,
    AccountCreate,
    AccountUpdate,
    AccountResponse,
    PaymentMethodCreate,
    PaymentMethodUpdate,
    PaymentMethodResponse,
    ResponsibleCreate,
    ResponsibleUpdate,
    ResponsibleResponse,
)

router = APIRouter(prefix="/settings", tags=["Configurações"])


# ===================== CATEGORIES =====================
@router.get("/categories", response_model=List[CategoryResponse])
def get_categories(
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    return db.query(Category).filter(
        Category.family_id == current_family.id,
        Category.is_active == True
    ).order_by(Category.order_index.asc(), Category.name.asc()).all()


@router.post("/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    data: CategoryCreate,
    current_family: FamilySpace = Depends(get_admin_family),
    db: Session = Depends(get_db)
) -> Any:
    category = Category(
        family_id=current_family.id,
        name=data.name,
        color=data.color,
        icon=data.icon,
        classification=data.classification,
        type=data.type,
        order_index=data.order_index,
        is_active=True
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.put("/categories/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: UUID,
    data: CategoryUpdate,
    current_family: FamilySpace = Depends(get_admin_family),
    db: Session = Depends(get_db)
) -> Any:
    category = db.query(Category).filter(
        Category.id == category_id,
        Category.family_id == current_family.id
    ).first()
    if not category:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    update_dict = data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(category, key, value)

    db.commit()
    db.refresh(category)
    return category


@router.delete("/categories/{category_id}", status_code=status.HTTP_200_OK)
def deactivate_category(
    category_id: UUID,
    current_family: FamilySpace = Depends(get_admin_family),
    db: Session = Depends(get_db)
) -> Any:
    category = db.query(Category).filter(
        Category.id == category_id,
        Category.family_id == current_family.id
    ).first()
    if not category:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    # Soft deactivate so historical transactions remain valid
    category.is_active = False
    db.commit()
    return {"message": "Categoria desativada com sucesso"}


# ===================== FINANCIAL ACCOUNTS =====================
def compute_account_balance(db: Session, account: FinancialAccount) -> Decimal:
    """
    Computes exact real balance:
    initial_balance + Realized Income - Realized Expense + Incoming Transfers - Outgoing Transfers
    """
    if account.initial_balance_date > date.today():
        return Decimal("0.00")
    initial = Decimal(str(account.initial_balance))

    # Realized Income on this account
    income_sum = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.account_id == account.id,
        Transaction.family_id == account.family_id,
        Transaction.date >= account.initial_balance_date,
        Transaction.date <= date.today(),
        Transaction.type == "RECEITA",
        Transaction.status == "REALIZADA",
        Transaction.is_deleted == False
    ).scalar()

    # Realized Expense on this account (excludes credit card purchases which are settled via invoice payment)
    expense_sum = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.account_id == account.id,
        Transaction.family_id == account.family_id,
        Transaction.date >= account.initial_balance_date,
        Transaction.date <= date.today(),
        Transaction.type == "DESPESA",
        Transaction.status == "REALIZADA",
        Transaction.is_deleted == False,
        ((Transaction.payment_mode != "CREDIT") | (Transaction.is_invoice_payment == True))
    ).scalar()

    # Incoming transfers to this account
    incoming_transfers = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.destination_account_id == account.id,
        Transaction.family_id == account.family_id,
        Transaction.date >= account.initial_balance_date,
        Transaction.date <= date.today(),
        Transaction.type == "TRANSFERENCIA",
        Transaction.status == "REALIZADA",
        Transaction.is_deleted == False
    ).scalar()

    # Outgoing transfers from this account
    outgoing_transfers = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.account_id == account.id,
        Transaction.family_id == account.family_id,
        Transaction.date >= account.initial_balance_date,
        Transaction.date <= date.today(),
        Transaction.type == "TRANSFERENCIA",
        Transaction.status == "REALIZADA",
        Transaction.is_deleted == False
    ).scalar()

    total = initial + Decimal(str(income_sum)) - Decimal(str(expense_sum)) + Decimal(str(incoming_transfers)) - Decimal(str(outgoing_transfers))
    return total.quantize(Decimal("0.01"))


@router.get("/accounts", response_model=List[AccountResponse])
def get_accounts(
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    accounts = db.query(FinancialAccount).filter(
        FinancialAccount.family_id == current_family.id,
        FinancialAccount.is_active == True
    ).order_by(FinancialAccount.name.asc()).all()

    result = []
    for acc in accounts:
        cur_bal = compute_account_balance(db, acc)
        resp = AccountResponse(
            id=acc.id,
            family_id=acc.family_id,
            name=acc.name,
            account_type=acc.account_type,
            bank_name=acc.bank_name,
            agency=acc.agency,
            account_number=acc.account_number,
            initial_balance=acc.initial_balance,
            initial_balance_date=acc.initial_balance_date,
            color=acc.color,
            is_active=acc.is_active,
            current_balance=cur_bal,
            created_at=acc.created_at
        )
        result.append(resp)
    return result


@router.post("/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(
    data: AccountCreate,
    current_family: FamilySpace = Depends(get_admin_family),
    db: Session = Depends(get_db)
) -> Any:
    account = FinancialAccount(
        family_id=current_family.id,
        name=data.name,
        account_type=data.account_type,
        bank_name=data.bank_name,
        agency=data.agency,
        account_number=data.account_number,
        initial_balance=data.initial_balance,
        initial_balance_date=data.initial_balance_date,
        color=data.color,
        is_active=True
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    
    resp = AccountResponse(
        id=account.id,
        family_id=account.family_id,
        name=account.name,
        account_type=account.account_type,
        bank_name=account.bank_name,
        agency=account.agency,
        account_number=account.account_number,
        initial_balance=account.initial_balance,
        initial_balance_date=account.initial_balance_date,
        color=account.color,
        is_active=account.is_active,
        current_balance=account.initial_balance,
        created_at=account.created_at
    )
    return resp


@router.put("/accounts/{account_id}", response_model=AccountResponse)
def update_account(
    account_id: UUID,
    data: AccountUpdate,
    current_family: FamilySpace = Depends(get_admin_family),
    db: Session = Depends(get_db)
) -> Any:
    account = db.query(FinancialAccount).filter(
        FinancialAccount.id == account_id,
        FinancialAccount.family_id == current_family.id
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")

    update_dict = data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(account, key, value)

    db.commit()
    db.refresh(account)
    cur_bal = compute_account_balance(db, account)
    
    return AccountResponse(
        id=account.id,
        family_id=account.family_id,
        name=account.name,
        account_type=account.account_type,
        bank_name=account.bank_name,
        agency=account.agency,
        account_number=account.account_number,
        initial_balance=account.initial_balance,
        initial_balance_date=account.initial_balance_date,
        color=account.color,
        is_active=account.is_active,
        current_balance=cur_bal,
        created_at=account.created_at
    )


@router.delete("/accounts/{account_id}", status_code=status.HTTP_200_OK)
def deactivate_account(
    account_id: UUID,
    current_family: FamilySpace = Depends(get_admin_family),
    db: Session = Depends(get_db)
) -> Any:
    account = db.query(FinancialAccount).filter(
        FinancialAccount.id == account_id,
        FinancialAccount.family_id == current_family.id
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")

    account.is_active = False
    db.commit()
    return {"message": "Conta desativada com sucesso"}


# ===================== PAYMENT METHODS =====================
@router.get("/payment-methods", response_model=List[PaymentMethodResponse])
def get_payment_methods(
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    return db.query(PaymentMethod).filter(
        PaymentMethod.family_id == current_family.id,
        PaymentMethod.is_active == True
    ).order_by(PaymentMethod.name.asc()).all()


@router.post("/payment-methods", response_model=PaymentMethodResponse, status_code=status.HTTP_201_CREATED)
def create_payment_method(
    data: PaymentMethodCreate,
    current_family: FamilySpace = Depends(get_admin_family),
    db: Session = Depends(get_db)
) -> Any:
    method = PaymentMethod(
        family_id=current_family.id,
        name=data.name,
        is_active=True
    )
    db.add(method)
    db.commit()
    db.refresh(method)
    return method


# ===================== RESPONSIBLE PERSONS =====================
@router.get("/responsibles", response_model=List[ResponsibleResponse])
def get_responsibles(
    current_family: FamilySpace = Depends(get_current_family),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Any:
    from app.services.responsibles import sync_responsibles
    sync_responsibles(db, current_family.id)
    db.commit()
    people = db.query(ResponsiblePerson).filter_by(family_id=current_family.id, is_active=True).all()
    people.sort(key=lambda p: (p.user_id != current_user.id, p.is_shared, p.name))
    return [ResponsibleResponse.model_validate(p).model_copy(update={'is_current_user': p.user_id == current_user.id}) for p in people]


@router.post("/responsibles", response_model=ResponsibleResponse, status_code=status.HTTP_201_CREATED)
def create_responsible(
    data: ResponsibleCreate,
    current_family: FamilySpace = Depends(get_admin_family),
    db: Session = Depends(get_db)
) -> Any:
    responsible = ResponsiblePerson(
        family_id=current_family.id,
        name=data.name,
        is_shared=data.is_shared,
        is_active=True
    )
    db.add(responsible)
    db.commit()
    db.refresh(responsible)
    return responsible


@router.put("/responsibles/{resp_id}", response_model=ResponsibleResponse)
def update_responsible(
    resp_id: UUID,
    data: ResponsibleUpdate,
    current_family: FamilySpace = Depends(get_admin_family),
    db: Session = Depends(get_db)
) -> Any:
    responsible = db.query(ResponsiblePerson).filter(
        ResponsiblePerson.id == resp_id,
        ResponsiblePerson.family_id == current_family.id
    ).first()
    if not responsible:
        raise HTTPException(status_code=404, detail="Responsável não encontrado")

    if responsible.is_system:
        from app.models.family import FamilyMembership
        if not responsible.user_id:
            raise HTTPException(409, detail='Conjunto é gerenciado automaticamente pelos membros do espaço')
        if data.is_shared or data.is_active is False:
            raise HTTPException(409, detail='Responsável de um membro ativo não pode ser desativado ou compartilhado')
        if data.name:
            membership = db.query(FamilyMembership).filter_by(family_id=current_family.id, user_id=responsible.user_id).one()
            membership.alias_name = data.name
    update_dict = data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(responsible, key, value)

    db.commit()
    db.refresh(responsible)
    return responsible
