import os
import subprocess
from flask import Blueprint, jsonify
from utils.openvpn_utils import log_message
from routes.helpers import login_required, json_csrf_protect

status_bp = Blueprint('status', __name__)

def check_openvpn_status():
    """
    检查 OpenVPN 服务是否正在运行。
    
    返回:
        str: 'running', 'installed', 或 'not_installed'。
    """
    # 尝试使用更通用的服务名称 openvpn.service
    service_name = 'openvpn@server.service' 

    try:
        # 检查服务是否正在运行
        cmd = ['systemctl', 'is-active', '--quiet', service_name]
        result = subprocess.run(cmd, check=False)

        if result.returncode == 0:
            log_message("OpenVPN 服务状态: running")
            return 'running'
        
        # 如果服务不在运行，检查它是否至少已安装（通过是否可启用判断）
        cmd = ['systemctl', 'is-enabled', '--quiet', service_name]
        result = subprocess.run(cmd, check=False)
        if result.returncode == 0:
            log_message("OpenVPN 服务状态: installed")
            return 'installed'
            
    except Exception as e:
        log_message(f"检查 OpenVPN 服务状态失败: {e}", level="error")

    log_message("OpenVPN 服务状态: not_installed")
    return 'not_installed'

@status_bp.route('/api/status', methods=['GET'])
@login_required
@json_csrf_protect
def get_status():
    status = check_openvpn_status()
    return jsonify({"status": status})