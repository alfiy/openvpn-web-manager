from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


csrf = CSRFProtect()


def login_user_key():
    """登录限流：IP + 用户名，避免单 IP 下多账号互相占额度，也限制撞库同一用户名。"""
    from flask import request
    ip = get_remote_address() or 'unknown'
    username = ''
    data = request.get_json(silent=True)
    if isinstance(data, dict):
        username = str(data.get('username') or '').strip().lower()[:64]
    return f"login:{ip}:{username or '-'}"


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[]
)