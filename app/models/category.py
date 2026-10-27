import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class Category(Base):
    __tablename__ = "categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    family_id = Column(UUID(as_uuid=True), ForeignKey("family_spaces.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    color = Column(String(20), default="#10B981", nullable=False)
    icon = Column(String(50), default="tag", nullable=False)
    classification = Column(String(30), default="NECESSIDADE", nullable=False)  # NECESSIDADE, DESEJO, INVESTIMENTO
    type = Column(String(20), default="DESPESA", nullable=False)  # DESPESA, RECEITA, AMBOS
    order_index = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    family = relationship("FamilySpace")
