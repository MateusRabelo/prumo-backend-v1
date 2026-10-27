import uuid
from datetime import datetime, timezone, date
from decimal import Decimal
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class CardInvoice(Base):
    __tablename__ = "card_invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    family_id = Column(UUID(as_uuid=True), ForeignKey("family_spaces.id", ondelete="CASCADE"), nullable=False, index=True)
    card_id = Column(UUID(as_uuid=True), ForeignKey("credit_cards.id", ondelete="CASCADE"), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)  # 1 to 12 (vencimento)
    closing_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    total_amount = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    paid_amount = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    status = Column(String(20), default="ABERTA", nullable=False)  # ABERTA, FECHADA, PAGA, VENCIDA
    payment_date = Column(Date, nullable=True)
    payment_account_id = Column(UUID(as_uuid=True), ForeignKey("financial_accounts.id", ondelete="SET NULL"), nullable=True)
    payment_transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL", use_alter=True, name="fk_card_invoices_payment_tx"), nullable=True)
    notes = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("card_id", "year", "month", name="uq_invoice_card_period"),
        CheckConstraint("month BETWEEN 1 AND 12 AND year BETWEEN 2000 AND 2100", name="ck_invoice_period"),
        CheckConstraint("paid_amount >= 0 AND total_amount >= paid_amount", name="ck_invoice_amounts"),
    )

    family = relationship("FamilySpace")
    card = relationship("CreditCard", back_populates="invoices")
    payment_account = relationship("FinancialAccount")
    payment_transaction = relationship("Transaction", foreign_keys=[payment_transaction_id])
