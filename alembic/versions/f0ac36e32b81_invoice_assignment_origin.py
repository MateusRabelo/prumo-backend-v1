"""Preserve explicit invoice choices while allowing date-based purchases to move."""
from alembic import op
import sqlalchemy as sa
revision='f0ac36e32b81'
down_revision='e41bd230aa17'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('transactions',sa.Column('invoice_assignment',sa.String(16),nullable=False,server_default='DATE'))
    op.execute("UPDATE transactions SET invoice_assignment='EXPLICIT' WHERE invoice_id IS NOT NULL")

def downgrade():
    op.drop_column('transactions','invoice_assignment')
