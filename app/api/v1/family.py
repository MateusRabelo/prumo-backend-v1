import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Any, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_user, get_current_family, get_admin_family
from app.models.user import User
from app.models.family import FamilySpace, FamilyMembership, FamilyInvitation
from app.services.family_service import list_user_families
from app.schemas.family import (
    FamilyCreate,
    FamilyResponse,
    FamilyMemberResponse,
    FamilyInviteCreate,
    FamilyInviteResponse,
    FamilyInviteSummary,
    FamilyInviteAccept,
)

router = APIRouter(prefix="/family", tags=["Espaço Familiar"])


@router.get("/current", response_model=FamilyResponse)
def get_current_family_info(current_family: FamilySpace = Depends(get_current_family),
                            current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Any:
    return next(f for f in list_user_families(db, current_user.id) if f.id == current_family.id)


@router.post("/", response_model=FamilyResponse, status_code=status.HTTP_201_CREATED)
def create_family_space(
    data: FamilyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Any:
    family = FamilySpace(
        name=data.name,
        owner_id=current_user.id,
        currency=data.currency
    )
    db.add(family)
    db.flush()

    membership = FamilyMembership(
        family_id=family.id,
        user_id=current_user.id,
        role="OWNER",
        alias_name=current_user.full_name.split()[0]
    )
    db.add(membership)
    db.commit()
    db.refresh(family)
    return family


@router.get("/members", response_model=List[FamilyMemberResponse])
def get_family_members(
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    members = db.query(FamilyMembership).filter(FamilyMembership.family_id == current_family.id).all()
    result = []
    for m in members:
        user = db.query(User).filter(User.id == m.user_id).first()
        result.append(FamilyMemberResponse(
            id=m.id,
            family_id=m.family_id,
            user_id=m.user_id,
            role=m.role,
            alias_name=m.alias_name,
            joined_at=m.joined_at,
            email=user.email if user else None,
            full_name=user.full_name if user else None
        ))
    return result


@router.post("/invite", response_model=FamilyInviteResponse, status_code=status.HTTP_201_CREATED)
def create_invitation(
    data: FamilyInviteCreate,
    current_user: User = Depends(get_current_user),
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    # Verify current user is OWNER or ADMIN
    membership = db.query(FamilyMembership).filter(
        FamilyMembership.family_id == current_family.id,
        FamilyMembership.user_id == current_user.id
    ).first()
    if not membership or membership.role not in ("OWNER", "ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas o proprietário ou administradores podem convidar membros"
        )

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    invitation = FamilyInvitation(
        family_id=current_family.id,
        invited_email=data.invited_email.lower(),
        invited_by_id=current_user.id,
        token=hashlib.sha256(token.encode()).hexdigest(),
        role=data.role,
        status="PENDING",
        expires_at=expires_at
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    response = FamilyInviteResponse.model_validate(invitation)
    response.token = token
    return response


@router.get("/invitations", response_model=List[FamilyInviteSummary])
def get_family_invitations(
    current_family: FamilySpace = Depends(get_admin_family),
    db: Session = Depends(get_db)
) -> Any:
    return db.query(FamilyInvitation).filter(
        FamilyInvitation.family_id == current_family.id,
        FamilyInvitation.status == "PENDING"
    ).all()


@router.post("/accept-invite", response_model=FamilyResponse)
def accept_invitation(
    data: FamilyInviteAccept,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Any:
    invitation = db.query(FamilyInvitation).filter(
        FamilyInvitation.token == hashlib.sha256(data.token.encode()).hexdigest(),
        FamilyInvitation.status == "PENDING"
    ).with_for_update().first()
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Convite inválido ou expirado"
        )
    if invitation.invited_email.casefold() != current_user.email.casefold():
        raise HTTPException(403, detail="Convite destinado a outro usuário")
    if invitation.expires_at < datetime.now(timezone.utc):
        invitation.status = "REVOKED"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este convite expirou"
        )

    # Check if already a member
    existing = db.query(FamilyMembership).filter(
        FamilyMembership.family_id == invitation.family_id,
        FamilyMembership.user_id == current_user.id
    ).first()
    if existing:
        invitation.status = "ACCEPTED"
        db.commit()
        return db.query(FamilySpace).filter(FamilySpace.id == invitation.family_id).first()

    alias = data.alias_name or current_user.full_name.split()[0]
    new_member = FamilyMembership(
        family_id=invitation.family_id,
        user_id=current_user.id,
        role=invitation.role,
        alias_name=alias
    )
    db.add(new_member)
    invitation.status = "ACCEPTED"
    from app.services.responsibles import sync_responsibles
    sync_responsibles(db, invitation.family_id)
    db.commit()

    return db.query(FamilySpace).filter(FamilySpace.id == invitation.family_id).first()


@router.delete("/invitations/{invitation_id}")
def revoke_invitation(invitation_id: UUID, family: FamilySpace = Depends(get_admin_family),
                      db: Session = Depends(get_db)):
    invitation = db.query(FamilyInvitation).filter_by(id=invitation_id, family_id=family.id).with_for_update().first()
    if not invitation:
        raise HTTPException(404, detail="Convite não encontrado")
    if invitation.status != "PENDING":
        raise HTTPException(409, detail="Convite já utilizado ou revogado")
    invitation.status = "REVOKED"
    db.commit()
    return {"message": "Convite revogado"}
