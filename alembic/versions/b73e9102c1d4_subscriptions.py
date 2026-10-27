"""Track reviewed subscriptions using recurrence rules."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
revision='b73e9102c1d4'
down_revision='a62d8e105fc9'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('recurrence_rules',sa.Column('is_subscription',sa.Boolean(),nullable=False,server_default=sa.false()))
    op.add_column('recurrence_rules',sa.Column('card_id',UUID(as_uuid=True),sa.ForeignKey('credit_cards.id',ondelete='RESTRICT')))
    op.add_column('recurrence_rules',sa.Column('merchant_key',sa.String(255)))
    op.add_column('recurrence_rules',sa.Column('next_due_date',sa.Date()))
    op.create_index('ix_subscription_lookup','recurrence_rules',['family_id','card_id','merchant_key'])

def downgrade():
    op.drop_index('ix_subscription_lookup',table_name='recurrence_rules')
    for name in ['next_due_date','merchant_key','card_id','is_subscription']:op.drop_column('recurrence_rules',name)
