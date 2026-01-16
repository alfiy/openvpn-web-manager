from flask import Blueprint, jsonify
from utils.openvpn_utils import check_openvpn_status
from routes.helpers import login_required

status_bp = Blueprint('status', __name__)

@status_bp.route('/api/status', methods=['GET'])
@login_required
def get_status():
    try:
        status = check_openvpn_status()
        if status not in ['running', 'installed', 'not_installed']:
            # 返回未知状态，而不是直接返回错误字符串
            status = 'unknown'
    except Exception as e:
        status = 'unknown'
        # 可以打印日志
        print(f"[SERVER] check_openvpn_status() 异常: {e}", flush=True)

    return jsonify({"status": status})