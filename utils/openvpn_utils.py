import os
import subprocess
import re
import sys
from models import db, Client
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Dict
def log_message(message):
    print(f"[SERVER] {message}", flush=True)
    sys.stdout.flush()


def check_openvpn_status():
    """
    检查 OpenVPN 服务状态并返回 'running', 'installed', 或 'not_installed'。
    此函数会使用 sudo 确保在普通用户环境下也能正常工作。
    """
    service_name = 'openvpn@server.service'
    config_path = '/etc/openvpn/server.conf'

    try:
        # --- 1. 检查运行状态：使用 systemctl is-active 的返回码 ---
        result_active = subprocess.run(
            ['sudo', 'systemctl', 'is-active', '--quiet', service_name],
            check=False  # 不抛出异常
        )
        if result_active.returncode == 0:
            return 'running'

        # --- 2. 检查安装状态：直接检查配置文件是否存在 ---
        # 使用 os.path.exists() 是最安全、最简洁的方法，且不依赖外部命令。
        # 但如果必须使用 sudo，subprocess.run + test -e 也是可行的。
        # 这里为了保持和原来风格一致，仍使用subprocess.run。
        result_config = subprocess.run(
            ['sudo', 'test', '-e', config_path],
            check=False
        )
        if result_config.returncode == 0:
            return 'installed'

        # --- 3. 未找到任何状态 ---
        return 'not_installed'
    
    except FileNotFoundError:
        # 捕获当 'sudo' 或 'systemctl' 命令本身不存在时的情况
        return 'error: required command not found'
    except Exception as e:
        return f'error: {str(e)}'

