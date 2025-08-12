#!/usr/bin/env python3
import os
import subprocess
import time
import re
import sys
import json
from datetime import datetime, timedelta
from collections import defaultdict
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file

app = Flask(__name__)
# Update script path to workspace directory
SCRIPT_PATH = './ubuntu-openvpn-install.sh'

# Enable verbose logging
app.config['DEBUG'] = True

def log_message(message):
    """Simple logging function that prints to stdout"""
    print(f"[SERVER] {message}", flush=True)
    sys.stdout.flush()

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
    """Get list of OpenVPN clients with expiration dates, online status, and disabled status"""
    clients = []
    
    # Get online clients first
    online_clients = get_online_clients()
    
    # Check for disabled clients
    disabled_clients = set()
    disabled_clients_dir = '/etc/openvpn/disabled_clients'
    if os.path.exists(disabled_clients_dir):
        try:
            for filename in os.listdir(disabled_clients_dir):
                if os.path.isfile(os.path.join(disabled_clients_dir, filename)):
                    disabled_clients.add(filename)
        except Exception as e:
            print(f"Error reading disabled clients: {e}")
    
    try:
        if os.path.exists('/etc/openvpn/easy-rsa/pki/index.txt'):
            with open('/etc/openvpn/easy-rsa/pki/index.txt', 'r') as f:
                for line in f:
                    if line.startswith('V') or line.startswith('R'):  # Valid or Revoked certificates
                        # Extract client name and expiration date from the index
                        parts = line.strip().split('\t')
                        if len(parts) >= 6:
                            expiry_date = parts[1]  # YYMMDDHHMMSSZ format
                            cn_field = parts[5]
                            match = re.search(r'CN=([^/]+)', cn_field)
                            if match:
                                client_name = match.group(1)
                                # Skip server certificate
                                if client_name == 'server':
                                    continue
                                    
                                # Convert expiry date to readable format
                                try:
                                    from datetime import datetime
                                    # Parse YYMMDDHHMMSSZ format (e.g., 341205000000Z)
                                    if len(expiry_date) == 13 and expiry_date.endswith('Z'):
                                        year = 2000 + int(expiry_date[:2])
                                        month = int(expiry_date[2:4])
                                        day = int(expiry_date[4:6])
                                        expiry_readable = f"{year}-{month:02d}-{day:02d}"
                                    else:
                                        expiry_readable = "Unknown"
                                except:
                                    expiry_readable = "Unknown"
                                
                                # Check if client is disabled
                                is_disabled = client_name in disabled_clients
                                
                                # Check if client is online (disabled clients cannot be online)
                                is_online = not is_disabled and client_name in online_clients
                                client_info = online_clients.get(client_name, {})
                                
                                # Check if certificate is revoked
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
        print(f"Error getting clients: {e}")
    return clients

