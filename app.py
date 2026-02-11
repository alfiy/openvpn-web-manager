# app.py
import os
from datetime import timedelta
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, url_for, flash
from flask_session import Session
from flask_mail import Mail
from flask_wtf.csrf import CSRFError
from flask_login import LoginManager
from sqlalchemy import event, Engine
from models import db, User, Role, ClientGroup
from routes.helpers import init_csrf_guard
from utils.api_response import api_error
from extensions import Limiter
from flask_limiter.util import get_remote_address
from redis import Redis

# 创建 Redis 连接
try:
    redis = Redis(host='localhost', port=6379, db=0)
    redis.ping()
    print("Redis connected successfully")
except Exception as e:
    print("Failed to connect to Redis:", e)

# 设置 Limiter 使用 Redis 存储
limiter = Limiter(get_remote_address, storage_uri="redis://localhost:6379/0")

# 加载环境变量
load_dotenv()

# 初始化扩展实例
mail = Mail()
login_manager = LoginManager()

# 从 extensions 统一导入 csrf
from extensions import csrf

# 统一导入所有蓝图
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
from routes.api.client_groups import client_groups_bp
from flask_wtf.csrf import generate_csrf
from routes.dashboard import dashboard_bp
from utils.tc_config_exporter import export_tc_config


def optimize_sqlite_connection():
    """
    启用 SQLite WAL 模式以改善并发性能
    """
    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        if 'sqlite' in str(dbapi_connection):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA cache_size=-64000")
            cursor.execute("PRAGMA temp_store=MEMORY")
            cursor.close()

def create_app():
    """
    应用程序工厂函数，用于创建和配置 Flask 应用实例。
    """
    app = Flask(__name__)
    limiter.init_app(app)
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

    # SQLite 优化配置（连接池和超时设置）
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'connect_args': {
            'timeout': 15,
        },
        'pool_size': 10,
        'pool_recycle': 3600,
        'pool_pre_ping': True,
    }

    # Session 存储路径
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['SESSION_FILE_DIR'] = os.path.join(DATA_DIR, "session")
    os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

    # 配置CSRF保护
    app.config['WTF_CSRF_ENABLED'] = True
    app.config['WTF_CSRF_TIME_LIMIT'] = 3600
    app.config['WTF_CSRF_SSL_STRICT'] = False
    app.config['WTF_CSRF_FIELD_NAME'] = 'csrf_token'
    app.config['WTF_CSRF_HEADERS'] = ['X-CSRFToken']

    # 全局 JSON 错误处理
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
        return api_error("Not found", status=404)

    @app.errorhandler(500)
    def _handle_500(e):
        return api_error("Internal server error", status=500)

    # 初始化扩展
    Session(app)
    mail.init_app(app)
    csrf.init_app(app)
    db.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)

    # 启用 SQLite WAL 优化
    optimize_sqlite_connection()

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
        flash('您需要登录才能访问此页面', 'warning')
        return redirect(url_for('auth_bp.login'))

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        return jsonify({'status': 'error', 'message': '安全令牌无效,请刷新页面后重试。'}), 400

    # 确保所有模板都能访问 csrf_token
    @app.context_processor
    def inject_csrf_token():
        return dict(csrf_token=generate_csrf())

    # 在应用上下文中执行数据库操作
    with app.app_context():
        db.create_all()
        
        # 检查并创建超级管理员账户
        if not User.query.filter_by(username='super_admin').first():
            super_admin = User(
                username='super_admin',
                email='super_admin@example.com',
                role=Role.SUPER_ADMIN
            )
            super_admin.set_password('admin123')
            db.session.add(super_admin)
            db.session.commit()
            print("✅ 默认超级管理员账户已创建: super_admin / admin123")
        
        # 检查并创建普通管理员账户
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                email='admin@example.com',
                role=Role.ADMIN
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("✅ 默认管理员账户已创建: admin / admin123")

         # 🆕 检查并创建默认用户组（不限速）
        if not ClientGroup.query.filter_by(name='default').first():
            default_group = ClientGroup(
                name='default',
                description='默认用户组（不限速）',
                upload_rate='1000Mbit',
                download_rate='1000Mbit'
            )
            db.session.add(default_group)
            db.session.commit()
            print("✅ 默认用户组已创建: default (不限速: 1000Mbit/1000Mbit)")       
        
        # 初始化导出 TC 配置
        try:
            export_tc_config()
            # print("✅ TC 配置已初始化")
        except Exception as e:
            print(f"⚠️  TC 配置初始化失败: {e}")

    # 列出所有需要 CSRF 校验的纯 JSON 蓝图
    json_blueprints = [
        auth_bp, install_bp, add_client_bp,
        revoke_client_bp, uninstall_bp, download_client_bp,
        modify_client_expiry_bp, enable_client_bp, ip_bp,
        user_bp, add_users_bp, delete_user_bp, status_bp,
        restart_openvpn_bp, client_groups_bp
    ]
    
    for bp in json_blueprints:
        init_csrf_guard(bp)

    # 注册所有蓝图
    app.register_blueprint(main_bp, url_prefix='/')
    app.register_blueprint(auth_bp, url_prefix="/auth")
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
    app.register_blueprint(api_bp)
    app.register_blueprint(client_groups_bp)
    app.register_blueprint(dashboard_bp)

    return app


# 启动应用
app = create_app()

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Flask VPN 管理系统启动中...")
    print("=" * 60)
    print("✅ SQLite WAL 模式已启用")
    print("✅ 数据库连接池已配置")
    print("✅ TC 配置导出已初始化")
    print("✅ 用户组管理路由已加载")
    print("=" * 60)
    print("📍 访问地址: http://0.0.0.0:8080")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=8080, use_reloader=False)