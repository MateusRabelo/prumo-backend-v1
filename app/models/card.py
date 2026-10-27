import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class CreditCard(Base):
    __tablename__ = "credit_cards"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    family_id = Column(UUID(as_uuid=True), ForeignKey("family_spaces.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    card_type = Column(String(30), default="CREDIT", nullable=False)  # CREDIT, DEBIT, MULTIPLE, BENEFIT
    brand = Column(String(50), default="Mastercard", nullable=False)  # Mastercard, Visa, Elo, Amex, Hipercard, Outro
    bank_name = Column(String(100), nullable=True)  # Nubank, Itaú, Inter, etc.
    last_digits = Column(String(4), nullable=True)
    credit_limit = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    closing_day = Column(Integer, default=1, nullable=False)  # 1-31
    due_day = Column(Integer, default=10, nullable=False)  # 1-31
    color = Column(String(20), default="#6366F1", nullable=False)
    
    responsible_name = Column(String(100), nullable=True)
    responsible_id = Column(UUID(as_uuid=True), ForeignKey("responsible_persons.id", ondelete="SET NULL"), nullable=True)
    account_id = Column(UUID(as_uuid=True), ForeignKey("financial_accounts.id", ondelete="SET NULL"), nullable=True)
    
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    family = relationship("FamilySpace")
    account = relationship("FinancialAccount")
    responsible = relationship("ResponsiblePerson")
    invoices = relationship("CardInvoice", back_populates="card", cascade="all, delete-orphan")