def get_online_clients():
    """Get currently connected OpenVPN clients with VPN IP and connection info"""
    online_clients = {}
    
    # Check for suspicious login patterns (异地登录检测)
    check_suspicious_logins()
    
    # Check OpenVPN status file - try the correct location first
    status_file = "/var/log/openvpn/status.log"
    if not os.path.exists(status_file):
        # Try alternative locations
        status_file = "/var/log/openvpn/openvpn-status.log"
        if not os.path.exists(status_file):
            status_file = "/etc/openvpn/server/openvpn-status.log"
    
    if not os.path.exists(status_file):
        print(f"OpenVPN status file not found: {status_file}")
        return online_clients
    
    try:
        with open(status_file, 'r') as f:
            lines = f.readlines()
        
        print(f"Reading status file: {status_file}")
        print(f"Status file has {len(lines)} lines")
        print(f"First 10 lines of status file:")
        for i, line in enumerate(lines[:10]):
            print(f"  {i+1}: {line.strip()}")  # Debug: show first 10 lines with line numbers
        
        # Parse different possible formats
        in_client_list = False
        routing_table_section = False
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
                
            # OpenVPN status format detection
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
                
            # Parse client list section (Common Name,Real Address,Bytes Received,Bytes Sent,Connected Since)
            if in_client_list and ',' in line and not line.startswith('Common Name'):
                parts = line.split(',')
                if len(parts) >= 5:
                    client_name = parts[0].strip()
                    real_address = parts[1].strip()
                    connected_since = parts[4].strip()
                    
                    if client_name and client_name != 'UNDEF':
                        # Calculate connection duration
                        try:
                            from datetime import datetime
                            # Try different date formats used by OpenVPN
                            connect_time = None
                            
                            # Format 1: "Mon Aug 12 03:15:42 2025" (common format)
                            try:
                                connect_time = datetime.strptime(connected_since, '%a %b %d %H:%M:%S %Y')
                                print(f"[DEBUG] Parsed time format 1: {connected_since} -> {connect_time}")
                            except ValueError:
                                pass
                            
                            # Format 2: "2025-08-12 03:15:42" 
                            if not connect_time:
                                try:
                                    connect_time = datetime.strptime(connected_since, '%Y-%m-%d %H:%M:%S')
                                    print(f"[DEBUG] Parsed time format 2: {connected_since} -> {connect_time}")
                                except ValueError:
                                    pass
                            
                            # Format 3: "Aug 12 03:15:42 2025"
                            if not connect_time:
                                try:
                                    connect_time = datetime.strptime(connected_since, '%b %d %H:%M:%S %Y')
                                    print(f"[DEBUG] Parsed time format 3: {connected_since} -> {connect_time}")
                                except ValueError:
                                    pass
                            
                            # Format 4: Unix timestamp
                            if not connect_time:
                                try:
                                    timestamp = float(connected_since)
                                    connect_time = datetime.fromtimestamp(timestamp)
                                    print(f"[DEBUG] Parsed timestamp: {connected_since} -> {connect_time}")
                                except (ValueError, OSError):
                                    pass
                            
                            if connect_time:
                                current_time = datetime.now()
                                duration = current_time - connect_time
                                
                                # Handle negative duration (clock skew)
                                if duration.total_seconds() < 0:
                                    duration_str = "00:00"
                                    print(f"[DEBUG] Negative duration detected, using 00:00")
                                else:
                                    # Format duration as hours:minutes:seconds for better accuracy
                                    total_seconds = int(duration.total_seconds())
                                    hours = total_seconds // 3600
                                    minutes = (total_seconds % 3600) // 60
                                    seconds = total_seconds % 60
                                    
                                    # Show format based on duration
                                    if hours > 0:
                                        duration_str = f"{hours}h{minutes:02d}m"
                                    elif minutes > 0:
                                        duration_str = f"{minutes}m{seconds:02d}s"
                                    else:
                                        duration_str = f"{seconds}s"
                                    
                                print(f"[DEBUG] Duration calculation: {current_time} - {connect_time} = {duration_str}")
                            else:
                                duration_str = "解析失败"
                                print(f"[DEBUG] Failed to parse time format: {connected_since}")
                                
                        except Exception as e:
                            print(f"Duration calculation error: {e}")
                            duration_str = "计算错误"
                        
                        # Extract real IP (remove port)
                        real_ip = real_address.split(':')[0] if ':' in real_address else real_address
                        
                        # Store with placeholder VPN IP - will be found in routing table
                        online_clients[client_name] = {
                            'vpn_ip': '',  # Will be updated from routing table
                            'real_ip': real_ip,
                            'duration': duration_str,
                            'connected_since': connected_since
                        }
                        continue
                        
            # Parse routing table section (Virtual Address,Common Name,Real Address,Last Ref)
            if routing_table_section and ',' in line and not line.startswith('Virtual Address'):
                parts = line.split(',')
                if len(parts) >= 2:
                    vpn_ip = parts[0].strip()  # This is the VPN IP (10.8.0.x)
                    client_name = parts[1].strip()
                    
                    if client_name and client_name in online_clients and vpn_ip:
                        # Update the VPN IP for this client
                        online_clients[client_name]['vpn_ip'] = vpn_ip
                        continue
                        
            # Alternative simple format: VPN_IP,client_name,real_IP:port,connected_since
            if not in_client_list and not routing_table_section and ',' in line:
                parts = line.split(',')
                if len(parts) >= 4:
                    vpn_ip = parts[0].strip()
                    client_name = parts[1].strip()
                    real_address = parts[2].strip()
                    connected_since = parts[3].strip()
                    
                    if client_name and client_name != 'UNDEF' and vpn_ip:
                        # Calculate connection duration
                        try:
                            from datetime import datetime
                            # Try different date formats used by OpenVPN
                            connect_time = None
                            
                            # Format 1: "2025-08-12 03:15:42"
                            try:
                                connect_time = datetime.strptime(connected_since, '%Y-%m-%d %H:%M:%S')
                                print(f"[DEBUG] Parsed time format 1: {connected_since} -> {connect_time}")
                            except ValueError:
                                pass
                            
                            # Format 2: "Mon Aug 12 03:15:42 2025" (common format)
                            if not connect_time:
                                try:
                                    connect_time = datetime.strptime(connected_since, '%a %b %d %H:%M:%S %Y')
                                    print(f"[DEBUG] Parsed time format 2: {connected_since} -> {connect_time}")
                                except ValueError:
                                    pass
                            
                            # Format 3: "Aug 12 03:15:42 2025"
                            if not connect_time:
                                try:
                                    connect_time = datetime.strptime(connected_since, '%b %d %H:%M:%S %Y')
                                    print(f"[DEBUG] Parsed time format 3: {connected_since} -> {connect_time}")
                                except ValueError:
                                    pass
                            
                            # Format 4: Unix timestamp
                            if not connect_time:
                                try:
                                    timestamp = float(connected_since)
                                    connect_time = datetime.fromtimestamp(timestamp)
                                    print(f"[DEBUG] Parsed timestamp: {connected_since} -> {connect_time}")
                                except (ValueError, OSError):
                                    pass
                            
                            if connect_time:
                                current_time = datetime.now()
                                duration = current_time - connect_time
                                
                                # Handle negative duration (clock skew)
                                if duration.total_seconds() < 0:
                                    duration_str = "00:00"
                                    print(f"[DEBUG] Negative duration detected, using 00:00")
                                else:
                                    # Format duration as hours:minutes:seconds for better accuracy
                                    total_seconds = int(duration.total_seconds())
                                    hours = total_seconds // 3600
                                    minutes = (total_seconds % 3600) // 60
                                    seconds = total_seconds % 60
                                    
                                    # Show format based on duration
                                    if hours > 0:
                                        duration_str = f"{hours}h{minutes:02d}m"
                                    elif minutes > 0:
                                        duration_str = f"{minutes}m{seconds:02d}s"
                                    else:
                                        duration_str = f"{seconds}s"
                                    
                                print(f"[DEBUG] Duration calculation: {current_time} - {connect_time} = {duration_str}")
                            else:
                                duration_str = "解析失败"
                                print(f"[DEBUG] Failed to parse time format: {connected_since}")
                                
                        except Exception as e:
                            print(f"Duration calculation error: {e}")
                            duration_str = "计算错误"
                        
                        # Extract real IP (remove port)
                        real_ip = real_address.split(':')[0] if ':' in real_address else real_address
                        
                        online_clients[client_name] = {
                            'vpn_ip': vpn_ip,
                            'real_ip': real_ip,
                            'duration': duration_str,
                            'connected_since': connected_since
                        }
                        
        print(f"Parsed online clients: {online_clients}")  # Debug output
        
    except Exception as e:
        print(f"Error reading OpenVPN status: {e}")
    
    return online_clients

