import os
import socket
import subprocess
import re
import sys
from models import db, Client
from utils.openvpn_ops import set_ccd_disabled
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Dict
import time
from datetime import datetime, timezone
from typing import Dict, NamedTuple, Optional
from sqlalchemy import text
import logging
def log_message(message):
    print(f"[SERVER] {message}", flush=True)
    sys.stdout.flush()

logger = logging.getLogger(__name__)

class OnlineClient(NamedTuple):

    vpn_ip: str
    real_ip: str
    duration_str: str          # 人类可读
    duration_sec: int          # 秒数,方便排序
    connected_since: str       # 原始字符串


# 缓存 10 s,避免并发刷爆 IO
_last_check: float = 0
_cache: Dict[str, OnlineClient] = {}
KICK_FILE = os.environ.get('VPNWM_KICK_FILE', '/opt/vpnwm/data/kicked-sessions.tsv')
KICK_HOLD_SEC = 180


def mark_client_kicked(client_name: str) -> None:
    """记录踢人时间，避免 status.log / 管理口缓存把旧会话立刻标回在线。"""
    global _last_check, _cache
    name = (client_name or '').strip().lower()
    if not name:
        return
    now = int(time.time())
    rows = {}
    try:
        with open(KICK_FILE, 'r', encoding='utf-8') as fh:
            for line in fh:
                parts = line.strip().split()
                if len(parts) >= 2:
                    rows[parts[0]] = parts[1]
    except OSError:
        pass
    rows[name] = str(now)
    try:
        os.makedirs(os.path.dirname(KICK_FILE), exist_ok=True)
        with open(KICK_FILE, 'w', encoding='utf-8') as fh:
            for key, ts in rows.items():
                fh.write(f'{key} {ts}\n')
    except OSError as exc:
        logger.warning('write kick file failed: %s', exc)
    _cache = {}
    _last_check = 0


def _kick_ts(client_name: str) -> float:
    name = (client_name or '').strip().lower()
    try:
        with open(KICK_FILE, 'r', encoding='utf-8') as fh:
            for line in fh:
                parts = line.strip().split()
                if len(parts) >= 2 and parts[0] == name:
                    return float(parts[1])
    except OSError:
        return 0
    return 0


def _session_started_after(info: OnlineClient, kick_ts: float) -> bool:
    raw = (info.connected_since or '').strip()
    if not raw or kick_ts <= 0:
        return False
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
        try:
            started = datetime.strptime(raw, fmt)
            return started.timestamp() > kick_ts + 1
        except ValueError:
            continue
    return False


def _apply_kick_hold(clients: Dict[str, OnlineClient]) -> Dict[str, OnlineClient]:
    now = time.time()
    kept = {}
    for cn, info in clients.items():
        kicked_at = _kick_ts(cn)
        if kicked_at and now - kicked_at < KICK_HOLD_SEC:
            if _session_started_after(info, kicked_at):
                kept[cn] = info
            continue
        kept[cn] = info
    return kept


