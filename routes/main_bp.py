from flask import Blueprint, request, render_template, jsonify
from flask_login import login_required
from utils.openvpn_utils import get_openvpn_clients
from routes.helpers import json_csrf_protect
from utils.openvpn_utils import check_openvpn_status

# 蓝图名称已从 'main' 更改为 'main_bp' 以避免命名冲突
main_bp = Blueprint('main_bp', __name__)

PER_PAGE = 10

# ---------- 工具函数 ----------
def _filter_clients(q: str):
    """
    根据查询字符串过滤客户端列表。
    """
    all_clients = get_openvpn_clients()
    if q:
        all_clients = [c for c in all_clients if q.lower() in c['name'].lower()]
    return all_clients

# ---------- 路由 ----------
@main_bp.route('/')
@login_required
def index():
    # ✅ 调用工具函数获取OpenVPN状态
    openvpn_status = check_openvpn_status()
    
    # 打印日志以供调试
    print(f"DEBUG: OpenVPN status is: {openvpn_status}")
    
    # ✅ 将状态变量传递给模板
    return render_template('index.html', status=openvpn_status)

@main_bp.route('/clients')
@login_required # 确保用户已登录
def clients():
    """
    处理客户端列表页面。
    这是一个传统的网页路由，用于直接渲染 HTML 模板。
    """
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '', type=str).strip()

    all_clients = _filter_clients(q)
    total = len(all_clients)
    total_pages = max((total + PER_PAGE - 1) // PER_PAGE, 1)
    offset = (page - 1) * PER_PAGE
    clients_page = all_clients[offset: offset + PER_PAGE]

    return render_template(
        'clients.html',
        clients=clients_page,
        page=page,
        total_pages=total_pages,
        q=q
    )

# ---------- AJAX 接口 ----------
@main_bp.route('/clients/data')
@login_required # 确保用户已登录
def clients_data():
    """
    供 AJAX 使用的 GET 接口，返回 JSON 格式的客户端数据。
    由于是 GET 请求，它不需要 CSRF 验证。
    """
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '', type=str).strip()

    all_clients = _filter_clients(q)
    total = len(all_clients)
    total_pages = max((total + PER_PAGE - 1) // PER_PAGE, 1)
    offset = (page - 1) * PER_PAGE
    clients_page = all_clients[offset: offset + PER_PAGE]

    return jsonify({
        'clients': clients_page,
        'page': page,
        'total_pages': total_pages,
        'q': q
    })