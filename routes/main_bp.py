from flask import Blueprint, request, render_template, jsonify
from utils.openvpn_utils import get_openvpn_clients
from datetime import datetime, timedelta
from flask_wtf.csrf import validate_csrf
from functools import wraps

main_bp = Blueprint('main', __name__)

# ---------- 公共 CSRF 装饰器 ----------
def json_csrf_protect(f):
    """与 add_client.py 完全一致，可用于任何 JSON POST"""
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

# ---------- 客户端列表页面 ----------
@main_bp.route('/clients')
def clients():
    page = request.args.get('page', 1, type=int)
    q    = request.args.get('q', '', type=str).strip()

    # 强制输出到 stderr，不会被缓冲
    import sys
    print('===== DEBUG =====', file=sys.stderr)
    print('q =', repr(q), file=sys.stderr)
    print('args =', dict(request.args), file=sys.stderr)

    all_clients = get_openvpn_clients()
    if q:
        all_clients = [c for c in all_clients if q.lower() in c['name'].lower()]
    print('after filter =', len(all_clients), file=sys.stderr)

    per_page     = 10
    total        = len(all_clients)
    total_pages  = max((total + per_page - 1) // per_page, 1)
    offset       = (page - 1) * per_page
    clients_page = all_clients[offset: offset + per_page]

    return render_template(
        'clients.html',
        clients=clients_page,
        page=page,
        total_pages=total_pages,
        q=q
    )