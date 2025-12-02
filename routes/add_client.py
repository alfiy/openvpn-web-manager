# from flask import Blueprint, request, jsonify
# import os
# import subprocess
# from datetime import datetime, timedelta
# from routes.helpers import login_required
# from models import Client,db


# add_client_bp = Blueprint('add_client', __name__)


# @add_client_bp.route('/add_client', methods=['POST'])
# @login_required
# def add_client():
#     """新增 OpenVPN 客户端（JSON 接口）"""

#     # 1. 解析 JSON 请求体
#     if not request.is_json:
#         return jsonify({'status': 'error', 'message': '请求必须是 JSON 格式'}), 400

#     data = request.get_json(silent=True) or {}
#     client_name = (data.get('client_name') or '').strip()
#     if not client_name:
#         return jsonify({'status': 'error', 'message': 'client_name 不能为空'}), 400

#     # 2. 有效期（天）
#     expiry_days = data.get('expiry_days', 3650)
#     try:
#         expiry_days = int(expiry_days)
#         if expiry_days <= 0:
#             expiry_days = 3650
#     except (TypeError, ValueError):
#         expiry_days = 3650

#     # 3. 执行 easy-rsa 命令并生成 .ovpn
#     try:
#         commands = [
#             # 生成客户端证书
#             [
#                 'sudo', 'bash', '-c',
#                 f'cd /etc/openvpn/easy-rsa && EASYRSA_CERT_EXPIRE={expiry_days} '
#                 f'./easyrsa --batch build-client-full "{client_name}" nopass'
#             ],
#             # 基于 client-template.txt 追加证书与密钥
#             [
#                 'sudo', 'bash', '-c', f'''
#                 set -e
#                 CONFIG="/etc/openvpn/client/{client_name}.ovpn"

#                 # 1) 先复制模板
#                 cp /etc/openvpn/client-template.txt "$CONFIG"

#                 # 2) 追加 CA
#                 echo ""  >> "$CONFIG"
#                 echo "<ca>" >> "$CONFIG"
#                 cat /etc/openvpn/easy-rsa/pki/ca.crt >> "$CONFIG"
#                 echo "</ca>" >> "$CONFIG"

#                 # 3) 追加客户端证书
#                 echo ""  >> "$CONFIG"
#                 echo "<cert>" >> "$CONFIG"
#                 awk '/BEGIN CERTIFICATE/,/END CERTIFICATE/' \
#                     /etc/openvpn/easy-rsa/pki/issued/{client_name}.crt >> "$CONFIG"
#                 echo "</cert>" >> "$CONFIG"

#                 # 4) 追加私钥
#                 echo ""  >> "$CONFIG"
#                 echo "<key>" >> "$CONFIG"
#                 cat /etc/openvpn/easy-rsa/pki/private/{client_name}.key >> "$CONFIG"
#                 echo "</key>" >> "$CONFIG"

#                 # 5) 追加 tls-crypt 密钥
#                 echo ""  >> "$CONFIG"
#                 echo "<tls-crypt>" >> "$CONFIG"
#                 cat /etc/openvpn/tls-crypt.key >> "$CONFIG"
#                 echo "</tls-crypt>" >> "$CONFIG"

#                 chmod 644 "$CONFIG"
#                 '''
#             ]
#         ]

#         for cmd in commands:
#             result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
#             if result.returncode != 0:
#                 # 检查是否是重复用户
#                 if "Request file already exists" in result.stderr:
#                     return jsonify({
#                         'status': 'error',
#                         'message': f'客户端 {client_name} 已存在，请使用不同名称'
#                     }), 400
#                 # 其他错误
#                 return jsonify({
#                     'status': 'error',
#                     'message': f'命令执行失败: {result.stderr}'
#                 }), 500

#     except subprocess.TimeoutExpired:
#         return jsonify({
#             'status': 'error',
#             'message': '生成客户端超时'
#         }), 500
#     except Exception as e:
#         return jsonify({
#             'status': 'error',
#             'message': f'内部错误: {str(e)}'
#         }), 500

#     # 4. 客户端生成成功，立即写入数据库 
#     try:
#         expiry_dt = datetime.now() + timedelta(days=expiry_days)
#         new_client = Client(
#             name=client_name,
#             expiry=expiry_dt,
#             online=False,
#             disabled=False,
#             vpn_ip="",
#             real_ip="",
#             duration=""
#         )
#         db.session.add(new_client)
#         db.session.commit()

