"""initial migration

Revision ID: c79a70ca7412
Revises: 
Create Date: 2026-10-23 21:53:27.752471

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c79a70ca7412'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        'users',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)

    # 2. family_spaces
    op.create_table(
        'family_spaces',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=False, server_default='BRL'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_family_spaces_id'), 'family_spaces', ['id'], unique=False)

    # 3. family_memberships
    op.create_table(
        'family_memberships',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('family_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False, server_default='MEMBER'),
        sa.Column('alias_name', sa.String(length=100), nullable=False),
        sa.Column('joined_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['family_id'], ['family_spaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('family_id', 'user_id', name='uq_family_user')
    )
    op.create_index(op.f('ix_family_memberships_family_id'), 'family_memberships', ['family_id'], unique=False)
    op.create_index(op.f('ix_family_memberships_id'), 'family_memberships', ['id'], unique=False)
    op.create_index(op.f('ix_family_memberships_user_id'), 'family_memberships', ['user_id'], unique=False)

    # 4. family_invitations
    op.create_table(
        'family_invitations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('family_id', sa.UUID(), nullable=False),
        sa.Column('invited_email', sa.String(length=255), nullable=False),
        sa.Column('invited_by_id', sa.UUID(), nullable=True),
        sa.Column('token', sa.String(length=100), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False, server_default='MEMBER'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='PENDING'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['family_id'], ['family_spaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invited_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_family_invitations_family_id'), 'family_invitations', ['family_id'], unique=False)
    op.create_index(op.f('ix_family_invitations_id'), 'family_invitations', ['id'], unique=False)
    op.create_index(op.f('ix_family_invitations_token'), 'family_invitations', ['token'], unique=True)

    # 5. categories
    op.create_table(
        'categories',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('family_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('color', sa.String(length=20), nullable=False, server_default='#10B981'),
        sa.Column('icon', sa.String(length=50), nullable=False, server_default='tag'),
        sa.Column('classification', sa.String(length=30), nullable=False, server_default='NECESSIDADE'),
        sa.Column('type', sa.String(length=20), nullable=False, server_default='DESPESA'),
        sa.Column('order_index', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['family_id'], ['family_spaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_categories_family_id'), 'categories', ['family_id'], unique=False)
    op.create_index(op.f('ix_categories_id'), 'categories', ['id'], unique=False)

    # 6. financial_accounts
    op.create_table(
        'financial_accounts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('family_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('account_type', sa.String(length=30), nullable=False, server_default='CHECKING'),
        sa.Column('initial_balance', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('initial_balance_date', sa.Date(), nullable=False),
        sa.Column('color', sa.String(length=20), nullable=False, server_default='#3B82F6'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['family_id'], ['family_spaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_financial_accounts_family_id'), 'financial_accounts', ['family_id'], unique=False)
    op.create_index(op.f('ix_financial_accounts_id'), 'financial_accounts', ['id'], unique=False)

    # 7. payment_methods
    op.create_table(
        'payment_methods',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('family_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['family_id'], ['family_spaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_payment_methods_family_id'), 'payment_methods', ['family_id'], unique=False)
    op.create_index(op.f('ix_payment_methods_id'), 'payment_methods', ['id'], unique=False)

    # 8. responsible_persons
    op.create_table(
        'responsible_persons',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('family_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('is_shared', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['family_id'], ['family_spaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_responsible_persons_family_id'), 'responsible_persons', ['family_id'], unique=False)
    op.create_index(op.f('ix_responsible_persons_id'), 'responsible_persons', ['id'], unique=False)

    # 9. recurrence_rules
    op.create_table(
        'recurrence_rules',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('family_id', sa.UUID(), nullable=False),
        sa.Column('created_by_id', sa.UUID(), nullable=True),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('category_id', sa.UUID(), nullable=False),
        sa.Column('account_id', sa.UUID(), nullable=False),
        sa.Column('responsible_name', sa.String(length=100), nullable=False),
        sa.Column('is_shared', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('classification', sa.String(length=30), nullable=False, server_default='NECESSIDADE'),
        sa.Column('frequency', sa.String(length=20), nullable=False, server_default='MONTHLY'),
        sa.Column('day_of_month', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('last_generated_date', sa.Date(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['financial_accounts.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['family_id'], ['family_spaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_recurrence_rules_family_id'), 'recurrence_rules', ['family_id'], unique=False)
    op.create_index(op.f('ix_recurrence_rules_id'), 'recurrence_rules', ['id'], unique=False)

    # 10. installment_plans
    op.create_table(
        'installment_plans',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('family_id', sa.UUID(), nullable=False),
        sa.Column('created_by_id', sa.UUID(), nullable=True),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.Column('category_id', sa.UUID(), nullable=False),
        sa.Column('account_id', sa.UUID(), nullable=True),
        sa.Column('payment_method_id', sa.UUID(), nullable=True),
        sa.Column('responsible_name', sa.String(length=100), nullable=False),
        sa.Column('is_shared', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('total_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('installments_count', sa.Integer(), nullable=False),
        sa.Column('purchase_date', sa.Date(), nullable=False),
        sa.Column('first_due_date', sa.Date(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='ACTIVE'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['financial_accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['family_id'], ['family_spaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['payment_method_id'], ['payment_methods.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_installment_plans_family_id'), 'installment_plans', ['family_id'], unique=False)
    op.create_index(op.f('ix_installment_plans_id'), 'installment_plans', ['id'], unique=False)

    # 11. transactions (created without FK to installments first to avoid cycle)
    op.create_table(
        'transactions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('family_id', sa.UUID(), nullable=False),
        sa.Column('created_by_id', sa.UUID(), nullable=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('category_id', sa.UUID(), nullable=True),
        sa.Column('account_id', sa.UUID(), nullable=False),
        sa.Column('destination_account_id', sa.UUID(), nullable=True),
        sa.Column('responsible_name', sa.String(length=100), nullable=False),
        sa.Column('is_shared', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('classification', sa.String(length=30), nullable=False, server_default='NECESSIDADE'),
        sa.Column('payment_method_id', sa.UUID(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='REALIZADA'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('installment_id', sa.UUID(), nullable=True),
        sa.Column('recurrence_id', sa.UUID(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['financial_accounts.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['destination_account_id'], ['financial_accounts.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['family_id'], ['family_spaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['payment_method_id'], ['payment_methods.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['recurrence_id'], ['recurrence_rules.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_transactions_date'), 'transactions', ['date'], unique=False)
    op.create_index(op.f('ix_transactions_family_id'), 'transactions', ['family_id'], unique=False)
    op.create_index(op.f('ix_transactions_id'), 'transactions', ['id'], unique=False)

    # 12. installments
    op.create_table(
        'installments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('installment_plan_id', sa.UUID(), nullable=False),
        sa.Column('installment_number', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='PENDENTE'),
        sa.Column('payment_date', sa.Date(), nullable=True),
        sa.Column('transaction_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['installment_plan_id'], ['installment_plans.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_installments_due_date'), 'installments', ['due_date'], unique=False)
    op.create_index(op.f('ix_installments_id'), 'installments', ['id'], unique=False)
    op.create_index(op.f('ix_installments_installment_plan_id'), 'installments', ['installment_plan_id'], unique=False)

    # 13. Add FK from transactions.installment_id to installments.id
    op.create_foreign_key(
        'fk_transactions_installment_id',
        'transactions',
        'installments',
        ['installment_id'],
        ['id'],
        ondelete='SET NULL'
    )

    # 14. budget_rules_503020
    op.create_table(
        'budget_rules_503020',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('family_id', sa.UUID(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('month', sa.Integer(), nullable=False),
        sa.Column('estimated_income', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('needs_percentage', sa.Numeric(precision=5, scale=2), nullable=False, server_default='50.00'),
        sa.Column('wants_percentage', sa.Numeric(precision=5, scale=2), nullable=False, server_default='30.00'),
        sa.Column('savings_percentage', sa.Numeric(precision=5, scale=2), nullable=False, server_default='20.00'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['family_id'], ['family_spaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('family_id', 'year', 'month', name='uq_budget_503020_period')
    )
    op.create_index(op.f('ix_budget_rules_503020_family_id'), 'budget_rules_503020', ['family_id'], unique=False)
    op.create_index(op.f('ix_budget_rules_503020_id'), 'budget_rules_503020', ['id'], unique=False)

    # 15. custom_budgets
    op.create_table(
        'custom_budgets',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('family_id', sa.UUID(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('month', sa.Integer(), nullable=False),
        sa.Column('category_id', sa.UUID(), nullable=True),
        sa.Column('responsible_name', sa.String(length=100), nullable=True),
        sa.Column('classification', sa.String(length=30), nullable=True),
        sa.Column('limit_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('alert_threshold_percentage', sa.Numeric(precision=5, scale=2), nullable=False, server_default='80.00'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['family_id'], ['family_spaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_custom_budgets_family_id'), 'custom_budgets', ['family_id'], unique=False)
    op.create_index(op.f('ix_custom_budgets_id'), 'custom_budgets', ['id'], unique=False)

    # 16. financial_goals
    op.create_table(
        'financial_goals',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('family_id', sa.UUID(), nullable=False),
        sa.Column('created_by_id', sa.UUID(), nullable=True),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('target_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('target_date', sa.Date(), nullable=True),
        sa.Column('responsible_name', sa.String(length=100), nullable=False),
        sa.Column('is_shared', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='EM_ANDAMENTO'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['family_id'], ['family_spaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_financial_goals_family_id'), 'financial_goals', ['family_id'], unique=False)
    op.create_index(op.f('ix_financial_goals_id'), 'financial_goals', ['id'], unique=False)

    # 17. goal_contributions
    op.create_table(
        'goal_contributions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('goal_id', sa.UUID(), nullable=False),
        sa.Column('created_by_id', sa.UUID(), nullable=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False, server_default='CONTRIBUICAO'),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('account_id', sa.UUID(), nullable=True),
        sa.Column('transaction_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['financial_accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['goal_id'], ['financial_goals.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_goal_contributions_goal_id'), 'goal_contributions', ['goal_id'], unique=False)
    op.create_index(op.f('ix_goal_contributions_id'), 'goal_contributions', ['id'], unique=False)

    # 18. audit_logs
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('family_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('entity_id', sa.String(length=100), nullable=False),
        sa.Column('old_values', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('new_values', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('ip_address', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['family_id'], ['family_spaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_audit_logs_entity_id'), 'audit_logs', ['entity_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_family_id'), 'audit_logs', ['family_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_id'), 'audit_logs', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_audit_logs_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_family_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_entity_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_created_at'), table_name='audit_logs')
    op.drop_table('audit_logs')

    op.drop_index(op.f('ix_goal_contributions_id'), table_name='goal_contributions')
    op.drop_index(op.f('ix_goal_contributions_goal_id'), table_name='goal_contributions')
    op.drop_table('goal_contributions')

    op.drop_index(op.f('ix_financial_goals_id'), table_name='financial_goals')
    op.drop_index(op.f('ix_financial_goals_family_id'), table_name='financial_goals')
    op.drop_table('financial_goals')

    op.drop_index(op.f('ix_custom_budgets_id'), table_name='custom_budgets')
    op.drop_index(op.f('ix_custom_budgets_family_id'), table_name='custom_budgets')
    op.drop_table('custom_budgets')

    op.drop_index(op.f('ix_budget_rules_503020_id'), table_name='budget_rules_503020')
    op.drop_index(op.f('ix_budget_rules_503020_family_id'), table_name='budget_rules_503020')
    op.drop_table('budget_rules_503020')

    op.drop_constraint('fk_transactions_installment_id', 'transactions', type_='foreignkey')

    op.drop_index(op.f('ix_installments_installment_plan_id'), table_name='installments')
    op.drop_index(op.f('ix_installments_id'), table_name='installments')
    op.drop_index(op.f('ix_installments_due_date'), table_name='installments')
    op.drop_table('installments')

    op.drop_index(op.f('ix_transactions_id'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_family_id'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_date'), table_name='transactions')
    op.drop_table('transactions')

    op.drop_index(op.f('ix_installment_plans_id'), table_name='installment_plans')
    op.drop_index(op.f('ix_installment_plans_family_id'), table_name='installment_plans')
    op.drop_table('installment_plans')

    op.drop_index(op.f('ix_recurrence_rules_id'), table_name='recurrence_rules')
    op.drop_index(op.f('ix_recurrence_rules_family_id'), table_name='recurrence_rules')
    op.drop_table('recurrence_rules')

    op.drop_index(op.f('ix_responsible_persons_id'), table_name='responsible_persons')
    op.drop_index(op.f('ix_responsible_persons_family_id'), table_name='responsible_persons')
    op.drop_table('responsible_persons')

    op.drop_index(op.f('ix_payment_methods_id'), table_name='payment_methods')
    op.drop_index(op.f('ix_payment_methods_family_id'), table_name='payment_methods')
    op.drop_table('payment_methods')

    op.drop_index(op.f('ix_financial_accounts_id'), table_name='financial_accounts')
    op.drop_index(op.f('ix_financial_accounts_family_id'), table_name='financial_accounts')
    op.drop_table('financial_accounts')

    op.drop_index(op.f('ix_categories_id'), table_name='categories')
    op.drop_index(op.f('ix_categories_family_id'), table_name='categories')
    op.drop_table('categories')

    op.drop_index(op.f('ix_family_invitations_token'), table_name='family_invitations')
    op.drop_index(op.f('ix_family_invitations_id'), table_name='family_invitations')
    op.drop_index(op.f('ix_family_invitations_family_id'), table_name='family_invitations')
    op.drop_table('family_invitations')

    op.drop_index(op.f('ix_family_memberships_user_id'), table_name='family_memberships')
    op.drop_index(op.f('ix_family_memberships_id'), table_name='family_memberships')
    op.drop_index(op.f('ix_family_memberships_family_id'), table_name='family_memberships')
    op.drop_table('family_memberships')

    op.drop_index(op.f('ix_family_spaces_id'), table_name='family_spaces')
    op.drop_table('family_spaces')

    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
