import os
import subprocess
import re
import sys

def log_message(message):
    print(f"[SERVER] {message}", flush=True)
    sys.stdout.flush()


def check_openvpn_status():
    """
    返回 running / installed / not_installed
    普通用户也能正常工作
    """
    try:
        # --- 1. 运行状态：用 systemctl ---
        # 加 sudo 让普通用户也能正常 query systemd
        result = subprocess.run(
            ['sudo', 'systemctl', 'is-active', 'openvpn@server'],
            capture_output=True,
            text=True
        )
        if result.stdout.strip() == 'active':
            return 'running'

        # --- 2. 安装状态：检查 server.conf ---
        # 同样用 sudo 避免权限问题
        result = subprocess.run(
            ['sudo', 'test', '-e', '/etc/openvpn/server.conf'],
            capture_output=True
        )
        if result.returncode == 0:
            return 'installed'

        return 'not_installed'
    except Exception as e:
        return f'error: {str(e)}'

def get_online_clients():
    online_clients = {}
    status_file = "/var/log/openvpn/status.log"
    if not os.path.exists(status_file):
        status_file = "/var/log/openvpn/openvpn-status.log"
        if not os.path.exists(status_file):
            status_file = "/etc/openvpn/server/openvpn-status.log"
    if not os.path.exists(status_file):
        return online_clients
    try:
        with open(status_file, 'r') as f:
            lines = f.readlines()
        in_client_list = False
        routing_table_section = False
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('OpenVPN CLIENT LIST'):
                in_client_list = True
                continue
            elif line.startswith('ROUTING TABLE'):
                in_client_list = False
                routing_table_section = True
                continue
            elif line.startswith('GLOBAL STATS'):
                routing_table_section = False
                continue
            if in_client_list and ',' in line and not line.startswith('Common Name'):
                parts = line.split(',')
                if len(parts) >= 5:
                    client_name = parts[0].strip()
                    real_address = parts[1].strip()
                    connected_since = parts[4].strip()
                    if client_name and client_name != 'UNDEF':
                        try:
                            from datetime import datetime
                            connect_time = None
                            try:
                                connect_time = datetime.strptime(connected_since, '%a %b %d %H:%M:%S %Y')
                            except ValueError:
                                pass
                            if not connect_time:
                                try:
                                    connect_time = datetime.strptime(connected_since, '%Y-%m-%d %H:%M:%S')
                                except ValueError:
                                    pass
                            if not connect_time:
                                try:
                                    connect_time = datetime.strptime(connected_since, '%b %d %H:%M:%S %Y')
                                except ValueError:
                                    pass
                            if not connect_time:
                                try:
                                    timestamp = float(connected_since)
                                    connect_time = datetime.fromtimestamp(timestamp)
                                except (ValueError, OSError):
                                    pass
                            if connect_time:
                                current_time = datetime.now()
                                duration = current_time - connect_time
                                if duration.total_seconds() < 0:
                                    duration_str = "00:00"
                                else:
                                    total_seconds = int(duration.total_seconds())
                                    hours = total_seconds // 3600
                                    minutes = (total_seconds % 3600) // 60
                                    seconds = total_seconds % 60
                                    if hours > 0:
                                        duration_str = f"{hours}h{minutes:02d}m"
                                    elif minutes > 0:
                                        duration_str = f"{minutes}m{seconds:02d}s"
                                    else:
                                        duration_str = f"{seconds}s"
                            else:
                                duration_str = "解析失败"
                        except Exception:
                            duration_str = "计算错误"
                        real_ip = real_address.split(':')[0] if ':' in real_address else real_address
                        online_clients[client_name] = {
                            'vpn_ip': '',
                            'real_ip': real_ip,
                            'duration': duration_str,
                            'connected_since': connected_since
                        }
                        continue
            if routing_table_section and ',' in line and not line.startswith('Virtual Address'):
                parts = line.split(',')
                if len(parts) >= 2:
                    vpn_ip = parts[0].strip()
                    client_name = parts[1].strip()
                    if client_name and client_name in online_clients and vpn_ip:
                        online_clients[client_name]['vpn_ip'] = vpn_ip
                        continue
            if not in_client_list and not routing_table_section and ',' in line:
                parts = line.split(',')
                if len(parts) >= 4:
                    vpn_ip = parts[0].strip()
                    client_name = parts[1].strip()
                    real_address = parts[2].strip()
                    connected_since = parts[3].strip()
                    if client_name and client_name != 'UNDEF' and vpn_ip:
                        try:
                            from datetime import datetime
                            connect_time = None
                            try:
                                connect_time = datetime.strptime(connected_since, '%Y-%m-%d %H:%M:%S')
                            except ValueError:
                                pass
                            if not connect_time:
                                try:
                                    connect_time = datetime.strptime(connected_since, '%a %b %d %H:%M:%S %Y')
                                except ValueError:
                                    pass
                            if not connect_time:
                                try:
                                    connect_time = datetime.strptime(connected_since, '%b %d %H:%M:%S %Y')
                                except ValueError:
                                    pass
                            if not connect_time:
                                try:
                                    timestamp = float(connected_since)
                                    connect_time = datetime.fromtimestamp(timestamp)
                                except (ValueError, OSError):
                                    pass
                            if connect_time:
                                current_time = datetime.now()
                                duration = current_time - connect_time
                                if duration.total_seconds() < 0:
                                    duration_str = "00:00"
                                else:
                                    total_seconds = int(duration.total_seconds())
                                    hours = total_seconds // 3600
                                    minutes = (total_seconds % 3600) // 60
                                    seconds = total_seconds % 60
                                    if hours > 0:
                                        duration_str = f"{hours}h{minutes:02d}m"
                                    elif minutes > 0:
                                        duration_str = f"{minutes}m{seconds:02d}s"
                                    else:
                                        duration_str = f"{seconds}s"
                            else:
                                duration_str = "解析失败"
                        except Exception:
                            duration_str = "计算错误"
                        real_ip = real_address.split(':')[0] if ':' in real_address else real_address
                        online_clients[client_name] = {
                            'vpn_ip': vpn_ip,
                            'real_ip': real_ip,
                            'duration': duration_str,
                            'connected_since': connected_since
                        }
        return online_clients
    except Exception:
        return online_clients


