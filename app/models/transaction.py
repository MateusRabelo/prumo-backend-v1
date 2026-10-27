import uuid
from datetime import datetime, timezone, date
from decimal import Decimal
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Numeric, String, Text, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    family_id = Column(UUID(as_uuid=True), ForeignKey("family_spaces.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    date = Column(Date, default=date.today, nullable=False, index=True)
    description = Column(String(255), nullable=False)
    type = Column(String(20), nullable=False)  # RECEITA, DESPESA, TRANSFERENCIA
    amount = Column(Numeric(12, 2), nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    account_id = Column(UUID(as_uuid=True), ForeignKey("financial_accounts.id", ondelete="RESTRICT"), nullable=False)
    destination_account_id = Column(UUID(as_uuid=True), ForeignKey("financial_accounts.id", ondelete="RESTRICT"), nullable=True)
    payment_mode = Column(String(16), default='ACCOUNT', server_default='ACCOUNT', nullable=False)
    card_id = Column(UUID(as_uuid=True), ForeignKey("credit_cards.id", ondelete="SET NULL"), nullable=True)
    responsible_name = Column(String(100), nullable=False)
    is_shared = Column(Boolean, default=False, nullable=False)
    classification = Column(String(30), default="NECESSIDADE", nullable=False)  # NECESSIDADE, DESEJO, INVESTIMENTO
    payment_method_id = Column(UUID(as_uuid=True), ForeignKey("payment_methods.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(20), default="REALIZADA", nullable=False)  # REALIZADA, PENDENTE, VENCIDA
    notes = Column(Text, nullable=True)
    installment_id = Column(UUID(as_uuid=True), ForeignKey("installments.id", ondelete="SET NULL", use_alter=True, name="fk_transactions_installment_id"), nullable=True)
    recurrence_id = Column(UUID(as_uuid=True), ForeignKey("recurrence_rules.id", ondelete="SET NULL"), nullable=True)
    is_invoice_payment = Column(Boolean, default=False, nullable=False)
    invoice_assignment = Column(String(16), default='DATE', server_default='DATE', nullable=False)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("card_invoices.id", ondelete="SET NULL", use_alter=True, name="fk_transactions_invoice_id"), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    idempotency_key = Column(String(64), nullable=True)
    request_fingerprint = Column(String(64), nullable=True)
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_transactions_idempotency_key"),
        CheckConstraint("amount > 0", name="ck_transaction_positive"),
        CheckConstraint("(type = 'TRANSFERENCIA' AND destination_account_id IS NOT NULL AND destination_account_id <> account_id AND card_id IS NULL) OR (type IN ('RECEITA', 'DESPESA') AND destination_account_id IS NULL)", name="ck_transaction_transfer"),
    )

    invoice = relationship("CardInvoice", foreign_keys=[invoice_id])
    family = relationship("FamilySpace")
    created_by = relationship("User", foreign_keys=[created_by_id])
    category = relationship("Category")
    account = relationship("FinancialAccount", foreign_keys=[account_id])
    destination_account = relationship("FinancialAccount", foreign_keys=[destination_account_id])
    payment_method = relationship("PaymentMethod")
    card = relationship("CreditCard")
