# app.py
import os
from datetime import timedelta
from dotenv import load_dotenv
from flask import Flask, redirect, url_for, flash
from flask_session import Session
from flask_mail import Mail
from flask_login import LoginManager
from sqlalchemy import event, Engine
from models import db, User, Role, ClientGroup
from routes.helpers import init_csrf_guard
from flask_limiter.util import get_remote_address
from redis import Redis
from flask_wtf.csrf import generate_csrf
import secrets

# ============================================================================
# 导入重构后的工具模块
# ============================================================================
from utils.request_monitor import ConcurrentRequestLimiter, RequestMonitor
from utils.api_response import register_error_handlers, register_request_handlers

# 创建并发限制器和监控器
concurrent_limiter = ConcurrentRequestLimiter(max_concurrent=10)
request_monitor = RequestMonitor(max_records=100)

# ============================================================================
# Redis 和 Limiter 初始化
# ============================================================================

# 创建 Redis 连接
try:
    redis = Redis(host='localhost', port=6379, db=0, socket_timeout=5)
    redis.ping()
    print("✅ Redis connected successfully")
except Exception as e:
    print(f"⚠️  Failed to connect to Redis: {e}")
    redis = None

# Limiter 使用 extensions 中的单例，避免重启接口限流失效
from extensions import limiter as _limiter_mod  # noqa: F401

# 加载环境变量
load_dotenv()

# 初始化扩展实例
mail = Mail()
login_manager = LoginManager()

# 从 extensions 统一导入 csrf
from extensions import csrf, limiter

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
from routes.dashboard import dashboard_bp

# 导入健康检查 API
from routes.api.health import health_bp, init_health_monitor

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
            cursor.execute("PRAGMA busy_timeout=10000")  # 10 秒超时
            cursor.close()


def _ensure_user_schema():
    """为已有库补齐 must_change_password 列。"""
    from sqlalchemy import inspect, text
    try:
        inspector = inspect(db.engine)
        if 'users' not in inspector.get_table_names():
            return
        cols = {c['name'] for c in inspector.get_columns('users')}
        if 'must_change_password' not in cols:
            db.session.execute(text(
                'ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT 0'
            ))
            db.session.commit()
            print('✅ 已为 users 表添加 must_change_password 列')
    except Exception as exc:
        db.session.rollback()
        print(f'⚠️  检查 users 表结构失败: {exc}')


def _flag_default_passwords():
    try:
        for user in User.query.filter(User.username.in_(['admin', 'super_admin'])).all():
            if user.check_password('admin123') and not user.must_change_password:
                user.must_change_password = True
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        print(f'⚠️  标记默认口令失败: {exc}')


def create_app():
    """
    应用程序工厂函数，用于创建和配置 Flask 应用实例。
    """
    app = Flask(__name__)
    flask_env = (os.getenv('FLASK_ENV') or os.getenv('FLASK_DEBUG') or '').lower()
    is_prod = flask_env in ('production', 'prod') or os.getenv('VPNWM_REQUIRE_SECRET') == '1'
    secret = (os.environ.get('SECRET_KEY') or '').strip()
    weak_secrets = {'', 'a-very-secret-key-that-should-be-kept-secret', 'changeme', 'secret'}
    if secret in weak_secrets:
        if is_prod:
            raise RuntimeError('生产环境必须通过环境变量 SECRET_KEY 设置足够强度的密钥')
        secret = secrets.token_hex(32)
        print('⚠️  未配置 SECRET_KEY，本次使用临时密钥（重启后 Session 失效）。生产环境请写入 .env')
    app.config['SECRET_KEY'] = secret
    app.config['DEBUG'] = (not is_prod) and os.getenv('FLASK_DEBUG', '0') == '1'
    if redis:
        app.config['RATELIMIT_STORAGE_URI'] = 'redis://localhost:6379/0'
    else:
        app.config['RATELIMIT_STORAGE_URI'] = 'memory://'
        print("⚠️  Using memory storage for rate limiting (Redis unavailable)")
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

    # ========================================================================
    # 注册全局错误处理器和请求处理器（使用重构后的模块）
    # ========================================================================
    register_error_handlers(app)
    register_request_handlers(app, concurrent_limiter, request_monitor)

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

    # 确保所有模板都能访问 csrf_token
    @app.context_processor
    def inject_csrf_token():
        return dict(csrf_token=generate_csrf())

    ALLOW_WHEN_MUST_CHANGE = {
        'auth_bp.login',
        'auth_bp.logout',
        'auth_bp.api_login',
        'auth_bp.api_change_password',
        'auth_bp.get_csrf_token',
        'api_bp.api_login',
        'static',
        'health.health_check',
    }

    @app.before_request
    def _force_password_change():
        from flask import request
        from flask_login import current_user
        if not getattr(current_user, 'is_authenticated', False):
            return None
        if not getattr(current_user, 'must_change_password', False):
            return None
        endpoint = request.endpoint or ''
        if endpoint in ALLOW_WHEN_MUST_CHANGE or endpoint.startswith('static'):
            return None
        if request.is_json or request.path.startswith('/api/'):
            return {
                'status': 'error',
                'code': 'must_change_password',
                'message': '请先修改默认密码后再使用系统'
            }, 403
        from flask import redirect, url_for, flash
        flash('请先修改默认密码后再使用系统', 'warning')
        return redirect(url_for('main_bp.index'))

    # 在应用上下文中执行数据库操作
    with app.app_context():
        db.create_all()
        _ensure_user_schema()
        _flag_default_passwords()
        
        # 检查并创建超级管理员账户
        if not User.query.filter_by(username='super_admin').first():
            super_admin = User(
                username='super_admin',
                email='super_admin@example.com',
                role=Role.SUPER_ADMIN
            )
            super_admin.set_password('admin123')
            super_admin.must_change_password = True
            db.session.add(super_admin)
            db.session.commit()
            print("✅ 默认超级管理员已创建: super_admin / admin123（首次登录必须改密）")
        
        # 检查并创建普通管理员账户
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                email='admin@example.com',
                role=Role.ADMIN
            )
            admin.set_password('admin123')
            admin.must_change_password = True
            db.session.add(admin)
            db.session.commit()
            print("✅ 默认管理员已创建: admin / admin123（首次登录必须改密）")

         # 检查并创建默认用户组（不限速）
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

    # ========================================================================
    # 注册所有蓝图
    # ========================================================================
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
    
    # 注册健康检查 API（放在最后）
    init_health_monitor(redis, concurrent_limiter, request_monitor)
    app.register_blueprint(health_bp)

    return app


# 启动应用
app = create_app()

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Flask VPN 管理系统启动中...")
    print("=" * 60)
    print("✅ SQLite WAL 模式已启用")
    print("✅ 数据库连接池已配置")
    print("✅ 请求超时保护已启用")
    print("✅ 并发请求限制已启用 (最大: 10)")
    print("✅ 性能监控已启用")
    print("✅ 健康检查 API: /api/health")
    print("✅ 性能指标 API: /api/metrics")
    print("✅ 系统状态 API: /api/status")
    print("✅ TC 配置导出已初始化")
    print("✅ 用户组管理路由已加载")
    print("=" * 60)
    print("📍 访问地址: http://0.0.0.0:8080")
    print("📍 健康检查: http://0.0.0.0:8080/api/health")
    print("📍 性能指标: http://0.0.0.0:8080/api/metrics")
    print("📍 系统状态: http://0.0.0.0:8080/api/status")
    print("=" * 60)
    app.run(debug=app.config.get('DEBUG', False), host='0.0.0.0', port=8080, use_reloader=False)