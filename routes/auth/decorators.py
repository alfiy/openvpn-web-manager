"""兼容入口：统一使用 routes.helpers 中的装饰器。"""
from routes.helpers import (  # noqa: F401
    login_required,
    admin_required,
    super_admin_required,
    roles_required,
    role_required,
)
