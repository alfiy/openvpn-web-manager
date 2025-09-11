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
    """Disable a client by creating a flag file and force disconnection"""
    try:
        # 尝试手动解析JSON
        data = json.loads(request.data)
    except (json.JSONDecodeError, KeyError) as e:
        log_message(f"Error parsing JSON from request: {e}")
        return jsonify({'status': 'error', 'message': 'Invalid JSON or missing client_name'}), 400

    client_name = data.get('client_name', '').strip()
    if not client_name:
        return jsonify({'status': 'error', 'message': 'Client name is required'}), 400

    log_message(f"Starting disable process for client: {client_name}")

    try:
        # Step 1: Create a disabled flag file
        disabled_clients_dir = '/etc/openvpn/disabled_clients'
        subprocess.run(['sudo', 'mkdir', '-p', disabled_clients_dir], check=True)
        
        flag_file = os.path.join(disabled_clients_dir, client_name)
        subprocess.run(['sudo', 'touch', flag_file], check=True)
        log_message(f"Created disabled flag file for client: {client_name}")

        # Step 2: Try to disconnect via management interface
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

    except subprocess.CalledProcessError as e:
        log_message(f"Command failed during disconnect process: {e}")
        return jsonify({'status': 'error', 'message': f'命令执行失败：{str(e)}'}), 500
    except Exception as e:
        log_message(f"Unexpected error during disconnect: {e}")
        return jsonify({'status': 'error', 'message': f'禁用过程中发生意外错误：{str(e)}'}), 500