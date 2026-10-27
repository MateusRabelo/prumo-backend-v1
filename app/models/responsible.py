import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class ResponsiblePerson(Base):
    __tablename__ = "responsible_persons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    family_id = Column(UUID(as_uuid=True), ForeignKey("family_spaces.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_system = Column(Boolean, default=False, server_default="false", nullable=False)
    name = Column(String(100), nullable=False)
    is_shared = Column(Boolean, default=False, nullable=False)  # True for "Conjunto"
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (UniqueConstraint('family_id','user_id',name='uq_responsible_family_user'),)

    family = relationship("FamilySpace")
