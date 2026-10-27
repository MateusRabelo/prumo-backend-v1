import hashlib
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import urlencode
from fastapi import HTTPException
from app.core.config import settings
from app.core.security import get_password_hash
from app.models.user import User
from app.models.security import PasswordResetToken


def send_reset_email(email, token):
    message = EmailMessage()
    message['From'] = settings.SMTP_FROM
    message['To'] = email
    message['Subject'] = 'MSFinanças — recuperação de senha'
    url = settings.PASSWORD_RESET_URL + '?' + urlencode({'token': token})
    message.set_content(f'Para redefinir sua senha, acesse: {url}\nO link expira em 30 minutos. Se não solicitou, ignore esta mensagem.')
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
        smtp.starttls()
        if settings.SMTP_USER:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(message)


def request_reset(db, email):
    if not settings.SMTP_HOST or not settings.SMTP_FROM or not settings.PASSWORD_RESET_URL:
        raise HTTPException(503, detail='Recuperação de senha indisponível no momento')
    user = db.query(User).filter(User.email == email.lower(), User.is_active == True).first()
    if not user:
        return
    token = secrets.token_urlsafe(32)
    db.query(PasswordResetToken).filter_by(user_id=user.id).delete()
    db.add(PasswordResetToken(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user.id,
                              expires_at=datetime.now(timezone.utc) + timedelta(minutes=30)))
    try:
        send_reset_email(user.email, token)
    except (OSError, smtplib.SMTPException):
        db.rollback()
        raise HTTPException(503, detail='Recuperação de senha indisponível no momento')
    db.commit()


def confirm_reset(db, token, password):
    record = db.query(PasswordResetToken).filter_by(token_hash=hashlib.sha256(token.encode()).hexdigest()).with_for_update().first()
    if not record or record.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(400, detail='Token inválido ou expirado')
    user = db.query(User).filter_by(id=record.user_id).with_for_update().one()
    if not user.is_active:
        raise HTTPException(400, detail='Token inválido ou expirado')
    user.hashed_password = get_password_hash(password)
    user.token_version += 1
    db.query(PasswordResetToken).filter_by(user_id=user.id).delete()
    db.commit()
