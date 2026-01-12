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
    修改客户端逻辑到期时间(不再吊销/重新颁发证书)
    - 只更新数据库的 expiry 或 logical_expiry 字段
    - 如果客户端当前被禁用,则启用它
    - 新的到期时间到达后,由定时任务自动禁用
    """
    data = request.get_json()
    client_name = data.get('client_name')
    expiry_days = data.get('expiry_days')

    if not client_name or not expiry_days:
        return jsonify({
            'status': 'error',
            'message': 'Client name and expiry days are required'
        })

    client_name = client_name.strip()
    if not client_name:
        return jsonify({
            'status': 'error',
            'message': 'Client name is required'
        })

    try:
        expiry_days = int(expiry_days)
        if expiry_days <= 0:
            return jsonify({
                'status': 'error',
                'message': 'Expiry days must be positive'
            })
    except ValueError:
        return jsonify({
            'status': 'error',
            'message': 'Invalid expiry days format'
        })

    try:
        # 查找客户端
        client = Client.query.filter_by(name=client_name).first()
        if not client:
            return jsonify({
                'status': 'error',
                'message': f'客户端 {client_name} 不存在'
            })

        # 计算新的到期时间
        new_expiry_date = datetime.now() + timedelta(days=expiry_days)
        expiry_date_str = new_expiry_date.strftime('%Y-%m-%d')

        # 更新数据库(使用 logical_expiry 如果存在,否则使用 expiry)
        if hasattr(client, 'logical_expiry'):
            client.logical_expiry = new_expiry_date
        else:
            client.expiry = new_expiry_date
        
        # 如果客户端当前被禁用,则启用它
        was_disabled = client.disabled
        if client.disabled:
            client.disabled = False
            
            # 删除 CCD 禁用文件
            ccd_dir = '/etc/openvpn/ccd'
            disable_file_path = os.path.join(ccd_dir, client_name)
            if os.path.exists(disable_file_path):
                try:
                    subprocess.run(
                        ['sudo', 'rm', '-f', disable_file_path],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                except subprocess.CalledProcessError as e:
                    print(f"[WARN] 删除禁用文件失败: {e.stderr}")

        db.session.commit()

        message = f'客户端 {client_name} 的到期时间已更新为 {expiry_days} 天(到期日:{expiry_date_str})'
        if was_disabled:
            message += ',客户端已重新启用'
        message += '。证书本身保持10年有效期不变,无需重新下发证书。'

        return jsonify({
            'status': 'success',
            'message': message
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': f'修改到期时间失败: {str(e)}'
        })