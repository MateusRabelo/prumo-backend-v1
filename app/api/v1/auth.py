from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_user
from app.core.security import create_access_token
from app.models.user import User
from app.models.family import FamilyMembership, FamilySpace
from app.schemas.auth import (
    UserRegister,
    UserLogin,
    UserResponse,
    Token,
    PasswordChange,
    PasswordResetRequest,
    PasswordResetConfirm,
)
from app.schemas.family import FamilyResponse
from app.services.auth_service import AuthService
from app.services.family_service import list_user_families

from app.api.rate_limit import limit_auth
from app.services.password_reset import request_reset, confirm_reset

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/register", dependencies=[Depends(limit_auth)], response_model=Token, status_code=status.HTTP_201_CREATED)
def register(data: UserRegister, db: Session = Depends(get_db)) -> Any:
    user, family = AuthService.register_user(db, data)
    token = create_access_token(subject=str(user.id), token_version=user.token_version)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user,
        "current_family_id": family.id
    }


@router.post("/login", dependencies=[Depends(limit_auth)], response_model=Token)
def login(data: UserLogin, db: Session = Depends(get_db)) -> Any:
    user, family = AuthService.authenticate_user(db, data)
    token = create_access_token(subject=str(user.id), token_version=user.token_version)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user,
        "current_family_id": family.id if family else None
    }


@router.get("/me", response_model=UserResponse)
def get_current_user_profile(current_user: User = Depends(get_current_user)) -> Any:
    return current_user


@router.get("/my-families", response_model=List[FamilyResponse])
def get_my_families(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Any:
    return list_user_families(db, current_user.id)


@router.post("/change-password", status_code=status.HTTP_200_OK)
def change_password(
    data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Any:
    AuthService.change_password(db, current_user, data)
    return {"message": "Senha alterada com sucesso"}


@router.post("/recover-password", dependencies=[Depends(limit_auth)], status_code=status.HTTP_200_OK)
def recover_password(data: PasswordResetRequest, db: Session = Depends(get_db)) -> Any:
    request_reset(db, str(data.email))
    return {"message": "Se o email estiver cadastrado, as instruções de recuperação foram enviadas."}


@router.post("/reset-password", dependencies=[Depends(limit_auth)])
def reset_password(data: PasswordResetConfirm, db: Session = Depends(get_db)):
    confirm_reset(db, data.token, data.new_password)
    return {"message": "Senha redefinida com sucesso"}


@router.post("/logout")
def logout(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.token_version += 1
    db.commit()
    return {"message": "Todas as sessões foram encerradas"}
