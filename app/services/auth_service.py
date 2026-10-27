from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.core.security import get_password_hash, verify_password, create_access_token
from app.models.user import User
from app.models.family import FamilySpace, FamilyMembership
from app.models.category import Category
from app.models.payment_method import PaymentMethod
from app.models.responsible import ResponsiblePerson
from app.models.account import FinancialAccount
from app.schemas.auth import UserRegister, UserLogin, PasswordChange


class AuthService:
    @staticmethod
    def register_user(db: Session, data: UserRegister) -> tuple[User, FamilySpace]:
        # Check if email already exists
        existing = db.query(User).filter(User.email == data.email.lower()).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email já cadastrado no sistema"
            )

        # 1. Create User
        user = User(
            email=data.email.lower(),
            hashed_password=get_password_hash(data.password),
            full_name=data.full_name,
            is_active=True
        )
        db.add(user)
        db.flush()

        # 2. Create Default Family Space
        family_name = f"Família {data.full_name.split()[0]}"
        family = FamilySpace(
            name=family_name,
            owner_id=user.id,
            currency="BRL"
        )
        db.add(family)
        db.flush()

        # 3. Create Membership as OWNER
        member = FamilyMembership(
            family_id=family.id,
            user_id=user.id,
            role="OWNER",
            alias_name=data.full_name.split()[0]
        )
        db.add(member)

        # 4. Create Default Categories
        default_categories = [
            ("Moradia", "#3B82F6", "home", "NECESSIDADE", "DESPESA", 1),
            ("Alimentação", "#10B981", "utensils", "NECESSIDADE", "DESPESA", 2),
            ("Transporte", "#F59E0B", "car", "NECESSIDADE", "DESPESA", 3),
            ("Saúde", "#EF4444", "heart", "NECESSIDADE", "DESPESA", 4),
            ("Educação", "#8B5CF6", "book-open", "NECESSIDADE", "DESPESA", 5),
            ("Lazer", "#EC4899", "film", "DESEJO", "DESPESA", 6),
            ("Investimentos", "#059669", "trending-up", "INVESTIMENTO", "DESPESA", 7),
            ("Salário", "#10B981", "briefcase", "NECESSIDADE", "RECEITA", 8),
            ("Renda Extra", "#3B82F6", "wallet", "DESEJO", "RECEITA", 9),
            ("Outros", "#6B7280", "more-horizontal", "DESEJO", "DESPESA", 10),
        ]
        for name, color, icon, classif, cat_type, order_idx in default_categories:
            db.add(Category(
                family_id=family.id,
                name=name,
                color=color,
                icon=icon,
                classification=classif,
                type=cat_type,
                order_index=order_idx,
                is_active=True
            ))

        # 5. Create Default Payment Methods
        default_methods = [
            "Dinheiro",
            "Pix",
            "Cartão de débito",
            "Cartão de crédito",
            "Transferência",
            "Boleto",
            "Outros"
        ]
        for method_name in default_methods:
            db.add(PaymentMethod(
                family_id=family.id,
                name=method_name,
                is_active=True
            ))

        from app.services.responsibles import sync_responsibles
        sync_responsibles(db, family.id)

        # 7. Create Default Account
        db.add(FinancialAccount(
            family_id=family.id,
            name="Conta Principal",
            account_type="CHECKING",
            initial_balance=0.00,
            color="#2563EB",
            is_active=True
        ))

        db.commit()
        db.refresh(user)
        db.refresh(family)
        return user, family

    @staticmethod
    def authenticate_user(db: Session, data: UserLogin) -> tuple[User, FamilySpace]:
        user = db.query(User).filter(User.email == data.email.lower()).first()
        if not user or not verify_password(data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email ou senha incorretos",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Usuário inativo"
            )

        # Retrieve user's primary family
        membership = db.query(FamilyMembership).filter(
            FamilyMembership.user_id == user.id
        ).order_by(FamilyMembership.joined_at.asc()).first()
        
        family = None
        if membership:
            family = db.query(FamilySpace).filter(FamilySpace.id == membership.family_id).first()
            
        return user, family

    @staticmethod
    def change_password(db: Session, user: User, data: PasswordChange) -> None:
        if not verify_password(data.current_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Senha atual incorreta"
            )
        user.hashed_password = get_password_hash(data.new_password)
        user.token_version += 1
        db.commit()
