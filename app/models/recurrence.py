import uuid
from datetime import datetime, timezone, date
from decimal import Decimal
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class RecurrenceRule(Base):
    __tablename__ = "recurrence_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    family_id = Column(UUID(as_uuid=True), ForeignKey("family_spaces.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_subscription = Column(Boolean,default=False,server_default='false',nullable=False)
    card_id = Column(UUID(as_uuid=True),ForeignKey('credit_cards.id',ondelete='RESTRICT'),nullable=True)
    merchant_key = Column(String(255),nullable=True)
    next_due_date = Column(Date,nullable=True)
    card = relationship('CreditCard')
    description = Column(String(255), nullable=False)
    type = Column(String(20), nullable=False)  # RECEITA, DESPESA
    amount = Column(Numeric(12, 2), nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False)
    account_id = Column(UUID(as_uuid=True), ForeignKey("financial_accounts.id", ondelete="RESTRICT"), nullable=False)
    responsible_name = Column(String(100), nullable=False)
    is_shared = Column(Boolean, default=False, nullable=False)
    classification = Column(String(30), default="NECESSIDADE", nullable=False)
    frequency = Column(String(20), default="MONTHLY", nullable=False)  # MONTHLY, WEEKLY, YEARLY
    day_of_month = Column(Integer, default=1, nullable=False)
    start_date = Column(Date, default=date.today, nullable=False)
    end_date = Column(Date, nullable=True)
    last_generated_date = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    family = relationship("FamilySpace")
    category = relationship("Category")
    account = relationship("FinancialAccount")
    created_by = relationship("User")
