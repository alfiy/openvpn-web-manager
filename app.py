# app.py
import os
from datetime import timedelta
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, url_for
from flask_session import Session
from flask_mail import Mail
from flask_wtf.csrf import CSRFError
from flask_login import LoginManager
from models import db, User, Role
from routes.helpers import init_csrf_guard
from utils.api_response import api_error

# 加载环境变量
load_dotenv()

# 初始化扩展实例（这里不要再创建 CSRFProtect()，统一从 extensions 导入）
mail = Mail()
login_manager = LoginManager()

# 从 extensions 统一导入 csrf（extensions.py 应包含 csrf = CSRFProtect()）
from extensions import csrf

# 统一导入所有蓝图（这些蓝图内部应 import extensions.csrf，而不是自行创建 csrf）
from routes.auth import auth_bp
from routes.main_bp import main_bp
from routes.install import install_bp
from routes.api.add_client import add_client_bp
from routes.api.revoke_client import revoke_client_bp
from routes.uninstall import uninstall_bp
from routes.api.download_client import download_client_bp
from routes.modify_client_expiry import modify_client_expiry_bp
from routes.api.enable_client import enable_client_bp
from routes.get_ip_list import ip_bp
from routes.get_users import user_bp
from routes.add_users import add_users_bp
from routes.delete_user import delete_user_bp
from routes.status_bp import status_bp
from routes.restart_openvpn import restart_openvpn_bp
from routes.api import api_bp
from flask_wtf.csrf import generate_csrf

def create_app():
    """
    应用程序工厂函数，用于创建和配置 Flask 应用实例。
    """
    app = Flask(__name__)
    app.config['DEBUG'] = True
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a-very-secret-key-that-should-be-kept-secret')
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

    # 邮件配置
    app.config.update(
        MAIL_SERVER=os.getenv('MAIL_SERVER', 'smtp.qq.com'),
        MAIL_PORT=int(os.getenv('MAIL_PORT', 465)),
        MAIL_USE_SSL=os.getenv('MAIL_USE_SSL', 'true').lower() in ('true', '1'),
        MAIL_USE_TLS=os.getenv('MAIL_USE_TLS', 'false').lower() in ('true', '1'),
        MAIL_USERNAME=os.getenv('MAIL_USERNAME'),
        MAIL_PASSWORD=os.getenv('MAIL_PASSWORD'),
        MAIL_DEFAULT_SENDER=os.getenv('MAIL_DEFAULT_SENDER')
    )

    # 生产环境数据目录
    DATA_DIR = "/opt/vpnwm/data"
    os.makedirs(DATA_DIR, exist_ok=True)

    # SQLite 单文件数据库 /opt/vpnwm/data/vpn_users.db
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(DATA_DIR, 'vpn_users.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Session 存储路径
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['SESSION_FILE_DIR'] = os.path.join(DATA_DIR, "session")
    os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

    # 配置CSRF保护（WTF 配置项仍可使用）
    app.config['WTF_CSRF_ENABLED'] = True
    app.config['WTF_CSRF_TIME_LIMIT'] = 3600
    app.config['WTF_CSRF_SSL_STRICT'] = False
    app.config['WTF_CSRF_FIELD_NAME'] = 'csrf_token'
    app.config['WTF_CSRF_HEADERS'] = ['X-CSRFToken']

    # 全局 JSON 错误处理（只对 API 请求有效）
    @app.errorhandler(400)
    def _handle_400(e):
        return api_error("Bad request", status=400)
    @app.errorhandler(401)
    def _handle_401(e):
        return api_error("Unauthorized", status=401)
    @app.errorhandler(403)
    def _handle_403(e):
        return api_error("Forbidden", status=403)
    @app.errorhandler(404)
    def _handle_404(e):
        # 如果请求期望 HTML，可以返回模板，这里默认 JSON
        return api_error("Not found", status=404)
    @app.errorhandler(500)
    def _handle_500(e):
        return api_error("Internal server error", status=500)

    # 初始化扩展（使用 extensions 中的 csrf）
    Session(app)
    mail.init_app(app)
    csrf.init_app(app)   # <-- 初始化来自 extensions 的 csrf 实例
    db.init_app(app)
    login_manager.init_app(app)

    # 告诉 Flask-Login 如何加载用户
    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except Exception:
            return None

    # 配置未授权用户的处理方式
    @login_manager.unauthorized_handler
    def unauthorized_callback():
        return redirect(url_for('auth_bp.login'))

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        # 使用统一的 JSON 错误格式
        return jsonify({'status': 'error', 'message': '安全令牌无效，请刷新页面后重试。'}), 400

    # 确保所有模板都能访问 csrf_token（使用 extensions.csrf 的 generate）
    @app.context_processor
    def inject_csrf_token():
        return dict(csrf_token=generate_csrf())

    # 在应用上下文中执行数据库操作（创建表与初始用户）
    with app.app_context():
        db.create_all()
        # 检查并创建管理员账户（仅在首次运行创建）
        if not User.query.filter_by(username='super_admin').first():
            super_admin = User(username='super_admin', email='super_admin@example.com', role=Role.SUPER_ADMIN)
            super_admin.set_password('admin123')
            db.session.add(super_admin)
            db.session.commit()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', email='admin@example.com', role=Role.ADMIN)
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()

    # 列出所有「纯 JSON」蓝图（按需增删）
    json_blueprints = [
        auth_bp, install_bp, add_client_bp,
        revoke_client_bp, uninstall_bp, download_client_bp,
        modify_client_expiry_bp, enable_client_bp, ip_bp,
        user_bp, add_users_bp, delete_user_bp,status_bp, restart_openvpn_bp
    ]
    for bp in json_blueprints:
        init_csrf_guard(bp)      # 给每个蓝图挂 before_request 校验

    # ---------------- 注册蓝图 ----------------
    app.register_blueprint(main_bp, url_prefix='/')
    app.register_blueprint(install_bp)
    app.register_blueprint(add_client_bp)
    app.register_blueprint(revoke_client_bp)
    app.register_blueprint(uninstall_bp)
    app.register_blueprint(download_client_bp)
    app.register_blueprint(modify_client_expiry_bp)
    app.register_blueprint(enable_client_bp)
    app.register_blueprint(ip_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(add_users_bp)
    app.register_blueprint(delete_user_bp)
    app.register_blueprint(status_bp)
    app.register_blueprint(restart_openvpn_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(api_bp)

    return app


# ---------------- 启动 ----------------
app = create_app()
if __name__ == '__main__':
    print("Starting Flask in Development Mode...")
    app.run(debug=True, host='0.0.0.0', port=8080, use_reloader=False)
