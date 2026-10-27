from datetime import datetime,timedelta,timezone
from fastapi import HTTPException
import jwt
from app.core.config import settings
from app.models.import_draft import ImportDraft
from app.models.user import User


def owned_draft(db,user_id,family_id,draft_id,lock=False):
    q=db.query(ImportDraft).filter(ImportDraft.id==draft_id,ImportDraft.user_id==user_id,
        ImportDraft.family_id==family_id,ImportDraft.completed_at.is_(None),ImportDraft.expires_at>datetime.now(timezone.utc))
    draft=(q.with_for_update() if lock else q).first()
    if not draft:raise HTTPException(404,detail='Rascunho não encontrado, concluído ou expirado.')
    return draft


def create_draft(db,user,family,file_name,payload,preview):
    now=datetime.now(timezone.utc)
    db.query(User).filter_by(id=user.id).with_for_update().one()
    db.query(ImportDraft).filter_by(user_id=user.id,family_id=family.id).filter(ImportDraft.expires_at<=now).delete(synchronize_session=False)
    if db.query(ImportDraft).filter_by(user_id=user.id,family_id=family.id,completed_at=None).count()>=10:
        raise HTTPException(409,detail='Você tem 10 rascunhos neste espaço. Conclua ou descarte um antes de enviar outro arquivo.')
    draft=ImportDraft(user_id=user.id,family_id=family.id,file_name=file_name[:255],preview_payload=payload,
        preview_data=preview,review_state={},revision=1,expires_at=now+timedelta(days=30))
    db.add(draft);db.flush()
    return draft


def draft_token(draft):
    now=datetime.now(timezone.utc)
    return jwt.encode({**draft.preview_payload,'draft_id':str(draft.id),'iat':now,'exp':now+timedelta(minutes=30)},settings.SECRET_KEY,algorithm='HS256')


def metadata(draft):
    return {'id':str(draft.id),'file_name':draft.file_name,'revision':draft.revision,
        'created_at':draft.created_at,'updated_at':draft.updated_at,'expires_at':draft.expires_at,
        'rows_count':len(draft.preview_payload['rows']),'source':'card' if draft.preview_payload['card'] else 'bank'}
