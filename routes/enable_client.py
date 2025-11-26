from flask import Blueprint, request, jsonify
import os
import subprocess
from utils.openvpn_utils import log_message
from routes.helpers import login_required

enable_client_bp = Blueprint('enable_client', __name__)

@enable_client_bp.route('/enable_client', methods=['POST'])
@login_required
def enable_client():
    """通过删除文件来重新启用客户端"""
    try:
        data = request.get_json()
        if not data:
            log_message("请求数据格式错误")
            return jsonify({'status': 'error', 'message': '请求数据格式错误'}), 400
        
        client_name = data.get('client_name', '').strip()
        if not client_name:
            log_message("客户端名称不能为空")
            return jsonify({'status': 'error', 'message': '客户端名称不能为空'}), 400

        log_message(f"正在为客户端 {client_name} 启动重新启用流程")

        ccd_dir = '/etc/openvpn/ccd'
        disable_file_path = os.path.join(ccd_dir, client_name)

        if not os.path.exists(disable_file_path):
            log_message(f"客户端 {client_name} 已经处于启用状态或文件 {disable_file_path} 不存在。")
            return jsonify({
                'status': 'warning',
                'message': f'客户端 {client_name} 已经处于启用状态。'
            })

        try:
            cmd = ['sudo', 'rm', '-f', disable_file_path]
            log_message(f"执行命令：{' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            log_message(f"命令执行成功：{result.stdout}")
        except subprocess.CalledProcessError as e:
            log_message(f"重新启用过程失败：{e.stderr}")
            return jsonify({'status': 'error', 'message': f'删除文件失败：{e.stderr}'}), 500

        log_message(f"成功重新启用客户端：{client_name}")
        return jsonify({
            'status': 'success',
            'message': f'客户端 {client_name} 已成功重新启用。'
        })

    except Exception as e:
        log_message(f"重新启用过程中发生意外错误：{str(e)}")
        return jsonify({'status': 'error', 'message': f'重新启用过程中发生意外错误：{str(e)}'}), 500