from flask import Blueprint, request, jsonify
import os
import subprocess
from utils.openvpn_utils import log_message
# 导入CSRF验证所需模块
from flask_wtf.csrf import validate_csrf
from functools import wraps

# JSON请求CSRF验证装饰器
def json_csrf_protect(f):
    """专门用于JSON格式POST请求的CSRF验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 获取请求头中的CSRF令牌
        csrf_token = request.headers.get('X-CSRFToken')
        
        # 检查令牌是否存在
        if not csrf_token:
            return jsonify({'status': 'error', 'message': '缺少CSRF令牌'}), 403
        
        # 验证令牌有效性
        try:
            validate_csrf(csrf_token)
        except Exception:
            return jsonify({'status': 'error', 'message': 'CSRF令牌验证失败，请刷新页面重试'}), 403
            
        return f(*args, **kwargs)
    return decorated_function

disconnect_client_bp = Blueprint('disconnect_client', __name__)

@disconnect_client_bp.route('/disconnect_client', methods=['POST'])
@json_csrf_protect
def disconnect_client():
    """Forcefully disconnect a client and prevent auto-reconnection"""
    client_name = request.form.get('client_name')
    if not client_name:
        return jsonify({'status': 'error', 'message': 'Client name is required'})

    client_name = client_name.strip()
    if not client_name:
        return jsonify({'status': 'error', 'message': 'Client name is required'})

    log_message(f"Starting permanent disconnect process for client: {client_name}")
    #print(f"[DISCONNECT] Starting permanent disconnect process for client: {client_name}", flush=True)

    try:
        # Step 1: Check if client exists in PKI
        if not os.path.exists('/etc/openvpn/easy-rsa/pki/index.txt'):
            log_message("PKI index.txt not found")
            return jsonify({'status': 'error', 'message': 'OpenVPN PKI not found'})

        # Check if client exists
        with open('/etc/openvpn/easy-rsa/pki/index.txt', 'r') as f:
            content = f.read()
            if f'CN={client_name}/' not in content and f'CN={client_name}' not in content:
                log_message(f"Client {client_name} not found in PKI")
                return jsonify({'status': 'error', 'message': f'Client {client_name} not found in certificate database'})

        # Step 2: Mark client as disabled by creating a disabled flag file
        disabled_clients_dir = '/etc/openvpn/disabled_clients'
        subprocess.run(['sudo', 'mkdir', '-p', disabled_clients_dir], check=False)
        subprocess.run(['sudo', 'touch', f'{disabled_clients_dir}/{client_name}'], check=True)
        log_message(f"Created disabled flag for client: {client_name}")

        # Step 3: Temporarily revoke certificate to force immediate disconnection
        log_message(f"Temporarily revoking certificate for immediate disconnect")
        revoke_result = subprocess.run([
            'sudo', 'bash', '-c', f'cd /etc/openvpn/easy-rsa && ./easyrsa --batch revoke "{client_name}"'
        ], capture_output=True, text=True, timeout=60)

        if revoke_result.returncode != 0 and 'already revoked' not in revoke_result.stderr:
            log_message(f"Failed to revoke certificate: {revoke_result.stderr}")
            return jsonify({
                'status': 'error',
                'message': f'Failed to revoke certificate: {revoke_result.stderr}'
            })

        # Step 4: Generate new CRL to apply revocation immediately
        log_message("Generating new CRL")
        crl_result = subprocess.run([
            'sudo', 'bash', '-c', 'cd /etc/openvpn/easy-rsa && ./easyrsa gen-crl'
        ], capture_output=True, text=True, timeout=60)

        if crl_result.returncode != 0:
            log_message(f"Failed to generate CRL: {crl_result.stderr}")
            return jsonify({
                'status': 'error',
                'message': f'Failed to generate CRL: {crl_result.stderr}'
            })

        # Step 5: Update CRL in OpenVPN directory
        subprocess.run(['sudo', 'rm', '-f', '/etc/openvpn/crl.pem'], check=False)
        subprocess.run(['sudo', 'cp', '/etc/openvpn/easy-rsa/pki/crl.pem', '/etc/openvpn/crl.pem'], check=True)
        subprocess.run(['sudo', 'chmod', '644', '/etc/openvpn/crl.pem'], check=True)

        # Step 6: Try management interface disconnect as well
        disconnect_via_management = False
        config_files = ['/etc/openvpn/server.conf', '/etc/openvpn/server/server.conf']

        for config_file in config_files:
            if os.path.exists(config_file):
                try:
                    with open(config_file, 'r') as f:
                        content = f.read()
                        for line in content.split('\n'):
                            if line.strip().startswith('management '):
                                parts = line.strip().split()
                                if len(parts) >= 3:
                                    if ':' in parts[2]:  # TCP socket
                                        host, port = parts[2].split(':')
                                        command = f'(echo "kill {client_name}"; sleep 1) | nc {host} {port}'
                                        log_message(f"Executing management command: {command}")
                                        kill_result = subprocess.run([
                                            'sudo', 'bash', '-c', command
                                        ], capture_output=True, text=True, timeout=10)

                                        if kill_result.returncode == 0:
                                            disconnect_via_management = True
                                            log_message("Successfully sent kill command via management interface")
                                    break
                except Exception as e:
                    log_message(f"Error accessing management interface: {e}")
                break

        # Step 7: Reload OpenVPN to apply CRL changes
        log_message("Reloading OpenVPN service to apply certificate revocation")
        reload_methods = [
            ['sudo', 'killall', '-SIGUSR1', 'openvpn'],
            ['sudo', 'systemctl', 'reload', 'openvpn@server']
        ]

        reload_success = False
        for method in reload_methods:
            try:
                result = subprocess.run(method, capture_output=True, text=True, timeout=30)
                log_message(f"Reload method {' '.join(method)}: {result.returncode}")
                if result.returncode == 0:
                    reload_success = True
                    break
            except Exception as e:
                log_message(f"Reload method error: {e}")

        if not reload_success:
            return jsonify({
                'status': 'warning',
                'message': f'Client {client_name} certificate revoked but OpenVPN reload failed. Client will be disconnected on next server restart.'
            })

        # Step 8: Clean up client files to prevent any reconnection
        cleanup_commands = [
            ['sudo', 'rm', '-f', f'/etc/openvpn/client/{client_name}.ovpn'],
            ['sudo', 'sed', '-i', f'/^{client_name},/d', '/etc/openvpn/ipp.txt'],
            ['sudo', 'rm', '-f', f'/etc/openvpn/ccd/{client_name}']
        ]

        for cmd in cleanup_commands:
            try:
                subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
            except Exception:
                pass

        log_message(f"Successfully disconnected and disabled client: {client_name}")
        return jsonify({
            'status': 'success',
            'message': f'Client {client_name} has been permanently disconnected and disabled. Client certificate has been revoked and cannot reconnect until manually re-enabled.'
        })

    except subprocess.TimeoutExpired:
        log_message("Disconnect operation timed out")
        return jsonify({'status': 'error', 'message': 'Disconnect operation timed out'})
    except subprocess.CalledProcessError as e:
        log_message(f"Command failed: {e}")
        return jsonify({'status': 'error', 'message': f'Command failed: {e}'})
    except Exception as e:
        log_message(f"Unexpected error: {e}")
        return jsonify({'status': 'error', 'message': f'Disconnect error: {str(e)}'})
