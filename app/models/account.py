import uuid
from datetime import datetime, timezone, date
from decimal import Decimal
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class FinancialAccount(Base):
    __tablename__ = "financial_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    family_id = Column(UUID(as_uuid=True), ForeignKey("family_spaces.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    account_type = Column(String(30), default="CHECKING", nullable=False)  # CHECKING, SAVINGS, WALLET, CREDIT_CARD, INVESTMENT
    bank_name = Column(String(100), nullable=True)
    agency = Column(String(20), nullable=True)
    account_number = Column(String(30), nullable=True)
    initial_balance = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    initial_balance_date = Column(Date, default=date.today, nullable=False)
    color = Column(String(20), default="#3B82F6", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    family = relationship("FamilySpace")
