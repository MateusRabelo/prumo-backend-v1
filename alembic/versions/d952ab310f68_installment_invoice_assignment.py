"""Explicit invoice assignment for observed installments."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='d952ab310f68'
down_revision='c84f0a9d721e'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('credit_cards',sa.Column('billing_month_offset',sa.Integer(),nullable=False,server_default='0'))
    op.create_check_constraint('ck_card_billing_month_offset','credit_cards','billing_month_offset IN (-1, 0)')
    op.add_column('installments',sa.Column('invoice_id',postgresql.UUID(as_uuid=True),nullable=True))
    op.create_foreign_key('fk_installments_invoice','installments','card_invoices',['invoice_id'],['id'],ondelete='SET NULL')
    op.create_index('ix_installments_invoice_id','installments',['invoice_id'])

def downgrade():
    op.drop_constraint('ck_card_billing_month_offset','credit_cards',type_='check')
    op.drop_column('credit_cards','billing_month_offset')
    op.drop_index('ix_installments_invoice_id',table_name='installments')
    op.drop_constraint('fk_installments_invoice','installments',type_='foreignkey')
    op.drop_column('installments','invoice_id')
