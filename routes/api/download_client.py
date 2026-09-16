from flask import Blueprint, request, jsonify, send_file
import os
from routes.helpers import login_required
from utils.validation import ValidationError, validate_client_name
from utils.openvpn_ops import ovpn_download_path

download_client_bp = Blueprint('download_client', __name__)


@download_client_bp.route('/download_client/<client_name>', methods=['GET'])
@login_required
def download_client(client_name):
    try:
        client_name = validate_client_name(client_name)
        client_path = ovpn_download_path(client_name)
    except ValidationError as exc:
        return jsonify({'status': 'error', 'message': str(exc)}), 400

    if not os.path.isfile(client_path):
        return jsonify({
            'status': 'error',
            'message': f'Client configuration file {client_name}.ovpn not found'
        }), 404

    return send_file(client_path, as_attachment=True, download_name=f"{client_name}.ovpn")
