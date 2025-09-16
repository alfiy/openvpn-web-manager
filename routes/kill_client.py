import os
import subprocess
import socket
import time
from flask import Blueprint, request, jsonify
from functools import wraps
import json
from utils.openvpn_utils import log_message
from routes.helpers import login_required, json_csrf_protect
from models import db,Client
from sqlalchemy.exc import SQLAlchemyError

# ==============================================================================
# 客户端踢出模块
# ------------------------------------------------------------------------------
# 此蓝图提供一个 API 端点，用于通过 OpenVPN 管理接口踢出特定客户端。
# ==============================================================================

kill_client_bp = Blueprint('kill_client', __name__)


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
        cid_idx = None
        if 'client id' in low_headers:
            cid_idx = low_headers.index('client id')
        cids = []
        for cl in client_lines:
            parts = cl.split(',')[1:]
            name = parts[idx_cn] if idx_cn < len(parts) else ''
            cid = (parts[cid_idx] if cid_idx is not None and cid_idx < len(parts) else None)
            if name == common_name:
                if cid:
                    cids.append(cid)
                else:
                    return []
        return cids if cids else None
    for i, ln in enumerate(lines):
        if ln.startswith('Common Name,') or ln.startswith('Common Name,'):
            for dl in lines[i+1:]:
                if dl.strip() == '' or dl.startswith('ROUTING TABLE') or dl.startswith('GLOBAL STATS') or dl == 'END':
                    break
                parts = dl.split(',')
                if parts and parts[0] == common_name:
                    return []
            break
    return None

def send_and_recv(sock, cmd, wait=0.05, recv_timeout=2.0):
    sock.sendall((cmd + "\n").encode('utf-8'))
    time.sleep(wait)
    return recv_all_until_end(sock, timeout=recv_timeout)

def openvpn_client_kill(host, port, client_name, mgmt_password=None, verbose=False):
    """
    核心踢出函数，直接返回结果而不是打印到控制台。
    """
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
            
            s.sendall(b"quit\n")

    except socket.error as e:
        return False, f"无法连接到 OpenVPN 管理接口: {e}"
    except Exception as e:
        return False, f"踢出客户端时发生错误: {e}"


# --- 路由定义 ---
@kill_client_bp.route('/kill_client', methods=['POST'])
@login_required
@json_csrf_protect
def kill_client():
    """
    通过 API 请求踢出客户端
    """
    data = request.json
    client_name = data.get('client_name')
    if not client_name:
        log_message("缺少 'client_name' 参数")
        return jsonify({"status": 'error', "message": "缺少 'client_name' 参数"}), 400

    # 1. 在 /etc/openvpn/ccd/ 目录下创建禁用文件并写入指令
    ccd_dir = '/etc/openvpn/ccd'
    disable_file_path = os.path.join(ccd_dir, client_name)
    
    try:
        # 使用 subprocess.run 安全地创建文件并写入内容
        # 确保目录存在
        os.makedirs(ccd_dir, exist_ok=True)
        # 使用 sudo 写入文件，因为 OpenVPN 的 ccd 目录可能需要 root 权限
        cmd = ['sudo', 'sh', '-c', f'echo "disable" > {disable_file_path}']
        log_message(f"执行命令以禁用客户端：{' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        log_message(f"禁用文件创建成功：{result.stdout.strip()}")
        # 修复文件权限，确保 OpenVPN 可以读取
        os.system(f"sudo chown root:root {disable_file_path}")
        os.system(f"sudo chmod 644 {disable_file_path}")

    except subprocess.CalledProcessError as e:
        log_message(f"创建禁用文件失败：{e.stderr}")
        return jsonify({"status": 'error', "message": f"创建禁用文件失败：{e.stderr}"}), 500

    # 2. 调用核心踢出逻辑，强制断开客户端的在线连接
    host = os.environ.get('OPENVPN_MGMT_HOST', '127.0.0.1')
    port = int(os.environ.get('OPENVPN_MGMT_PORT', 7505))
    password = os.environ.get('OPENVPN_MGMT_PASSWORD')

    log_message(f"正在通过管理接口踢出客户端: {client_name}")
    success, message = openvpn_client_kill(host, port, client_name, mgmt_password=password)

    if success:
                # 3. 踢出成功后，更新数据库中的 'disabled' 字段
        try:
            client = Client.query.filter_by(name=client_name).first()
            if client:
                client.disabled = True
                db.session.commit()
                log_message(f"成功将客户端 {client_name} 的 'disabled' 状态更新为 True。")
            else:
                log_message(f"数据库中未找到客户端 {client_name}。")
                
        except SQLAlchemyError as e:
            db.session.rollback()
            log_message(f"数据库更新失败：{e}")
            return jsonify({"status": 'error', "message": f"数据库更新失败：{e}"}), 500

        log_message(f"成功踢出客户端 {client_name}。")
        return jsonify({"status": 'success', "message": f"客户端 {client_name} 已成功禁用并断开连接。"})
    else:
        log_message(f"踢出客户端 {client_name} 失败: {message}")
        return jsonify({"status": 'error', "message": f"客户端已禁用，但踢出失败: {message}"}), 500