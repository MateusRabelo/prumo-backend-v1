from sqlalchemy import func
from app.models.family import FamilyMembership, FamilySpace
from app.schemas.family import FamilyResponse


def list_user_families(db, user_id):
    counts = db.query(FamilyMembership.family_id, func.count(FamilyMembership.id).label('members_count')).group_by(FamilyMembership.family_id).subquery()
    rows = db.query(FamilySpace, FamilyMembership.role, counts.c.members_count).join(
        FamilyMembership, FamilyMembership.family_id == FamilySpace.id).join(
        counts, counts.c.family_id == FamilySpace.id).filter(FamilyMembership.user_id == user_id).order_by(FamilyMembership.joined_at).all()
    return [FamilyResponse.model_validate(family).model_copy(update={'role': role, 'members_count': count})
            for family, role, count in rows]