def get_openvpn_clients():
    clients = []
    online_clients = get_online_clients()
    disabled_clients = set()
    disabled_clients_dir = '/etc/openvpn/disabled_clients'
    if os.path.exists(disabled_clients_dir):
        try:
            for filename in os.listdir(disabled_clients_dir):
                if os.path.isfile(os.path.join(disabled_clients_dir, filename)):
                    disabled_clients.add(filename)
        except Exception:
            pass

    try:
        # ✅ 使用 sudo 读取 index.txt
        result = subprocess.run(
            ['sudo', 'cat', '/etc/openvpn/easy-rsa/pki/index.txt'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            log_message(f"无法读取 index.txt：{result.stderr}")
            return clients

        for line in result.stdout.splitlines():
            if line.startswith('V') or line.startswith('R'):
                parts = line.strip().split('\t')
                if len(parts) >= 6:
                    expiry_date = parts[1]
                    cn_field = parts[5]
                    match = re.search(r'CN=([^/]+)', cn_field)
                    if match:
                        client_name = match.group(1)
                        if client_name == 'server':
                            continue
                        try:
                            from datetime import datetime
                            if len(expiry_date) == 13 and expiry_date.endswith('Z'):
                                year = 2000 + int(expiry_date[:2])
                                month = int(expiry_date[2:4])
                                day = int(expiry_date[4:6])
                                expiry_readable = f"{year}-{month:02d}-{day:02d}"
                            else:
                                expiry_readable = "Unknown"
                        except:
                            expiry_readable = "Unknown"

                        is_disabled = client_name in disabled_clients
                        is_online = not is_disabled and client_name in online_clients
                        client_info = online_clients.get(client_name, {})
                        is_revoked = line.startswith('R')
                        clients.append({
                            'name': client_name,
                            'expiry': expiry_readable,
                            'online': is_online,
                            'disabled': is_disabled or is_revoked,
                            'vpn_ip': client_info.get('vpn_ip', ''),
                            'real_ip': client_info.get('real_ip', ''),
                            'duration': client_info.get('duration', ''),
                            'connected_since': client_info.get('connected_since', '')
                        })
    except Exception as e:
        log_message(f"读取 index.txt 异常：{e}")
    return clients


def get_openvpn_port():
    try:
        with open('/etc/openvpn/server.conf') as f:
            for line in f:
                if line.startswith('port '):
                    return int(line.split()[1])
    except Exception:
        pass
    return 1194  # 默认兜底