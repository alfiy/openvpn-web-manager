# routes/api/add_client.py
from flask import Blueprint, request
from datetime import datetime, timedelta

from routes.helpers import admin_required
from models import Client, db, ClientGroup
from utils.api_response import api_success, api_error
from utils.validation import ValidationError, validate_client_name
from utils.openvpn_ops import build_client_cert, write_ovpn_config
from sqlalchemy.exc import IntegrityError

add_client_bp = Blueprint('add_client', __name__)


@add_client_bp.route('/api/clients/add', methods=['POST'])
@admin_required
def add_client():
    if not request.is_json:
        return api_error(data={"error": "请求必须是 JSON 格式"}, code=400)

    data = request.get_json(silent=True) or {}
    try:
        client_name = validate_client_name((data.get('client_name') or '').strip())
    except ValidationError as exc:
        return api_error(data={"error": str(exc)}, code=400)

    description = (data.get("description") or "").strip() or client_name

    logical_expiry_days = data.get('expiry_days', 365)
    try:
        logical_expiry_days = int(logical_expiry_days)
        if logical_expiry_days <= 0:
            logical_expiry_days = 365
    except (TypeError, ValueError):
        logical_expiry_days = 365

    cert_expiry_days = 3650

    group_id = data.get('group_id', None)
    if group_id is None:
        default_group = ClientGroup.query.filter_by(name='default').first()
        if default_group:
            group_id = default_group.id
    else:
        try:
            group_id = int(group_id)
            group = ClientGroup.query.get(group_id)
            if not group:
                return api_error(data={"error": f"指定的用户组不存在 (ID: {group_id})"}, code=400)
        except (TypeError, ValueError):
            return api_error(data={"error": "group_id 必须是有效的整数"}, code=400)

    existing = Client.query.filter(Client.name == client_name).first()
    if existing:
        return api_error(data={"error": f"客户端已存在：{existing.name}"}, code=400)

    try:
        ok, err = build_client_cert(client_name, cert_expiry_days)
        if not ok:
            if "already exists" in (err or "").lower():
                return api_error(data={"error": f"客户端已存在：{client_name}"}, code=400)
            return api_error(data={"error": f"命令执行失败: {err}"}, code=500)
        ok, err = write_ovpn_config(client_name)
        if not ok:
            return api_error(data={"error": f"生成配置失败: {err}"}, code=500)
    except ValidationError as exc:
        return api_error(data={"error": str(exc)}, code=400)
    except Exception as e:
        return api_error(data={"error": f"内部错误: {str(e)}"}, code=500)

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
            group_id=group_id
        )
        db.session.add(new_client)
        db.session.commit()
        from utils.tc_config_exporter import export_tc_config
        export_tc_config()
    except IntegrityError:
        db.session.rollback()
        return api_error(data={"error": f"客户端已存在：{client_name}"}, code=400)
    except Exception as e:
        db.session.rollback()
        return api_error(data={"error": f"客户端已创建，但数据库写入失败: {str(e)}"}, code=500)

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
