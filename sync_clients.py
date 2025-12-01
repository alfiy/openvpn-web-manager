# #!/usr/bin/env python3
# import os
# import sys

# PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
# sys.path.insert(0, PROJECT_DIR)

# from models import db, Client
# from utils.openvpn_utils import get_openvpn_clients, log_message
# from sqlalchemy import create_engine
# from sqlalchemy.orm import sessionmaker
# from sqlalchemy.exc import SQLAlchemyError

# # -----------------------------
# # 数据库 URL（与 Flask 配置保持一致）
# # -----------------------------
# # 生产环境数据目录
# DATA_DIR = "/var/lib/vpnwm"
# os.makedirs(DATA_DIR, exist_ok=True)

# # SQLite 单文件数据库/var/lib/vpnwm/vpn_users.db
# DATABASE_URL = 'sqlite:///' + os.path.join(DATA_DIR, 'vpn_users.db')

# # 初始化 SQLAlchemy engine 和 session
# engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
# Session = sessionmaker(bind=engine)
# session = Session()

# def sync_clients_to_db():
#     try:
#         clients = get_openvpn_clients()
#         changed_count = 0
#         online_map = {c['name']: c for c in clients if c['online']}

#         # STEP1: 新增客户端
#         for c in clients:
#             name = c['name']
#             exists = session.query(Client).filter_by(name=name).first()
#             if not exists:
#                 session.add(Client(
#                     name=name,
#                     disabled=c['disabled'],
#                     vpn_ip=c['vpn_ip'],
#                     real_ip=c['real_ip'],
#                     duration=c['duration']
#                 ))
#                 changed_count += 1
#         if changed_count:
#             session.commit()
#             log_message(f"新增 {changed_count} 个客户端到数据库")

#         # STEP2: 全部标记离线
#         session.query(Client).update({
#             Client.online: False,
#             Client.vpn_ip: None,
#             Client.real_ip: None,
#             Client.duration: None
#         })
#         session.commit()

#         # STEP3: 更新在线状态
#         for name, info in online_map.items():
#             session.query(Client).filter_by(name=name).update({
#                 Client.online: True,
#                 Client.vpn_ip: info['vpn_ip'],
#                 Client.real_ip: info['real_ip'],
#                 Client.duration: info['duration']
#             })
#         session.commit()
#         log_message("同步在线状态完成")

#     except SQLAlchemyError as e:
#         session.rollback()
#         log_message(f"数据库同步失败: {e}")
#     except Exception as e:
#         log_message(f"未知错误: {e}")


# if __name__ == "__main__":
#     sync_clients_to_db()


#!/usr/bin/env python3
import os
import sys
import re
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import SQLAlchemyError

# ------------------- 配置 -------------------
DATA_DIR = "/opt/vpnwm/data"
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "vpn_users.db")

OPENVPN_STATUS_FILE = "/var/log/openvpn/status.log"
CCD_DIR = "/etc/openvpn/ccd"
INDEX_TXT = "/etc/openvpn/easy-rsa/pki/index.txt"

SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

# ------------------- 数据库模型（与 models.py 保持一致）-------------------
Base = declarative_base()

class Client(Base):
    __tablename__ = 'clients'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    expiry = Column(DateTime, nullable=True)  # 修改为 DateTime 类型，与 models.py 一致
    online = Column(Boolean, default=False)
    disabled = Column(Boolean, default=False)
    vpn_ip = Column(String(15), nullable=True)
    real_ip = Column(String(15), nullable=True)
    duration = Column(String(50), nullable=True)
    # 注意：models.py 中没有 connected_since 字段，所以我们不在这里添加

# ------------------- 数据库初始化 -------------------
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

# 不要创建表，因为表已经由 Flask 应用创建
# Base.metadata.create_all(engine)

# ------------------- 工具函数 -------------------
def log_message(msg):
    print(f"[SYNC] {msg}", flush=True)

def parse_connected_since(text):
    try:
        naive = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        return naive.astimezone(timezone.utc)
    except:
        return None

def parse_expiry_date(expiry_raw):
    """解析过期日期字符串为 datetime 对象"""
    if len(expiry_raw) == 13 and expiry_raw.endswith("Z"):
        try:
            y = 2000 + int(expiry_raw[:2])
            m = int(expiry_raw[2:4])
            d = int(expiry_raw[4:6])
            return datetime(y, m, d)
        except:
            return None
    return None

