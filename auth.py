from functools import wraps
from flask import session, redirect, url_for, request, jsonify, render_template

def login_required(f):
    """登录验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            if request.is_json:
                return jsonify({'error': '未登录'}), 401
            else:
                return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# 登录路由（示例）
def init_auth_routes(app):
    from flask import Blueprint
    auth_bp = Blueprint('auth', __name__)

    @auth_bp.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            # 示例用户名密码，生产环境请用数据库验证
            if username == 'admin' and password == 'admin123':
                session['logged_in'] = True
                session['username'] = username
                return redirect(url_for('index'))
            else:
                return render_template('login.html', error='用户名或密码错误')
        return render_template('login.html')

    @auth_bp.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('auth.login'))

    @auth_bp.route('/api/check_auth')
    def check_auth():
        return jsonify({'logged_in': 'logged_in' in session})

    app.register_blueprint(auth_bp)