# 旧的get_online_clients函数
# def get_online_clients():
#     online_clients = {}
#     status_file = "/var/log/openvpn/status.log"
#     if not os.path.exists(status_file):
#         status_file = "/var/log/openvpn/openvpn-status.log"
#         if not os.path.exists(status_file):
#             status_file = "/etc/openvpn/server/openvpn-status.log"
#     if not os.path.exists(status_file):
#         return online_clients
#     try:
#         with open(status_file, 'r') as f:
#             lines = f.readlines()
#         in_client_list = False
#         routing_table_section = False
#         for line in lines:
#             line = line.strip()
#             if not line or line.startswith('#'):
#                 continue
#             if line.startswith('OpenVPN CLIENT LIST'):
#                 in_client_list = True
#                 continue
#             elif line.startswith('ROUTING TABLE'):
#                 in_client_list = False
#                 routing_table_section = True
#                 continue
#             elif line.startswith('GLOBAL STATS'):
#                 routing_table_section = False
#                 continue
#             if in_client_list and ',' in line and not line.startswith('Common Name'):
#                 parts = line.split(',')
#                 if len(parts) >= 5:
#                     client_name = parts[0].strip()
#                     real_address = parts[1].strip()
#                     connected_since = parts[4].strip()
#                     if client_name and client_name != 'UNDEF':
#                         try:
#                             from datetime import datetime
#                             connect_time = None
#                             try:
#                                 connect_time = datetime.strptime(connected_since, '%a %b %d %H:%M:%S %Y')
#                             except ValueError:
#                                 pass
#                             if not connect_time:
#                                 try:
#                                     connect_time = datetime.strptime(connected_since, '%Y-%m-%d %H:%M:%S')
#                                 except ValueError:
#                                     pass
#                             if not connect_time:
#                                 try:
#                                     connect_time = datetime.strptime(connected_since, '%b %d %H:%M:%S %Y')
#                                 except ValueError:
#                                     pass
#                             if not connect_time:
#                                 try:
#                                     timestamp = float(connected_since)
#                                     connect_time = datetime.fromtimestamp(timestamp)
#                                 except (ValueError, OSError):
#                                     pass
#                             if connect_time:
#                                 current_time = datetime.now()
#                                 duration = current_time - connect_time
#                                 if duration.total_seconds() < 0:
#                                     duration_str = "00:00"
#                                 else:
#                                     total_seconds = int(duration.total_seconds())
#                                     hours = total_seconds // 3600
#                                     minutes = (total_seconds % 3600) // 60
#                                     seconds = total_seconds % 60
#                                     if hours > 0:
#                                         duration_str = f"{hours}h{minutes:02d}m"
#                                     elif minutes > 0:
#                                         duration_str = f"{minutes}m{seconds:02d}s"
#                                     else:
#                                         duration_str = f"{seconds}s"
#                             else:
#                                 duration_str = "解析失败"
#                         except Exception:
#                             duration_str = "计算错误"
#                         real_ip = real_address.split(':')[0] if ':' in real_address else real_address
#                         online_clients[client_name] = {
#                             'vpn_ip': '',
#                             'real_ip': real_ip,
#                             'duration': duration_str,
#                             'connected_since': connected_since
#                         }
#                         continue
#             if routing_table_section and ',' in line and not line.startswith('Virtual Address'):
#                 parts = line.split(',')
#                 if len(parts) >= 2:
#                     vpn_ip = parts[0].strip()
#                     client_name = parts[1].strip()
#                     if client_name and client_name in online_clients and vpn_ip:
#                         online_clients[client_name]['vpn_ip'] = vpn_ip
#                         continue
#             if not in_client_list and not routing_table_section and ',' in line:
#                 parts = line.split(',')
#                 if len(parts) >= 4:
#                     vpn_ip = parts[0].strip()
#                     client_name = parts[1].strip()
#                     real_address = parts[2].strip()
#                     connected_since = parts[3].strip()
#                     if client_name and client_name != 'UNDEF' and vpn_ip:
#                         try:
#                             from datetime import datetime
#                             connect_time = None
#                             try:
#                                 connect_time = datetime.strptime(connected_since, '%Y-%m-%d %H:%M:%S')
#                             except ValueError:
#                                 pass
#                             if not connect_time:
#                                 try:
#                                     connect_time = datetime.strptime(connected_since, '%a %b %d %H:%M:%S %Y')
#                                 except ValueError:
#                                     pass
#                             if not connect_time:
#                                 try:
#                                     connect_time = datetime.strptime(connected_since, '%b %d %H:%M:%S %Y')
#                                 except ValueError:
#                                     pass
#                             if not connect_time:
#                                 try:
#                                     timestamp = float(connected_since)
#                                     connect_time = datetime.fromtimestamp(timestamp)
#                                 except (ValueError, OSError):
#                                     pass
#                             if connect_time:
#                                 current_time = datetime.now()
#                                 duration = current_time - connect_time
#                                 if duration.total_seconds() < 0:
#                                     duration_str = "00:00"
#                                 else:
#                                     total_seconds = int(duration.total_seconds())
#                                     hours = total_seconds // 3600
#                                     minutes = (total_seconds % 3600) // 60
#                                     seconds = total_seconds % 60
#                                     if hours > 0:
#                                         duration_str = f"{hours}h{minutes:02d}m"
#                                     elif minutes > 0:
#                                         duration_str = f"{minutes}m{seconds:02d}s"
#                                     else:
#                                         duration_str = f"{seconds}s"
#                             else:
#                                 duration_str = "解析失败"
#                         except Exception:
#                             duration_str = "计算错误"
#                         real_ip = real_address.split(':')[0] if ':' in real_address else real_address
#                         online_clients[client_name] = {
#                             'vpn_ip': vpn_ip,
#                             'real_ip': real_ip,
#                             'duration': duration_str,
#                             'connected_since': connected_since
#                         }
#         return online_clients
#     except Exception:
#         return online_clients

# 优化后的get_openvpn_clients函数
import os
import time
from datetime import datetime, timezone
from typing import Dict, NamedTuple, Optional

class OnlineClient(NamedTuple):
    vpn_ip: str
    real_ip: str
    duration_str: str          # 人类可读
    duration_sec: int          # 秒数，方便排序
    connected_since: str       # 原始字符串


# 缓存 10 s，避免并发刷爆 IO
_last_check: float = 0
_cache: Dict[str, OnlineClient] = {}


def _parse_connected_since(text: str) -> Optional[datetime]:
    """
    OpenVPN status 只有两种合法格式：
    1. Wed Jun 11 14:22:33 2025   (status-version 1/2)
    2. 1722344556                 (status-version 3, Unix timestamp)
    """
    try:
        return datetime.strptime(text, "%a %b %d %H:%M:%S %Y")
    except ValueError:
        pass
    try:
        return datetime.fromtimestamp(float(text), tz=timezone.utc)
    except (ValueError, OSError):
        return None


