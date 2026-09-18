import hashlib
import secrets
import string
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional
from flask import current_app
from flask_mail import Message


def issue_login_session(user) -> str:
    """签发新的登录令牌并写入 session，使该账号其它浏览器中的会话失效。"""
    from flask import session
    from models import db
    token = secrets.token_hex(16)
    user.session_token = token
    db.session.commit()
    session.permanent = True
    session['login_token'] = token
    return token


def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def generate_token(length: int = 32) -> str:
    """Return a URL-safe token (raw) to be sent to the user.
    Store only its SHA256 hash in DB."""
    return secrets.token_urlsafe(length)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def generate_strong_password(length: int = 16) -> str:
    """生成强密码,确保包含至少3种字符类型"""
    alphabet = string.ascii_letters + string.digits + string.punctuation
    
    # 确保最小长度
    if length < 4:
        length = 4
    
    while True:
        pwd = ''.join(secrets.choice(alphabet) for _ in range(length))
        
        # 检查密码强度:至少包含3种字符类型
        classes = sum(
            bool(set(pwd) & set(chars)) 
            for chars in (
                string.ascii_lowercase, 
                string.ascii_uppercase, 
                string.digits, 
                string.punctuation
            )
        )
        
        # ✅ 正确的缩进:if 和 return 都在 while 循环内
        if classes >= 3:
            return pwd




def send_mail(subject: str, recipients: list, body: str) -> None:
    mail = current_app.extensions.get('mail')
    if not mail:
        current_app.logger.error('Flask-Mail not configured')
        raise RuntimeError('Mail not configured')
    
    msg = Message(subject, recipients=recipients)
    msg.body = body
    mail.send(msg)