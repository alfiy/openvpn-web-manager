from functools import wraps
from flask import request, jsonify, redirect, url_for, flash
from flask_wtf.csrf import validate_csrf
from flask_login import current_user
from models import Role


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'status': 'error', 'message': '未登录'}), 401
            return redirect(url_for('auth_bp.login'))
        return f(*args, **kwargs)
    return decorated


def require_login():
    """用于 before_request"""
    if not current_user.is_authenticated:
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'status': 'error', 'message': '未登录'}), 401
        return redirect(url_for('auth_bp.login'))


def _forbidden(message='您没有权限访问此页面'):
    if request.is_json or request.path.startswith('/api/'):
        return jsonify({'status': 'error', 'message': message}), 403
    flash(message, 'danger')
    try:
        return redirect(url_for('main_bp.index'))
    except Exception:
        return redirect(url_for('auth_bp.login'))


def role_required(required_roles):
    """Decorator: current_user.role 属于允许列表。"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                if request.is_json or request.path.startswith('/api/'):
                    return jsonify({'status': 'error', 'message': '未登录'}), 401
                return redirect(url_for('auth_bp.login'))
            if not hasattr(current_user, 'role') or current_user.role not in required_roles:
                return _forbidden('权限不足')
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_required(f):
    """ADMIN 或 SUPER_ADMIN。"""
    return role_required([Role.ADMIN, Role.SUPER_ADMIN])(f)


def super_admin_required(f):
    return role_required([Role.SUPER_ADMIN])(f)


def json_csrf_protect(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        csrf_token = request.headers.get('X-CSRFToken')
        if not csrf_token:
            return jsonify({'status': 'error', 'message': '缺少 CSRF 令牌'}), 403
        try:
            validate_csrf(csrf_token)
        except Exception:
            return jsonify({'status': 'error', 'message': 'CSRF 令牌验证失败，请刷新页面'}), 403
        return f(*args, **kwargs)
    return decorated_function


def init_csrf_guard(bp):
    @bp.before_request
    def _csrf_guard():
        if request.endpoint in ('auth_bp.api_login', 'auth_bp.get_csrf_token', 'api_bp.api_login'):
            return None
        if request.method in ('POST', 'PUT', 'DELETE') and request.is_json:
            token = request.headers.get('X-CSRFToken') or \
                (request.json.get('csrf_token') if request.json else None)
            if not token:
                return jsonify({'status': 'error', 'message': '缺少 CSRF 令牌'}), 403
            try:
                validate_csrf(token)
            except Exception:
                return jsonify({'status': 'error', 'message': 'CSRF 令牌无效'}), 403
