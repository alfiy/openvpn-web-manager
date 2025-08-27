from flask import Blueprint, render_template, request
from utils.openvpn_utils import check_openvpn_status, get_openvpn_clients
from math import ceil

index_bp = Blueprint('index', __name__)

@index_bp.route('/')
def index():
    status = check_openvpn_status()
    clients = []
    total_pages = 0
    page = 1

    if status in ['running', 'installed']:
        # 获取分页参数
        page = request.args.get('page', 1, type=int)  # 当前页码，默认为第一页
        per_page = 10  # 每页显示的客户端数量

        # 获取所有客户端信息
        all_clients = get_openvpn_clients()
        total_clients = len(all_clients)
        total_pages = ceil(total_clients / per_page)

        # 获取当前页的客户端数据
        start_index = (page - 1) * per_page
        end_index = start_index + per_page
        clients = all_clients[start_index:end_index]

    return render_template('index.html', status=status, clients=clients, page=page, total_pages=total_pages)
