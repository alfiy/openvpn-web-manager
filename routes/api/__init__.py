# routes/api/__init__.py
from flask import Blueprint

api_bp = Blueprint('api_bp', __name__, url_prefix='/api')

from . import auth, clients  # 导入子模块以注册路由
