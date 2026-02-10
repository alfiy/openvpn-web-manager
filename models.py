from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import enum
import logging
from datetime import datetime, timezone
from sqlalchemy import func

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


# ==================== 🔥 ClientGroup 模型（重点改进）====================
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
        unique=True,
        index=True  # 🆕 添加索引，提升查询性能
    )
    
    description = db.Column(db.String(255), nullable=True)
    
    # 🆕 速率字段：添加默认值和验证注释
    upload_rate = db.Column(
        db.String(50), 
        default="2Mbit", 
        nullable=False,
        comment="上行速率，格式如: 2Mbit, 10Mbit"
    )
    download_rate = db.Column(
        db.String(50), 
        default="2Mbit", 
        nullable=False,
        comment="下行速率，格式如: 2Mbit, 50Mbit"
    )
    
    # 时间戳
    created_at = db.Column(
        db.DateTime, 
        default=lambda: datetime.now(timezone.utc), 
        nullable=False
    )
    updated_at = db.Column(
        db.DateTime, 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc), 
        nullable=False
    )
    
    # 🔥 关系定义：修复级联策略
    clients = db.relationship(
        'Client', 
        backref='group', 
        lazy='dynamic',  # 🆕 改为 dynamic，避免一次性加载所有客户端
        # 🆕 删除用户组时，客户端的 group_id 设为 NULL（而非删除客户端）
        cascade='save-update, merge',
        passive_deletes=True  # 🆕 让数据库处理级联
    )
    
    def to_dict(self, include_members=False):
        """
        序列化为字典
        
        Args:
            include_members: 是否包含成员列表（默认否，避免性能问题）
        """
        # 🆕 优化：使用 scalar 代替 count()，性能更好
        client_count = self.clients.count()  # lazy='dynamic' 支持 .count()
        
        is_default = self.name.lower() == 'default'

        result = {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'upload_rate': self.upload_rate,
            'download_rate': self.download_rate,
            'client_count': client_count,
            'is_default': is_default, 
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        
        # 🆕 可选：包含成员列表（仅在需要时）
        if include_members:
            result['members'] = [
                {
                    'id': c.id,
                    'name': c.name,
                    'online': c.online,
                    'vpn_ip': c.vpn_ip
                }
                for c in self.clients.all()
            ]
        
        return result
    
    def __repr__(self):
        return f'<ClientGroup {self.name}>'


# ==================== 🔥 Client 模型（重点改进）====================
class Client(db.Model):
    __tablename__ = 'clients'

    id = db.Column(db.Integer, primary_key=True)

    # ✅ NOCASE 唯一
    name = db.Column(
        db.String(100, collation="NOCASE"),
        nullable=False,
        unique=True,
        index=True  # 🆕 添加索引
    )

    description = db.Column(db.String(255), nullable=True)
    expiry = db.Column(db.DateTime, nullable=True)          # 证书真实到期时间
    logical_expiry = db.Column(db.DateTime, nullable=True)  # 逻辑到期时间
    
    # 🆕 在线状态字段
    online = db.Column(db.Boolean, default=False, index=True)  # 添加索引
    disabled = db.Column(db.Boolean, default=False)
    
    # 🆕 网络信息字段（添加索引用于查询）
    vpn_ip = db.Column(db.String(15), nullable=True, index=True)  # 🆕 添加索引
    real_ip = db.Column(db.String(15), nullable=True)
    duration = db.Column(db.String(50), nullable=True)

    # 🆕 关联到用户组（添加 ondelete 规则）
    group_id = db.Column(
        db.Integer, 
        db.ForeignKey('client_groups.id', ondelete='SET NULL'),  # 🆕 用户组删除时自动设为 NULL
        nullable=True,
        index=True  # 🆕 添加索引，提升分组查询性能
    )
    
    # ✅ 时间戳
    created_at = db.Column(
        db.DateTime, 
        default=lambda: datetime.now(timezone.utc), 
        nullable=False
    )
    updated_at = db.Column(
        db.DateTime, 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc), 
        nullable=False
    )
    
    # 最后在线时间（用于追踪）
    last_seen = db.Column(
        db.DateTime, 
        nullable=True,
        comment="最后在线时间"
    )

    def to_dict(self, include_group_details=False):
        """
        将客户端对象序列化为字典
        
        Args:
            include_group_details: 是否包含完整的用户组信息（默认否）
        """
        result = {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'expiry': self.expiry.isoformat() if self.expiry else None,
            'logical_expiry': self.logical_expiry.isoformat() if self.logical_expiry else None,
            'online': self.online,
            'disabled': self.disabled,
            'vpn_ip': self.vpn_ip,
            'real_ip': self.real_ip,
            'duration': self.duration,
            'group_id': self.group_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        
        # 条件加载 group 信息
        if include_group_details and self.group:
            result['group'] = {
                'id': self.group.id,
                'name': self.group.name,
                'upload_rate': self.group.upload_rate,
                'download_rate': self.group.download_rate
            }
        else:
            # 默认只返回组名
            result['group'] = self.group.name if self.group else None
        
        # 🆕 添加最后在线时间
        if self.last_seen:
            result['last_seen'] = self.last_seen.isoformat()
        
        return result
    
    # 🆕 添加便捷方法：获取速率配置
    def get_rate_limits(self):
        """
        获取客户端的速率限制
        
        Returns:
            dict: {'upload_rate': '5Mbit', 'download_rate': '10Mbit'}
                  如果没有分组则返回 None
        """
        if not self.group:
            return None
        
        return {
            'upload_rate': self.group.upload_rate,
            'download_rate': self.group.download_rate
        }
    
    # 🆕 添加便捷方法：更新在线状态
    def set_online(self, is_online: bool):
        """
        更新在线状态并记录时间
        
        Args:
            is_online: 是否在线
        """
        self.online = is_online
        if is_online:
            self.last_seen = datetime.now(timezone.utc)
    
    def __repr__(self):
        return f'<Client {self.name}>'