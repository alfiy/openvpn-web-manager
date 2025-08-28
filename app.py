from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from flask import Flask, render_template, session, request, jsonify, redirect, url_for, flash
from flask_session import Session
from functools import wraps
import json
import os
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User
from flask_mail import Mail, Message
import secrets
# 导入CSRF保护所需模块（补充validate_csrf导入）
from flask_wtf.csrf import CSRFProtect, generate_csrf, validate_csrf


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
from routes.main_bp          import main_bp

# ---------------- Flask 配置 ----------------
app = Flask(__name__)
app.config['DEBUG'] = True  # 生产环境应设为False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'replace-me-in-production-with-a-strong-key')  # 增强默认密钥安全性
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

# 配置CSRF保护
app.config['WTF_CSRF_ENABLED'] = True  # 启用CSRF保护
app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # CSRF令牌有效期1小时
app.config['WTF_CSRF_SSL_STRICT'] = False  # 开发环境暂时关闭严格SSL验证（生产环境需开启）
app.config['WTF_CSRF_FIELD_NAME'] = 'csrf_token'  # 与前端表单字段名保持一致
app.config['WTF_CSRF_HEADERS'] = ['X-CSRFToken']  # 指定从请求头获取令牌的字段名


load_dotenv()
# 邮件配置
app.config.update(
    MAIL_SERVER=os.getenv('MAIL_SERVER', 'smtp.qq.com'),
    MAIL_PORT=int(os.getenv('MAIL_PORT', 465)),
    MAIL_USE_SSL=os.getenv('MAIL_USE_SSL', 'true').lower() in ('true', '1'),  # QQ邮箱默认使用SSL
    MAIL_USE_TLS=os.getenv('MAIL_USE_TLS', 'false').lower() in ('true', '1'),
    MAIL_USERNAME=os.getenv('MAIL_USERNAME'),
    MAIL_PASSWORD=os.getenv('MAIL_PASSWORD'),
    MAIL_DEFAULT_SENDER=os.getenv('MAIL_DEFAULT_SENDER')
)


# SQLite 单文件数据库
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'vpn_users.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 初始化扩展
Session(app)
mail = Mail(app)
db.init_app(app)
csrf = CSRFProtect(app)  # 初始化CSRF保护

# 确保所有模板都能访问csrf_token（关键修复：保持变量名与Flask-WTF默认一致）
@app.context_processor
def inject_csrf_token():
    """将CSRF令牌注入所有模板上下文，供前端表单使用"""
    return dict(csrf_token=generate_csrf())

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
    
# JSON请求CSRF验证装饰器（修复了validate_csrf导入问题）
def json_csrf_protect(f):
    """专门用于JSON格式POST请求的CSRF验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 获取请求头中的CSRF令牌
        csrf_token = request.headers.get('X-CSRFToken')
        
        # 检查令牌是否存在
        if not csrf_token:
            return jsonify({'status': 'error', 'message': '缺少CSRF令牌'}), 403
        
        # 验证令牌有效性
        try:
            validate_csrf(csrf_token)
        except Exception:
            return jsonify({'status': 'error', 'message': 'CSRF令牌验证失败，请刷新页面重试'}), 403
            
        return f(*args, **kwargs)
    return decorated_function

# ---------------- 认证蓝图 ----------------
from flask import Blueprint
auth_bp = Blueprint('auth', __name__)

# 为AJAX请求提供CSRF令牌的接口
@app.route('/api/csrf-token')
def get_csrf_token():
    """供前端AJAX请求获取最新的CSRF令牌"""
    return jsonify({'csrf_token': generate_csrf()})


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # 表单提交，Flask-WTF会自动验证CSRF
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
    # 表单提交，Flask-WTF会自动验证CSRF
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
@csrf.exempt
def login():
    if request.method == 'POST':
        # ⚠️ 根据请求类型，从正确的位置获取数据
        is_api_request = request.is_json or 'application/json' in request.headers.get('Content-Type', '')
        
        if is_api_request:
            data = request.get_json()
            if not data:
                return jsonify({'status': 'error', 'message': '无效的JSON请求'}), 400
            username = data.get('username')
            password = data.get('password')
        else:
            # 兼容传统的表单提交
            username = request.form.get('username')
            password = request.form.get('password')

        # 检查用户名和密码是否为空，这是个好习惯
        if not username or not password:
             return jsonify({'status': 'error', 'message': '用户名和密码不能为空'}), 400

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['logged_in'] = True
            session['username'] = username
            
            # 登录成功，根据请求类型返回不同响应
            if is_api_request:
                csrf_token = generate_csrf()
                return jsonify({
                    'status': 'success',
                    'message': '登录成功',
                    'csrf_token': csrf_token
                }), 200
            else:
                return redirect(url_for('index.index'))
        
        # 登录失败，根据请求类型返回不同响应
        if is_api_request:
            return jsonify({'status': 'error', 'message': '用户名或密码错误'}), 401
        else:
            return render_template('login.html', error='用户名或密码错误')
    
    return render_template('login.html')


@auth_bp.route('/change_password', methods=['POST'])
@login_required
@json_csrf_protect  # 应用JSON CSRF验证装饰器
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
app.register_blueprint(main_bp, url_prefix='/')  


# ---------------- 启动 ----------------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
