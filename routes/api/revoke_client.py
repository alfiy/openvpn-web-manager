# routes/api/revoke_client.py
import os
import socket
from flask import Blueprint, request
from routes.helpers import admin_required
from models import Client, db
from utils.api_response import api_success, api_error
from utils.validation import ValidationError, validate_client_name
from utils.openvpn_ops import (
    INDEX_TXT, revoke_client_cert, generate_and_install_crl, cleanup_client_files,
)

revoke_client_bp = Blueprint('revoke_client', __name__)

MGMT_HOST = '127.0.0.1'
MGMT_PORT = 7505
MGMT_TIMEOUT = 5


def disconnect_client_via_mgmt(client_name: str):
    try:
        with socket.create_connection((MGMT_HOST, MGMT_PORT), timeout=MGMT_TIMEOUT) as s:
            s.recv(4096)
            s.sendall(b'status 2\n')
            resp = b""
            while True:
                chunk = s.recv(4096)
                resp += chunk
                if b'END' in chunk:
                    break
            lines = resp.decode(errors='ignore').splitlines()
            for line in lines:
                if line.startswith("CLIENT_LIST"):
                    parts = line.split(',')
                    if len(parts) >= 2:
                        cn = parts[1].strip()
                        if cn == client_name:
                            cmd = ('kill %s\n' % client_name).encode()
                            s.sendall(cmd)
                            s.recv(4096)
                            return True
        return False
    except Exception as e:
        print(f"[WARN] Management interface disconnect failed: {e}")
        return False


@revoke_client_bp.route('/api/clients/revoke', methods=['POST'])
@admin_required
def api_revoke_client():
    data = request.get_json()
    if not data:
        return api_error("请求数据格式错误", code=400)
    try:
        client_name = validate_client_name((data.get('client_name') or '').strip())
    except ValidationError as exc:
        return api_error(str(exc), code=400)

    crt_path = f'/etc/openvpn/easy-rsa/pki/issued/{client_name}.crt'

    try:
        if not os.path.exists(INDEX_TXT):
            return api_error("OpenVPN PKI 不存在", code=500)
        if not os.path.exists(crt_path):
            return api_error(f"证书文件 {client_name}.crt 不存在，无法撤销", code=500)

        found = False
        with open(INDEX_TXT, 'r') as f:
            for line in f:
                if f'CN={client_name},' in line or line.rstrip().endswith(f'CN={client_name}'):
                    found = True
                    break
        if not found:
            return api_error(f"客户端 {client_name} 不存在于证书数据库", code=404)

        ok, err = revoke_client_cert(client_name)
        if not ok:
            return api_error(f"撤销失败: {err}", code=500)

        ok, err = generate_and_install_crl()
        if not ok:
            return api_error(f"生成 CRL 失败: {err}", code=500)

        cleanup_client_files(client_name)

        try:
            client = Client.query.filter_by(name=client_name).first()
            if client:
                db.session.delete(client)
                db.session.commit()
        except Exception as db_err:
            print(f"[WARN] Failed to delete client {client_name} from DB:", db_err)

        disconnected = disconnect_client_via_mgmt(client_name)
        msg = f"客户端 {client_name} 已撤销，CRL 已更新"
        if disconnected:
            msg += "，并已立即断开在线连接"
        else:
            msg += "。该客户端当前可能未在线"
        return api_success(data={"message": msg})
    except ValidationError as exc:
        return api_error(str(exc), code=400)
    except Exception as e:
        return api_error(f"撤销异常: {str(e)}", code=500)
