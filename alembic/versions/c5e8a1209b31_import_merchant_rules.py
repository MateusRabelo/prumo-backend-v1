"""Remember statement merchant names within each family."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = 'c5e8a1209b31'
down_revision = '84b921ad1800'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('import_merchant_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('family_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('family_spaces.id', ondelete='CASCADE'), nullable=False),
        sa.Column('merchant_key', sa.String(255), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('category_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('categories.id', ondelete='SET NULL')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('family_id', 'merchant_key', name='uq_import_merchant_family'))
    op.create_index('ix_import_merchant_rules_family_id', 'import_merchant_rules', ['family_id'])
    # Schema translation preserves isolated test schemas as well as public in production.
    op.execute('ALTER TABLE import_merchant_rules ENABLE ROW LEVEL SECURITY')
    op.execute('REVOKE ALL ON import_merchant_rules FROM PUBLIC')
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN REVOKE ALL ON import_merchant_rules FROM anon; END IF; IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN REVOKE ALL ON import_merchant_rules FROM authenticated; END IF; END $$")


def downgrade():
    op.drop_table('import_merchant_rules')
