from flask import Blueprint, jsonify
from utils.openvpn_utils import check_openvpn_status
from routes.helpers import login_required

status_bp = Blueprint('status', __name__)

@status_bp.route('/api/status', methods=['GET'])
@login_required
def get_status():
    status = check_openvpn_status()
    return jsonify({"status": status})