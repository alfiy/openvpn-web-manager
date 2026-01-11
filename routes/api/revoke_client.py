# # routes/api/revoke_client.py  v3.0
# import os
# import socket
# import logging
# import subprocess
# import re
# import time
# import json
# from datetime import datetime
# from typing import Tuple, List

# from flask import Blueprint, request, g
# from sqlalchemy import exc
# from routes.helpers import login_required
# from models import Client, db
# from utils.api_response import api_success, api_error

# # ---------- 三方库 ----------
# try:
#     from tenacity import retry, stop_after_attempt, wait_fixed
# except ImportError:  # 降级：无 tenacity 时手动重试
#     retry = lambda **_: (lambda f: f)  # type: ignore


# logger = logging.getLogger(__name__)
# bp = Blueprint("revoke_client", __name__)

# CFG = dict(
#     host=os.getenv("OPENVPN_MGMT_HOST", "127.0.0.1"),
#     port=int(os.getenv("OPENVPN_MGMT_PORT", 7505)),
#     timeout=int(os.getenv("OPENVPN_MGMT_TIMEOUT", 5)),
#     easyrsa="/etc/openvpn/easy-rsa",
#     crl="/etc/openvpn/crl.pem",
#     lock_dir="/run/openvpn",
# )
# os.makedirs(CFG["lock_dir"], mode=0o755, exist_ok=True)  # 1. 目录 755


# # ---------- 工具 ----------
# def sudo_script(script: str, timeout: int = 60) -> Tuple[bool, str]:
#     """执行带有sudo权限的脚本，并添加重试机制"""
#     cmd = ["sudo", "bash", "-c", f"set -euo pipefail; cd {CFG['easyrsa']}; {script}"]
#     try:
#         cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
#         return cp.returncode == 0, cp.stderr or cp.stdout
#     except subprocess.TimeoutExpired:
#         return False, "sudo script timeout"
#     except subprocess.CalledProcessError as e:
#         return False, f"sudo script failed: {e.stderr or e.stdout}"


# def validate_client_name(client: str) -> bool:
#     """验证客户端名称"""
#     return bool(re.fullmatch(r"[a-zA-Z0-9_-]+", client))


# def atomically_filter(path: str, pattern: str) -> bool:
#     """原子删除文件中的指定行"""
#     tmp = f"{path}.{os.getpid()}.tmp"
#     try:
#         with open(path) as fr, open(tmp, "w") as fw:
#             for ln in fr:
#                 if pattern not in ln:
#                     fw.write(ln)
#         ok, _ = sudo_script(f"mv {tmp} {path}")
#         return ok
#     except Exception as e:
#         logger.error(f"Error filtering file {path}: {e}")
#         return False
#     finally:
#         if os.path.exists(tmp):
#             os.remove(tmp)


# # ---------- 踢人 / CRL 重载（tenacity 装饰） ----------
# @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
# def kick_client(client: str) -> Tuple[bool, str]:
#     """踢下线客户端"""
#     try:
#         with socket.create_connection((CFG["host"], CFG["port"]), CFG["timeout"]) as s:
#             s.recv(4096)
#             s.sendall(b"status 2\n")
#             resp = b""
#             while b"END" not in resp:
#                 resp += s.recv(4096)
#             for ln in resp.decode().splitlines():
#                 if ln.startswith("CLIENT_LIST"):
#                     _, name, cid, *_ = ln.split(",")
#                     if name == client:
#                         s.sendall(f"client-kill {cid}\n".encode())
#                         return True, f"CID={cid}"
#         return False, "not online"
#     except Exception as e:
#         logger.error(f"Error kicking client {client}: {e}")
#         return False, str(e)


# @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
# def reload_crl() -> bool:
#     """重载 CRL"""
#     try:
#         with socket.create_connection((CFG["host"], CFG["port"]), CFG["timeout"]) as s:
#             s.recv(4096)
#             s.sendall(b"signal SIGUSR1\n")
#             return b"SUCCESS" in s.recv(1024)
#     except Exception as e:
#         logger.error(f"Error reloading CRL: {e}")
#         return False


