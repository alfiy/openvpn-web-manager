# routes/api/enable_client.py
import os
import subprocess
from flask import Blueprint, request
from utils.openvpn_utils import log_message
from routes.helpers import login_required
from models import db, Client
from sqlalchemy.exc import SQLAlchemyError
from utils.api_response import api_success, api_error   # ⭐ 统一格式

enable_client_bp = Blueprint('enable_client', __name__)

@enable_client_bp.route('/api/clients/enable', methods=['POST'])
@login_required
def api_enable_client():
    """重新启用客户端：删除 CCD disable 文件 + 更新数据库 disabled=False"""
    try:
        data = request.get_json()
        if not data:
            log_message("请求数据格式错误")
            return api_error("请求数据格式错误", status=400)

        client_name = data.get('client_name', '').strip()
        if not client_name:
            log_message("客户端名称不能为空")
            return api_error("客户端名称不能为空", status=400)

        ccd_dir = '/etc/openvpn/ccd'
        disable_file_path = os.path.join(ccd_dir, client_name)

        # 若文件不存在 → 客户端已经启用
        if not os.path.exists(disable_file_path):
            log_message(f"客户端 {client_name} 已经启用（文件不存在）")
            return api_success(
                message=f"客户端 {client_name} 已处于启用状态。",
                data={"client_name": client_name}
            )

        # 删除 disable 文件
        try:
            cmd = ['sudo', 'rm', '-f', disable_file_path]
            subprocess.run(cmd, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            log_message(f"删除 disable 文件失败：{e.stderr}")
            return api_error(f"删除文件失败：{e.stderr}", status=500)

        # 更新数据库：disabled=False
        try:
            client = Client.query.filter_by(name=client_name).first()
            if client:
                client.disabled = False
                db.session.commit()
                log_message(f"数据库更新：客户端 {client_name} disabled=False")
            else:
                log_message(f"数据库中未找到客户端：{client_name}")
        except SQLAlchemyError as e:
            db.session.rollback()
            log_message(f"数据库更新失败：{e}")
            return api_error(f"数据库更新失败：{e}", status=500)

        # 成功响应（与 /clients/disable 保持一致）
        return api_success(
            message=f"客户端 {client_name} 已成功重新启用",
            data={"client_name": client_name}
        )

    except Exception as e:
        log_message(f"启用客户端出现意外错误：{str(e)}")
        return api_error(f"启用客户端出现意外错误：{str(e)}", status=500)
