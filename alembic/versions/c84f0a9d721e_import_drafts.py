"""Private import reviews and explicit spending classifications."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID,JSONB
revision='c84f0a9d721e'
down_revision='b73e9102c1d4'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('installment_plans',sa.Column('classification',sa.String(30),nullable=True))
    op.add_column('import_merchant_rules',sa.Column('classification',sa.String(30),nullable=True))
    op.create_table('import_drafts',sa.Column('id',UUID(as_uuid=True),primary_key=True),
        sa.Column('family_id',UUID(as_uuid=True),sa.ForeignKey('family_spaces.id',ondelete='CASCADE'),nullable=False),
        sa.Column('user_id',UUID(as_uuid=True),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),
        sa.Column('file_name',sa.String(255),nullable=False),sa.Column('preview_payload',JSONB,nullable=False),
        sa.Column('preview_data',JSONB,nullable=False),sa.Column('review_state',JSONB,nullable=False),
        sa.Column('completed_at',sa.DateTime(timezone=True)),sa.Column('revision',sa.Integer(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_import_drafts_owner','import_drafts',['user_id','family_id','expires_at'])
    op.execute('ALTER TABLE import_drafts ENABLE ROW LEVEL SECURITY')
    op.execute('REVOKE ALL ON import_drafts FROM PUBLIC')
    op.execute("DO $$ BEGIN IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN REVOKE ALL ON import_drafts FROM anon; END IF; IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN REVOKE ALL ON import_drafts FROM authenticated; END IF; END $$")

def downgrade():
    op.drop_table('import_drafts')
    op.drop_column('import_merchant_rules','classification')
    op.drop_column('installment_plans','classification')
