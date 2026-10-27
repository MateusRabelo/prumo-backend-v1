"""Audit administrative changes in the same transaction as the mutation."""
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session
from app.models.audit import AuditLog

AUDITED = {'financial_accounts', 'credit_cards', 'categories', 'responsible_persons',
           'payment_methods', 'budget_rules_503020', 'custom_budgets', 'family_invitations',
           'family_memberships'}


def install_audit_hooks():
    if event.contains(Session, 'before_flush', audit_changes):
        return
    event.listen(Session, 'before_flush', audit_changes)


def audit_changes(session, flush_context, instances):
    if not session.info.get('user_id') or not session.info.get('family_id'):
        return
    def serial(value):
        return value if value is None or isinstance(value, (str, int, bool, float)) else str(value)
    for obj in list(session.new) + list(session.dirty) + list(session.deleted):
        table = getattr(obj, '__tablename__', '')
        if table not in AUDITED:
            continue
        if obj in session.dirty and not session.is_modified(obj, include_collections=False):
            continue
        action = 'CREATE' if obj in session.new else 'DELETE' if obj in session.deleted else 'UPDATE'
        old, new = {}, {}
        for attr in inspect(obj).mapper.column_attrs:
            if attr.key in ('token', 'hashed_password'):
                continue
            value = getattr(obj, attr.key)
            if attr.key == 'id' and value is None:
                import uuid
                obj.id = value = uuid.uuid4()
            new[attr.key] = serial(value)
            history = inspect(obj).attrs[attr.key].history
            if history.deleted:
                old[attr.key] = serial(history.deleted[0])
        session.add(AuditLog(family_id=session.info['family_id'], user_id=session.info['user_id'],
            action=action, entity_type=table.upper(), entity_id=str(obj.id),
            old_values=old or None, new_values=new))
