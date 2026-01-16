from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import enum
import logging

logger = logging.getLogger(__name__)

db = SQLAlchemy()


class Role(enum.Enum):
    NORMAL = 0
    ADMIN = 1
    SUPER_ADMIN = 2


class User(db.Model, UserMixin):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)

    # ✅ 用户名：大小写不敏感唯一
    username = db.Column(
        db.String(64, collation="NOCASE"),
        nullable=False,
        unique=True
    )

    # ✅ Email：大小写不敏感唯一
    email = db.Column(
        db.String(120, collation="NOCASE"),
        nullable=False,
        unique=True
    )

    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.Enum(Role), default=Role.NORMAL, nullable=False)

    reset_token = db.Column(db.String(128))
    reset_expire = db.Column(db.DateTime, nullable=True)

    def set_password(self, raw):
        if not raw:
            raise ValueError("密码不能为空")
        if len(raw) < 6:
            raise ValueError("密码长度至少为6个字符")
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    def get_id(self):
        return str(self.id)

    @property
    def role_name(self):
        if self.role == Role.SUPER_ADMIN:
            return "超级管理员"
        elif self.role == Role.ADMIN:
            return "管理员"
        return "普通用户"


class Client(db.Model):
    __tablename__ = 'clients'

    id = db.Column(db.Integer, primary_key=True)

    # ✅ 关键修复点：NOCASE 唯一
    name = db.Column(
        db.String(100, collation="NOCASE"),
        nullable=False,
        unique=True
    )

    description = db.Column(db.String(255), nullable=True)
    expiry = db.Column(db.DateTime, nullable=True)          # 证书真实到期时间
    logical_expiry = db.Column(db.DateTime, nullable=True)  # 逻辑到期时间
    online = db.Column(db.Boolean, default=False)
    disabled = db.Column(db.Boolean, default=False)
    vpn_ip = db.Column(db.String(15), nullable=True)
    real_ip = db.Column(db.String(15), nullable=True)
    duration = db.Column(db.String(50), nullable=True)
