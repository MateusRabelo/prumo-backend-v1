"""Record externally paid invoices without a second bank debit."""
from alembic import op
import sqlalchemy as sa
revision='a62d8e105fc9'
down_revision='f0ac36e32b81'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('card_invoices',sa.Column('external_settled',sa.Boolean(),nullable=False,server_default=sa.false()))
    op.add_column('card_invoices',sa.Column('external_paid_amount',sa.Numeric(12,2),nullable=False,server_default='0'))

def downgrade():
    op.drop_column('card_invoices','external_paid_amount')
    op.drop_column('card_invoices','external_settled')