def check_openvpn_status():
    """
    检查 OpenVPN 服务状态并返回 'running', 'installed', 或 'not_installed'。
    优先用当前用户执行 systemctl is-active（无需 sudo）；失败再尝试 sudo -n。
    
    返回值:
        - 'running': OpenVPN 服务正在运行
        - 'installed': OpenVPN 已安装但未运行
        - 'not_installed': OpenVPN 未安装
    
    注意: 此函数不会抛出异常,所有错误都会被捕获并返回 'not_installed'
    """
    service_name = 'openvpn@server.service'
    config_path = '/etc/openvpn/server.conf'

    try:
        # --- 1. 检查运行状态:使用 systemctl is-active 的返回码 ---
        # logger.debug(f"检查服务运行状态: {service_name}")
        # 普通用户即可查询 systemd 状态，避免 sudoers 未覆盖 --quiet 时误判为未运行
        result_active = subprocess.run(
            ['systemctl', 'is-active', service_name],
            check=False,
            timeout=5,
            capture_output=True,
            text=True,
        )
        if result_active.returncode == 0 and (result_active.stdout or '').strip() == 'active':
            return 'running'

        result_sudo = subprocess.run(
            ['sudo', '-n', 'systemctl', 'is-active', service_name],
            check=False,
            timeout=5,
            capture_output=True,
            text=True,
        )
        if result_sudo.returncode == 0 and (result_sudo.stdout or '').strip() == 'active':
            return 'running'
        
        logger.debug(f"服务未运行,返回码: {result_active.returncode}")

        # --- 2. 检查安装状态:直接检查配置文件是否存在 ---
        logger.debug(f"检查配置文件: {config_path}")
        
        # 方法1: 使用 Python 原生方法 (推荐,不需要 sudo)
        if os.path.exists(config_path) and os.path.isfile(config_path):
            logger.info("✅ OpenVPN 已安装但未运行")
            return 'installed'
        
        # 方法2: 如果文件权限问题导致 os.path.exists 失败,尝试使用 sudo
        logger.debug("使用 sudo 检查配置文件")
        result_config = subprocess.run(
            ['sudo', 'test', '-e', config_path],
            check=False,
            timeout=5,
            capture_output=True
        )
        
        if result_config.returncode == 0:
            logger.info("✅ OpenVPN 已安装但未运行 (通过 sudo 检测)")
            return 'installed'

        # --- 3. 额外检查: 检查 openvpn 可执行文件 ---
        logger.debug("检查 openvpn 可执行文件")
        try:
            result_which = subprocess.run(
                ['which', 'openvpn'],
                capture_output=True,
                text=True,
                timeout=5,
                check=False
            )
            
            if result_which.returncode == 0:
                openvpn_path = result_which.stdout.strip()
                logger.info(f"✅ 找到 openvpn 可执行文件: {openvpn_path},但配置文件缺失")
                # 即使找到可执行文件,如果配置文件不存在,也视为未安装
                return 'not_installed'
        except Exception as e:
            logger.debug(f"检查可执行文件失败: {e}")

        # --- 4. 未找到任何状态 ---
        logger.info("❌ OpenVPN 未安装")
        return 'not_installed'
    
    except subprocess.TimeoutExpired as e:
        # 命令执行超时
        logger.error(f"❌ 检查 OpenVPN 状态超时: {e}")
        log_message(f"check_openvpn_status() 超时: {e}")
        return 'not_installed'  # 超时时假设未安装
    
    except FileNotFoundError as e:
        # 捕获当 'sudo' 或 'systemctl' 命令本身不存在时的情况
        logger.error(f"❌ 必需的命令不存在: {e}")
        log_message(f"check_openvpn_status() 命令未找到: {e}")
        return 'not_installed'
    
    except PermissionError as e:
        # 权限不足
        logger.error(f"❌ 权限不足: {e}")
        log_message(f"check_openvpn_status() 权限错误: {e}")
        return 'not_installed'
    
    except Exception as e:
        # 捕获所有其他异常
        logger.error(f"❌ 检查 OpenVPN 状态时发生未知错误: {e}", exc_info=True)
        log_message(f"check_openvpn_status() 未知错误: {e}")
        return 'not_installed'  # 出错时假设未安装


def _parse_connected_since(text: str) -> Optional[datetime]:
    # 1. 你的 status-version 1/2 新格式 → 先当本地时间解析
    try:
        naive = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        # 把本地时间转 UTC(系统默认时区)
        return naive.astimezone(timezone.utc)
    except ValueError:
        pass
    # 2. 旧英文格式
    try:
        naive = datetime.strptime(text, "%a %b %d %H:%M:%S %Y")
        return naive.astimezone(timezone.utc)
    except ValueError:
        pass
    # 3. 时间戳
    try:
        return datetime.fromtimestamp(float(text), tz=timezone.utc)
    except (ValueError, OSError):
        return None

def _human_duration(seconds: int) -> str:
    """>=1 h 输出 1h23m;<1 h 输出 5m12s;<1 min 输出 45s"""
    if seconds < 0:
        return "00:00"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def _mgmt_recv_until_end(sock: socket.socket) -> bytes:
    chunks = []
    while True:
        piece = sock.recv(8192)
        if not piece:
            break
        chunks.append(piece)
        blob = b''.join(chunks)
        if b'\nEND' in blob or blob.rstrip().endswith(b'END'):
            break
    return b''.join(chunks)


