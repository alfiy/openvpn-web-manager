from flask import Flask, render_template, session, request, jsonify, redirect, url_for
from flask_session import Session
from datetime import timedelta
from functools import wraps
import json
import os
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User


USERS_FILE = os.path.join(os.path.dirname(__file__), 'users.json')

def load_users():
    if not os.path.exists(USERS_FILE):
        return {'admin': generate_password_hash('admin123')}
    with open(USERS_FILE) as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

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

# SQLite 单文件数据库
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'vpn_users.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin')
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()

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

# ---------------- 修改登录校验 ----------------
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('index.index'))
        return render_template('login.html', error='用户名或密码错误')
    return render_template('login.html')

@auth_bp.route('/change_password', methods=['POST'])
@login_required
def change_password():
    data = request.get_json() or {}
    new_pwd = data.get('new_pwd', '').strip()
    if len(new_pwd) < 6:
        return jsonify(status='error', message='密码至少 6 位'), 400

    user = User.query.filter_by(username=session['username']).first()
    user.set_password(new_pwd)
    db.session.commit()
    return jsonify(status='success', message='密码修改成功')

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

USERS_FILE = os.path.join(os.path.dirname(__file__), 'users.json')

def load_users():
    if not os.path.exists(USERS_FILE):
        return {'admin': generate_password_hash('admin123')}
    with open(USERS_FILE) as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)


# ---------------- 启动 ----------------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)