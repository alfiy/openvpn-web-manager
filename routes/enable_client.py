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
    """通过删除标志文件来重新启用客户端"""
    try:
        data = request.get_json()
        if not data:
            log_message("Invalid JSON data from request.")
            return jsonify({'status': 'error', 'message': '请求数据格式错误'}), 400
        
        client_name = data.get('client_name', '').strip()
        if not client_name:
            log_message("Client name is missing.")
            return jsonify({'status': 'error', 'message': '客户端名称不能为空'}), 400

        log_message(f"Starting re-enable process for client: {client_name}")

        disabled_clients_dir = '/etc/openvpn/disabled_clients'
        flag_file_path = os.path.join(disabled_clients_dir, client_name)

        if not os.path.exists(flag_file_path):
            log_message(f"Client {client_name} is already enabled or flag file not found at {flag_file_path}.")
            return jsonify({
                'status': 'warning',
                'message': f'客户端 {client_name} 已经处于启用状态或未被禁用。'
            })

        # 使用与 revoke_client.py 相同的模式执行命令
        # 这种模式能够处理路径中的特殊字符，并且更可靠
        try:
            cmd = ['sudo', 'rm', '-f', flag_file_path]
            log_message(f"Executing command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            log_message(f"Command successful: {result.stdout}")
        except subprocess.CalledProcessError as e:
            log_message(f"Command failed during re-enable process: {e.stderr}")
            return jsonify({'status': 'error', 'message': f'删除标志文件失败：{e.stderr}'}), 500

        log_message(f"Successfully re-enabled client: {client_name}")
        return jsonify({
            'status': 'success',
            'message': f'客户端 {client_name} 已成功重新启用。'
        })

    except Exception as e:
        log_message(f"Unexpected error during re-enable: {str(e)}")
        return jsonify({'status': 'error', 'message': f'重新启用过程中发生意外错误：{str(e)}'}), 500