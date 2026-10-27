import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, String, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    token_version = Column(Integer, nullable=False, default=0, server_default="0")
    full_name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    owned_families = relationship("FamilySpace", back_populates="owner", foreign_keys="FamilySpace.owner_id")
    memberships = relationship("FamilyMembership", back_populates="user", cascade="all, delete-orphan")
