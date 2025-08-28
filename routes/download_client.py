from flask import Blueprint, send_file, jsonify, request
import os

download_client_bp = Blueprint('download_client', __name__)

@download_client_bp.route('/download_client/<client_name>', methods=['GET'])
def download_client(client_name):
    client_path = f"/etc/openvpn/client/{client_name}.ovpn"
    if not os.path.exists(client_path):
        return jsonify({
            'status': 'error', 
            'message': f'Client configuration file {client_name}.ovpn not found in /etc/openvpn/client folder'
        }), 404
        
    # 判断是否为接口请求（例如，通过非浏览器User-Agent）
    user_agent = request.user_agent.string
    if "Mozilla" not in user_agent and "Chrome" not in user_agent and "Safari" not in user_agent:
        # 接口下载
        with open(client_path, 'r') as f:
            content = f.read()
        return jsonify({'status': 'success', 'content': content})
    else:
        # 网页下载
        return send_file(client_path, as_attachment=True, download_name=f"{client_name}.ovpn")
