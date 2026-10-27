from typing import Generator, Optional
from uuid import UUID
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User
from app.models.family import FamilySpace, FamilyMembership

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login",
    auto_error=False
)


def get_current_user(
    db: Session = Depends(get_db),
    token: Optional[str] = Depends(reusable_oauth2)
) -> User:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Não autenticado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
        )
    try:
        user_uuid = UUID(user_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=401, detail="Token inválido")
    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado",
        )
    if payload.get("ver") != user.token_version:
        raise HTTPException(status_code=401, detail="Sessão revogada")
    db.info["user_id"] = user.id
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário inativo",
        )
    return user


def get_current_family(
    x_family_id: Optional[str] = Header(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> FamilySpace:
    """
    Retrieves the current family space and validates that current_user has access to it.
    If x_family_id is not provided, defaults to the user's first family membership.
    """
    family_uuid: Optional[UUID] = None
    if x_family_id:
        try:
            family_uuid = UUID(x_family_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Formato de ID de família inválido"
            )

    query = db.query(FamilyMembership).filter(FamilyMembership.user_id == current_user.id)
    if family_uuid:
        query = query.filter(FamilyMembership.family_id == family_uuid)
    
    membership = query.first()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado a este espaço financeiro"
        )

    family = db.query(FamilySpace).filter(FamilySpace.id == membership.family_id).first()
    if not family:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Espaço financeiro não encontrado"
        )
    db.info["family_id"] = family.id
    return family


def get_admin_family(current_family: FamilySpace = Depends(get_current_family),
                     current_user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)) -> FamilySpace:
    membership = db.query(FamilyMembership).filter_by(family_id=current_family.id, user_id=current_user.id).first()
    if membership.role not in ("OWNER", "ADMIN"):
        raise HTTPException(403, detail="Operação restrita a administradores")
    return current_family
