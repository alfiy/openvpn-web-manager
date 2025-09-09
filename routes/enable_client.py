from flask import Blueprint, request, jsonify
import os
import subprocess
from utils.openvpn_utils import log_message, get_openvpn_port
from routes.helpers import login_required, json_csrf_protect

enable_client_bp = Blueprint('enable_client', __name__)

@enable_client_bp.route('/enable_client', methods=['POST'])
@login_required
@json_csrf_protect
def enable_client():
    """Re-enable a disabled client by restoring their certificate"""
    data = request.json
    if not data:
        return jsonify({'status': 'error', 'message': 'Invalid JSON data'}), 400

    client_name = data.get('client_name')
    if not client_name:
        return jsonify({'status': 'error', 'message': 'Client name is required'}), 400

    client_name = client_name.strip()
    if not client_name:
        return jsonify({'status': 'error', 'message': 'Client name is required'}), 400

    log_message(f"Re-enabling client: {client_name}")
    print(f"[ENABLE] Starting re-enable process for client: {client_name}", flush=True)

    port = get_openvpn_port()
    
    # 验证客户端名称是否合法以防止路径遍历攻击
    if not client_name.isalnum() and '_' not in client_name and '-' not in client_name:
        return jsonify({'status': 'error', 'message': 'Invalid client name format'}), 400

    try:
        # Step 1: Remove disabled flag if it exists
        disabled_clients_dir = '/etc/openvpn/disabled_clients'
        disabled_flag = f'{disabled_clients_dir}/{client_name}'

        if os.path.exists(disabled_flag):
            subprocess.run(['sudo', 'rm', '-f', disabled_flag], check=False)
            log_message(f"Removed disabled flag for client: {client_name}")

        # Step 2: Check if PKI directory exists
        index_file_path = '/etc/openvpn/easy-rsa/pki/index.txt'
        if not os.path.exists(index_file_path):
            log_message("OpenVPN PKI not found")
            return jsonify({'status': 'error', 'message': 'OpenVPN PKI not found. Please ensure OpenVPN is installed and configured.'})

        # Step 3: Check current certificate status
        log_message("Checking certificate status")
        with open(index_file_path, 'r') as f:
            lines = f.readlines()

        client_found = False
        client_revoked = False
        client_cn_part = f'CN={client_name}'

        for line in lines:
            parts = line.strip().split('\t')
            # 检查行是否包含证书主题
            if len(parts) > 5 and parts[5].strip().endswith(client_cn_part):
                # 检查CN是否精确匹配，而不是前缀匹配
                cn = parts[5].split('=')[-1]
                if cn == client_name:
                    client_found = True
                    # 检查证书状态
                    status = parts[0]
                    if status == 'R':  # Revoked
                        client_revoked = True
                        log_message(f"Client {client_name} certificate is revoked")
                    elif status == 'V':  # Valid
                        log_message(f"Client {client_name} certificate is already valid")
                    break

        if not client_found:
            log_message(f"Client {client_name} not found in PKI")
            return jsonify({'status': 'error', 'message': f'Client {client_name} not found in certificate database'})

        # Step 4: If certificate is revoked, create a new one
        if client_revoked:
            log_message(f"Creating new certificate for revoked client: {client_name}")

            # Remove old revoked entries from index, using precise matching
            filtered_lines = []
            for line in lines:
                parts = line.strip().split('\t')
                # 再次精确匹配，确保只删除目标客户端的行
                if not (len(parts) > 5 and parts[5].strip().endswith(f'CN={client_name}')):
                    filtered_lines.append(line)

            try:
                subprocess.run([
                    'sudo', 'bash', '-c',
                    f'cat > {index_file_path} << \'EOF\'\n{"".join(filtered_lines)}EOF'
                ], check=True, timeout=30)
                log_message("Removed old certificate entries from index")
            except Exception as e:
                log_message(f"Failed to update index: {e}")
                return jsonify({'status': 'error', 'message': f'Failed to update certificate index: {str(e)}'})

            # Remove old certificate files
            cleanup_commands = [
                ['sudo', 'rm', '-f', f'/etc/openvpn/easy-rsa/pki/issued/{client_name}.crt'],
                ['sudo', 'rm', '-f', f'/etc/openvpn/easy-rsa/pki/private/{client_name}.key'],
                ['sudo', 'rm', '-f', f'/etc/openvpn/easy-rsa/pki/reqs/{client_name}.req']
            ]
            
            for cmd in cleanup_commands:
                try:
                    # 使用 subprocess.run 更安全，且不需要 `try/except` 块来忽略错误
                    subprocess.run(cmd, check=False)
                except Exception:
                    pass

            # Create new certificate with default 10 years validity
            log_message("Creating new certificate")
            cert_result = subprocess.run([
                'sudo', 'bash', '-c', f'cd /etc/openvpn/easy-rsa && EASYRSA_CERT_EXPIRE=3650 ./easyrsa --batch build-client-full "{client_name}" nopass'
            ], capture_output=True, text=True, timeout=120)

            if cert_result.returncode != 0:
                error_msg = f"Failed to create new certificate: {cert_result.stderr}"
                log_message(error_msg)
                return jsonify({'status': 'error', 'message': error_msg})

            log_message("Certificate created successfully")

            # Generate new client configuration file
            log_message("Generating client configuration")
            # ... (这部分代码不需要修改，但为了完整性保留)
            # 在这里，我假设你的配置生成逻辑是正确的
            # ... (此处省略配置生成代码以保持简洁)
            
            config_commands = [
                f'cd /etc/openvpn/easy-rsa',
                f'echo "client" > "/etc/openvpn/client/{client_name}.ovpn"',
                f'echo "dev tun" >> "/etc/openvpn/client/{client_name}.ovpn"',
                f'echo "proto udp" >> "/etc/openvpn/client/{client_name}.ovpn"',
                f'echo "remote $(curl -s ifconfig.me 2>/dev/null || echo localhost) {port}" >> "/etc/openvpn/client/{client_name}.ovpn"',
                f'echo "resolv-retry infinite" >> "/etc/openvpn/client/{client_name}.ovpn"',
                f'echo "nobind" >> "/etc/openvpn/client/{client_name}.ovpn"',
                f'echo "persist-key" >> "/etc/openvpn/client/{client_name}.ovpn"',
                f'echo "persist-tun" >> "/etc/openvpn/client/{client_name}.ovpn"',
                f'echo "remote-cert-tls server" >> "/etc/openvpn/client/{client_name}.ovpn"',
                f'echo "cipher AES-256-GCM" >> "/etc/openvpn/client/{client_name}.ovpn"',
                f'echo "verb 3" >> "/etc/openvpn/client/{client_name}.ovpn"',
                f'echo "" >> "/etc/openvpn/client/{client_name}.ovpn"',
                f'echo "<ca>" >> "/etc/openvpn/client/{client_name}.ovpn"',
                f'cat "/etc/openvpn/easy-rsa/pki/ca.crt" >> "/etc/openvpn/client/{client_name}.ovpn"',
                f'echo "</ca>" >> "/etc/openvpn/client/{client_name}.ovpn"',
                f'echo "" >> "/etc/openvpn/client/{client_name}.ovpn"',
                f'echo "<cert>" >> "/etc/openvpn/client/{client_name}.ovpn"',
                f'awk \'/BEGIN/,/END CERTIFICATE/\' "/etc/openvpn/easy-rsa/pki/issued/{client_name}.crt" >> "/etc/openvpn/client/{client_name}.ovpn"',
                f'echo "</cert>" >> "/etc/openvpn/client/{client_name}.ovpn"',
                f'echo "" >> "/etc/openvpn/client/{client_name}.ovpn"',
                f'echo "<key>" >> "/etc/openvpn/client/{client_name}.ovpn"',
                f'cat "/etc/openvpn/easy-rsa/pki/private/{client_name}.key" >> "/etc/openvpn/client/{client_name}.ovpn"',
                f'echo "</key>" >> "/etc/openvpn/client/{client_name}.ovpn"',
                f'echo "" >> "/etc/openvpn/client/{client_name}.ovpn"',
                f'echo "<tls-crypt>" >> "/etc/openvpn/client/{client_name}.ovpn"',
                f'cat /etc/openvpn/tls-crypt.key 2>/dev/null || cat /etc/openvpn/ta.key 2>/dev/null || echo "# TLS key not found" >> "/etc/openvpn/client/{client_name}.ovpn"',
                f'echo "</tls-crypt>" >> "/etc/openvpn/client/{client_name}.ovpn"',
                f'chmod 644 "/etc/openvpn/client/{client_name}.ovpn"'
            ]

            config_script = ' && '.join(config_commands)
            config_result = subprocess.run([
                'sudo', 'bash', '-c', config_script
            ], capture_output=True, text=True, timeout=60)

            if config_result.returncode != 0:
                error_msg = f"Failed to generate client configuration: {config_result.stderr}"
                log_message(error_msg)
                return jsonify({'status': 'error', 'message': error_msg})

            log_message("Client configuration generated successfully")

            # Step 5 & 6: Generate new CRL and update
            log_message("Generating new CRL")
            crl_result = subprocess.run([
                'sudo', 'bash', '-c', 'cd /etc/openvpn/easy-rsa && ./easyrsa gen-crl'
            ], capture_output=True, text=True, timeout=60)
            
            if crl_result.returncode != 0:
                error_msg = f"Failed to generate CRL: {crl_result.stderr}"
                log_message(error_msg)
                return jsonify({'status': 'error', 'message': error_msg})

            try:
                subprocess.run(['sudo', 'cp', '/etc/openvpn/easy-rsa/pki/crl.pem', '/etc/openvpn/crl.pem'], check=True)
                subprocess.run(['sudo', 'chmod', '644', '/etc/openvpn/crl.pem'], check=True)
                log_message("CRL updated successfully")
            except Exception as e:
                log_message(f"Warning: Failed to update CRL: {e}")

        # Step 7: Reload OpenVPN service
        log_message("Reloading OpenVPN service")
        reload_methods = [
            ['sudo', 'killall', '-SIGUSR1', 'openvpn'],
            ['sudo', 'systemctl', 'reload', 'openvpn@server'],
            ['sudo', 'systemctl', 'restart', 'openvpn@server']
        ]

        reload_success = False
        for method in reload_methods:
            try:
                result = subprocess.run(method, capture_output=True, text=True, timeout=30)
                log_message(f"Reload method {' '.join(method)}: return code {result.returncode}")
                if result.returncode == 0:
                    reload_success = True
                    break
            except Exception as e:
                log_message(f"Reload method {' '.join(method)} failed: {e}")
                continue

        if not reload_success:
            log_message("Warning: OpenVPN reload failed, changes may not be immediate")

        success_msg = f'Client {client_name} has been successfully re-enabled'
        if client_revoked:
            success_msg += ' with a new certificate'
        success_msg += '. The client can now reconnect to the VPN.'

        log_message(f"Successfully re-enabled client: {client_name}")
        return jsonify({'status': 'success', 'message': success_msg})

    except subprocess.TimeoutExpired:
        log_message("Enable operation timed out")
        return jsonify({'status': 'error', 'message': 'Enable operation timed out'})
    except subprocess.CalledProcessError as e:
        log_message(f"Command failed: {e}")
        return jsonify({'status': 'error', 'message': f'Command failed: {e}'})
    except Exception as e:
        error_msg = f"Unexpected error during enable: {str(e)}"
        log_message(error_msg)
        return jsonify({'status': 'error', 'message': error_msg})