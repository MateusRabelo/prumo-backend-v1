"""Separate credit/debit and track managed members/imported parcels."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = 'e41bd230aa17'
down_revision = 'c5e8a1209b31'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('transactions', sa.Column('payment_mode', sa.String(16), nullable=False, server_default='ACCOUNT'))
    op.execute("UPDATE transactions SET payment_mode=CASE WHEN c.card_type IN ('DEBIT','BENEFIT') THEN 'DEBIT' ELSE 'CREDIT' END FROM credit_cards c WHERE transactions.card_id=c.id AND NOT transactions.is_invoice_payment")
    op.create_check_constraint('ck_payment_mode', 'transactions', "payment_mode IN ('ACCOUNT','CREDIT','DEBIT')")
    op.add_column('responsible_persons', sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')))
    op.add_column('responsible_persons', sa.Column('is_system', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_unique_constraint('uq_responsible_family_user', 'responsible_persons', ['family_id', 'user_id'])
    op.execute("UPDATE responsible_persons SET is_system=true WHERE is_shared=true AND lower(name)='conjunto'")
    op.add_column('installment_plans', sa.Column('imported_from_number', sa.Integer(), nullable=False, server_default='1'))

    op.create_table('statement_import_links',
        sa.Column('key', sa.String(64), primary_key=True),
        sa.Column('family_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('family_spaces.id', ondelete='CASCADE'), nullable=False),
        sa.Column('installment_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('installments.id', ondelete='SET NULL')),
        sa.Column('transaction_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('transactions.id', ondelete='SET NULL')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_statement_import_links_family_id', 'statement_import_links', ['family_id'])
    op.create_index('ix_statement_import_links_installment_id', 'statement_import_links', ['installment_id'])
    op.execute('ALTER TABLE statement_import_links ENABLE ROW LEVEL SECURITY')
    op.execute('REVOKE ALL ON statement_import_links FROM PUBLIC')
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN REVOKE ALL ON statement_import_links FROM anon; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN REVOKE ALL ON statement_import_links FROM authenticated; END IF; END $$")


def downgrade():
    op.drop_table('statement_import_links')
    op.drop_column('installment_plans', 'imported_from_number')
    op.drop_constraint('uq_responsible_family_user', 'responsible_persons')
    op.drop_column('responsible_persons', 'is_system')
    op.drop_column('responsible_persons', 'user_id')
    op.drop_constraint('ck_payment_mode', 'transactions')
    op.drop_column('transactions', 'payment_mode')
