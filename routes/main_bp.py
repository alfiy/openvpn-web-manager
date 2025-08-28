from flask import Blueprint, request, render_template, jsonify
from utils.openvpn_utils import get_openvpn_clients
from flask_wtf.csrf import validate_csrf
from functools import wraps

main_bp = Blueprint('main', __name__)

PER_PAGE = 10

# ---------- 公共 CSRF 装饰器 ----------
def json_csrf_protect(f):
    """
    仅用于 POST / PUT / DELETE 等不安全方法的 CSRF 验证。
    GET 请求不需要，也不会触发此装饰器。
    """
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

# ---------- 工具函数 ----------
def _filter_clients(q: str):
    all_clients = get_openvpn_clients()
    if q:
        all_clients = [c for c in all_clients if q.lower() in c['name'].lower()]
    return all_clients

# ---------- 模板页 ----------
@main_bp.route('/clients')
def clients():
    """普通模板页，支持直接访问、无 JS 也能用"""
    page = request.args.get('page', 1, type=int)
    q    = request.args.get('q', '', type=str).strip()

    all_clients  = _filter_clients(q)
    total        = len(all_clients)
    total_pages  = max((total + PER_PAGE - 1) // PER_PAGE, 1)
    offset       = (page - 1) * PER_PAGE
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
def clients_data():
    """
    供 AJAX 使用的 GET 接口，返回 JSON。
    由于使用 GET，无需 CSRF 验证。
    """
    page = request.args.get('page', 1, type=int)
    q    = request.args.get('q', '', type=str).strip()

    all_clients  = _filter_clients(q)
    total        = len(all_clients)
    total_pages  = max((total + PER_PAGE - 1) // PER_PAGE, 1)
    offset       = (page - 1) * PER_PAGE
    clients_page = all_clients[offset: offset + PER_PAGE]

    return jsonify({
        'clients'     : clients_page,
        'page'        : page,
        'total_pages' : total_pages,
        'q'           : q
    })