#     except Exception as e:
#         # 数据库写入失败不影响证书生成，不回滚 OpenVPN 创建！
#         return jsonify({
#             "status": "error",
#             "message": f"客户端已创建，但数据库写入失败：{str(e)}"
#         }), 500
    
#     # 5. 成功返回
#     expiry_date_str = (datetime.now() + timedelta(days=expiry_days)).strftime('%Y-%m-%d')
#     return jsonify({
#         'status': 'success',
#         'message': f'客户端 {client_name} 已创建，有效期 {expiry_days} 天（到期：{expiry_date_str}）'
#     }), 201



# routes/api/add_client.py
# from flask import Blueprint, jsonify, request
# import os
# import subprocess
# from datetime import datetime, timedelta
# from routes.helpers import login_required
# from models import Client, db
# from utils.api_response import api_success, api_error


# add_client_bp = Blueprint('add_client', __name__)

# @add_client_bp.route('/api/clients/add', methods=['POST'])
# @login_required
# def add_client():
#     """新增 OpenVPN 客户端（统一 API 风格）"""

#     # 1. 解析 JSON 请求体
#     if not request.is_json:
#         return api_error("请求必须是 JSON 格式", code=400)

#     data = request.get_json(silent=True) or {}
#     client_name = (data.get('client_name') or '').strip()
#     if not client_name:
#         return api_error("client_name 不能为空", code=400)

#     # 2. 有效期（天）
#     expiry_days = data.get('expiry_days', 3650)
#     try:
#         expiry_days = int(expiry_days)
#         if expiry_days <= 0:
#             expiry_days = 3650
#     except (TypeError, ValueError):
#         expiry_days = 3650

#     # 3. 执行 easy-rsa 命令并生成 .ovpn
#     try:
#         commands = [
#             # 生成客户端证书
#             [
#                 'sudo', 'bash', '-c',
#                 f'cd /etc/openvpn/easy-rsa && EASYRSA_CERT_EXPIRE={expiry_days} '
#                 f'./easyrsa --batch build-client-full "{client_name}" nopass'
#             ],
#             # 基于 client-template.txt 追加证书与密钥
#             [
#                 'sudo', 'bash', '-c', f'''
#                 set -e
#                 CONFIG="/etc/openvpn/client/{client_name}.ovpn"
#                 cp /etc/openvpn/client-template.txt "$CONFIG"
#                 echo "" >> "$CONFIG"
#                 echo "<ca>" >> "$CONFIG"
#                 cat /etc/openvpn/easy-rsa/pki/ca.crt >> "$CONFIG"
#                 echo "</ca>" >> "$CONFIG"
#                 echo "" >> "$CONFIG"
#                 echo "<cert>" >> "$CONFIG"
#                 awk '/BEGIN CERTIFICATE/,/END CERTIFICATE/' /etc/openvpn/easy-rsa/pki/issued/{client_name}.crt >> "$CONFIG"
#                 echo "</cert>" >> "$CONFIG"
#                 echo "" >> "$CONFIG"
#                 echo "<key>" >> "$CONFIG"
#                 cat /etc/openvpn/easy-rsa/pki/private/{client_name}.key >> "$CONFIG"
#                 echo "</key>" >> "$CONFIG"
#                 echo "" >> "$CONFIG"
#                 echo "<tls-crypt>" >> "$CONFIG"
#                 cat /etc/openvpn/tls-crypt.key >> "$CONFIG"
#                 echo "</tls-crypt>" >> "$CONFIG"
#                 chmod 644 "$CONFIG"
#                 '''
#             ]
#         ]

#         for cmd in commands:
#             result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
#             if result.returncode != 0:
#                 if "Request file already exists" in result.stderr:
#                     return api_error(f'客户端 {client_name} 已存在，请使用不同名称', code=400)
#                 return api_error(f'命令执行失败: {result.stderr}', code=500)

#     except subprocess.TimeoutExpired:
#         return api_error('生成客户端超时', code=500)
#     except Exception as e:
#         return api_error(f'内部错误: {str(e)}', code=500)

#     # 4. 客户端生成成功，立即写入数据库
#     try:
#         expiry_dt = datetime.now() + timedelta(days=expiry_days)
#         new_client = Client(
#             name=client_name,
#             expiry=expiry_dt,
#             online=False,
#             disabled=False,
#             vpn_ip="",
#             real_ip="",
#             duration=""
#         )
#         db.session.add(new_client)
#         db.session.commit()
#     except Exception as e:
#         # 数据库写入失败不影响证书生成，不回滚 OpenVPN 创建！
#         return jsonify({
#             "status": "error",
#             "message": f"客户端已创建，但数据库写入失败：{str(e)}"
#         }), 500
    