# # ---------- 主流程 ----------
# # ---------- 主流程 ----------
# @bp.route("/api/clients/revoke", methods=["POST"])
# @login_required
# def revoke_client():
#     logger.error(">>> ENTER /api/clients/revoke")
#     data = request.get_json() or {}
#     client = (data.get("client_name") or "").strip()
#     logger.error(">>> client=%r", client)  
#     if not client or not validate_client_name(client):
#         logger.error(">>> 400: invalid client_name")
#         return api_error("invalid client_name", 400)
#     if not data.get("confirm"):
#         logger.error(">>> 400: confirm missing")
#         return api_error("confirm=true required", 400)

#     crt_path = f"{CFG['easyrsa']}/pki/issued/{client}.crt"
#     if not os.path.exists(crt_path):
#         return api_error("certificate not found", 404)

#     # 利用自动事务，不再手动 begin
#     try:
#         ok, msg = sudo_script(
#             f"""
# ./easyrsa --batch revoke "{client}"
# ./easyrsa gen-crl
# cp pki/crl.pem {CFG['crl']}
# chmod 644 {CFG['crl']}
# sed -i '/^{client},/d' /etc/openvpn/ipp.txt
# sed -i '/CN={client},/d' pki/index.txt
# sed -i '/^{client} /d' /etc/openvpn/state/online.map
# """
#         )
#         if not ok and "already revoked" not in msg.lower():
#             raise ValueError(msg)
#         Client.query.filter_by(name=client).delete()
#         # 自动事务会在函数返回时提交（无异常）或回滚（有异常）
#     except ValueError as e:
#         db.session.rollback()
#         return api_error(str(e), 500)
#     except exc.SQLAlchemyError as e:
#         db.session.rollback()
#         logger.exception("DB error during revoke: %s", e)
#         return api_error("database error", 500)

#     # 踢人 + 重载（最佳努力）
#     kicked, kick_msg = kick_client(client)
#     crl_ok = reload_crl()

#     logger.info(
#         "revoke_audit %s",
#         json.dumps(
#             {
#                 "user": g.user.name,
#                 "client": client,
#                 "kicked": kicked,
#                 "crl_reloaded": crl_ok,
#                 "ts": datetime.utcnow().isoformat() + "+00:00",
#             }
#         ),
#     )

#     return api_success(
#         f"client {client} revoked",
#         data={"kicked": kicked, "kick_msg": kick_msg, "crl_reloaded": crl_ok},
#     )

# revoke_client_bp = bp


# routes/api/revoke_client.py
import os
import socket
import subprocess
from flask import Blueprint, request
from routes.helpers import login_required
from models import Client, db
from utils.api_response import api_success, api_error

revoke_client_bp = Blueprint('revoke_client', __name__)

# Management interface 配置
MGMT_HOST = '127.0.0.1'
MGMT_PORT = 7505
MGMT_TIMEOUT = 5  # 秒

def disconnect_client_via_mgmt(client_name: str):
    """
    使用 OpenVPN management interface 踢下线指定客户端
    """
    try:
        with socket.create_connection((MGMT_HOST, MGMT_PORT), timeout=MGMT_TIMEOUT) as s:
            # 读取 welcome banner
            s.recv(4096)

            # 发送状态命令获取客户端列表
            s.sendall(b'status 2\n')
            resp = b""
            while True:
                chunk = s.recv(4096)
                resp += chunk
                if b'END' in chunk:
                    break

            # 解析客户端 common name
            lines = resp.decode().splitlines()
            for line in lines:
                # Status 输出格式: CLIENT_LIST,CommonName,RealAddress,VirtualAddress,BytesReceived,...
                if line.startswith("CLIENT_LIST"):
                    parts = line.split(',')
                    if len(parts) >= 2:
                        cn = parts[1].strip()
                        if cn == client_name:
                            # 踢掉客户端
                            cmd = f'kill {client_name}\n'.encode()
                            s.sendall(cmd)
                            s.recv(4096)  # 读取确认
                            return True
        return False
    except Exception as e:
        print(f"[WARN] Management interface disconnect failed: {e}")
        return False


