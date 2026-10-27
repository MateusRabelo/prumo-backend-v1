import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class ImportMerchantRule(Base):
    __tablename__ = 'import_merchant_rules'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id = Column(UUID(as_uuid=True), ForeignKey('family_spaces.id', ondelete='CASCADE'), nullable=False, index=True)
    merchant_key = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey('categories.id', ondelete='SET NULL'), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    __table_args__ = (UniqueConstraint('family_id', 'merchant_key', name='uq_import_merchant_family'),)
