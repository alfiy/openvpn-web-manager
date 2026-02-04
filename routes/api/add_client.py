# routes/api/add_client.py
from flask import Blueprint, request
import subprocess
from datetime import datetime, timedelta

from routes.helpers import login_required
from models import Client, db, ClientGroup
from utils.api_response import api_success, api_error

from sqlalchemy.exc import IntegrityError

add_client_bp = Blueprint('add_client', __name__)


@add_client_bp.route('/api/clients/add', methods=['POST'])
@login_required
def add_client():
    """新增 OpenVPN 客户端(JSON 接口,统一API风格)"""

    # ------------------------------------------------------------------
    # 1. 校验 JSON
    # ------------------------------------------------------------------
    if not request.is_json:
        return api_error(data={"error": "请求必须是 JSON 格式"}, code=400)

    data = request.get_json(silent=True) or {}
    client_name = (data.get('client_name') or '').strip()

    if not client_name:
        return api_error(data={"error": "client_name 不能为空"}, code=400)
    
    description = (data.get("description") or "").strip()

    if not description:
        description = client_name 

    # ------------------------------------------------------------------
    # 2. 逻辑有效期（天）
    # ------------------------------------------------------------------
    logical_expiry_days = data.get('expiry_days', 365)
    try:
        logical_expiry_days = int(logical_expiry_days)
        if logical_expiry_days <= 0:
            logical_expiry_days = 365
    except (TypeError, ValueError):
        logical_expiry_days = 365

    # ------------------------------------------------------------------
    # 3. 证书真实有效期（固定 10 年）
    # ------------------------------------------------------------------
    cert_expiry_days = 3650

    # ------------------------------------------------------------------
    # 🆕 4. 用户组选择（如果未指定则使用默认用户组）
    # ------------------------------------------------------------------
    group_id = data.get('group_id', None)
    
    # 如果没有指定用户组，自动分配到默认用户组
    if group_id is None:
        default_group = ClientGroup.query.filter_by(name='default').first()
        if default_group:
            group_id = default_group.id
    else:
        # 验证指定的用户组是否存在
        try:
            group_id = int(group_id)
            group = ClientGroup.query.get(group_id)
            if not group:
                return api_error(
                    data={"error": f"指定的用户组不存在 (ID: {group_id})"},
                    code=400
                )
        except (TypeError, ValueError):
            return api_error(
                data={"error": "group_id 必须是有效的整数"},
                code=400
            )

    # ------------------------------------------------------------------
    # 5. 🔒 数据库预检查（NOCASE 生效，防 Test001 / test001）
    # ------------------------------------------------------------------
    existing = Client.query.filter(Client.name == client_name).first()
    if existing:
        return api_error(
            data={"error": f"客户端已存在：{existing.name}"},
            code=400
        )

    # ------------------------------------------------------------------
    # 6. 调用 easy-rsa 生成证书和 ovpn
    # ------------------------------------------------------------------
    try:
        commands = [
            # 生成客户端证书
            [
                'sudo', 'bash', '-c',
                f'cd /etc/openvpn/easy-rsa && '
                f'EASYRSA_CERT_EXPIRE={cert_expiry_days} '
                f'./easyrsa --batch build-client-full "{client_name}" nopass'
            ],
            # 生成 .ovpn
            [
                'sudo', 'bash', '-c', f'''
                set -e

                CONFIG="/etc/openvpn/client/{client_name}.ovpn"
                TEMPLATE="/etc/openvpn/client-template.txt"

                cp "$TEMPLATE" "$CONFIG"

                echo "" >> "$CONFIG"
                echo "<ca>" >> "$CONFIG"
                cat /etc/openvpn/easy-rsa/pki/ca.crt >> "$CONFIG"
                echo "</ca>" >> "$CONFIG"

                echo "" >> "$CONFIG"
                echo "<cert>" >> "$CONFIG"
                awk '/BEGIN CERTIFICATE/,/END CERTIFICATE/' \
                    /etc/openvpn/easy-rsa/pki/issued/{client_name}.crt >> "$CONFIG"
                echo "</cert>" >> "$CONFIG"

                echo "" >> "$CONFIG"
                echo "<key>" >> "$CONFIG"
                cat /etc/openvpn/easy-rsa/pki/private/{client_name}.key >> "$CONFIG"
                echo "</key>" >> "$CONFIG"

                echo "" >> "$CONFIG"
                echo "<tls-crypt>" >> "$CONFIG"
                cat /etc/openvpn/tls-crypt.key >> "$CONFIG"
                echo "</tls-crypt>" >> "$CONFIG"

                chmod 644 "$CONFIG"
                '''
            ]
        ]

        for cmd in commands:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                stderr = (result.stderr or "").lower()

                if "already exists" in stderr:
                    return api_error(
                        data={"error": f"客户端已存在：{client_name}"},
                        code=400
                    )

                return api_error(
                    data={"error": f"命令执行失败: {result.stderr}"},
                    code=500
                )

    except subprocess.TimeoutExpired:
        return api_error(data={"error": "生成客户端超时"}, code=500)
    except Exception as e:
        return api_error(data={"error": f"内部错误: {str(e)}"}, code=500)

    # ------------------------------------------------------------------
    # 7. 写入数据库（最终裁决，防并发）
    # ------------------------------------------------------------------
    try:
        cert_expiry_dt = datetime.now() + timedelta(days=cert_expiry_days)
        logical_expiry_dt = datetime.now() + timedelta(days=logical_expiry_days)

        new_client = Client(
            name=client_name,
            description=description,
            expiry=cert_expiry_dt,
            logical_expiry=logical_expiry_dt,
            online=False,
            disabled=False,
            vpn_ip="",
            real_ip="",
            duration="",
            group_id=group_id  # 🆕 设置用户组
        )

        db.session.add(new_client)
        db.session.commit()

        # 🆕 导出 TC 配置（更新限速规则）
        from utils.tc_config_exporter import export_tc_config
        export_tc_config()

    except IntegrityError:
        db.session.rollback()
        return api_error(
            data={"error": f"客户端已存在：{client_name}"},
            code=400
        )

    except Exception as e:
        db.session.rollback()
        return api_error(
            data={"error": f"客户端已创建，但数据库写入失败: {str(e)}"},
            code=500
        )

    # ------------------------------------------------------------------
    # 8. 返回成功(包含用户组信息)
    # ------------------------------------------------------------------
    group_info = ""
    if group_id:
        group = ClientGroup.query.get(group_id)
        if group:
            group_info = f"，已分配到用户组：{group.name} (上行:{group.upload_rate} 下行:{group.download_rate})"

    return api_success(
        data={
            "client_name": client_name,
            "group_id": group_id,
            "logical_expiry_days": logical_expiry_days,
            "logical_expiry_date": logical_expiry_dt.strftime('%Y-%m-%d'),
            "cert_expiry_date": cert_expiry_dt.strftime('%Y-%m-%d'),
            "message": (
                f'客户端 {client_name} 已创建，'
                f'逻辑有效期 {logical_expiry_days} 天 '
                f'(到期:{logical_expiry_dt.strftime("%Y-%m-%d")})，'
                f'证书有效期10年 '
                f'(到期:{cert_expiry_dt.strftime("%Y-%m-%d")})'
                f'{group_info}'
            )
        },
        code=0,
        status=201
    )
