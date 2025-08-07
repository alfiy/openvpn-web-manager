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
    client_number = request.form.get('client_number')
    if not client_number:
        return jsonify({'status': 'error', 'message': 'Client number is required'})
    
    try:
        # Execute the script with the appropriate options to revoke a client
        process = subprocess.Popen(['sudo', 'bash', SCRIPT_PATH], 
                                  stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
        
        # Select option 2 (Revoke existing user)
        process.stdin.write(b'2\n')
        process.stdin.flush()
        time.sleep(0.5)
        
        # Enter client number
        process.stdin.write(f"{client_number}\n".encode())
        process.stdin.flush()
        
        process.communicate()
        
        return jsonify({'status': 'success', 'message': 'Client revoked successfully'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error: {str(e)}'})

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
