from flask import Blueprint, request, jsonify
import os
import subprocess
import time

install_bp = Blueprint('install', __name__)

SCRIPT_PATH = './ubuntu-openvpn-install.sh'

@install_bp.route('/install', methods=['POST'])
def install():
    # Check if the OpenVPN script exists
    if not os.path.exists(SCRIPT_PATH):
        return jsonify({
            'status': 'error',
            'message': f'OpenVPN安装脚本不存在: {SCRIPT_PATH}。请确保ubuntu-openvpn-install.sh文件存在于工作目录中。'
        })

    # Check if sudo is available
    try:
        subprocess.run(['which', 'sudo'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return jsonify({
            'status': 'error',
            'message': 'sudo命令不可用。OpenVPN安装需要管理员权限。请确保在支持sudo的环境中运行此应用程序。'
        })

    try:
        # Get internal IP address for NAT environment
        def get_internal_ip():
            try:
                # Get the internal IP address
                result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
                if result.returncode == 0:
                    # Get the first IP address (usually the main interface)
                    internal_ip = result.stdout.strip().split()[0]
                    return internal_ip
                else:
                    # Fallback method using ip command
                    result = subprocess.run(['ip', 'route', 'get', '8.8.8.8'], capture_output=True, text=True)
                    if result.returncode == 0:
                        lines = result.stdout.strip().split('\n')
                        for line in lines:
                            if 'src' in line:
                                return line.split('src')[1].strip().split()[0]
                return '10.0.0.1'  # Default fallback
            except:
                return '10.0.0.1'  # Default fallback

        internal_ip = get_internal_ip()

        # Execute the installation script with NAT configuration
        process = subprocess.Popen(['sudo', 'bash', SCRIPT_PATH],
                                  stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  text=True)

        # Send responses to the interactive script
        inputs = [
            internal_ip + '\n',  # Use internal IP instead of external IP
            '1194\n',           # Default OpenVPN port
            '1\n',              # UDP protocol
            '1\n',              # DNS resolver (default)
            '\n',               # Default client name
            '1\n'               # Passwordless client
        ]

        # Send all inputs to the script
        for input_data in inputs:
            process.stdin.write(input_data)
            process.stdin.flush()
            time.sleep(0.5)

        # Wait for the process to complete (with timeout)
        try:
            stdout, stderr = process.communicate(timeout=300)  # 5 minutes timeout

            if process.returncode == 0:
                return jsonify({
                    'status': 'success',
                    'message': f'OpenVPN installed successfully with internal IP: {internal_ip}'
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': f'Installation failed: {stderr}'
                })

        except subprocess.TimeoutExpired:
            process.kill()
            return jsonify({
                'status': 'timeout',
                'message': 'Installation timed out after 5 minutes'
            })

    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Installation error: {str(e)}'})
