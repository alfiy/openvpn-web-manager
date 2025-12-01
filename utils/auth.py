# utils/auth.py
from functools import wraps
from flask_login import current_user
from utils.api_response import api_error

# 你可以在需要的 API 上用 `@require_role('SUPER_ADMIN')`
def require_role(role):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return api_error("请先登录", status=401)
            if current_user.role.name != role:
                return api_error("权限不足", status=403)
            return f(*args, **kwargs)
        return wrapped
    return decorator