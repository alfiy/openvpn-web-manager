from flask import Blueprint, request, jsonify
import os
import subprocess
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

revoke_client_bp = Blueprint('revoke_client', __name__)

@revoke_client_bp.route('/revoke_client', methods=['POST'])
@json_csrf_protect
def revoke_client():
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': '请求数据格式错误'}), 400
    
    client_name = data.get('client_name')
    if not client_name:
        return jsonify({'status': 'error', 'message': 'Client name is required'})

    # Strip whitespace and newline characters
    client_name = client_name.strip()
    if not client_name:
        return jsonify({'status': 'error', 'message': 'Client name is required'})

    try:
        # Step 1: Check if client exists in the index
        if not os.path.exists('/etc/openvpn/easy-rsa/pki/index.txt'):
            return jsonify({'status': 'error', 'message': 'OpenVPN PKI not found'})

        # Check if client exists
        with open('/etc/openvpn/easy-rsa/pki/index.txt', 'r') as f:
            content = f.read()
            if f'CN={client_name}/' not in content and f'CN={client_name}' not in content:
                return jsonify({'status': 'error', 'message': f'Client {client_name} not found in certificate database'})

        # Step 2: Revoke the certificate
        revoke_result = subprocess.run([
            'sudo', 'bash', '-c', f'cd /etc/openvpn/easy-rsa && ./easyrsa --batch revoke "{client_name}"'
        ], capture_output=True, text=True, timeout=60)

        if revoke_result.returncode != 0 and 'already revoked' not in revoke_result.stderr:
            return jsonify({
                'status': 'error',
                'message': f'Failed to revoke certificate: {revoke_result.stderr}'
            })

        # Step 3: Generate new CRL
        crl_result = subprocess.run([
            'sudo', 'bash', '-c', 'cd /etc/openvpn/easy-rsa && ./easyrsa gen-crl'
        ], capture_output=True, text=True, timeout=60)

        if crl_result.returncode != 0:
            return jsonify({
                'status': 'error',
                'message': f'Failed to generate CRL: {crl_result.stderr}'
            })

        # Step 4: Update CRL in OpenVPN directory
        subprocess.run(['sudo', 'rm', '-f', '/etc/openvpn/crl.pem'], check=False)
        subprocess.run(['sudo', 'cp', '/etc/openvpn/easy-rsa/pki/crl.pem', '/etc/openvpn/crl.pem'], check=True)
        subprocess.run(['sudo', 'chmod', '644', '/etc/openvpn/crl.pem'], check=True)

        # Step 5: Clean up all client files
        cleanup_commands = [
            # Remove client configuration file from /etc/openvpn/client
            ['sudo', 'rm', '-f', f'/etc/openvpn/client/{client_name}.ovpn'],
            # Remove from IP persistence file
            ['sudo', 'sed', '-i', f'/^{client_name},/d', '/etc/openvpn/ipp.txt'],
            # Remove client-specific configuration
            ['sudo', 'rm', '-f', f'/etc/openvpn/ccd/{client_name}'],
            # Remove certificate files (optional cleanup)
            ['sudo', 'rm', '-f', f'/etc/openvpn/easy-rsa/pki/issued/{client_name}.crt'],
            ['sudo', 'rm', '-f', f'/etc/openvpn/easy-rsa/pki/private/{client_name}.key'],
            ['sudo', 'rm', '-f', f'/etc/openvpn/easy-rsa/pki/reqs/{client_name}.req']
        ]

        for cmd in cleanup_commands:
            try:
                subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
            except Exception:
                pass  # Ignore cleanup errors

        # Step 6: Clean up index.txt - remove revoked client entries
        try:
            if os.path.exists('/etc/openvpn/easy-rsa/pki/index.txt'):
                # Read the current index.txt
                with open('/etc/openvpn/easy-rsa/pki/index.txt', 'r') as f:
                    lines = f.readlines()

                # Filter out lines containing the revoked client
                filtered_lines = []
                for line in lines:
                    if f'CN={client_name}/' not in line and f'CN={client_name}' not in line:
                        filtered_lines.append(line)

                # Write back the filtered content
                subprocess.run([
                    'sudo', 'bash', '-c',
                    f'cat > /etc/openvpn/easy-rsa/pki/index.txt << \'EOF\'\n{"".join(filtered_lines)}EOF'
                ], check=True, timeout=30)

        except Exception as cleanup_error:
            # Continue even if index cleanup fails
            pass

        # Step 7: Reload OpenVPN using signal (no service interruption)
        reload_result = subprocess.run([
            'sudo', 'killall', '-SIGUSR1', 'openvpn'
        ], capture_output=True, text=True, timeout=30)

        if reload_result.returncode != 0:
            # If killall fails, try alternative method using systemctl reload
            reload_result = subprocess.run([
                'sudo', 'systemctl', 'reload', 'openvpn@server'
            ], capture_output=True, text=True, timeout=30)

            if reload_result.returncode != 0:
                return jsonify({
                    'status': 'warning',
                    'message': f'Client {client_name} revoked but CRL reload failed. Changes will take effect on next client reconnection: {reload_result.stderr}'
                })

        return jsonify({
            'status': 'success',
            'message': f'Client {client_name} successfully revoked and CRL reloaded without disconnecting active users'
        })

    except subprocess.TimeoutExpired:
        return jsonify({'status': 'error', 'message': 'Revocation operation timed out'})
    except subprocess.CalledProcessError as e:
        return jsonify({'status': 'error', 'message': f'Command failed: {e}'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Revocation error: {str(e)}'})
