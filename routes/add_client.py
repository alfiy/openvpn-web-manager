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

    port = get_openvpn_port()

    # 4. 执行 easy-rsa 命令
    try:
        commands = [
            # 生成客户端证书
            [
                'sudo', 'bash', '-c',
                f'cd /etc/openvpn/easy-rsa && EASYRSA_CERT_EXPIRE={expiry_days} '
                f'./easyrsa --batch build-client-full "{client_name}" nopass'
            ],
            # 生成 .ovpn 配置文件
            [
                'sudo', 'bash', '-c', f'''
                set -e
                cd /etc/openvpn/easy-rsa

                # 基础配置
                cp /etc/openvpn/client-template.txt "/etc/openvpn/client/{client_name}.ovpn" 2>/dev/null || cat > "/etc/openvpn/client/{client_name}.ovpn" <<EOF
client
dev tun
proto udp
remote $(curl -s ifconfig.me || echo localhost) {port}
resolv-retry infinite
nobind
persist-key
persist-tun
remote-cert-tls server
cipher AES-256-GCM
verb 3
EOF

                # 追加证书与密钥
                echo ""  >> "/etc/openvpn/client/{client_name}.ovpn"
                echo "<ca>" >> "/etc/openvpn/client/{client_name}.ovpn"
                cat "/etc/openvpn/easy-rsa/pki/ca.crt" >> "/etc/openvpn/client/{client_name}.ovpn"
                echo "</ca>" >> "/etc/openvpn/client/{client_name}.ovpn"

                echo ""  >> "/etc/openvpn/client/{client_name}.ovpn"
                echo "<cert>" >> "/etc/openvpn/client/{client_name}.ovpn"
                awk '/BEGIN CERTIFICATE/,/END CERTIFICATE/' "/etc/openvpn/easy-rsa/pki/issued/{client_name}.crt" >> "/etc/openvpn/client/{client_name}.ovpn"
                echo "</cert>" >> "/etc/openvpn/client/{client_name}.ovpn"

                echo ""  >> "/etc/openvpn/client/{client_name}.ovpn"
                echo "<key>" >> "/etc/openvpn/client/{client_name}.ovpn"
                cat "/etc/openvpn/easy-rsa/pki/private/{client_name}.key" >> "/etc/openvpn/client/{client_name}.ovpn"
                echo "</key>" >> "/etc/openvpn/client/{client_name}.ovpn"

                echo ""  >> "/etc/openvpn/client/{client_name}.ovpn"
                echo "<tls-crypt>" >> "/etc/openvpn/client/{client_name}.ovpn"
                cat /etc/openvpn/tls-crypt.key 2>/dev/null || cat /etc/openvpn/ta.key 2>/dev/null || echo "# TLS key not found" >> "/etc/openvpn/client/{client_name}.ovpn"
                echo "</tls-crypt>" >> "/etc/openvpn/client/{client_name}.ovpn"

                chmod 644 "/etc/openvpn/client/{client_name}.ovpn"
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
            'message': f'生成客户端超时'
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