def _mgmt_query_status() -> Optional[str]:
    host = os.environ.get('OPENVPN_MGMT_HOST', '127.0.0.1')
    port = int(os.environ.get('OPENVPN_MGMT_PORT', '7505'))
    password = os.environ.get('OPENVPN_MGMT_PASSWORD')
    try:
        with socket.create_connection((host, port), timeout=3) as sock:
            sock.settimeout(4)
            banner = sock.recv(4096)
            if banner and b'PASSWORD' in banner.upper():
                sock.sendall(((password or '') + '\r\n').encode())
                sock.recv(4096)
            sock.sendall(b'status 2\r\n')
            raw = _mgmt_recv_until_end(sock)
            text = raw.decode('utf-8', errors='ignore')
            if 'CLIENT_LIST,' not in text and 'OpenVPN CLIENT LIST' not in text:
                sock.sendall(b'status\r\n')
                raw2 = _mgmt_recv_until_end(sock)
                extra = raw2.decode('utf-8', errors='ignore')
                text = text + '\n' + extra
            try:
                sock.sendall(b'quit\r\n')
            except OSError:
                pass
            return text
    except OSError as exc:
        logger.warning('openvpn management %s:%s 不可用: %s', host, port, exc)
        return None


def _parse_mgmt_status(text: str) -> Dict[str, OnlineClient]:
    clients: Dict[str, OnlineClient] = {}
    if not text:
        return clients
    routes = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('ROUTING_TABLE,'):
            parts = line.split(',')
            if len(parts) >= 3 and parts[2] not in ('Common Name',):
                routes[parts[2].strip()] = parts[1].strip()
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith('CLIENT_LIST,'):
            continue
        parts = line.split(',')
        if len(parts) < 5:
            continue
        cn = parts[1].strip()
        if not cn or cn in ('UNDEF', 'Common Name'):
            continue
        real_addr = parts[2].strip() if len(parts) > 2 else ''
        vpn_ip = parts[3].strip() if len(parts) > 3 else ''
        conn_since = parts[7].strip() if len(parts) > 7 else (parts[4].strip() if len(parts) > 4 else '')
        conn_dt = _parse_connected_since(conn_since)
        if conn_dt is None and len(parts) > 8:
            try:
                conn_dt = datetime.fromtimestamp(float(parts[8]), tz=timezone.utc)
                conn_since = parts[8]
            except (ValueError, OSError):
                conn_dt = None
        duration_sec = 0
        if conn_dt is not None:
            duration_sec = max(0, int((datetime.now(timezone.utc) - conn_dt).total_seconds()))
        real_ip = real_addr.split(':')[0] if ':' in real_addr else real_addr
        clients[cn] = OnlineClient(
            vpn_ip=vpn_ip or routes.get(cn, ''),
            real_ip=real_ip,
            duration_str=_human_duration(duration_sec),
            duration_sec=duration_sec,
            connected_since=conn_since,
        )
    return clients


def _is_vpn_ip(ip: str) -> bool:
    ip = (ip or '').strip()
    if not ip:
        return False
    return ip.startswith('10.') or ip.startswith('172.') or ip.startswith('192.168.')


def _ping_ok(ip: str) -> bool:
    if not _is_vpn_ip(ip):
        return False
    try:
        result = subprocess.run(
            ['ping', '-c', '1', '-W', '1', ip],
            capture_output=True,
            timeout=2,
        )
        return result.returncode == 0
    except Exception:
        return False


def _filter_by_ping(clients: Dict[str, OnlineClient]) -> Dict[str, OnlineClient]:
    """管理口/status 可能仍列出已断开会话；VPN 虚拟 IP ping 不通则视为离线。"""
    if not clients:
        return clients
    targets = {cn: info for cn, info in clients.items() if _is_vpn_ip(info.vpn_ip)}
    if not targets:
        return clients
    reachable = set()
    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=min(16, len(targets))) as pool:
            futs = {pool.submit(_ping_ok, info.vpn_ip): cn for cn, info in targets.items()}
            for fut in as_completed(futs):
                cn = futs[fut]
                try:
                    if fut.result():
                        reachable.add(cn)
                except Exception:
                    pass
    except Exception:
        for cn, info in targets.items():
            if _ping_ok(info.vpn_ip):
                reachable.add(cn)
    kept = {}
    for cn, info in clients.items():
        if cn in targets and cn not in reachable:
            continue
        kept[cn] = info
    return kept


