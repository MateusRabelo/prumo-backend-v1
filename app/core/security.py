from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union
import bcrypt
import secrets
from pwdlib import PasswordHash

password_hasher = PasswordHash.recommended()
import jwt
from app.core.config import settings


def get_password_hash(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        if not hashed_password.startswith(('$2a$', '$2b$', '$2y$')):
            return password_hasher.verify(plain_password, hashed_password)
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except Exception:
        return False


def create_access_token(
    subject: Union[str, Any],
    expires_delta: Optional[timedelta] = None,
    token_version: int = 0
) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode = {"exp": expire, "iat": datetime.now(timezone.utc), "sub": str(subject),
                 "ver": token_version, "jti": secrets.token_urlsafe(24)}
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require": ["exp", "sub", "ver", "jti"]}
        )
        return payload
    except jwt.PyJWTError:
        return None
