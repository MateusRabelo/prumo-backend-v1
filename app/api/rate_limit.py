import hashlib
import time
from datetime import datetime, timezone, timedelta
from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete
from app.core.database import get_db
from app.models.security import RateLimitBucket


def limit_auth(request: Request, db=Depends(get_db)):
    """Shared database counters: no trust in client-supplied forwarding headers."""
    from sqlalchemy.dialects.postgresql import insert
    now = datetime.now(timezone.utc)
    peer = request.client.host if request.client else 'unknown'
    key = hashlib.sha256(f'{peer}:{request.url.path}:{int(time.time() // 60)}'.encode()).hexdigest()
    statement = insert(RateLimitBucket).values(key=key, count=1, expires_at=now + timedelta(minutes=2))
    statement = statement.on_conflict_do_update(index_elements=['key'], set_={'count': RateLimitBucket.count + 1}).returning(RateLimitBucket.count)
    count = db.execute(statement).scalar_one()
    db.execute(delete(RateLimitBucket).where(RateLimitBucket.expires_at < now))
    db.commit()
    limit = 20 if request.url.path.endswith('/login') else 5
    if count > limit:
        raise HTTPException(429, detail='Muitas tentativas. Aguarde um minuto.', headers={'Retry-After': '60'})