def human_duration(seconds):
    if seconds < 0:
        return "00:00"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h: return f"{h}h{m:02d}m"
    if m: return f"{m}m{s:02d}s"
    return f"{s}s"

# ------------------- OpenVPN 数据解析 -------------------
def get_online_clients(status_file=OPENVPN_STATUS_FILE):
    clients = {}
    try:
        with open(status_file, "r", encoding="utf-8", errors="ignore") as f:
            data = f.read()
    except Exception as e:
        log_message(f"无法读取 status.log: {e}")
        return clients

    in_client_list = False
    for line in data.splitlines():
        line = line.strip()
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
        cn, real_addr, _, _, conn_since = parts[:5]
        if cn == "UNDEF":
            continue
        dt = parse_connected_since(conn_since)
        if not dt:
            continue
        duration_sec = int((datetime.now(timezone.utc) - dt).total_seconds())
        clients[cn.lower()] = {
            "real_ip": real_addr.split(":")[0],
            "duration": human_duration(duration_sec),
            "connected_since": conn_since,
            "vpn_ip": ""
        }

    routing = False
    for line in data.splitlines():
        line = line.strip()
        if line.startswith("ROUTING TABLE"):
            routing = True
            continue
        if line.startswith("GLOBAL STATS"):
            routing = False
            continue
        if not routing or not line.count(","):
            continue
        vpn_ip, cn = line.split(",")[:2]
        cn = cn.lower()
        if cn in clients:
            clients[cn]["vpn_ip"] = vpn_ip

    return clients

def get_openvpn_clients():
    clients_list = []
    online_clients = get_online_clients()
    disabled_clients = set()
    if os.path.isdir(CCD_DIR):
        try:
            disabled_clients = {f.lower() for f in os.listdir(CCD_DIR)}
        except:
            pass

    try:
        with open(INDEX_TXT, "r") as f:
            lines = f.readlines()
    except Exception as e:
        log_message(f"无法读取 index.txt: {e}")
        lines = []

    for line in lines:
        line = line.strip()
        if not (line.startswith("V") or line.startswith("R")):
            continue
        parts = line.split("\t")
        if len(parts) < 6:
            continue
        expiry_raw = parts[1]
        cn_field = parts[5]
        match = re.search(r"CN=([^/]+)", cn_field)
        if not match:
            continue
        name = match.group(1).lower()
        if name == "server":
            continue

        # 解析过期日期为 datetime 对象
        expiry_date = parse_expiry_date(expiry_raw)

        is_revoked = line.startswith("R")
        is_disabled = name in disabled_clients or is_revoked
        is_online = not is_disabled and name in online_clients

        oc = online_clients.get(name)
        clients_list.append({
            "name": name,
            "expiry": expiry_date,  # 现在是 datetime 对象
            "online": is_online,
            "disabled": is_disabled,
            "vpn_ip": oc["vpn_ip"] if oc else "",
            "real_ip": oc["real_ip"] if oc else "",
            "duration": oc["duration"] if oc else ""
            # 移除 connected_since，因为 models.py 中没有这个字段
        })
    return clients_list

# ------------------- 同步逻辑 -------------------
def sync_clients_to_db():
    session = SessionLocal()
    try:
        clients = get_openvpn_clients()
        if not clients:
            log_message("没有客户端数据可同步")
            return

        # 使用一次事务处理新增和更新
        for c in clients:
            db_c = session.query(Client).filter_by(name=c['name']).first()
            if not db_c:
                db_c = Client(name=c['name'])
                session.add(db_c)
            
            # 更新字段，确保类型匹配
            db_c.expiry = c['expiry']  # datetime 对象
            db_c.disabled = c['disabled']
            db_c.online = c['online']
            db_c.vpn_ip = c['vpn_ip']
            db_c.real_ip = c['real_ip']
            db_c.duration = c['duration']
            # 不设置 connected_since，因为 models.py 中没有这个字段

        session.commit()
        log_message(f"同步完成 ✅ 客户端总数: {len(clients)}")

    except SQLAlchemyError as e:
        session.rollback()
        log_message(f"数据库错误: {e}")
    except Exception as e:
        session.rollback()
        log_message(f"未知错误: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    sync_clients_to_db()
