import os
import json
from datetime import timedelta, timezone
from dotenv import load_dotenv
from flask import Flask, render_template, session, jsonify, redirect, url_for
from flask_session import Session
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect, generate_csrf, CSRFError
from flask_login import LoginManager
from models import db, User, Role

# 加载环境变量
load_dotenv()

# 初始化扩展，但不在全局作用域绑定
mail = Mail()
csrf = CSRFProtect()
login_manager = LoginManager()

# 统一导入所有蓝图，避免循环导入问题
from routes.auth import auth_bp
from routes.main_bp import main_bp
from routes.install import install_bp
from routes.add_client import add_client_bp
from routes.revoke_client import revoke_client_bp
from routes.uninstall import uninstall_bp
from routes.download_client import download_client_bp
from routes.modify_client_expiry import modify_client_expiry_bp
from routes.enable_client import enable_client_bp
from routes.get_ip_list import ip_bp
from routes.index import index_bp
from routes.get_users import user_bp
from routes.add_users import add_users_bp
from routes.delete_user import delete_user_bp
from routes.kill_client import kill_client_bp
# from routes.disconnect_client import disconnect_client_bp


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

    # SQLite 单文件数据库
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'vpn_users.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # 配置CSRF保护
    app.config['WTF_CSRF_ENABLED'] = True
    app.config['WTF_CSRF_TIME_LIMIT'] = 3600
    app.config['WTF_CSRF_SSL_STRICT'] = False
    # ✅ 修复：移除对 CSRF 头的显式配置，使用默认值
    app.config['WTF_CSRF_FIELD_NAME'] = 'csrf_token'
    app.config['WTF_CSRF_HEADERS'] = ['X-CSRFToken']

    # 初始化扩展
    Session(app)
    mail.init_app(app)
    csrf.init_app(app)
    db.init_app(app)
    login_manager.init_app(app)

    # 告诉 Flask-Login 如何加载用户
    @login_manager.user_loader
    def load_user(user_id):
        user = db.session.get(User, int(user_id))
        return user

    # 配置未授权用户的处理方式
    @login_manager.unauthorized_handler
    def unauthorized_callback():
        return redirect(url_for('auth_bp.login'))

    @app.errorhandler(CSRFError)
    def csrf_error(reason):
        response = jsonify({'status': 'error', 'message': '安全令牌无效，请刷新页面后重试。'})
        response.status_code = 400
        return response

    # 确保所有模板都能访问csrf_token
    @app.context_processor
    def inject_csrf_token():
        return dict(csrf_token=generate_csrf())

    # 在应用上下文中执行数据库操作
    with app.app_context():
        db.create_all()
        # 检查并创建管理员账户
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
    
    # ---------------- 注册蓝图 ----------------
    # ✅ 修复：只将需要访问根路由的蓝图注册到 '/'
    # main_bp 包含了主页 '/'，其他蓝图应有自己的前缀或不设前缀
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp, url_prefix='/')
    app.register_blueprint(install_bp)
    app.register_blueprint(add_client_bp)
    app.register_blueprint(revoke_client_bp)
    app.register_blueprint(uninstall_bp)
    app.register_blueprint(download_client_bp)
    app.register_blueprint(modify_client_expiry_bp)
    app.register_blueprint(enable_client_bp)
    app.register_blueprint(ip_bp)
    app.register_blueprint(index_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(add_users_bp)
    app.register_blueprint(delete_user_bp)
    # app.register_blueprint(disable_client_bp)
    app.register_blueprint(kill_client_bp)

    return app

# ---------------- 启动 ----------------
if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=8080)