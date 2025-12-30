# routes/api/clients.py
import os
import subprocess
import socket
import time
from flask import jsonify, request
from flask_login import login_required
from . import api_bp
from utils.api_response import api_success, api_error
from utils.openvpn_utils import log_message
from models import Client, db
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import asc

PER_PAGE = 10

def client_to_dict(c):
    return {
        "id": c.id,
        "name": c.name,
        "expiry": c.expiry.isoformat() if c.expiry else None,
        "logical_expiry": c.logical_expiry.isoformat() if c.logical_expiry else None,
        "online": bool(c.online),
        "disabled": bool(c.disabled),
        "vpn_ip": c.vpn_ip,
        "real_ip": c.real_ip,
        "duration": c.duration
    }

# ----------------- 查询分页 -----------------
@api_bp.route('/clients', methods=['GET'])
@login_required
def api_clients():
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '', type=str).strip().lower()

    query = Client.query.order_by(asc(Client.name))
    if q:
        query = query.filter(Client.name.ilike(f"%{q}%"))

    total = query.count()
    total_pages = (total + PER_PAGE - 1) // PER_PAGE
    clients = query.offset((page-1)*PER_PAGE).limit(PER_PAGE).all()

    data = {
        "clients": [client_to_dict(c) for c in clients],
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "q": q
    }
    return api_success(data)


RECV_CHUNK = 4096

def recv_all_until_end(sock, timeout=3.0):
    sock.settimeout(timeout)
    data = b''
    while True:
        try:
            chunk = sock.recv(RECV_CHUNK)
            if not chunk:
                break
            data += chunk
            if b'\nEND' in data or data.endswith(b'END') or b'\r\nEND' in data:
                break
        except socket.timeout:
            break
    return data.decode('utf-8', errors='ignore')

def parse_status_for_cids(status_text, common_name):
    lines = status_text.splitlines()
    header_cols = None
    client_lines = []
    for ln in lines:
        if ln.startswith('HEADER,CLIENT_LIST'):
            parts = ln.split(',')
            header_cols = parts[2:]
            continue
        if ln.startswith('CLIENT_LIST,'):
            client_lines.append(ln)

    if header_cols:
        low_headers = [h.strip().lower() for h in header_cols]
        try:
            idx_cn = low_headers.index('common name')
        except ValueError:
            idx_cn = 0
        cid_idx = low_headers.index('client id') if 'client id' in low_headers else None
        cids = []
        for cl in client_lines:
            parts = cl.split(',')[1:]
            name = parts[idx_cn] if idx_cn < len(parts) else ''
            cid = parts[cid_idx] if cid_idx is not None and cid_idx < len(parts) else None
            if name == common_name:
                if cid:
                    cids.append(cid)
                else:
                    return []
        return cids if cids else None
    return None

def send_and_recv(sock, cmd, wait=0.05, recv_timeout=2.0):
    sock.sendall((cmd + "\n").encode('utf-8'))
    time.sleep(wait)
    return recv_all_until_end(sock, timeout=recv_timeout)

def openvpn_client_kill(host, port, client_name, mgmt_password=None):
    try:
        with socket.create_connection((host, port), timeout=5) as s:
            banner = s.recv(RECV_CHUNK).decode('utf-8', errors='ignore')
            if mgmt_password:
                s.sendall(f"password {mgmt_password}\n".encode())
                time.sleep(0.05)
                _ = recv_all_until_end(s, timeout=1.0)

            raw_status = send_and_recv(s, "status 2", wait=0.05, recv_timeout=2.0)
            parse_res = parse_status_for_cids(raw_status, client_name)

            if parse_res is None:
                resp = send_and_recv(s, f"kill {client_name}", wait=0.05, recv_timeout=2.0)
                return True, f"未在状态中找到客户端 '{client_name}'。尝试使用 kill {client_name}。响应: {resp.strip()}"
            elif isinstance(parse_res, list) and len(parse_res) == 0:
                resp = send_and_recv(s, f"kill {client_name}", wait=0.05, recv_timeout=2.0)
                return True, f"找到了 '{client_name}' 但未找到客户端 ID。尝试使用 kill {client_name}。响应: {resp.strip()}"
            else:
                cids = parse_res
                results = []
                for cid in cids:
                    resp = send_and_recv(s, f"client-kill {cid}", wait=0.05, recv_timeout=2.0)
                    results.append(f"client-kill {cid} 响应: {resp.strip()}")
                return True, "成功踢出客户端。\n" + "\n".join(results)
    except socket.error as e:
        return False, f"无法连接到 OpenVPN 管理接口: {e}"
    except Exception as e:
        return False, f"踢出客户端时发生错误: {e}"


# ---------------- API 禁用客户端接口 ----------------
@api_bp.route('/clients/disable', methods=['POST'])
@login_required
def api_disable_client():
    """
    禁用客户端(创建 ccd disable 文件 + 断开客户端 + 数据库标志位)
    """
    data = request.get_json()
    client_name = data.get('client_name', '').strip()
    if not client_name:
        return api_error("缺少 client_name", 400)

    # ---------- 1. 创建禁用文件 ----------
    try:
        ccd_dir = '/etc/openvpn/ccd'
        disable_file_path = os.path.join(ccd_dir, client_name)
        os.makedirs(ccd_dir, exist_ok=True)

        cmd = ['sudo', 'sh', '-c', f'echo "disable" > {disable_file_path}']
        log_message(f"执行命令以禁用客户端:{' '.join(cmd)}")
        subprocess.run(cmd, capture_output=True, text=True, check=True)

        os.system(f"sudo chown root:root {disable_file_path}")
        os.system(f"sudo chmod 644 {disable_file_path}")
        log_message(f"禁用文件创建成功:{disable_file_path}")

    except subprocess.CalledProcessError as e:
        return api_error(f"创建禁用文件失败:{e.stderr}")
    except Exception as e:
        return api_error(f"创建禁用文件异常:{e}")

    # ---------- 2. 调用管理接口踢出客户端 ----------
    host = os.environ.get('OPENVPN_MGMT_HOST', '127.0.0.1')
    port = int(os.environ.get('OPENVPN_MGMT_PORT', 7505))
    password = os.environ.get('OPENVPN_MGMT_PASSWORD')

    success, kill_msg = openvpn_client_kill(host, port, client_name, mgmt_password=password)

    # ---------- 3. 更新数据库 ----------
    try:
        client = Client.query.filter_by(name=client_name).first()
        if client:
            client.disabled = True
            db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        return api_error(f"数据库更新失败:{e}")

    # ---------- 4. 统一格式化响应 ----------
    if success:
        return api_success(
            message=f"客户端 {client_name} 已成功禁用",
            data={
                "client_name": client_name,
                "kill_response": kill_msg
            }
        )
    else:
        return api_error(
            message=f"客户端已禁用,但踢出失败:{kill_msg}"
        )