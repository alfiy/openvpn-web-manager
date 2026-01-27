from flask import Blueprint, jsonify
from utils.openvpn_utils import check_openvpn_status
from routes.helpers import login_required
import logging

logger = logging.getLogger(__name__)

status_bp = Blueprint('status', __name__)

@status_bp.route('/api/status', methods=['GET'])
@login_required
def get_status():
    """
    获取 OpenVPN 状态
    """
    try:
        # 调用改进后的状态检查函数
        status = check_openvpn_status()
        
        # ✅ 确保返回的状态是标准值
        valid_statuses = ['running', 'installed', 'not_installed']
        if status not in valid_statuses:
            logger.warning(f"⚠️  check_openvpn_status() 返回了非标准状态: {status}")
            status = 'not_installed'  # 默认为未安装
        
        # logger.info(f"✅ OpenVPN 状态: {status}")
        
        # ✅ 返回标准 JSON 格式
        return jsonify({
            "status": status
        }), 200
        
    except Exception as e:
        # ✅ 即使出错也返回 JSON 和 200 状态码
        logger.error(f"❌ 获取 OpenVPN 状态失败: {e}", exc_info=True)
        
        return jsonify({
            "status": "not_installed"
        }), 200  # ⚠️ 注意: 返回 200 而不是 500