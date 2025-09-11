from flask import Blueprint, request, jsonify, json
import os
import subprocess
from utils.openvpn_utils import log_message
from routes.helpers import login_required, json_csrf_protect

disconnect_client_bp = Blueprint('disconnect_client', __name__)

@disconnect_client_bp.route('/disconnect_client', methods=['POST'])
@login_required
@json_csrf_protect
def disconnect_client():
    """禁用客户端，创建标志文件并强制断开连接"""
    try:
        data = json.loads(request.data)
    except (json.JSONDecodeError, KeyError) as e:
        log_message(f"Error parsing JSON from request: {e}")
        return jsonify({'status': 'error', 'message': 'Invalid JSON or missing client_name'}), 400

    client_name = data.get('client_name', '').strip()
    if not client_name:
        return jsonify({'status': 'error', 'message': 'Client name is required'}), 400

    log_message(f"Starting disable process for client: {client_name}")

    disabled_clients_dir = '/etc/openvpn/disabled_clients'
    flag_file = os.path.join(disabled_clients_dir, client_name)

    # 步骤1：创建禁用标志文件
    try:
        # 检查目录是否存在，不存在则创建
        if not os.path.isdir(disabled_clients_dir):
            log_message(f"Attempting to create directory: {disabled_clients_dir}")
            subprocess.run(['sudo', 'mkdir', '-p', disabled_clients_dir], check=True, capture_output=True, text=True)
            log_message("Directory created successfully.")

        log_message(f"Attempting to create flag file: {flag_file}")
        # 使用 'sudo touch' 创建标志文件
        result = subprocess.run(['sudo', 'touch', flag_file], check=True, capture_output=True, text=True)
        log_message(f"Touch command stdout: {result.stdout}")
        log_message(f"Touch command stderr: {result.stderr}")
        log_message(f"Created disabled flag file for client: {client_name}")
    except subprocess.CalledProcessError as e:
        log_message(f"Command failed with return code {e.returncode}: {e.stderr}")
        return jsonify({'status': 'error', 'message': f'创建标志文件失败：{e.stderr}'}), 500
    except Exception as e:
        log_message(f"Unexpected error during file creation: {str(e)}")
        return jsonify({'status': 'error', 'message': f'创建标志文件过程中发生意外错误：{str(e)}'}), 500

    # 步骤2：尝试通过管理接口断开连接 (保留原有逻辑)
    try:
        config_file = '/etc/openvpn/server.conf'
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                for line in f.readlines():
                    if line.strip().startswith('management '):
                        parts = line.strip().split()
                        if len(parts) >= 3:
                            host, port = parts[1], parts[2]
                            if port.isdigit():
                                kill_command = f'(echo "kill {client_name}"; sleep 1) | nc {host} {port}'
                                subprocess.run(['sudo', 'bash', '-c', kill_command], timeout=10)
                                log_message(f"Sent kill command to client {client_name} via management interface.")
                                break
    except Exception as e:
        log_message(f"Warning: Failed to send kill command via management interface: {e}")
        pass

    log_message(f"Successfully disabled client: {client_name}")
    return jsonify({
        'status': 'success',
        'message': f'客户端 {client_name} 已成功禁用。其连接已被终止，将无法重新连接。'
    })