def check_suspicious_logins():
    """检测异地登录并发送通知"""
    try:
        # 读取OpenVPN日志文件 - 优先使用真实日志
        log_files = [
            '/var/log/openvpn/openvpn.log',  # 真实OpenVPN日志文件
            '/var/log/openvpn/server.log', 
            '/var/log/openvpn.log',
            '/var/log/syslog',
            '/tmp/openvpn_test/openvpn.log'  # 测试日志文件作为后备
        ]</to_replace>
</Editor.edit_file_by_replace>

<Editor.edit_file_by_replace>
<file_name>/workspace/openvpn-web/app.py</file_name>
<to_replace>                try:
                    # 读取最近1000行日志 - 不使用sudo以适配当前环境
                    if os.access(log_file, os.R_OK):
                        with open(log_file, 'r') as f:
                            lines = f.readlines()
                            # 取最后1000行
                            lines = lines[-1000:] if len(lines) > 1000 else lines
                            result_stdout = ''.join(lines)
                            result_returncode = 0
                    else:
                        # 尝试使用tail命令
                        result = subprocess.run([
                            'tail', '-n', '1000', log_file
                        ], capture_output=True, text=True, timeout=10)
                        result_stdout = result.stdout
                        result_returncode = result.returncode</to_replace>
<new_content>                try:
                    # 优先尝试直接读取文件
                    if os.access(log_file, os.R_OK):
                        try:
                            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                                lines = f.readlines()
                                # 取最后1000行
                                lines = lines[-1000:] if len(lines) > 1000 else lines
                                result_stdout = ''.join(lines)
                                result_returncode = 0
                        except Exception as read_error:
                            print(f"[SECURITY] Direct read failed for {log_file}: {read_error}")
                            # 如果直接读取失败，尝试使用系统命令
                            result = subprocess.run([
                                'cat', log_file
                            ], capture_output=True, text=True, timeout=30)
                            if result.returncode == 0:
                                lines = result.stdout.split('\n')
                                lines = lines[-1000:] if len(lines) > 1000 else lines
                                result_stdout = '\n'.join(lines)
                                result_returncode = 0
                            else:
                                result_stdout = ''
                                result_returncode = 1
                    else:
                        # 文件无法直接访问，尝试使用系统命令
                        commands_to_try = [
                            ['cat', log_file],
                            ['tail', '-n', '1000', log_file],
                            ['head', '-n', '1000', log_file]
                        ]
                        
                        result_stdout = ''
                        result_returncode = 1
                        
                        for cmd in commands_to_try:
                            try:
                                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                                if result.returncode == 0 and result.stdout.strip():
                                    result_stdout = result.stdout
                                    result_returncode = 0
                                    print(f"[SECURITY] Successfully read {log_file} using {' '.join(cmd)}")
                                    break
                            except Exception as cmd_error:
                                print(f"[SECURITY] Command {' '.join(cmd)} failed: {cmd_error}")
                                continue
        
        log_content = []
        used_log_file = None
        
        for log_file in log_files:
            if os.path.exists(log_file):
                try:
                    # 读取最近1000行日志 - 不使用sudo以适配当前环境
                    if os.access(log_file, os.R_OK):
                        with open(log_file, 'r') as f:
                            lines = f.readlines()
                            # 取最后1000行
                            lines = lines[-1000:] if len(lines) > 1000 else lines
                            result_stdout = ''.join(lines)
                            result_returncode = 0
                    else:
                        # 尝试使用tail命令
                        result = subprocess.run([
                            'tail', '-n', '1000', log_file
                        ], capture_output=True, text=True, timeout=10)
                        result_stdout = result.stdout
                        result_returncode = result.returncode
                    
                    if result.returncode == 0 and result.stdout.strip():
                        lines = result.stdout.split('\n')
                        log_content.extend(lines)
                        used_log_file = log_file
                        print(f"[SECURITY] Read {len(lines)} lines from {log_file}")
                        
                        # 显示一些样本日志行用于调试
                        sample_lines = [line for line in lines[:10] if line.strip()]
                        if sample_lines:
                            print(f"[SECURITY] Sample log lines from {log_file}:")
                            for i, line in enumerate(sample_lines[:3]):
                                print(f"[SECURITY]   {i+1}: {line}")
                        break
                except Exception as e:
                    print(f"[SECURITY] Error reading {log_file}: {e}")
                    continue
        
        if not log_content:
            print("[SECURITY] No OpenVPN log files found or all files are empty")
            print("[SECURITY] Available log files:")
            for log_file in log_files:
                if os.path.exists(log_file):
                    try:
                        size = os.path.getsize(log_file)
                        print(f"[SECURITY]   {log_file}: {size} bytes")
                    except:
                        print(f"[SECURITY]   {log_file}: cannot get size")
                else:
                    print(f"[SECURITY]   {log_file}: does not exist")
            return
        
        print(f"[SECURITY] Processing {len(log_content)} log lines from {used_log_file}")
        
        # 解析日志，查找可疑登录
        current_time = datetime.now()
        recent_logins = defaultdict(list)  # {client_name: [(timestamp, ip, action), ...]}
        
        connection_patterns_found = 0
        duplicate_patterns_found = 0
        
        for line in log_content:
            if not line.strip():
                continue
                
            # 匹配新连接日志 - 支持多种格式
            # 格式1: 2025-08-12 14:04:17 192.168.50.1:39931 [mxb] Peer Connection Initiated
            peer_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+([0-9.]+):\d+\s+\[([^\]]+)\]\s+Peer Connection Initiated', line)
            if not peer_match:
                # 格式2: Dec 12 14:04:17 hostname openvpn[1234]: 192.168.50.1:39931 [mxb] Peer Connection Initiated
                peer_match = re.search(r'(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}).*openvpn.*([0-9.]+):\d+\s+\[([^\]]+)\]\s+Peer Connection Initiated', line)
                if peer_match:
                    # 转换月份格式到完整日期
                    timestamp_str, ip_addr, client_name = peer_match.groups()
                    try:
                        # 假设是当前年份
                        current_year = datetime.now().year
                        timestamp = datetime.strptime(f"{current_year} {timestamp_str}", '%Y %b %d %H:%M:%S')
                    except ValueError:
                        continue
                else:
                    # 格式3: 简单的时间戳格式
                    peer_match = re.search(r'([0-9.]+):\d+\s+\[([^\]]+)\]\s+Peer Connection Initiated', line)
                    if peer_match:
                        ip_addr, client_name = peer_match.groups()
                        timestamp = current_time  # 使用当前时间作为近似值
                    else:
                        peer_match = None
            else:
                timestamp_str, ip_addr, client_name = peer_match.groups()
                try:
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    continue
            
            if peer_match:
                # 只处理最近1小时内的日志
                if (current_time - timestamp).total_seconds() <= 3600:
                    recent_logins[client_name].append((timestamp, ip_addr, 'connect'))
                    connection_patterns_found += 1
                    print(f"[SECURITY] Found connection: {client_name} from {ip_addr} at {timestamp}")
            
            # 匹配多重连接警告日志 - 支持多种格式
            multi_patterns = [
                r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*MULTI: new connection by client \'([^\']+)\' will cause previous active sessions',
                r'(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}).*MULTI: new connection by client \'([^\']+)\' will cause previous active sessions',
                r'MULTI: new connection by client \'([^\']+)\' will cause previous active sessions'
            ]
            
            for pattern in multi_patterns:
                multi_match = re.search(pattern, line)
                if multi_match:
                    groups = multi_match.groups()
                    if len(groups) == 2:
                        timestamp_str, client_name = groups
                        try:
                            if re.match(r'\d{4}-\d{2}-\d{2}', timestamp_str):
                                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                            else:
                                # 月份格式
                                current_year = datetime.now().year
                                timestamp = datetime.strptime(f"{current_year} {timestamp_str}", '%Y %b %d %H:%M:%S')
                        except ValueError:
                            timestamp = current_time
                    else:
                        # 只有客户端名称，使用当前时间
                        client_name = groups[0]
                        timestamp = current_time
                    
                    if (current_time - timestamp).total_seconds() <= 3600:
                        recent_logins[client_name].append((timestamp, 'MULTI_DROP', 'duplicate'))
                        duplicate_patterns_found += 1
                        print(f"[SECURITY] Found duplicate login warning for {client_name} at {timestamp}")
                    break
        
        print(f"[SECURITY] Found {connection_patterns_found} connection patterns and {duplicate_patterns_found} duplicate patterns")
        
        # 分析可疑登录模式
        for client_name, login_events in recent_logins.items():
            if len(login_events) < 2:
                continue
                
            # 按时间排序
            login_events.sort(key=lambda x: x[0])
            
            # 检查是否有来自不同IP的连续登录
            for i in range(1, len(login_events)):
                prev_time, prev_ip, prev_action = login_events[i-1]
                curr_time, curr_ip, curr_action = login_events[i]
                
                # 如果在短时间内有来自不同IP的登录
                if (curr_action == 'connect' and prev_action == 'connect' and 
                    prev_ip != curr_ip and prev_ip != 'MULTI_DROP' and
                    (curr_time - prev_time).total_seconds() <= 600):  # 10分钟内
                    
                    # 发送异地登录通知
                    send_suspicious_login_notification(client_name, prev_ip, curr_ip, prev_time, curr_time)
                
                # 检查duplicate login模式
                elif curr_action == 'duplicate' and i > 0:
                    prev_connect = None
                    # 查找之前最近的连接
                    for j in range(i-1, -1, -1):
                        if login_events[j][2] == 'connect':
                            prev_connect = login_events[j]
                            break
                    
                    if prev_connect and (curr_time - prev_connect[0]).total_seconds() <= 300:  # 5分钟内
                        # 查找当前连接的IP
                        curr_connect = None
                        for j in range(i+1, len(login_events)):
                            if login_events[j][2] == 'connect':
                                curr_connect = login_events[j]
                                break
                        
                        if curr_connect and prev_connect[1] != curr_connect[1]:
                            send_suspicious_login_notification(
                                client_name, prev_connect[1], curr_connect[1], 
                                prev_connect[0], curr_connect[0]
                            )
    
    except Exception as e:
        print(f"[SECURITY] Error in suspicious login check: {e}")

