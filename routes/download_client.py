from flask import Blueprint, send_file, jsonify
import os

download_client_bp = Blueprint('download_client', __name__)

@download_client_bp.route('/download_client/<client_name>', methods=['GET'])
def download_client(client_name):
    # Client config file is always saved in /tmp folder
    client_path = f"/tmp/{client_name}.ovpn"
    if os.path.exists(client_path):
        #print(f"Found client config at: {client_path}")
        return send_file(client_path, as_attachment=True, download_name=f"{client_name}.ovpn")
    else:
        #print(f"Client config not found at: {client_path}")
        return jsonify({'status': 'error', 'message': f'Client configuration file {client_name}.ovpn not found in /tmp folder'})
