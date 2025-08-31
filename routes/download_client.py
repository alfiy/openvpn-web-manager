from flask import Blueprint, session, request, jsonify, redirect, url_for, send_file
import os
from routes.helpers import login_required


download_client_bp = Blueprint('download_client', __name__)

@download_client_bp.route('/download_client/<client_name>', methods=['GET'])
@login_required
def download_client(client_name):
    """
    根据客户端名称下载 .ovpn 配置文件。
    - 如果是浏览器请求，则直接触发文件下载。
    - 如果是非浏览器（API）请求，则返回文件内容作为 JSON 字符串。
    """
    client_path = f"/etc/openvpn/client/{client_name}.ovpn"
    
    # 检查文件是否存在
    if not os.path.exists(client_path):
        return jsonify({
            'status': 'error', 
            'message': f'Client configuration file {client_name}.ovpn not found in /etc/openvpn/client folder'
        }), 404
        
    # 判断是否为接口请求（例如，通过非浏览器User-Agent）
    user_agent = request.user_agent.string
    if "Mozilla" not in user_agent and "Chrome" not in user_agent and "Safari" not in user_agent:
        # 接口下载：读取文件内容并作为 JSON 返回
        with open(client_path, 'r') as f:
            content = f.read()
        return jsonify({'status': 'success', 'content': content})
    else:
        # 网页下载：使用 send_file 触发下载
        return send_file(client_path, as_attachment=True, download_name=f"{client_name}.ovpn")

