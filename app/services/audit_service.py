from typing import Any, Dict, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from app.models.audit import AuditLog


class AuditService:
    @staticmethod
    def log(
        db: Session,
        family_id: UUID,
        user_id: Optional[UUID],
        action: str,
        entity_type: str,
        entity_id: str,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> AuditLog:
        entry = AuditLog(
            family_id=family_id,
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address
        )
        db.add(entry)
        # Flush so it is added within the transaction
        db.flush()
        return entry
