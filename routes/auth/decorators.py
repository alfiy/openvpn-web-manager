from functools import wraps
from flask import jsonify
from flask_login import current_user
from models import Role


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'status': 'error', 'message': '未登录'}), 401
        if current_user.role not in {Role.ADMIN, Role.SUPER_ADMIN}:
            return jsonify({'status': 'error', 'message': '权限不足'}), 403
        return f(*args, **kwargs)
    return wrapper