from flask import Blueprint, request, jsonify
import os
import subprocess

add_client_bp = Blueprint('add_client', __name__)

SCRIPT_PATH = './ubuntu-openvpn-install.sh'



@add_client_bp.route('/add_client', methods=['POST'])
def add_client():
    # Check if the OpenVPN script exists
    if not os.path.exists(SCRIPT_PATH):
        return jsonify({
            'status': 'error', 
            'message': f'OpenVPN安装脚本不存在: {SCRIPT_PATH}。请确保ubuntu-openvpn-install.sh文件存在于工作目录中。'
        })
    
    client_name = request.form.get('client_name')
    if not client_name:
        return jsonify({'status': 'error', 'message': 'Client name is required'})
    
    # Strip whitespace and newline characters
    client_name = client_name.strip()
    if not client_name:
        return jsonify({'status': 'error', 'message': 'Client name is required'})
    
    # Get expiration days from form (default to 3650 days if not provided)
    expiry_days = request.form.get('expiry_days', '3650')
    try:
        expiry_days = int(expiry_days)
        if expiry_days <= 0:
            expiry_days = 3650
    except:
        expiry_days = 3650
    
    try:
        # Use a more direct approach to add the client
        # Create the client certificate directly using easy-rsa commands
        commands = [
            # Change to easy-rsa directory and create client certificate with custom expiration
            ['sudo', 'bash', '-c', f'cd /etc/openvpn/easy-rsa && EASYRSA_CERT_EXPIRE={expiry_days} ./easyrsa --batch build-client-full "{client_name}" nopass'],
            # Generate client configuration file - save only in /tmp
            ['sudo', 'bash', '-c', f'''
            cd /etc/openvpn/easy-rsa
            
            # Create base client configuration in /tmp
            cp /etc/openvpn/client-template.txt "/tmp/{client_name}.ovpn" 2>/dev/null || echo "client
dev tun
proto udp
remote $(curl -s ifconfig.me || echo localhost) 1194
resolv-retry infinite
nobind
persist-key
persist-tun
remote-cert-tls server
cipher AES-256-GCM
verb 3" > "/tmp/{client_name}.ovpn"
            
            # Append certificates and keys to the configuration file
            {{
                echo ""
                echo "<ca>"
                cat "/etc/openvpn/easy-rsa/pki/ca.crt"
                echo "</ca>"
                echo ""
                echo "<cert>"
                awk '/BEGIN/,/END CERTIFICATE/' "/etc/openvpn/easy-rsa/pki/issued/{client_name}.crt"
                echo "</cert>"
                echo ""
                echo "<key>"
                cat "/etc/openvpn/easy-rsa/pki/private/{client_name}.key"
                echo "</key>"
                echo ""
                echo "<tls-crypt>"
                cat /etc/openvpn/tls-crypt.key 2>/dev/null || cat /etc/openvpn/ta.key 2>/dev/null || echo "# TLS key not found"
                echo "</tls-crypt>"
            }} >> "/tmp/{client_name}.ovpn"
            
            # Set proper permissions for the config file
            chmod 644 "/tmp/{client_name}.ovpn"
            
            echo "Client configuration saved to /tmp/{client_name}.ovpn"
            ''']
        ]
        
        for cmd in commands:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if result.returncode != 0:
                    return jsonify({
                        'status': 'error', 
                        'message': f'Failed to execute command: {result.stderr}'
                    })
            except subprocess.TimeoutExpired:
                return jsonify({
                    'status': 'error', 
                    'message': f'Command timed out while adding client {client_name}'
                })
        
        # Calculate expiry date for display
        from datetime import datetime, timedelta
        expiry_date = datetime.now() + timedelta(days=expiry_days)
        expiry_date_str = expiry_date.strftime('%Y-%m-%d')
        
        return jsonify({'status': 'success', 'message': f'Client {client_name} added successfully with {expiry_days} days validity (expires: {expiry_date_str})'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error: {str(e)}'})

