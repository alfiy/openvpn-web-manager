from flask import Blueprint, request, jsonify
import os
import subprocess
from utils.openvpn_utils import get_openvpn_port
from datetime import datetime, timedelta

# —— CSRF 保护（仅演示，生产环境请用更安全的方案）——
from flask_wtf.csrf import validate_csrf
from functools import wraps

def json_csrf_protect(f):
    """对 JSON POST 请求做 CSRF 校验"""
    @wraps(f)
    def decorated(*args, **kwargs):
        csrf_token = request.headers.get('X-CSRFToken')
        if not csrf_token:
            return jsonify({'status': 'error', 'message': '缺少 CSRF 令牌'}), 403
        try:
            validate_csrf(csrf_token)
        except Exception:
            return jsonify({'status': 'error', 'message': 'CSRF 令牌验证失败，请刷新页面重试'}), 403
        return f(*args, **kwargs)
    return decorated


add_client_bp = Blueprint('add_client', __name__)
SCRIPT_PATH = './ubuntu-openvpn-install.sh'


@add_client_bp.route('/add_client', methods=['POST'])
@json_csrf_protect
def add_client():
    """新增 OpenVPN 客户端（JSON 接口）"""

    # 1. 检查安装脚本是否存在
    if not os.path.exists(SCRIPT_PATH):
        return jsonify({
            'status': 'error',
            'message': f'OpenVPN 安装脚本不存在: {SCRIPT_PATH}'
        }), 400

    # 2. 解析 JSON 请求体
    if not request.is_json:
        return jsonify({'status': 'error', 'message': '请求必须是 JSON 格式'}), 400

    data = request.get_json(silent=True) or {}
    client_name = (data.get('client_name') or '').strip()
    if not client_name:
        return jsonify({'status': 'error', 'message': 'client_name 不能为空'}), 400

    # 3. 有效期（天）
    expiry_days = data.get('expiry_days', 3650)
    try:
        expiry_days = int(expiry_days)
        if expiry_days <= 0:
            expiry_days = 3650
    except (TypeError, ValueError):
        expiry_days = 3650

    # 4. 执行 easy-rsa 命令并生成 .ovpn
    try:
        commands = [
            # 生成客户端证书
            [
                'sudo', 'bash', '-c',
                f'cd /etc/openvpn/easy-rsa && EASYRSA_CERT_EXPIRE={expiry_days} '
                f'./easyrsa --batch build-client-full "{client_name}" nopass'
            ],
            # 基于 client-template.txt 追加证书与密钥
            [
                'sudo', 'bash', '-c', f'''
                set -e
                CONFIG="/etc/openvpn/client/{client_name}.ovpn"

                # 1) 先复制模板
                cp /etc/openvpn/client-template.txt "$CONFIG"

                # 2) 追加 CA
                echo ""  >> "$CONFIG"
                echo "<ca>" >> "$CONFIG"
                cat /etc/openvpn/easy-rsa/pki/ca.crt >> "$CONFIG"
                echo "</ca>" >> "$CONFIG"

                # 3) 追加客户端证书
                echo ""  >> "$CONFIG"
                echo "<cert>" >> "$CONFIG"
                awk '/BEGIN CERTIFICATE/,/END CERTIFICATE/' \
                    /etc/openvpn/easy-rsa/pki/issued/{client_name}.crt >> "$CONFIG"
                echo "</cert>" >> "$CONFIG"

                # 4) 追加私钥
                echo ""  >> "$CONFIG"
                echo "<key>" >> "$CONFIG"
                cat /etc/openvpn/easy-rsa/pki/private/{client_name}.key >> "$CONFIG"
                echo "</key>" >> "$CONFIG"

                # 5) 追加 tls-crypt 密钥
                echo ""  >> "$CONFIG"
                echo "<tls-crypt>" >> "$CONFIG"
                cat /etc/openvpn/tls-crypt.key >> "$CONFIG"
                echo "</tls-crypt>" >> "$CONFIG"

                chmod 644 "$CONFIG"
                '''
            ]
        ]

        for cmd in commands:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                return jsonify({
                    'status': 'error',
                    'message': f'命令执行失败: {result.stderr}'
                }), 500

    except subprocess.TimeoutExpired:
        return jsonify({
            'status': 'error',
            'message': '生成客户端超时'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'内部错误: {str(e)}'
        }), 500

    # 5. 成功返回
    expiry_date_str = (datetime.now() + timedelta(days=expiry_days)).strftime('%Y-%m-%d')
    return jsonify({
        'status': 'success',
        'message': f'客户端 {client_name} 已创建，有效期 {expiry_days} 天（到期：{expiry_date_str}）'
    }), 201