def get_online_clients(status_file: str = None, cache_ttl: int = 10) -> Dict[str, OnlineClient]:
    global _last_check, _cache
    now = time.time()
    if now - _last_check < cache_ttl and _cache:
        return _cache

    mgmt_text = _mgmt_query_status()
    if mgmt_text is not None:
        clients = _filter_by_ping(_apply_kick_hold(_parse_mgmt_status(mgmt_text)))
        _last_check = now
        _cache = clients
        return clients


    candidates = []
    if status_file:
        candidates.append(status_file)
    candidates.extend([
        "/var/log/openvpn/status.log",
        "/run/openvpn/server.status",
        "/etc/openvpn/openvpn-status.log",
    ])

    data = ""
    last_error = None
    seen = set()
    for path in candidates:
        if not path or path in seen:
            continue
        seen.add(path)
        try:
            with open(path, "rb") as f:
                data = f.read().decode("utf-8", errors="ignore")
            if data.strip():
                break
        except OSError as e:
            last_error = e
            try:
                result = subprocess.run(
                    ["sudo", "-n", "cat", path],
                    capture_output=True, timeout=5
                )
                if result.returncode == 0 and result.stdout:
                    data = result.stdout.decode("utf-8", errors="ignore")
                    break
            except Exception as exc:
                last_error = exc
    if not data.strip():
        import logging
        logging.getLogger(__name__).warning("read openvpn status failed: %s", last_error)
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

        # log_message(f"DEBUG  cn={cn}  conn_since={conn_since}")

        conn_dt = _parse_connected_since(conn_since)

        if conn_dt is None:
            log_message(f"DEBUG  → conn_dt is None, skip")
            continue
        duration_sec = int((datetime.now(timezone.utc) - conn_dt).total_seconds())
        # log_message(f"DEBUG  → conn_dt={conn_dt}  duration_sec={duration_sec}")

        real_ip = real_addr.split(":")[0] if ":" in real_addr else real_addr

        clients[cn] = OnlineClient(
            vpn_ip="",                         # 稍后二次扫描补全
            real_ip=real_ip,
            duration_str=_human_duration(duration_sec),
            duration_sec=duration_sec,
            connected_since=conn_since
        )

    # 二次扫描:补 vpn_ip(ROUTING TABLE 段)
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

    clients = _filter_by_ping(_apply_kick_hold(clients))
    _last_check = now
    _cache = clients
    return clients

