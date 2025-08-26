from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from flask import Flask, render_template, session, request, jsonify, redirect, url_for,flash
from flask_session import Session
from datetime import datetime, timedelta
from functools import wraps
import json
import os
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User
from flask_mail import Mail, Message
import secrets



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


load_dotenv()
# 邮件配置
app.config.update(
    MAIL_SERVER=os.getenv('MAIL_SERVER', 'smtp.qq.com'),
    MAIL_PORT=int(os.getenv('MAIL_PORT', 465)),
    MAIL_USE_SSL=os.getenv('MAIL_USE_SSL', 'false').lower() in ('true', '1'),
    MAIL_USE_TLS=os.getenv('MAIL_USE_TLS', 'false').lower() in ('true', '1'),
    MAIL_USERNAME=os.getenv('MAIL_USERNAME'),
    MAIL_PASSWORD=os.getenv('MAIL_PASSWORD'),
    MAIL_DEFAULT_SENDER=os.getenv('MAIL_DEFAULT_SENDER')
)


# SQLite 单文件数据库
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'vpn_users.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

Session(app)
mail = Mail(app)
db.init_app(app)

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin',email='admin@example.com')
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



@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email    = request.form['email'].strip()
        password = request.form['password'].strip()

        if len(password) < 6:
            return jsonify({'status': 'error', 'message': '密码至少 6 位'}), 400
        if User.query.filter((User.username == username) | (User.email == email)).first():
            return jsonify({'status': 'error', 'message': '用户名或邮箱已存在'}), 400

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        # ✅ 成功返回 JSON，前端 JS 负责跳转
        return jsonify({'status': 'success'})

    # GET 请求返回注册页
    return render_template('register.html')

def generate_token():
    return secrets.token_urlsafe(32)

@auth_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'GET':
        # 直接渲染模板
        return render_template('forgot_password.html')

    # --- POST ---
    email = request.form.get('email', '').strip()
    user  = User.query.filter_by(email=email).first()

    if not user:
        flash('邮箱未注册', 'danger')
        return redirect(url_for('auth.forgot_password'))

    token = generate_token()
    user.reset_token  = token
    user.reset_expire = datetime.now(timezone.utc) + timedelta(minutes=30)
    db.session.commit()

    link = url_for('auth.reset_password', token=token, _external=True)
    msg = Message('重置密码', recipients=[email])
    msg.body = f'点击链接重置密码（30 分钟内有效）：{link}'
    mail.send(msg)

    flash('重置邮件已发送，请查收', 'success')
    return redirect(url_for('auth.login'))

@auth_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()
    if not user:
        flash('链接已失效', 'danger')
        return redirect(url_for('auth.login'))

    # 把 naive → aware
    if user.reset_expire.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        flash('链接已过期', 'danger')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        new_pwd = request.form['new_pwd'].strip()
        if len(new_pwd) < 6:
            flash('密码至少 6 位', 'danger')
            return redirect(url_for('auth.reset_password', token=token))

        user.set_password(new_pwd)
        user.reset_token = None
        user.reset_expire = None
        db.session.commit()

        flash('密码已重置，请重新登录', 'success')
        return redirect(url_for('auth.login'))

    return render_template('reset_password.html')

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
    old_pwd   = data.get('old_pwd', '').strip()
    new_pwd = data.get('new_pwd', '').strip()

    if len(new_pwd) < 6:
        return jsonify(status='error', message='密码至少 6 位'), 400

    user = User.query.filter_by(username=session['username']).first()
    if not user or not user.check_password(old_pwd):
        return jsonify({'status': 'error', 'message': '旧密码错误'}), 400
    
    # 更新密码
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


# ---------------- 启动 ----------------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)