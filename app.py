#!/usr/bin/env python3
import os
import subprocess
import time
import re
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file

app = Flask(__name__)
# Update script path to same directory as app.py
SCRIPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ubuntu-openvpn-install.sh')

def check_openvpn_status():
    """Check if OpenVPN is installed and running"""
    try:
        result = subprocess.run(['systemctl', 'is-active', 'openvpn@server'], 
                              capture_output=True, text=True)
        if result.stdout.strip() == 'active':
            return 'running'
        
        # Check if OpenVPN is installed but not running
        result = subprocess.run(['test', '-e', '/etc/openvpn/server.conf'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            return 'installed'
            
        return 'not_installed'
    except Exception as e:
        return f'error: {str(e)}'

def get_openvpn_clients():
    """Get list of OpenVPN clients"""
    clients = []
    try:
        if os.path.exists('/etc/openvpn/easy-rsa/pki/index.txt'):
            with open('/etc/openvpn/easy-rsa/pki/index.txt', 'r') as f:
                for line in f:
                    if line.startswith('V'):
                        # Extract client name from the CN field
                        match = re.search(r'CN=([^/]+)', line)
                        if match:
                            clients.append(match.group(1))
    except Exception as e:
        print(f"Error getting clients: {e}")
    return clients

@app.route('/')
def index():
    status = check_openvpn_status()
    clients = []
    if status in ['running', 'installed']:
        clients = get_openvpn_clients()
    
    return render_template('index.html', 
                          status=status, 
                          clients=clients)

@app.route('/install', methods=['POST'])
def install():
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

@app.route('/add_client', methods=['POST'])
def add_client():
    client_name = request.form.get('client_name')
    if not client_name:
        return jsonify({'status': 'error', 'message': 'Client name is required'})
    
    # Strip whitespace and newline characters
    client_name = client_name.strip()
    if not client_name:
        return jsonify({'status': 'error', 'message': 'Client name is required'})
    
    try:
        # Execute the script with the appropriate options to add a new client
        # In production, you would set up a proper way to communicate with the script
        process = subprocess.Popen(['sudo', 'bash', SCRIPT_PATH], 
                                  stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
        
        # Select option 1 (Add a new user)
        process.stdin.write(b'1\n')
        process.stdin.flush()
        time.sleep(0.5)
        
        # Enter client name
        process.stdin.write(f"{client_name}\n".encode())
        process.stdin.flush()
        time.sleep(0.5)
        
        # Select option 1 (passwordless client)
        process.stdin.write(b'1\n')
        process.stdin.flush()
        
        process.communicate()
        
        return jsonify({'status': 'success', 'message': f'Client {client_name} added successfully'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error: {str(e)}'})

@app.route('/revoke_client', methods=['POST'])
def revoke_client():
    client_name = request.form.get('client_name')
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
            # Remove client configuration file
            ['sudo', 'rm', '-f', f'/root/{client_name}.ovpn'],
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

@app.route('/uninstall', methods=['POST'])
def uninstall():
    try:
        # Direct uninstall commands without interactive script
        commands = [
            # Stop OpenVPN service
            ['sudo', 'systemctl', 'stop', 'openvpn@server'],
            ['sudo', 'systemctl', 'disable', 'openvpn@server'],
            
            # Stop and disable iptables service
            ['sudo', 'systemctl', 'stop', 'iptables-openvpn'],
            ['sudo', 'systemctl', 'disable', 'iptables-openvpn'],
            
            # Remove systemd service file
            ['sudo', 'rm', '-f', '/etc/systemd/system/iptables-openvpn.service'],
            
            # Reload systemd
            ['sudo', 'systemctl', 'daemon-reload'],
            
            # Remove iptables scripts
            ['sudo', 'rm', '-f', '/etc/iptables/add-openvpn-rules.sh'],
            ['sudo', 'rm', '-f', '/etc/iptables/rm-openvpn-rules.sh'],
            
            # Remove OpenVPN package
            ['sudo', 'apt-get', 'remove', '--purge', '-y', 'openvpn'],
            
            # Clean up configuration files
            ['sudo', 'rm', '-rf', '/etc/openvpn'],
            ['sudo', 'rm', '-f', '/etc/sysctl.d/99-openvpn.conf'],
            ['sudo', 'rm', '-rf', '/var/log/openvpn'],
            
            # Remove client config files from root
            ['sudo', 'find', '/root/', '-maxdepth', '1', '-name', '*.ovpn', '-delete'],
            
            # Restore IP forwarding
            ['sudo', 'sysctl', '-w', 'net.ipv4.ip_forward=0'],
        ]
        
        failed_commands = []
        for cmd in commands:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode != 0 and 'systemctl' not in cmd[0]:  # systemctl commands may fail if service doesn't exist
                    failed_commands.append(f"{' '.join(cmd)}: {result.stderr}")
            except subprocess.TimeoutExpired:
                failed_commands.append(f"{' '.join(cmd)}: Command timed out")
            except Exception as cmd_error:
                failed_commands.append(f"{' '.join(cmd)}: {str(cmd_error)}")
        
        if failed_commands:
            return jsonify({'status': 'warning', 'message': f'OpenVPN partially uninstalled. Some commands failed: {"; ".join(failed_commands)}'})
        else:
            return jsonify({'status': 'success', 'message': 'OpenVPN completely uninstalled successfully'})
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Uninstall error: {str(e)}'})

@app.route('/download_client/<client_name>', methods=['GET'])
def download_client(client_name):
    # Path to the client config file
    client_path = f"/root/{client_name}.ovpn"
    
    if os.path.exists(client_path):
        return send_file(client_path, as_attachment=True)
    else:
        return jsonify({'status': 'error', 'message': 'Client configuration file not found'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
