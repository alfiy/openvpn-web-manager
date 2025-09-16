import os
import subprocess
from flask import Blueprint, jsonify
from utils.openvpn_utils import log_message, check_openvpn_status
from routes.helpers import login_required, json_csrf_protect

status_bp = Blueprint('status', __name__)

# def check_openvpn_status():
#     """
#     检查 OpenVPN 服务是否正在运行。
    
#     返回:
#         str: 'running', 'installed', 或 'not_installed'。
#     """
#     # 尝试使用更通用的服务名称 openvpn@server.service
#     service_name = 'openvpn@server.service'

#     try:
#         # 步骤1: 检查服务是否处于活动状态
#         # --quiet 选项会抑制输出，我们只关心返回码
#         if subprocess.run(['systemctl', 'is-active', '--quiet', service_name]).returncode == 0:
#             log_message("OpenVPN 服务状态: running")
#             return 'running'
            
#         # 步骤2: 检查服务是否已安装（但不处于活动状态）
#         # 'systemctl status' 可以判断服务是否存在
#         if subprocess.run(['systemctl', 'status', service_name], capture_output=True).returncode in [3, 4]:
#             # 退出码 3: 服务非活动，但已加载（installed）
#             # 退出码 4: 服务不存在（not_installed）
#             # 这里检查的是服务已存在但未运行的情况
#             log_message("OpenVPN 服务状态: installed")
#             return 'installed'
            
#     except FileNotFoundError:
#         # 'systemctl' 命令不存在，通常意味着系统不是 Systemd
#         log_message("Systemd (systemctl) 命令不存在。", level="error")
#     except Exception as e:
#         log_message(f"检查 OpenVPN 服务状态失败: {e}", level="error")
    
#     log_message("OpenVPN 服务状态: not_installed")
#     return 'not_installed'

@status_bp.route('/api/status', methods=['GET'])
@login_required
@json_csrf_protect
def get_status():
    status = check_openvpn_status()
    return jsonify({"status": status})