def _human_duration(seconds: int) -> str:
    """>=1 h 输出 1h23m；<1 h 输出 5m12s；<1 min 输出 45s"""
    if seconds < 0:
        return "00:00"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def get_online_clients(status_file: str = None, cache_ttl: int = 10) -> Dict[str, OnlineClient]:
    global _last_check, _cache
    now = time.time()
    if now - _last_check < cache_ttl and _cache:
        return _cache

    if status_file is None:
        # 自动探测，保持与原逻辑一致
        for cand in ("/var/log/openvpn/status.log",
                     "/var/log/openvpn/openvpn-status.log",
                     "/etc/openvpn/server/openvpn-status.log"):
            if os.path.isfile(cand):
                status_file = cand
                break
        else:
            return {}   # 文件不存在，返回空

    try:
        with open(status_file, "rb") as f:        # 二进制读，防止中文 locale 异常
            data = f.read().decode("utf-8", errors="ignore")
    except OSError as e:
        # 权限、磁盘故障等，记录日志后返回空
        import logging
        logging.getLogger(__name__).warning("read status %s failed: %s", status_file, e)
        return {}

    clients: Dict[str, OnlineClient] = {}
    in_client_list = False
    for line in data.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("OpenVPN CLIENT LIST"):
            in_client_list = True
            continue
        if line.startswith("ROUTING TABLE"):
            in_client_list = False
            continue
        if not in_client_list or not line.count(","):
            continue
        if line.startswith("Common Name"):
            continue

        parts = line.split(",")
        if len(parts) < 5:
            continue
        cn, real_addr, _bytes_recv, _bytes_sent, conn_since = parts[0:5]
        if cn == "UNDEF":
            continue

        conn_dt = _parse_connected_since(conn_since)
        if conn_dt is None:
            continue
        duration_sec = int((datetime.now(timezone.utc) - conn_dt).total_seconds())
        real_ip = real_addr.split(":")[0] if ":" in real_addr else real_addr

        clients[cn] = OnlineClient(
            vpn_ip="",                         # 稍后二次扫描补全
            real_ip=real_ip,
            duration_str=_human_duration(duration_sec),
            duration_sec=duration_sec,
            connected_since=conn_since
        )

    # 二次扫描：补 vpn_ip（ROUTING TABLE 段）
    routing_section = False
    for line in data.splitlines():
        line = line.strip()
        if line.startswith("ROUTING TABLE"):
            routing_section = True
            continue
        if line.startswith("GLOBAL STATS"):
            routing_section = False
            continue
        if not routing_section or not line.count(","):
            continue
        vpn_ip, cn = line.split(",")[0:2]
        if cn in clients:
            clients[cn] = clients[cn]._replace(vpn_ip=vpn_ip)

    _last_check = now
    _cache = clients
    return clients



# def get_openvpn_clients():
#     clients = []
#     online_clients = get_online_clients()
#     disabled_clients = set()
#     disabled_clients_dir = '/etc/openvpn/ccd'
#     if os.path.exists(disabled_clients_dir):
#         try:
#             for filename in os.listdir(disabled_clients_dir):
#                 if os.path.isfile(os.path.join(disabled_clients_dir, filename)):
#                     disabled_clients.add(filename)
#         except Exception:
#             pass

#     try:
#         # ✅ 使用 sudo 读取 index.txt
#         result = subprocess.run(
#             ['sudo', 'cat', '/etc/openvpn/easy-rsa/pki/index.txt'],
#             capture_output=True,
#             text=True,
#             timeout=5
#         )
#         if result.returncode != 0:
#             log_message(f"无法读取 index.txt：{result.stderr}")
#             return clients

#         for line in result.stdout.splitlines():
#             if line.startswith('V') or line.startswith('R'):
#                 parts = line.strip().split('\t')
#                 if len(parts) >= 6:
#                     expiry_date = parts[1]
#                     cn_field = parts[5]
#                     match = re.search(r'CN=([^/]+)', cn_field)
#                     if match:
#                         client_name = match.group(1)
#                         if client_name == 'server':
#                             continue
#                         try:
#                             from datetime import datetime
#                             if len(expiry_date) == 13 and expiry_date.endswith('Z'):
#                                 year = 2000 + int(expiry_date[:2])
#                                 month = int(expiry_date[2:4])
#                                 day = int(expiry_date[4:6])
#                                 expiry_readable = f"{year}-{month:02d}-{day:02d}"
#                             else:
#                                 expiry_readable = "Unknown"
#                         except:
#                             expiry_readable = "Unknown"

