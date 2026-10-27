import uuid
from datetime import datetime, timezone, date
from decimal import Decimal
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class FinancialGoal(Base):
    __tablename__ = "financial_goals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    family_id = Column(UUID(as_uuid=True), ForeignKey("family_spaces.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    target_amount = Column(Numeric(12, 2), nullable=False)
    target_date = Column(Date, nullable=True)
    responsible_name = Column(String(100), nullable=False)
    is_shared = Column(Boolean, default=False, nullable=False)
    status = Column(String(20), default="EM_ANDAMENTO", nullable=False)  # EM_ANDAMENTO, CONCLUIDA, CANCELADA
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    family = relationship("FamilySpace")
    created_by = relationship("User")
    contributions = relationship("GoalContribution", back_populates="goal", cascade="all, delete-orphan", order_by="GoalContribution.date.desc()")


class GoalContribution(Base):
    __tablename__ = "goal_contributions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    goal_id = Column(UUID(as_uuid=True), ForeignKey("financial_goals.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    date = Column(Date, default=date.today, nullable=False)
    type = Column(String(20), default="CONTRIBUICAO", nullable=False)  # CONTRIBUICAO, RETIRADA, AJUSTE
    amount = Column(Numeric(12, 2), nullable=False)
    notes = Column(Text, nullable=True)
    account_id = Column(UUID(as_uuid=True), ForeignKey("financial_accounts.id", ondelete="SET NULL"), nullable=True)
    is_reversed = Column(Boolean, nullable=False, default=False, server_default="false")
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    goal = relationship("FinancialGoal", back_populates="contributions")
    created_by = relationship("User")
    account = relationship("FinancialAccount")
    transaction = relationship("Transaction")
