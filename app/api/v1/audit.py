from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_family
from app.models.family import FamilySpace
from app.models.audit import AuditLog
from app.models.user import User

router = APIRouter(prefix="/audit", tags=["Auditoria"])


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    family_id: UUID
    user_id: Optional[UUID] = None
    user_name: Optional[str] = None
    action: str
    entity_type: str
    entity_id: str
    old_values: Optional[dict] = None
    new_values: Optional[dict] = None
    created_at: datetime


@router.get("/", response_model=List[AuditLogResponse])
def get_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    entity_type: Optional[str] = None,
    current_family: FamilySpace = Depends(get_current_family),
    db: Session = Depends(get_db)
) -> Any:
    query = db.query(AuditLog).filter(AuditLog.family_id == current_family.id)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)

    logs = query.order_by(AuditLog.created_at.desc()).limit(limit).all()
    result = []
    for log in logs:
        user_name = None
        if log.user_id:
            u = db.query(User).filter(User.id == log.user_id).first()
            if u:
                user_name = u.full_name
        result.append(AuditLogResponse(
            id=log.id,
            family_id=log.family_id,
            user_id=log.user_id,
            user_name=user_name,
            action=log.action,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            old_values=log.old_values,
            new_values=log.new_values,
            created_at=log.created_at
        ))
    return result
