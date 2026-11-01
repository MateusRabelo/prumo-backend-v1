"""Persist the cadence of installment agreements."""
from alembic import op
import sqlalchemy as sa
revision='e0637ca952b1'
down_revision='d952ab310f68'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('installment_plans',sa.Column('frequency',sa.String(16),server_default='MONTHLY',nullable=False))
    op.create_check_constraint('ck_installment_plan_frequency','installment_plans',"frequency IN ('MONTHLY', 'WEEKLY')")

def downgrade():
    op.drop_constraint('ck_installment_plan_frequency','installment_plans',type_='check')
    op.drop_column('installment_plans','frequency')