@revoke_client_bp.route('/api/clients/revoke', methods=['POST'])
@login_required
def api_revoke_client():
    """
    精确撤销客户端证书，更新 CRL，清理相关文件，并立即踢下线被撤销客户端
    """
    data = request.get_json()
    if not data:
        return api_error("请求数据格式错误", code=400)

    client_name = (data.get('client_name') or '').strip()
    if not client_name:
        return api_error("客户端名称不能为空", code=400)

    index_path = '/etc/openvpn/easy-rsa/pki/index.txt'
    crt_path = f'/etc/openvpn/easy-rsa/pki/issued/{client_name}.crt'

    try:
        # Step 1: 检查 PKI 和证书文件
        if not os.path.exists(index_path):
            return api_error("OpenVPN PKI 不存在", code=500)
        if not os.path.exists(crt_path):
            return api_error(f"证书文件 {client_name}.crt 不存在，无法撤销", code=500)

        # Step 2: 检查 CN 是否存在于 index.txt
        found = False
        with open(index_path, 'r') as f:
            for line in f:
                if f'CN={client_name},' in line or f'CN={client_name}\n' in line:
                    found = True
                    break
        if not found:
            return api_error(f"客户端 {client_name} 不存在于证书数据库", code=404)

        # Step 3: 撤销证书
        revoke_result = subprocess.run(
            ['sudo', 'bash', '-c', f'cd /etc/openvpn/easy-rsa && ./easyrsa --batch revoke "{client_name}"'],
            capture_output=True, text=True, timeout=60
        )
        if revoke_result.returncode != 0 and 'already revoked' not in revoke_result.stderr:
            return api_error(f"撤销失败: {revoke_result.stderr}", code=500)

        # Step 4: 生成 CRL
        crl_result = subprocess.run(
            ['sudo', 'bash', '-c', 'cd /etc/openvpn/easy-rsa && ./easyrsa gen-crl'],
            capture_output=True, text=True, timeout=60
        )
        if crl_result.returncode != 0:
            return api_error(f"生成 CRL 失败: {crl_result.stderr}", code=500)

        # Step 5: 更新 OpenVPN CRL
        subprocess.run(['sudo', 'rm', '-f', '/etc/openvpn/crl.pem'], check=False)
        subprocess.run(['sudo', 'cp', '/etc/openvpn/easy-rsa/pki/crl.pem', '/etc/openvpn/crl.pem'], check=True)
        subprocess.run(['sudo', 'chmod', '644', '/etc/openvpn/crl.pem'], check=True)

        # Step 6: 清理客户端文件
        cleanup_commands = [
            ['sudo', 'rm', '-f', f'/etc/openvpn/client/{client_name}.ovpn'],
            ['sudo', 'sed', '-i', f'/^{client_name},/d', '/etc/openvpn/ipp.txt'],
            ['sudo', 'rm', '-f', f'/etc/openvpn/ccd/{client_name}'],
            ['sudo', 'rm', '-f', f'/etc/openvpn/easy-rsa/pki/issued/{client_name}.crt'],
            ['sudo', 'rm', '-f', f'/etc/openvpn/easy-rsa/pki/private/{client_name}.key'],
            ['sudo', 'rm', '-f', f'/etc/openvpn/easy-rsa/pki/reqs/{client_name}.req']
        ]
        for cmd in cleanup_commands:
            subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)

        # Step 6.5: 从数据库删除客户端
        try:
            client = Client.query.filter_by(name=client_name).first()
            if client:
                db.session.delete(client)
                db.session.commit()
        except Exception as db_err:
            print(f"[WARN] Failed to delete client {client_name} from DB:", db_err)

        # Step 7: 精确清理 index.txt
        with open(index_path, 'r') as f:
            lines = f.readlines()
        filtered_lines = [line for line in lines if f'CN={client_name},' not in line and f'CN={client_name}\n' not in line]
        with open('/tmp/index.txt', 'w') as f:
            f.writelines(filtered_lines)
        subprocess.run(['sudo', 'mv', '/tmp/index.txt', index_path], check=True)

        # Step 8: 立即踢下线被撤销客户端
        disconnected = disconnect_client_via_mgmt(client_name)
        msg = f"客户端 {client_name} 已撤销，CRL 已更新"
        if disconnected:
            msg += "，并已立即断开在线连接"
        else:
            msg += "。该客户端当前可能未在线"

        return api_success(data={"message": msg})

    except subprocess.TimeoutExpired:
        return api_error("操作超时", code=500)
    except subprocess.CalledProcessError as e:
        return api_error(f"命令执行失败: {e}", code=500)
    except Exception as e:
        return api_error(f"撤销异常: {str(e)}", code=500)