#                         is_disabled = client_name in disabled_clients
#                         is_online = not is_disabled and client_name in online_clients
#                         client_info = online_clients.get(client_name, {})
#                         is_revoked = line.startswith('R')
#                         clients.append({
#                             'name': client_name,
#                             'expiry': expiry_readable,
#                             'online': is_online,
#                             'disabled': is_disabled or is_revoked,
#                             'vpn_ip': client_info.get('vpn_ip', ''),
#                             'real_ip': client_info.get('real_ip', ''),
#                             'duration': client_info.get('duration', ''),
#                             'connected_since': client_info.get('connected_since', '')
#                         })
#     except Exception as e:
#         log_message(f"读取 index.txt 异常：{e}")
#     return clients


def get_openvpn_clients() -> List[Dict[str, str]]:
    clients: List[Dict[str, str]] = []
    # ① 拿在线列表（带缓存，10 s 内不重复读盘）
    online_clients: Dict[str, OnlineClient] = get_online_clients()

    # ② 被禁用（ccd 目录存在同名文件）或被吊销的客户端
    disabled_clients: set[str] = set()
    disabled_dir = "/etc/openvpn/ccd"
    if os.path.isdir(disabled_dir):
        try:
            disabled_clients = {f for f in os.listdir(disabled_dir)
                               if os.path.isfile(os.path.join(disabled_dir, f))}
        except Exception as e:
            log_message(f"枚举禁用客户端失败：{e}")

    # ③ 读取 easy-rsa 索引
    try:
        result = subprocess.run(
            ["sudo", "cat", "/etc/openvpn/easy-rsa/pki/index.txt"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            log_message(f"无法读取 index.txt：{result.stderr}")
            return clients

        for line in result.stdout.splitlines():
            line = line.strip()
            if not (line.startswith("V") or line.startswith("R")):
                continue
            parts = line.split("\t")
            if len(parts) < 6:
                continue

            expiry_date = parts[1]
            cn_field = parts[5]
            match = re.search(r"CN=([^/]+)", cn_field)
            if not match:
                continue
            client_name = match.group(1)
            if client_name == "server":
                continue

            # 过期日期解析（easy-rsa 3.x 输出格式固定：yymmddHHMMSSZ）
            try:
                if len(expiry_date) == 13 and expiry_date.endswith("Z"):
                    y = 2000 + int(expiry_date[0:2])
                    m = int(expiry_date[2:4])
                    d = int(expiry_date[4:6])
                    expiry_readable = f"{y}-{m:02d}-{d:02d}"
                else:
                    expiry_readable = "Unknown"
            except Exception:
                expiry_readable = "Unknown"

            is_revoked = line.startswith("R")
            is_disabled = client_name in disabled_clients
            # 只有“未被禁用且未被吊销”才判断在线
            is_online = not (is_disabled or is_revoked) and client_name in online_clients

            # 取在线信息（可能不存在）
            oc: OnlineClient = online_clients.get(client_name)  # type: ignore
            clients.append(
                {
                    "name": client_name,
                    "expiry": expiry_readable,
                    "online": is_online,
                    "disabled": is_disabled or is_revoked,
                    "vpn_ip": oc.vpn_ip if oc else "",
                    "real_ip": oc.real_ip if oc else "",
                    "duration": oc.duration_str if oc else "",
                    "connected_since": oc.connected_since if oc else "",
                }
            )
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

def sync_openvpn_clients_to_db():
    """
    同步 OpenVPN 客户端列表到数据库。
    - 如果客户端不存在于 DB → 自动新增
    - 如果存在 → 不修改任何字段
    """
    try:
        ovpn_clients = get_openvpn_clients()  # 使用你现有的完整函数

        changed = False
        for c in ovpn_clients:
            name = c.get("name")
            if not name:
                continue

            # 若数据库中不存在 → 自动新增
            exists = Client.query.filter_by(name=name).first()
            if not exists:
                new_client = Client(name=name, disabled=False)
                db.session.add(new_client)
                changed = True

        if changed:
            db.session.commit()

    except SQLAlchemyError as e:
        db.session.rollback()
        log_message(f"数据库同步失败: {e}")

    except Exception as e:
        log_message(f"sync_openvpn_clients_to_db() 错误: {e}")