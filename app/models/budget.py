import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class BudgetRule503020(Base):
    __tablename__ = "budget_rules_503020"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    family_id = Column(UUID(as_uuid=True), ForeignKey("family_spaces.id", ondelete="CASCADE"), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    estimated_income = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    needs_percentage = Column(Numeric(5, 2), default=Decimal("50.00"), nullable=False)
    wants_percentage = Column(Numeric(5, 2), default=Decimal("30.00"), nullable=False)
    savings_percentage = Column(Numeric(5, 2), default=Decimal("20.00"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    family = relationship("FamilySpace")

    __table_args__ = (
        UniqueConstraint("family_id", "year", "month", name="uq_budget_503020_period"),
    )


class CustomBudget(Base):
    __tablename__ = "custom_budgets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    family_id = Column(UUID(as_uuid=True), ForeignKey("family_spaces.id", ondelete="CASCADE"), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    responsible_name = Column(String(100), nullable=True)
    classification = Column(String(30), nullable=True)
    limit_amount = Column(Numeric(12, 2), nullable=False)
    alert_threshold_percentage = Column(Numeric(5, 2), default=Decimal("80.00"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    family = relationship("FamilySpace")
    category = relationship("Category")