#     # 5. 成功返回
#     expiry_date_str = (datetime.now() + timedelta(days=expiry_days)).strftime('%Y-%m-%d')
#     return jsonify({
#         'status': 'success',
#         'message': f'客户端 {client_name} 已创建，有效期 {expiry_days} 天（到期：{expiry_date_str}）'
#     }), 201

# routes/add_client.py
from flask import Blueprint, request
import os
import subprocess
from datetime import datetime, timedelta
from routes.helpers import login_required
from models import Client, db
from utils.api_response import api_success, api_error

add_client_bp = Blueprint('add_client', __name__)


@add_client_bp.route('/api/clients/add', methods=['POST'])
@login_required
def add_client():
    """新增 OpenVPN 客户端（JSON 接口，统一API风格）"""

    # 1. 验证 JSON 请求
    if not request.is_json:
        return api_error(data={"error": "请求必须是 JSON 格式"}, code=400)

    data = request.get_json(silent=True) or {}
    client_name = (data.get('client_name') or '').strip()
    if not client_name:
        return api_error(data={"error": "client_name 不能为空"}, code=400)

    # 2. 有效期（天）
    expiry_days = data.get('expiry_days', 3650)
    try:
        expiry_days = int(expiry_days)
        if expiry_days <= 0:
            expiry_days = 3650
    except (TypeError, ValueError):
        expiry_days = 3650

    # 3. 执行 easy-rsa 命令生成客户端证书和 .ovpn 文件
    try:
        commands = [
            # 生成客户端证书
            [
                'sudo', 'bash', '-c',
                f'cd /etc/openvpn/easy-rsa && EASYRSA_CERT_EXPIRE={expiry_days} '
                f'./easyrsa --batch build-client-full "{client_name}" nopass'
            ],
            # 基于模板生成 .ovpn
            [
                'sudo', 'bash', '-c', f'''
                set -e
                CONFIG="/etc/openvpn/client/{client_name}.ovpn"

                cp /etc/openvpn/client-template.txt "$CONFIG"

                echo ""  >> "$CONFIG"
                echo "<ca>" >> "$CONFIG"
                cat /etc/openvpn/easy-rsa/pki/ca.crt >> "$CONFIG"
                echo "</ca>" >> "$CONFIG"

                echo ""  >> "$CONFIG"
                echo "<cert>" >> "$CONFIG"
                awk '/BEGIN CERTIFICATE/,/END CERTIFICATE/' \
                    /etc/openvpn/easy-rsa/pki/issued/{client_name}.crt >> "$CONFIG"
                echo "</cert>" >> "$CONFIG"

                echo ""  >> "$CONFIG"
                echo "<key>" >> "$CONFIG"
                cat /etc/openvpn/easy-rsa/pki/private/{client_name}.key >> "$CONFIG"
                echo "</key>" >> "$CONFIG"

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
                if "Request file already exists" in result.stderr:
                    return api_error(
                        data={"error": f'客户端 {client_name} 已存在，请使用不同名称'}, code=400
                    )
                return api_error(
                    data={"error": f'命令执行失败: {result.stderr}'}, code=500
                )

    except subprocess.TimeoutExpired:
        return api_error(data={"error": "生成客户端超时"}, code=500)
    except Exception as e:
        return api_error(data={"error": f"内部错误: {str(e)}"}, code=500)

    # 4. 写入数据库
    try:
        expiry_dt = datetime.now() + timedelta(days=expiry_days)
        new_client = Client(
            name=client_name,
            expiry=expiry_dt,
            online=False,
            disabled=False,
            vpn_ip="",
            real_ip="",
            duration=""
        )
        db.session.add(new_client)
        db.session.commit()
    except Exception as e:
        # 数据库写入失败不影响证书生成
        return api_error(
            data={"error": f"客户端已创建，但数据库写入失败：{str(e)}"}, code=500
        )

    # 5. 返回成功，前端显示 message，可自动消失
    expiry_date_str = expiry_dt.strftime('%Y-%m-%d')
    return api_success(
        data={
            "client_name": client_name,
            "expiry_days": expiry_days,
            "expiry_date": expiry_date_str,
            "message": f'客户端 {client_name} 已创建，有效期 {expiry_days} 天（到期：{expiry_date_str}）'
        },
        code=0,
        status=201
    )