def get_openvpn_clients() -> List[Dict[str, str]]:
    clients: List[Dict[str, str]] = []
    # ① 拿在线列表(带缓存,1 s 内不重复读盘)
    online_clients: Dict[str, OnlineClient] = get_online_clients(cache_ttl=1)

    # ② 被禁用(ccd 目录存在同名文件)或被吊销的客户端
    disabled_clients: set[str] = set()
    disabled_dir = "/etc/openvpn/ccd"
    if os.path.isdir(disabled_dir):
        try:
            disabled_clients = {f.lower() for f in os.listdir(disabled_dir)
                               if os.path.isfile(os.path.join(disabled_dir, f))}
        except Exception as e:
            log_message(f"枚举禁用客户端失败:{e}")

    # ③ 读取 easy-rsa 索引
    try:
        result = subprocess.run(
            ["sudo", "cat", "/etc/openvpn/easy-rsa/pki/index.txt"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            log_message(f"openvpn-utils 无法读取 index.txt:{result.stderr}")
            return clients

        for line in result.stdout.splitlines():
            line = line.strip()
            # 已吊销(R)不进入客户端列表，避免同步回卡片
            if not line.startswith("V"):
                continue
            parts = line.split("\t")
            if len(parts) < 6:
                continue

            expiry_date = parts[1]
            cn_field = parts[5]
            match = re.search(r"CN=([^/]+)", cn_field)
            if not match:
                continue
            client_name = match.group(1).lower()
            if client_name == "server":
                continue

            # 过期日期解析(easy-rsa 3.x 输出格式固定:yymmddHHMMSSZ)
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

            is_disabled = client_name in disabled_clients
            
            # 检查逻辑到期时间
            is_logically_expired = False
            try:
                db_client = Client.query.filter_by(name=client_name).first()
                if db_client and db_client.logical_expiry:
                    if datetime.now() > db_client.logical_expiry:
                        is_logically_expired = True
                        # 自动禁用逻辑过期的客户端
                        if not db_client.disabled:
                            db_client.disabled = True
                            db.session.commit()
                            # 创建 CCD 禁用文件
                            try:
                                ok, err = set_ccd_disabled(client_name, True)
                                if not ok:
                                    log_message(f"自动禁用客户端 {client_name} 失败: {err}")
                            except Exception as e:
                                log_message(f"自动禁用客户端 {client_name} 失败: {e}")
            except Exception as e:
                log_message(f"检查逻辑到期时间失败: {e}")
            
            # 只有"未被禁用且未被吊销且未逻辑过期"才判断在线
            is_online = not (is_disabled or is_logically_expired) and client_name in online_clients

            # 取在线信息(可能不存在)
            oc: OnlineClient = online_clients.get(client_name)  # type: ignore
            clients.append(
                {
                    "name": client_name,
                    "expiry": expiry_readable,
                    "online": is_online,
                    "disabled": is_disabled or is_logically_expired,
                    "vpn_ip": oc.vpn_ip if oc else "",
                    "real_ip": oc.real_ip if oc else "",
                    "duration": oc.duration_str if oc else "",
                    "connected_since": oc.connected_since if oc else "",
                }
            )

        # for c in clients:          # 返回前加一段日志
        #     log_message(f"DEBUG final  name={c['name']}  online={c['online']}  duration={c['duration']}")
            
    except Exception as e:
        log_message(f"读取 index.txt 异常:{e}")

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
        ovpn_clients = get_openvpn_clients()
        valid_names = {(c.get("name") or "").lower() for c in ovpn_clients if c.get("name")}

        result = subprocess.run(
            ["sudo", "-n", "cat", "/etc/openvpn/easy-rsa/pki/index.txt"],
            capture_output=True, text=True, timeout=5
        )
        revoked = set()
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if not line.startswith("R"):
                    continue
                match = re.search(r"CN=([^/]+)", line)
                if match and match.group(1).lower() != "server":
                    revoked.add(match.group(1).lower())

        changed = False
        if revoked:
            for row in Client.query.all():
                if row.name.lower() in revoked and row.name.lower() not in valid_names:
                    db.session.delete(row)
                    changed = True

        for c in ovpn_clients:
            name = c.get("name")
            if not name:
                continue

            # 若数据库中不存在 → 自动新增
            if c.get("disabled") and not Client.query.filter_by(name=name).first():
                continue
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

def sync_online_state_to_db():
    try:
        online = get_online_clients()  # {cn: OnlineClient}

        # STEP1: 全部先标记为离线
        db.session.execute(text("""
            UPDATE clients 
            SET 
                online = 0, 
                vpn_ip = NULL, 
                real_ip = NULL,
                duration = NULL
        """))

        # STEP2: 将在线用户写入数据库
        for name, info in online.items():
            db.session.execute(text("""
                UPDATE clients
                SET 
                    online = 1,
                    vpn_ip = :vpn_ip,
                    real_ip = :real_ip,
                    duration = :duration
                WHERE lower(name) = lower(:name)
            """), {
                "name": name,
                "vpn_ip": info.vpn_ip,
                "real_ip": info.real_ip,
                "duration": info.duration_str  # 你已有字段 duration
            })

        db.session.commit()
        try:
            from utils.openvpn_ops import cleanup_stale_first_wins_locks
            cleanup_stale_first_wins_locks(online.keys())
        except Exception as exc:
            log_message(f"清理 first-wins 残留锁失败: {exc}")

    except SQLAlchemyError as e:
        db.session.rollback()
        log_message(f"sync_online_state_to_db() 数据库错误: {e}")

    except Exception as e:
        log_message(f"sync_online_state_to_db() 未知错误: {e}")