"""
OpenVPN 监控模块
一个功能完整、模块化的OpenVPN监控系统
"""

import os
from flask import Blueprint

# 获取模块目录
module_dir = os.path.dirname(os.path.abspath(__file__))

# 创建蓝图 - 使用绝对路径
openvpn_bp = Blueprint(
    'openvpn',
    __name__,
    template_folder=os.path.join(module_dir, 'templates'),
    static_folder=os.path.join(module_dir, 'static'),
    url_prefix='/openvpn'
)

# 导入路由
from . import routes

__version__ = '1.0.0'
__all__ = ['openvpn_bp']