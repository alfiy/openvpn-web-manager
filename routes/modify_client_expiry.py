from flask import Blueprint, request, jsonify
import os
import subprocess

modify_client_expiry_bp = Blueprint('modify_client_expiry',__name__)

@modify_client_expiry_bp.route('/modify_client_expiry', methods=['POST'])
def modify_client_expiry():
    #alert("The function is under development.")
    """Modify client certificate expiration date by revoke + reissue"""
    client_name = request.form.get('client_name')
    expiry_days = request.form.get('expiry_days')

    if not client_name or not expiry_days:
        return jsonify({'status': 'error', 'message': 'Client name and expiry days are required'})

    client_name = client_name.strip()
    if not client_name:
        return jsonify({'status': 'error', 'message': 'Client name is required'})

    try:
        expiry_days = int(expiry_days)
        if expiry_days <= 0:
            return jsonify({'status': 'error', 'message': 'Expiry days must be positive'})
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid expiry days format'})

    easy_rsa_dir = "/etc/openvpn/easy-rsa"

    try:
        # Step 1: Revoke old certificate
        revoke_cmd = [
            'sudo', 'bash', '-c',
            f'cd {easy_rsa_dir} && echo "yes" | ./easyrsa revoke "{client_name}"'
        ]
        result = subprocess.run(revoke_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return jsonify({'status': 'error', 'message': f'Failed to revoke old cert: {result.stderr or result.stdout}'})

        # Step 2: Update CRL
        subprocess.run([
            'sudo', 'bash', '-c',
            f'cd {easy_rsa_dir} && ./easyrsa gen-crl && cp pki/crl.pem /etc/openvpn/'
        ], capture_output=True, text=True)

        # Step 3: Reissue new certificate with updated expiry
        build_cmd = [
            'sudo', 'bash', '-c',
            f'cd {easy_rsa_dir} && EASYRSA_CERT_EXPIRE={expiry_days} ./easyrsa --batch build-client-full "{client_name}" nopass'
        ]
        result = subprocess.run(build_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return jsonify({'status': 'error', 'message': f'Failed to reissue cert: {result.stderr or result.stdout}'})

        # Step 4: Regenerate client configuration file
        config_cmd = [
            'sudo', 'bash', '-c', f'''
            cd {easy_rsa_dir}
            cat > "/etc/openvpn/client/{client_name}.ovpn" << EOL
client
dev tun
proto udp
remote $(curl -s ifconfig.me || echo localhost) 1194
resolv-retry infinite
nobind
persist-key
persist-tun
remote-cert-tls server
cipher AES-256-GCM
verb 3
<ca>
EOL
            cat pki/ca.crt >> "/tmp/{client_name}.ovpn"
            echo "</ca>" >> "/tmp/{client_name}.ovpn"
            echo "<cert>" >> "/tmp/{client_name}.ovpn"
            awk '/BEGIN/,/END CERTIFICATE/' pki/issued/{client_name}.crt >> "/tmp/{client_name}.ovpn"
            echo "</cert>" >> "/tmp/{client_name}.ovpn"
            echo "<key>" >> "/tmp/{client_name}.ovpn"
            cat pki/private/{client_name}.key >> "/tmp/{client_name}.ovpn"
            echo "</key>" >> "/tmp/{client_name}.ovpn"
            echo "<tls-crypt>" >> "/tmp/{client_name}.ovpn"
            cat /etc/openvpn/tls-crypt.key >> "/tmp/{client_name}.ovpn"
            echo "</tls-crypt>" >> "/tmp/{client_name}.ovpn"
            chmod 644 "/tmp/{client_name}.ovpn"
            '''
        ]
        result = subprocess.run(config_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return jsonify({'status': 'error', 'message': f'Failed to generate client config: {result.stderr or result.stdout}'})

        # Step 5: Restart OpenVPN to reload CRL
        subprocess.run([
            'sudo', 'systemctl', 'reload', 'openvpn@server'
        ], capture_output=True, text=True)

        # Calculate new expiry date
        from datetime import datetime, timedelta
        new_expiry_date = datetime.now() + timedelta(days=expiry_days)
        expiry_date_str = new_expiry_date.strftime('%Y-%m-%d')

        return jsonify({
            'status': 'success',
            'message': f'Client {client_name} expiry modified successfully to {expiry_days} days (expires: {expiry_date_str}). Old cert revoked, new cert issued.'
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to modify client expiry: {str(e)}'})
