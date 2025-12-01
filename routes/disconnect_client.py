# import os
# import subprocess
# from flask import Blueprint, request, jsonify, json
# import socket
# from utils.openvpn_utils import log_message
# from routes.helpers import login_required

# disconnect_client_bp = Blueprint('disconnect_client', __name__)

# # 使用 socket 连接到 OpenVPN 的管理接口
# def kill_client_via_management(client_name):
#     # 确保这里的 IP 和端口与 server.conf 中的设置一致
#     host = '127.0.0.1'
#     port = 5555
#     try:
#         log_message(f"Attempting to connect to OpenVPN management interface at {host}:{port}")
#         with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
#             s.connect((host, port))
#             # 发送 kill 命令到管理接口
#             s.sendall(f"kill {client_name}\n".encode('utf-8'))
#             log_message(f"Sent 'kill {client_name}' command to management interface.")
#             # 读取并记录管理接口的响应
#             response = s.recv(1024).decode('utf-8')
#             log_message(f"Management interface response: {response}")
#             return True
#     except ConnectionRefusedError:
#         log_message(f"Error: Connection to management interface refused. Is OpenVPN running and configured with management directives?")
#         return False
#     except Exception as e:
#         log_message(f"An unexpected error occurred while communicating with the management interface: {e}")
#         return False

# @disconnect_client_bp.route('/disconnect_client', methods=['POST'])
# @login_required
# def disconnect_client():
#     """Disable a client by creating a flag file and force disconnection"""
#     try:
#         data = json.loads(request.data)
#         client_name = data.get('client_name', '').strip()
#         if not client_name:
#             return jsonify({'status': 'error', 'message': 'Client name is required'}), 400

#         log_message(f"Starting disable process for client: {client_name}")

#         disabled_clients_dir = '/etc/openvpn/disabled_clients'
#         flag_file = os.path.join(disabled_clients_dir, client_name)

#         # 步骤1: 创建禁用标志文件
#         try:
#             # 这里的目录创建逻辑依赖于你的安装脚本，但为了健壮性保留了
#             subprocess.run(['sudo', 'mkdir', '-p', disabled_clients_dir], check=True)
#             log_message(f"Attempting to create flag file: {flag_file}")
#             # 使用 'sudo touch' 创建标志文件
#             subprocess.run(['sudo', 'touch', flag_file], check=True)
#             log_message(f"Successfully created disabled flag file for client: {client_name}")
#         except subprocess.CalledProcessError as e:
#             log_message(f"Command failed with return code {e.returncode}: {e.stderr}")
#             return jsonify({'status': 'error', 'message': f'创建标志文件失败：{e.stderr}'}), 500
#         except Exception as e:
#             log_message(f"Unexpected error during file creation: {str(e)}")
#             return jsonify({'status': 'error', 'message': f'创建标志文件过程中发生意外错误：{str(e)}'}), 500

#         # 步骤2: 立即断开客户端连接
#         if kill_client_via_management(client_name):
#             message = f'客户端 {client_name} 已成功禁用。其连接已被终止，将无法重新连接。'
#         else:
#             message = f'客户端 {client_name} 已禁用，但未能立即终止其连接。'
        
#         log_message(f"Finished disable process for client: {client_name}")
#         return jsonify({
#             'status': 'success',
#             'message': message
#         })

#     except Exception as e:
#         log_message(f"Unexpected error in disconnect_client endpoint: {e}")
#         return jsonify({'status': 'error', 'message': f'禁用过程中发生意外错误：{str(e)}'}), 500