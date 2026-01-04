from flask import Blueprint, request, render_template, jsonify
from flask_login import login_required
from models import Client  # ORM 模型
from utils.openvpn_utils import (
    get_openvpn_clients,
    check_openvpn_status,
    sync_openvpn_clients_to_db,
    sync_online_state_to_db
)

main_bp = Blueprint('main_bp', __name__)
PER_PAGE = 10

# ---------- 工具函数 ----------
def serialize_client(c: Client):
    """将 Client ORM 对象序列化为前端需要的字典"""
    return {
        "name": c.name,
        "online": c.online,
        "disabled": c.disabled,
        "vpn_ip": c.vpn_ip,
        "real_ip": c.real_ip,
        "duration": c.duration,
        # 前端显示 expiry = logical_expiry
        "expiry": c.logical_expiry.strftime('%Y-%m-%d %H:%M:%S') if c.logical_expiry else None
    }

# ---------- 首页路由 ----------
@main_bp.route('/')
@login_required
def index():
    """首页，显示 OpenVPN 状态"""
    openvpn_status = check_openvpn_status()
    print(f"DEBUG: OpenVPN status is: {openvpn_status}")
    return render_template('index.html', status=openvpn_status)

# ---------- 网页客户端列表路由 ----------
@main_bp.route('/clients')
@login_required
def clients():
    """
    客户端列表页面，直接渲染 HTML 模板
    使用 ORM 查询分页并支持搜索
    """
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '', type=str).strip()

    sync_openvpn_clients_to_db()
    sync_online_state_to_db()

    query = Client.query
    if q:
        query = query.filter(Client.name.ilike(f"%{q}%"))

    total = query.count()
    total_pages = max((total + PER_PAGE - 1) // PER_PAGE, 1)

    clients_page = (
        query
        .order_by(Client.id.desc())
        .offset((page - 1) * PER_PAGE)
        .limit(PER_PAGE)
        .all()
    )

    return render_template(
        'clients.html',
        clients=clients_page,          # ORM 对象列表，可在模板中访问 c.logical_expiry
        page=page,
        total_pages=total_pages,
        q=q
    )

# ---------- AJAX 接口 ----------
@main_bp.route('/clients/data')
@login_required
def clients_data():
    """
    AJAX GET 接口，返回 JSON 格式客户端数据
    前端显示的 expiry = logical_expiry
    """
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '', type=str).strip()

    # 同步 OpenVPN 客户端状态
    sync_openvpn_clients_to_db()
    sync_online_state_to_db()

    query = Client.query
    if q:
        query = query.filter(Client.name.ilike(f"%{q}%"))

    total = query.count()
    total_pages = max((total + PER_PAGE - 1) // PER_PAGE, 1)

    clients_page = (
        query
        .order_by(Client.id.desc())
        .offset((page - 1) * PER_PAGE)
        .limit(PER_PAGE)
        .all()
    )

    clients_serialized = [serialize_client(c) for c in clients_page]

    return jsonify({
        "clients": clients_serialized,
        "page": page,
        "total_pages": total_pages,
        "q": q
    })
