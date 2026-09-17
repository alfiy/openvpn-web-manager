# routes/api/clients.py
import os
import subprocess
import socket
import time
from flask import jsonify, request
from flask_login import login_required
from routes.helpers import admin_required
from utils.validation import ValidationError, validate_client_name
from utils.openvpn_ops import set_ccd_disabled, kick_client_sessions
from . import api_bp
from utils.api_response import api_success, api_error
from utils.openvpn_utils import log_message
from models import Client, db
from datetime import datetime, timedelta
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
@admin_required
def api_disable_client():
    """
    禁用客户端(创建 ccd disable 文件 + 断开客户端 + 数据库标志位)
    """
    data = request.get_json() or {}
    try:
        client_name = validate_client_name(data.get('client_name', '').strip())
    except ValidationError as exc:
        return api_error(str(exc), 400)

    # ---------- 1. 创建禁用文件 ----------
    try:
        ok, err = set_ccd_disabled(client_name, True)
        if not ok:
            return api_error(f"创建禁用文件失败:{err}")
        log_message(f"禁用文件创建成功:{err}")
    except ValidationError as e:
        return api_error(str(e))
    except Exception as e:
        return api_error(f"创建禁用文件异常:{e}")

    # ---------- 2. 通过 7505 踢掉全部会话（先写 CCD，避免被踢后立刻重连成功）----------
    success, kill_msg = kick_client_sessions(client_name)
    log_message(f"禁用踢出 {client_name}: {kill_msg}")

    # ---------- 3. 更新数据库 ----------
    try:
        client = Client.query.filter_by(name=client_name).first()
        if not client:
            client = Client.query.filter(Client.name.ilike(client_name)).first()
        if client:
            client.disabled = True
            client.online = False
            client.vpn_ip = None
            client.real_ip = None
            client.duration = None
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


@api_bp.route('/clients/kick', methods=['POST'])
@admin_required
def api_kick_client():
    """只断开当前会话，不写 CCD、不改 disabled。客户端可自动重连。"""
    data = request.get_json() or {}
    try:
        client_name = validate_client_name(data.get('client_name', '').strip())
    except ValidationError as exc:
        return api_error(str(exc), 400)

    success, kill_msg = kick_client_sessions(client_name)
    log_message(f"踢下线 {client_name}: {kill_msg}")
    try:
        from utils.openvpn_ops import release_first_wins_lock
        release_first_wins_lock(client_name)
    except Exception as exc:
        log_message(f"清 first-wins 锁失败 {client_name}: {exc}")
    try:
        from utils.openvpn_utils import mark_client_kicked
        mark_client_kicked(client_name)
    except Exception:
        pass
    try:
        client = Client.query.filter_by(name=client_name).first()
        if not client:
            client = Client.query.filter(Client.name.ilike(client_name)).first()
        if client:
            client.online = False
            client.vpn_ip = None
            client.real_ip = None
            client.duration = None
            db.session.commit()
    except Exception as exc:
        db.session.rollback()
        log_message(f"踢下线后更新库失败 {client_name}: {exc}")

    if success:
        return api_success(
            message=f"已踢下线 {client_name}，未禁用，客户端可能自动重连",
            data={"client_name": client_name, "kill_response": kill_msg}
        )
    return api_error(message=f"踢下线失败（请确认已打开 management 127.0.0.1 7505）: {kill_msg}")


def _batch_disable_one(name: str):
    ok, err = set_ccd_disabled(name, True)
    if not ok:
        raise RuntimeError(f'写 CCD 失败: {err}')
    kick_ok, kick_msg = kick_client_sessions(name)
    client = Client.query.filter_by(name=name).first()
    if not client:
        client = Client.query.filter(Client.name.ilike(name)).first()
    if client:
        client.disabled = True
        client.online = False
        client.vpn_ip = None
        client.real_ip = None
        client.duration = None
        db.session.commit()
    if not kick_ok:
        return f'已禁用，但踢出未完成: {kick_msg}'
    return '已禁用'


