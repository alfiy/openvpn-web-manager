from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import enum
import logging
from datetime import datetime,timezone

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

    # ✅ NOCASE 唯一
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

        
    # 🆕 关联到用户组
    group_id = db.Column(db.Integer, db.ForeignKey('client_groups.id'), nullable=True)
    
    # ✅ 改进：添加创建时间和更新时间
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class ClientGroup(db.Model):
    """
    🆕 用户组模型：用于将客户端分组管理和限速
    """
    __tablename__ = 'client_groups'

    id = db.Column(db.Integer, primary_key=True)
    
    # 用户组名称（唯一，不区分大小写）
    name = db.Column(
        db.String(100, collation="NOCASE"),
        nullable=False,
        unique=True
    )
    
    # 用户组描述
    description = db.Column(db.String(255), nullable=True)
    
    # 上行速率（单位：Mbit，例如：5, 10, 20）
    upload_rate = db.Column(db.String(50), default="2Mbit", nullable=False)
    
    # 下行速率（单位：Mbit，例如：5, 10, 50）
    download_rate = db.Column(db.String(50), default="2Mbit", nullable=False)
    
    # 创建时间
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # 更新时间
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    # 用户组的客户端关系（一对多）
    clients = db.relationship('Client', backref='group', lazy=True, cascade='save-update, merge')
    
    def to_dict(self):
        """序列化为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'upload_rate': self.upload_rate,
            'download_rate': self.download_rate,
            'client_count': len(self.clients),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
