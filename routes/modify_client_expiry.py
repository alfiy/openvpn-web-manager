from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from routes.helpers import login_required
from models import Client, db
import os
import subprocess

modify_client_expiry_bp = Blueprint('modify_client_expiry', __name__)

@modify_client_expiry_bp.route('/api/clients/modify_expiry', methods=['POST'])
@login_required
def modify_client_expiry():
    """
    修改客户端逻辑到期时间（支持 expiry_days 或 expiry_date）
    - 如果客户端当前被禁用，则启用它
    - 证书本身保持10年有效期不变
    """
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': '请求数据格式错误'}), 400

    client_name = data.get('client_name', '').strip()
    expiry_days = data.get('expiry_days')
    expiry_date = data.get('expiry_date')  # 新字段

    if not client_name:
        return jsonify({'status': 'error', 'message': '客户端名称不能为空'}), 400

    # 计算新的到期时间
    try:
        if expiry_date:
            # 支持 YYYY-MM-DD 或 ISO 格式
            try:
                new_expiry_date = datetime.fromisoformat(expiry_date)
            except ValueError:
                return jsonify({'status': 'error', 'message': 'expiry_date 格式无效,应为 YYYY-MM-DD'}), 400
        elif expiry_days:
            expiry_days = int(expiry_days)
            if expiry_days <= 0:
                return jsonify({'status': 'error', 'message': 'expiry_days 必须为正整数'}), 400
            new_expiry_date = datetime.now() + timedelta(days=expiry_days)
        else:
            return jsonify({'status': 'error', 'message': '必须提供 expiry_days 或 expiry_date'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'解析到期时间失败: {str(e)}'}), 400

    try:
        # 查找客户端
        client = Client.query.filter_by(name=client_name).first()
        if not client:
            return jsonify({'status': 'error', 'message': f'客户端 {client_name} 不存在'}), 404

        # 更新数据库（logical_expiry 优先）
        if hasattr(client, 'logical_expiry'):
            client.logical_expiry = new_expiry_date
        else:
            client.expiry = new_expiry_date

        # 如果客户端被禁用,启用它并删除 CCD 文件
        was_disabled = client.disabled
        if client.disabled:
            client.disabled = False
            ccd_dir = '/etc/openvpn/ccd'
            disable_file_path = os.path.join(ccd_dir, client_name)
            if os.path.exists(disable_file_path):
                try:
                    subprocess.run(['sudo', 'rm', '-f', disable_file_path],
                                   capture_output=True, text=True, check=True)
                except subprocess.CalledProcessError as e:
                    print(f"[WARN] 删除禁用文件失败: {e.stderr}")

        db.session.commit()

        expiry_date_str = new_expiry_date.strftime('%Y-%m-%d')
        message = f'客户端 {client_name} 的到期时间已更新为 {expiry_date_str}'
        if was_disabled:
            message += ', 客户端已重新启用'
        message += '。证书本身保持10年有效期不变,无需重新下发证书。'

        return jsonify({'status': 'success', 'message': message})

    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': f'修改到期时间失败: {str(e)}'}), 500