def _batch_enable_one(name: str):
    from routes.api.enable_client import enable_client as do_enable
    client = Client.query.filter_by(name=name).first()
    if not client:
        raise RuntimeError('客户端不存在')
    if not client.disabled:
        return '本来就未禁用'
    expiry_time = client.logical_expiry or client.expiry
    if expiry_time:
        now = datetime.now()
        exp = expiry_time.replace(tzinfo=None) if getattr(expiry_time, 'tzinfo', None) else expiry_time
        if exp <= now:
            raise RuntimeError('已到期，请先修改到期时间后再启用')
    do_enable(name)
    return '已启用'


def _batch_revoke_one(name: str):
    from utils.openvpn_ops import (
        INDEX_TXT, path_exists, revoke_client_cert, generate_and_install_crl,
        cleanup_client_files,
    )
    crt_path = f'/etc/openvpn/easy-rsa/pki/issued/{name}.crt'
    if not path_exists(INDEX_TXT):
        raise RuntimeError('PKI 不存在')
    if not path_exists(crt_path):
        raise RuntimeError('证书文件不存在')
    ok, err = revoke_client_cert(name)
    if not ok:
        raise RuntimeError(err or '撤销失败')
    ok, err = generate_and_install_crl()
    if not ok:
        raise RuntimeError(err or '生成 CRL 失败')
    cleanup_client_files(name)
    client = Client.query.filter_by(name=name).first()
    if client:
        db.session.delete(client)
        db.session.commit()
        try:
            from utils.tc_config_exporter import export_tc_config
            export_tc_config()
        except Exception:
            pass
    kick_client_sessions(name)
    return '已撤销'


def _parse_batch_expiry(data):
    expiry_date = data.get('expiry_date')
    expiry_days = data.get('expiry_days')
    if expiry_date:
        try:
            return datetime.fromisoformat(str(expiry_date).strip())
        except ValueError as exc:
            raise RuntimeError('expiry_date 格式无效,应为 YYYY-MM-DD') from exc
    if expiry_days not in (None, ''):
        days = int(expiry_days)
        if days <= 0:
            raise RuntimeError('expiry_days 必须为正整数')
        return datetime.now() + timedelta(days=days)
    raise RuntimeError('必须提供 expiry_days 或 expiry_date')


def _batch_expiry_one(name: str, new_expiry):
    client = Client.query.filter_by(name=name).first()
    if not client:
        raise RuntimeError('客户端不存在')
    client.logical_expiry = new_expiry
    was_disabled = bool(client.disabled)
    if client.disabled:
        client.disabled = False
        ok, err = set_ccd_disabled(name, False)
        if not ok:
            raise RuntimeError(f'已改到期，但启用失败: {err}')
    db.session.commit()
    text = f'到期已改为 {new_expiry.strftime("%Y-%m-%d")}'
    if was_disabled:
        text += '，并已启用'
    return text


@api_bp.route('/clients/batch', methods=['POST'])
@admin_required
def api_clients_batch():
    data = request.get_json() or {}
    action = (data.get('action') or '').strip().lower()
    raw_names = data.get('names') or []
    if action not in ('disable', 'enable', 'revoke', 'expiry'):
        return api_error('不支持的批量操作', 400)
    if not isinstance(raw_names, list) or not raw_names:
        return api_error('请先勾选客户端', 400)
    if len(raw_names) > 50:
        return api_error('单次最多操作 50 个客户端', 400)

    new_expiry = None
    if action == 'expiry':
        try:
            new_expiry = _parse_batch_expiry(data)
        except Exception as exc:
            return api_error(str(exc), 400)

    results = []
    ok_count = 0
    for raw in raw_names:
        try:
            name = validate_client_name(str(raw).strip())
            if action == 'disable':
                detail = _batch_disable_one(name)
            elif action == 'enable':
                detail = _batch_enable_one(name)
            elif action == 'expiry':
                detail = _batch_expiry_one(name, new_expiry)
            else:
                detail = _batch_revoke_one(name)
            results.append({'name': name, 'ok': True, 'detail': detail})
            ok_count += 1
        except Exception as exc:
            results.append({'name': str(raw), 'ok': False, 'detail': str(exc)})

    return api_success(
        message=f'完成 {ok_count}/{len(raw_names)}',
        data={'action': action, 'results': results}
    )