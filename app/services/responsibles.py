"""Membership labels are managed; existing historical ledger labels stay unchanged."""
from app.models.family import FamilySpace, FamilyMembership
from app.models.responsible import ResponsiblePerson


def sync_responsibles(db, family_id):
    db.query(FamilySpace).filter_by(id=family_id).with_for_update().one()
    db.flush()
    members = db.query(FamilyMembership).filter_by(family_id=family_id).order_by(FamilyMembership.joined_at).all()
    persons = db.query(ResponsiblePerson).filter_by(family_id=family_id).all()
    member_ids = {m.user_id for m in members}
    for member in members:
        person = next((p for p in persons if p.user_id == member.user_id), None)
        if person is None:
            matching = [p for p in persons if p.user_id is None and not p.is_shared and p.name.casefold() == member.alias_name.casefold()]
            person = matching[0] if len(matching) == 1 else ResponsiblePerson(family_id=family_id, name=member.alias_name)
            if person not in persons:
                db.add(person); persons.append(person)
        person.user_id, person.is_system, person.is_active, person.is_shared = member.user_id, True, True, False
        person.name = member.alias_name
    for person in persons:
        if person.is_system and person.user_id and person.user_id not in member_ids:
            person.is_active = False
    shared = next((p for p in persons if p.is_system and p.is_shared), None)
    if shared is None:
        shared = next((p for p in persons if p.is_shared and p.name.casefold() == 'conjunto'), None)
    if len(members) > 1:
        if shared is None:
            shared = ResponsiblePerson(family_id=family_id, name='Conjunto', is_shared=True, is_system=True)
            db.add(shared)
        shared.is_system, shared.is_active, shared.name = True, True, 'Conjunto'
    elif shared:
        shared.is_active = False
    db.flush()
