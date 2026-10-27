import uuid
from datetime import datetime, timezone, date
from decimal import Decimal
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class InstallmentPlan(Base):
    __tablename__ = "installment_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    family_id = Column(UUID(as_uuid=True), ForeignKey("family_spaces.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    classification = Column(String(30), nullable=True)
    description = Column(String(255), nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False)
    account_id = Column(UUID(as_uuid=True), ForeignKey("financial_accounts.id", ondelete="SET NULL"), nullable=True)
    card_id = Column(UUID(as_uuid=True), ForeignKey("credit_cards.id", ondelete="SET NULL"), nullable=True)
    payment_method_id = Column(UUID(as_uuid=True), ForeignKey("payment_methods.id", ondelete="SET NULL"), nullable=True)
    responsible_name = Column(String(100), nullable=False)
    is_shared = Column(Boolean, default=False, nullable=False)
    total_amount = Column(Numeric(12, 2), nullable=False)
    imported_from_number = Column(Integer, default=1, server_default="1", nullable=False)
    installments_count = Column(Integer, nullable=False)
    purchase_date = Column(Date, default=date.today, nullable=False)
    first_due_date = Column(Date, nullable=False)
    notes = Column(Text, nullable=True)
    status = Column(String(20), default="ACTIVE", nullable=False)  # ACTIVE, COMPLETED, CANCELLED
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    family = relationship("FamilySpace")
    category = relationship("Category")
    account = relationship("FinancialAccount")
    card = relationship("CreditCard")
    payment_method = relationship("PaymentMethod")
    created_by = relationship("User")
    installments = relationship("Installment", back_populates="plan", cascade="all, delete-orphan", order_by="Installment.installment_number")


class Installment(Base):
    __tablename__ = "installments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    installment_plan_id = Column(UUID(as_uuid=True), ForeignKey("installment_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    installment_number = Column(Integer, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    due_date = Column(Date, nullable=False, index=True)
    status = Column(String(20), default="PENDENTE", nullable=False)  # PENDENTE, PAGA, CANCELADA
    payment_date = Column(Date, nullable=True)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL", use_alter=True, name="fk_installments_transaction_id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    plan = relationship("InstallmentPlan", back_populates="installments")
    transaction = relationship("Transaction", foreign_keys=[transaction_id])
