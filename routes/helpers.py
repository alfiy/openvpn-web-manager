from functools import wraps
from flask import session, request, jsonify, redirect, url_for, flash
from flask_wtf.csrf import validate_csrf
from flask_login import current_user
from models import User, Role

# 登录验证装饰器
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.is_json:
                return jsonify({'error': 'Not logged in'}), 401
            return redirect(url_for('auth_bp.login'))
        return f(*args, **kwargs)
    return decorated

# 登录验证装饰器
# def login_required(f):
#     @wraps(f)
#     def decorated_function(*args, **kwargs):
#         if not current_user.is_authenticated:          # ← 用官方代理
#             return jsonify({'success': False, 'message': '请先登录'}), 401
#         # 无需再手动 g.current_user = load_user(...)
#         return f(*args, **kwargs)
#     return decorated_function

def require_login():
    """Helper function: Checks if a user is logged in for before_request."""
    # 核心改动：使用 Flask-Login 的 is_authenticated 属性
    if not current_user.is_authenticated:
        if request.is_json:
            return jsonify({'error': 'Not logged in'}), 401
        return redirect(url_for('auth_bp.login'))

def role_required(required_roles):
    """Decorator: Checks if the logged-in user's role is in the allowed list."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 核心改动：使用 Flask-Login 的 current_user 对象
            if not current_user.is_authenticated:
                if request.is_json:
                    return jsonify({'error': 'Not logged in'}), 401
                return redirect(url_for('auth_bp.login'))

            # 使用 current_user 对象直接访问角色信息
            # 无需再从数据库查询用户
            if not hasattr(current_user, 'role') or current_user.role not in required_roles:
                flash('您没有权限访问此页面', 'danger')
                if request.is_json:
                    return jsonify({'error': 'Insufficient permissions'}), 403
                return redirect(url_for('main.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def json_csrf_protect(f):
    """Decorator for CSRF validation on JSON POST requests."""
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