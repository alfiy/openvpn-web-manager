from flask import Flask, render_template, session, request, jsonify, redirect, url_for
from flask_session import Session
from datetime import timedelta
from functools import wraps

# ---------------- 业务蓝图 ----------------
from routes.index            import index_bp
from routes.install          import install_bp
from routes.add_client       import add_client_bp
from routes.revoke_client    import revoke_client_bp
from routes.uninstall        import uninstall_bp
from routes.download_client  import download_client_bp
from routes.disconnect_client import disconnect_client_bp
from routes.modify_client_expiry import modify_client_expiry_bp
from routes.enable_client    import enable_client_bp
from routes.get_ip_list      import ip_bp

# ---------------- Flask 配置 ----------------
app = Flask(__name__)
app.config['DEBUG'] = True
app.config['SECRET_KEY'] = 'replace-me-in-production'
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)
Session(app)

# ---------------- 认证工具 ----------------
def login_required(f):
    """装饰器：给视图函数用"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'logged_in' not in session:
            if request.is_json:
                return jsonify({'error': '未登录'}), 401
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

def require_login():
    """普通函数：给 before_request 用"""
    if 'logged_in' not in session:
        if request.is_json:
            return jsonify({'error': '未登录'}), 401
        return redirect(url_for('auth.login'))

# ---------------- 认证蓝图 ----------------
from flask import Blueprint
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        # TODO: 替换为数据库校验
        if username == 'admin' and password == 'admin123':
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('index.index'))
        return render_template('login.html', error='用户名或密码错误')
    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))

@auth_bp.route('/api/check_auth')
def check_auth():
    return jsonify({'logged_in': 'logged_in' in session})

# ---------------- 统一登录保护 ----------------
protected_blueprints = [
    index_bp, install_bp, add_client_bp, revoke_client_bp,
    uninstall_bp, download_client_bp, disconnect_client_bp,
    modify_client_expiry_bp, enable_client_bp, ip_bp
]

for bp in protected_blueprints:
    bp.before_request(require_login)

# ---------------- 注册蓝图 ----------------
app.register_blueprint(auth_bp)
app.register_blueprint(index_bp)
app.register_blueprint(install_bp)
app.register_blueprint(add_client_bp)
app.register_blueprint(revoke_client_bp)
app.register_blueprint(uninstall_bp)
app.register_blueprint(download_client_bp)
app.register_blueprint(disconnect_client_bp)
app.register_blueprint(modify_client_expiry_bp)
app.register_blueprint(enable_client_bp)
app.register_blueprint(ip_bp, url_prefix='/')

# ---------------- 启动 ----------------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)