"""Protect sessions, payments, and family relationships.

Revision ID: 84b921ad1800
Revises: 57792a3ae22b
"""
from alembic import op
import sqlalchemy as sa

revision = '84b921ad1800'
down_revision = '57792a3ae22b'
branch_labels = None
depends_on = None

RELATIONS = {
    'transactions': [('account_id', 'financial_accounts'), ('destination_account_id', 'financial_accounts'),
                     ('category_id', 'categories'), ('card_id', 'credit_cards'), ('payment_method_id', 'payment_methods'), ('invoice_id', 'card_invoices')],
    'installment_plans': [('account_id', 'financial_accounts'), ('category_id', 'categories'), ('card_id', 'credit_cards'), ('payment_method_id', 'payment_methods')],
    'credit_cards': [('account_id', 'financial_accounts'), ('responsible_id', 'responsible_persons')],
    'custom_budgets': [('category_id', 'categories')],
    'card_invoices': [('card_id', 'credit_cards'), ('payment_account_id', 'financial_accounts')],
    'goal_contributions': [('account_id', 'financial_accounts')],
}


def upgrade():
    op.add_column('goal_contributions', sa.Column('is_reversed', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('users', sa.Column('token_version', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('transactions', sa.Column('idempotency_key', sa.String(64), nullable=True))
    op.add_column('transactions', sa.Column('request_fingerprint', sa.String(64), nullable=True))
    op.create_unique_constraint('uq_transactions_idempotency_key', 'transactions', ['idempotency_key'])
    op.create_unique_constraint('uq_invoice_card_period', 'card_invoices', ['card_id', 'year', 'month'])
    op.create_check_constraint('ck_invoice_period', 'card_invoices', 'month BETWEEN 1 AND 12 AND year BETWEEN 2000 AND 2100')
    op.create_check_constraint('ck_invoice_amounts', 'card_invoices', 'paid_amount >= 0 AND total_amount >= paid_amount')
    op.create_check_constraint('ck_transaction_positive', 'transactions', 'amount > 0')
    op.create_check_constraint('ck_transaction_transfer', 'transactions', "(type = 'TRANSFERENCIA' AND destination_account_id IS NOT NULL AND destination_account_id <> account_id AND card_id IS NULL) OR (type IN ('RECEITA', 'DESPESA') AND destination_account_id IS NULL)")
    op.create_table('rate_limit_buckets', sa.Column('key', sa.String(64), primary_key=True),
                    sa.Column('count', sa.Integer(), nullable=False), sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_rate_limit_buckets_expires_at', 'rate_limit_buckets', ['expires_at'])
    op.create_table('password_reset_tokens', sa.Column('token_hash', sa.String(64), primary_key=True),
                   sa.Column('user_id', sa.UUID(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
                   sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_password_reset_tokens_user_id', 'password_reset_tokens', ['user_id'])
    # Legacy invitations held plaintext bearer tokens. Revoke rather than reuse them.
    op.execute("UPDATE family_invitations SET status = 'REVOKED' WHERE status = 'PENDING'")
    op.execute('''CREATE FUNCTION enforce_family_references() RETURNS trigger AS $$
    DECLARE row_data jsonb; expected uuid; actual uuid; ref_id uuid; i integer;
    BEGIN
      row_data := to_jsonb(NEW);
      IF TG_TABLE_NAME = 'goal_contributions' THEN
        SELECT family_id INTO expected FROM financial_goals WHERE id = NEW.goal_id;
      ELSE
        expected := (row_data->>'family_id')::uuid;
      END IF;
      i := 0;
      WHILE i < TG_NARGS LOOP
        ref_id := (row_data->>TG_ARGV[i])::uuid;
        IF ref_id IS NOT NULL THEN
          EXECUTE format('SELECT family_id FROM %I WHERE id = $1', TG_ARGV[i+1]) INTO actual USING ref_id;
          IF actual IS DISTINCT FROM expected THEN
            RAISE EXCEPTION 'Reference crosses family boundary: %', TG_ARGV[i] USING ERRCODE = '23514';
          END IF;
        END IF;
        i := i + 2;
      END LOOP;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql''')
    for table, refs in RELATIONS.items():
        # Abort on existing contamination: never silently rewrite financial history.
        for field, target in refs:
            family_expr = 's.family_id' if table != 'goal_contributions' else '(SELECT family_id FROM financial_goals WHERE id=s.goal_id)'
            bad = op.get_bind().execute(sa.text(f'SELECT 1 FROM {table} s JOIN {target} t ON t.id=s.{field} WHERE t.family_id IS DISTINCT FROM {family_expr} LIMIT 1')).first()
            if bad:
                raise RuntimeError(f'Existing cross-family reference in {table}.{field}; reconcile before migration')
        args = ', '.join("'" + value + "'" for pair in refs for value in pair)
        op.execute(f'CREATE TRIGGER {table}_family_guard BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION enforce_family_references({args})')


def downgrade():
    for table in RELATIONS:
        op.execute(f'DROP TRIGGER {table}_family_guard ON {table}')
    op.execute('DROP FUNCTION enforce_family_references()')
    op.drop_table('password_reset_tokens')
    op.drop_table('rate_limit_buckets')
    for name in ['ck_transaction_transfer', 'ck_transaction_positive', 'uq_transactions_idempotency_key']:
        op.drop_constraint(name, 'transactions')
    for name in ['ck_invoice_amounts', 'ck_invoice_period', 'uq_invoice_card_period']:
        op.drop_constraint(name, 'card_invoices')
    op.drop_column('transactions', 'request_fingerprint')
    op.drop_column('transactions', 'idempotency_key')
    op.drop_column('users', 'token_version')
    op.drop_column('goal_contributions', 'is_reversed')