def send_suspicious_login_notification(client_name, old_ip, new_ip, old_time, new_time):
    """发送异地登录通知"""
    try:
        # 创建通知目录
        notification_dir = '/tmp/openvpn_notifications'
        subprocess.run(['mkdir', '-p', notification_dir], check=False)
        
        # 获取地理位置信息 (简化版，实际可以使用IP地理位置API)
        old_location = get_ip_location(old_ip)
        new_location = get_ip_location(new_ip)
        
        notification = {
            'client_name': client_name,
            'alert_type': 'suspicious_login',
            'timestamp': datetime.now().isoformat(),
            'old_connection': {
                'ip': old_ip,
                'time': old_time.isoformat(),
                'location': old_location
            },
            'new_connection': {
                'ip': new_ip, 
                'time': new_time.isoformat(),
                'location': new_location
            },
            'message': f'检测到客户端 {client_name} 异地登录！\n原连接: {old_ip} ({old_location}) 于 {old_time.strftime("%Y-%m-%d %H:%M:%S")}\n新连接: {new_ip} ({new_location}) 于 {new_time.strftime("%Y-%m-%d %H:%M:%S")}'
        }
        
        # 保存通知到文件
        notification_file = f'{notification_dir}/alert_{client_name}_{int(time.time())}.json'
        with open(notification_file, 'w', encoding='utf-8') as f:
            json.dump(notification, f, ensure_ascii=False, indent=2)
        
        print(f"[SECURITY] 🚨 异地登录警报: {client_name}")
        print(f"[SECURITY] 原IP: {old_ip} ({old_location}) -> 新IP: {new_ip} ({new_location})")
        print(f"[SECURITY] 时间差: {(new_time - old_time).total_seconds():.0f}秒")
        print(f"[SECURITY] 通知已保存到: {notification_file}")
        
        # 可以在这里实现更多通知方式：
        # - 发送邮件
        # - 发送到Webhook
        # - 写入系统日志
        # - 通过管理接口断开可疑连接
        
        # 写入系统日志
        log_message(f"SECURITY ALERT: Suspicious login detected for client '{client_name}' - Old IP: {old_ip}, New IP: {new_ip}")
        
    except Exception as e:
        print(f"[SECURITY] Error sending notification: {e}")

