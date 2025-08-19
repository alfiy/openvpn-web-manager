from flask import Blueprint, render_template
from utils.openvpn_utils import check_openvpn_status, get_openvpn_clients

index_bp = Blueprint('index', __name__)

@index_bp.route('/')
def index():
    status = check_openvpn_status()
    clients = []
    if status in ['running', 'installed']:
        clients = get_openvpn_clients()
    return render_template('index.html', status=status, clients=clients)
