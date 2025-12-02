# from functools import wraps
# from flask import request, jsonify, redirect, url_for, flash
# from flask_wtf.csrf import validate_csrf
# from flask_login import current_user

# # 登录验证装饰器
# def login_required(f):
#     @wraps(f)
#     def decorated(*args, **kwargs):
#         if not current_user.is_authenticated:
#             if request.is_json:
#                 return jsonify({'error': 'Not logged in'}), 401
#             return redirect(url_for('auth_bp.login'))
#         return f(*args, **kwargs)
#     return decorated

# def require_login():
#     """Helper function: Checks if a user is logged in for before_request."""
#     # 核心改动：使用 Flask-Login 的 is_authenticated 属性
#     if not current_user.is_authenticated:
#         if request.is_json:
#             return jsonify({'error': 'Not logged in'}), 401
#         return redirect(url_for('auth_bp.login'))

# def role_required(required_roles):
#     """Decorator: Checks if the logged-in user's role is in the allowed list."""
#     def decorator(f):
#         @wraps(f)
#         def decorated_function(*args, **kwargs):
#             # 核心改动：使用 Flask-Login 的 current_user 对象
#             if not current_user.is_authenticated:
#                 if request.is_json:
#                     return jsonify({'error': 'Not logged in'}), 401
#                 return redirect(url_for('auth_bp.login'))

#             # 使用 current_user 对象直接访问角色信息
#             # 无需再从数据库查询用户
#             if not hasattr(current_user, 'role') or current_user.role not in required_roles:
#                 flash('您没有权限访问此页面', 'danger')
#                 if request.is_json:
#                     return jsonify({'error': 'Insufficient permissions'}), 403
#                 return redirect(url_for('main.index'))
#             return f(*args, **kwargs)
#         return decorated_function
#     return decorator

# def json_csrf_protect(f):
#     """用于对 JSON POST 请求进行 CSRF 验证的装饰器"""
#     @wraps(f)
#     def decorated_function(*args, **kwargs):
#         csrf_token = request.headers.get('X-CSRFToken')
#         if not csrf_token:
#             return jsonify({'status': 'error', 'message': '缺少 CSRF 令牌'}), 403
#         try:
#             validate_csrf(csrf_token)
#         except Exception:
#             return jsonify({'status': 'error', 'message': 'CSRF 令牌验证失败，请刷新页面'}), 403
#         return f(*args, **kwargs)
#     return decorated_function

# def init_csrf_guard(bp):
#     """给某个蓝图的所有写操作统一加 CSRF 校验"""
#     @bp.before_request
#     def _csrf_guard():
#         if request.method in ('POST','PUT','DELETE') and request.is_json:
#             token = request.headers.get('X-CSRFToken') or request.json.get('csrf_token')
#             if not token:
#                 return jsonify({'status':'error','message':'缺少 CSRF 令牌'}), 403
#             try:
#                 validate_csrf(token)
#             except Exception:
#                 return jsonify({'status':'error','message':'CSRF 令牌无效'}), 403

from functools import wraps
from flask import request, jsonify, redirect, url_for, flash
from flask_wtf.csrf import validate_csrf, generate_csrf
from flask_login import current_user



# ---------------------
# 登录验证
# ---------------------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.is_json:
                return jsonify({'error': 'Not logged in'}), 401
            return redirect(url_for('auth_bp.login'))
        return f(*args, **kwargs)
    return decorated


def require_login():
    """用于 before_request"""
    if not current_user.is_authenticated:
        if request.is_json:
            return jsonify({'error': 'Not logged in'}), 401
        return redirect(url_for('auth_bp.login'))


# ---------------------
# 角色验证
# ---------------------
def role_required(required_roles):
    """Decorator: Checks if current_user.role 属于允许列表"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):

            if not current_user.is_authenticated:
                if request.is_json:
                    return jsonify({'error': 'Not logged in'}), 401
                return redirect(url_for('auth_bp.login'))

            if not hasattr(current_user, 'role') or current_user.role not in required_roles:
                flash('您没有权限访问此页面', 'danger')
                if request.is_json:
                    return jsonify({'error': 'Insufficient permissions'}), 403
                return redirect(url_for('main.index'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ---------------------
# JSON CSRF 专用保护
# ---------------------
def json_csrf_protect(f):
    """用于 JSON POST 请求进行 CSRF 校验"""
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


# ---------------------
# 蓝图统一 JSON CSRF 保护
# ---------------------
def init_csrf_guard(bp):
    @bp.before_request
    def _csrf_guard():
        # ❗排除无需CSRF的接口（如登录、获取CSRF）
        if request.endpoint in ('auth_bp.api_login', 'auth_bp.get_csrf_token'):
            return None

        # 对 JSON 写操作启用 CSRF
        if request.method in ('POST', 'PUT', 'DELETE') and request.is_json:
            token = request.headers.get('X-CSRFToken') or \
                (request.json.get('csrf_token') if request.json else None)

            if not token:
                return jsonify({'status': 'error', 'message': '缺少 CSRF 令牌'}), 403

            try:
                validate_csrf(token)
            except Exception:
                return jsonify({'status': 'error', 'message': 'CSRF 令牌无效'}), 403