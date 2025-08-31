from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import enum

db = SQLAlchemy()

class Role(enum.Enum):
    NORMAL = 0
    ADMIN = 1
    SUPER_ADMIN = 2

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    # ✅ 修复：将字段名改为 password_hash，以便更好地表示存储的是哈希值
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.Enum(Role), default=Role.NORMAL, nullable=False)
    reset_token = db.Column(db.String(128))
    reset_expire = db.Column(db.DateTime, nullable=True)

    def set_password(self, raw):
        # ✅ 修复：将哈希值赋给正确的字段 password_hash
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        # ✅ 修复：从正确的字段 password_hash 中获取哈希值进行验证
        return check_password_hash(self.password_hash, raw)

    # Flask-Login 提供的 UserMixin 已经包含了 is_authenticated 等方法，
    # 除非你有特殊需求，否则无需重写，以避免潜在的错误。
    # 我已将这些方法移除。
    
    # ✅ 确保 get_id 方法返回字符串类型，UserMixin 已经提供了
    def get_id(self):
        return str(self.id)

    @property
    def role_name(self):
        """返回角色的中文名称"""
        if self.role == Role.SUPER_ADMIN:
            return "超级管理员"
        elif self.role == Role.ADMIN:
            return "管理员"
        else:
            return "普通用户"

class Client(db.Model):
    __tablename__ = 'clients'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    expiry = db.Column(db.DateTime, nullable=True)
    online = db.Column(db.Boolean, default=False)
    disabled = db.Column(db.Boolean, default=False)
    vpn_ip = db.Column(db.String(15), nullable=True)
    real_ip = db.Column(db.String(15), nullable=True)
    duration = db.Column(db.String(50), nullable=True)