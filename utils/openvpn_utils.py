import os
import subprocess
import re
import sys
from models import db, Client
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


def check_openvpn_status():
    """
    检查 OpenVPN 服务状态并返回 'running', 'installed', 或 'not_installed'。
    此函数会使用 sudo 确保在普通用户环境下也能正常工作。
    
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
        result_active = subprocess.run(
            ['sudo', 'systemctl', 'is-active', '--quiet', service_name],
            check=False,  # 不抛出异常
            timeout=5,    # 添加超时保护
            capture_output=True
        )
        
        if result_active.returncode == 0:
            # logger.info("✅ OpenVPN 正在运行")
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


def get_online_clients(status_file: str = None, cache_ttl: int = 10) -> Dict[str, OnlineClient]:
    global _last_check, _cache
    now = time.time()
    if now - _last_check < cache_ttl and _cache:
        return _cache

    if status_file is None:
        status_file = "/var/log/openvpn/status.log" 

    try:
        with open(status_file, "rb") as f:        # 二进制读,防止中文 locale 异常
            data = f.read().decode("utf-8", errors="ignore")
    except OSError as e:
        # 权限、磁盘故障等,记录日志后返回空
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

        log_message(f"DEBUG  cn={cn}  conn_since={conn_since}")

        conn_dt = _parse_connected_since(conn_since)

        if conn_dt is None:
            log_message(f"DEBUG  → conn_dt is None, skip")
            continue
        duration_sec = int((datetime.now(timezone.utc) - conn_dt).total_seconds())
        log_message(f"DEBUG  → conn_dt={conn_dt}  duration_sec={duration_sec}")

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

            is_revoked = line.startswith("R")
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
                            disable_file_path = os.path.join(disabled_dir, client_name)
                            try:
                                os.makedirs(disabled_dir, exist_ok=True)
                                subprocess.run(['sudo', 'sh', '-c', f'echo "disable" > {disable_file_path}'],
                                             capture_output=True, text=True, check=True)
                            except Exception as e:
                                log_message(f"自动禁用客户端 {client_name} 失败: {e}")
            except Exception as e:
                log_message(f"检查逻辑到期时间失败: {e}")
            
            # 只有"未被禁用且未被吊销且未逻辑过期"才判断在线
            is_online = not (is_disabled or is_revoked or is_logically_expired) and client_name in online_clients

            # 取在线信息(可能不存在)
            oc: OnlineClient = online_clients.get(client_name)  # type: ignore
            clients.append(
                {
                    "name": client_name,
                    "expiry": expiry_readable,
                    "online": is_online,
                    "disabled": is_disabled or is_revoked or is_logically_expired,
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
                WHERE name = :name
            """), {
                "name": name,
                "vpn_ip": info.vpn_ip,
                "real_ip": info.real_ip,
                "duration": info.duration_str  # 你已有字段 duration
            })

        db.session.commit()

    except SQLAlchemyError as e:
        db.session.rollback()
        log_message(f"sync_online_state_to_db() 数据库错误: {e}")

    except Exception as e:
        log_message(f"sync_online_state_to_db() 未知错误: {e}")