def get_ip_location(ip):
    """获取IP地址的地理位置 (简化版)"""
    try:
        # 检查是否为内网IP
        if ip.startswith('192.168.') or ip.startswith('10.') or ip.startswith('172.'):
            return '内网地址'
        elif ip.startswith('127.'):
            return '本地地址'
        else:
            # 这里可以调用IP地理位置API，比如 ipapi.co, ipinfo.io 等
            # 为了简化，这里返回一个占位符
            return f'外网地址({ip})'
    except:
        return '未知位置'

@app.route('/notifications')
def get_notifications():
    """获取安全通知列表"""
    try:
        notification_dir = '/tmp/openvpn_notifications'
        if not os.path.exists(notification_dir):
            return jsonify({'notifications': []})
        
        notifications = []
        for filename in os.listdir(notification_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(notification_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        notification = json.load(f)
                        notifications.append(notification)
                except Exception as e:
                    print(f"Error reading notification file {filename}: {e}")
        
        # 按时间倒序排列
        notifications.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        # 只返回最近100条
        return jsonify({'notifications': notifications[:100]})
        
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/clear_notifications', methods=['POST'])
def clear_notifications():
    """清空所有通知"""
    try:
        notification_dir = '/tmp/openvpn_notifications'
        if os.path.exists(notification_dir):
            subprocess.run(['rm', '-rf', notification_dir], check=False)
            subprocess.run(['mkdir', '-p', notification_dir], check=False)
        
        return jsonify({'status': 'success', 'message': '所有通知已清空'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

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
    # Check if the OpenVPN script exists
    if not os.path.exists(SCRIPT_PATH):
        return jsonify({
            'status': 'error', 
            'message': f'OpenVPN安装脚本不存在: {SCRIPT_PATH}。请确保ubuntu-openvpn-install.sh文件存在于工作目录中。'
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

@app.route('/add_client', methods=['POST'])
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
            # Remove client configuration file from /tmp
            ['sudo', 'rm', '-f', f'/tmp/{client_name}.ovpn'],
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

@app.route('/download_client/<client_name>', methods=['GET'])
def download_client(client_name):
    # Client config file is always saved in /tmp folder
    client_path = f"/tmp/{client_name}.ovpn"
    
    if os.path.exists(client_path):
        print(f"Found client config at: {client_path}")
        return send_file(client_path, as_attachment=True, download_name=f"{client_name}.ovpn")
    else:
        print(f"Client config not found at: {client_path}")
        return jsonify({'status': 'error', 'message': f'Client configuration file {client_name}.ovpn not found in /tmp folder'})

@app.route('/disconnect_client', methods=['POST'])
def disconnect_client():
    """Forcefully disconnect a client and prevent auto-reconnection"""
    client_name = request.form.get('client_name')
    if not client_name:
        return jsonify({'status': 'error', 'message': 'Client name is required'})
    
    client_name = client_name.strip()
    if not client_name:
        return jsonify({'status': 'error', 'message': 'Client name is required'})
    
    log_message(f"Starting permanent disconnect process for client: {client_name}")
    print(f"[DISCONNECT] Starting permanent disconnect process for client: {client_name}", flush=True)
    
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
            ['sudo', 'rm', '-f', f'/tmp/{client_name}.ovpn'],
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

@app.route('/enable_client', methods=['POST'])
def enable_client():
    """Re-enable a disabled client by restoring their certificate"""
    client_name = request.form.get('client_name')
    if not client_name:
        return jsonify({'status': 'error', 'message': 'Client name is required'})
    
    client_name = client_name.strip()
    if not client_name:
        return jsonify({'status': 'error', 'message': 'Client name is required'})
    
    log_message(f"Re-enabling client: {client_name}")
    print(f"[ENABLE] Starting re-enable process for client: {client_name}", flush=True)
    
    try:
        # Step 1: Remove disabled flag if it exists
        disabled_clients_dir = '/etc/openvpn/disabled_clients'
        disabled_flag = f'{disabled_clients_dir}/{client_name}'
        
        if os.path.exists(disabled_flag):
            subprocess.run(['sudo', 'rm', '-f', disabled_flag], check=False)
            log_message(f"Removed disabled flag for client: {client_name}")
        
        # Step 2: Check if PKI directory exists
        if not os.path.exists('/etc/openvpn/easy-rsa/pki/index.txt'):
            log_message("OpenVPN PKI not found")
            return jsonify({'status': 'error', 'message': 'OpenVPN PKI not found. Please ensure OpenVPN is installed and configured.'})
        
        # Step 3: Check current certificate status
        log_message("Checking certificate status")
        with open('/etc/openvpn/easy-rsa/pki/index.txt', 'r') as f:
            lines = f.readlines()
        
        client_found = False
        client_revoked = False
        
        for line in lines:
            if f'CN={client_name}/' in line or f'CN={client_name}' in line:
                client_found = True
                if line.startswith('R'):  # Revoked
                    client_revoked = True
                    log_message(f"Client {client_name} certificate is revoked")
                elif line.startswith('V'):  # Valid
                    log_message(f"Client {client_name} certificate is already valid")
                break
        
        if not client_found:
            log_message(f"Client {client_name} not found in PKI")
            return jsonify({'status': 'error', 'message': f'Client {client_name} not found in certificate database'})
        
        # Step 4: If certificate is revoked, create a new one
        if client_revoked:
            log_message(f"Creating new certificate for revoked client: {client_name}")
            
            # Remove old revoked entries from index
            filtered_lines = []
            for line in lines:
                if f'CN={client_name}/' not in line and f'CN={client_name}' not in line:
                    filtered_lines.append(line)
            
            # Write back filtered content
            try:
                subprocess.run([
                    'sudo', 'bash', '-c', 
                    f'cat > /etc/openvpn/easy-rsa/pki/index.txt << \'EOF\'\n{"".join(filtered_lines)}EOF'
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
                    subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
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
            config_commands = [
                f'cd /etc/openvpn/easy-rsa',
                f'echo "client" > "/tmp/{client_name}.ovpn"',
                f'echo "dev tun" >> "/tmp/{client_name}.ovpn"',
                f'echo "proto udp" >> "/tmp/{client_name}.ovpn"',
                f'echo "remote $(curl -s ifconfig.me 2>/dev/null || echo localhost) 1194" >> "/tmp/{client_name}.ovpn"',
                f'echo "resolv-retry infinite" >> "/tmp/{client_name}.ovpn"',
                f'echo "nobind" >> "/tmp/{client_name}.ovpn"',
                f'echo "persist-key" >> "/tmp/{client_name}.ovpn"',
                f'echo "persist-tun" >> "/tmp/{client_name}.ovpn"',
                f'echo "remote-cert-tls server" >> "/tmp/{client_name}.ovpn"',
                f'echo "cipher AES-256-GCM" >> "/tmp/{client_name}.ovpn"',
                f'echo "verb 3" >> "/tmp/{client_name}.ovpn"',
                f'echo "" >> "/tmp/{client_name}.ovpn"',
                f'echo "<ca>" >> "/tmp/{client_name}.ovpn"',
                f'cat "/etc/openvpn/easy-rsa/pki/ca.crt" >> "/tmp/{client_name}.ovpn"',
                f'echo "</ca>" >> "/tmp/{client_name}.ovpn"',
                f'echo "" >> "/tmp/{client_name}.ovpn"',
                f'echo "<cert>" >> "/tmp/{client_name}.ovpn"',
                f'awk \'/BEGIN/,/END CERTIFICATE/\' "/etc/openvpn/easy-rsa/pki/issued/{client_name}.crt" >> "/tmp/{client_name}.ovpn"',
                f'echo "</cert>" >> "/tmp/{client_name}.ovpn"',
                f'echo "" >> "/tmp/{client_name}.ovpn"',
                f'echo "<key>" >> "/tmp/{client_name}.ovpn"',
                f'cat "/etc/openvpn/easy-rsa/pki/private/{client_name}.key" >> "/tmp/{client_name}.ovpn"',
                f'echo "</key>" >> "/tmp/{client_name}.ovpn"',
                f'echo "" >> "/tmp/{client_name}.ovpn"',
                f'echo "<tls-crypt>" >> "/tmp/{client_name}.ovpn"',
                f'cat /etc/openvpn/tls-crypt.key 2>/dev/null || cat /etc/openvpn/ta.key 2>/dev/null || echo "# TLS key not found" >> "/tmp/{client_name}.ovpn"',
                f'echo "</tls-crypt>" >> "/tmp/{client_name}.ovpn"',
                f'chmod 644 "/tmp/{client_name}.ovpn"'
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
        
        # Step 5: Generate new CRL to remove any revocation
        log_message("Generating new CRL")
        crl_result = subprocess.run([
            'sudo', 'bash', '-c', 'cd /etc/openvpn/easy-rsa && ./easyrsa gen-crl'
        ], capture_output=True, text=True, timeout=60)
        
        if crl_result.returncode != 0:
            error_msg = f"Failed to generate CRL: {crl_result.stderr}"
            log_message(error_msg)
            return jsonify({'status': 'error', 'message': error_msg})
        
        # Step 6: Update CRL in OpenVPN directory
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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
