from flask import Blueprint, json, request, jsonify
import os
import subprocess
from utils.openvpn_utils import log_message
from routes.helpers import login_required, json_csrf_protect

enable_client_bp = Blueprint('enable_client', __name__)

@enable_client_bp.route('/enable_client', methods=['POST'])
@login_required
@json_csrf_protect
def enable_client():
    """Re-enable a disabled client by removing the flag file"""
    try:
        data = json.loads(request.data)
    except (json.JSONDecodeError, KeyError) as e:
        log_message(f"Error parsing JSON from request: {e}")
        return jsonify({'status': 'error', 'message': 'Invalid JSON or missing client_name'}), 400

    client_name = data.get('client_name', '').strip()
    if not client_name:
        return jsonify({'status': 'error', 'message': 'Client name is required'}), 400

    log_message(f"Starting re-enable process for client: {client_name}")

    try:
        # Step 1: Remove the disabled flag file
        disabled_clients_dir = '/etc/openvpn/disabled_clients'
        flag_file = os.path.join(disabled_clients_dir, client_name)

        if os.path.exists(flag_file):
            subprocess.run(['sudo', 'rm', '-f', flag_file], check=True)
            log_message(f"Removed disabled flag file for client: {client_name}")
        else:
            log_message(f"Client {client_name} is not disabled or flag file not found.")
            return jsonify({
                'status': 'warning',
                'message': f'Client {client_name} 已经处于启用状态或未被禁用。'
            })

        log_message(f"Successfully re-enabled client: {client_name}")
        return jsonify({
            'status': 'success',
            'message': f'客户端 {client_name} 已成功重新启用。'
        })

    except subprocess.CalledProcessError as e:
        log_message(f"Command failed during re-enable process: {e}")
        return jsonify({'status': 'error', 'message': f'命令执行失败：{str(e)}'}), 500
    except Exception as e:
        log_message(f"Unexpected error during re-enable: {e}")
        return jsonify({'status': 'error', 'message': f'重新启用过程中发生意外错误：{str(e)}'}), 500