from flask import Blueprint, request, jsonify
import subprocess

uninstall_bp = Blueprint('uninstall', __name__)

@uninstall_bp.route('/uninstall', methods=['POST'])
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
            # Remove client config files from /tmp
            ['sudo', 'find', '/tmp/', '-maxdepth', '1', '-name', '*.ovpn', '-delete'],
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
