from flask import Blueprint, request
from datetime import datetime, timezone
from routes.helpers import login_required
from models import Client, db
from utils.openvpn_utils import log_message
from utils.api_response import api_success, api_error
import os
import subprocess

enable_client_bp = Blueprint('enable_client', __name__)

def enable_client(client_name):
    """
    启用客户端:
    - 删除 CCD 禁用文件
    - 更新数据库: client.disabled = False
    """
    ccd_dir = '/etc/openvpn/ccd'
    disable_file_path = os.path.join(ccd_dir, client_name)
    
    # 删除 CCD 禁用文件
    if os.path.exists(disable_file_path):
        try:
            subprocess.run(
                ['sudo', 'rm', '-f', disable_file_path],
                capture_output=True,
                text=True,
                check=True
            )
            log_message(f"已删除客户端 {client_name} 的禁用文件")
        except subprocess.CalledProcessError as e:
            raise Exception(f"删除禁用文件失败: {e.stderr}")
    
    # 更新数据库: client.disabled = False
    client = Client.query.filter_by(name=client_name).first()
    if client:
        client.disabled = False
        db.session.commit()
        log_message(f"数据库更新: 客户端 {client_name} disabled=False")

@enable_client_bp.route('/api/clients/enable', methods=['POST'])
@login_required
def api_enable_client():
    """
    重新启用客户端:
    - 如果客户端是到期禁用,返回特殊状态码,前端弹出修改到期时间页面
    - 如果客户端是手动禁用(未到期),直接启用
    """
    try:
        data = request.get_json()
        if not data:
            log_message("请求数据格式错误")
            return api_error("请求数据格式错误", status=400)
        
        client_name = data.get('client_name', '').strip()
        if not client_name:
            log_message("客户端名称不能为空")
            return api_error("客户端名称不能为空", status=400)
        
        # 查询客户端
        client = Client.query.filter_by(name=client_name).first()
        if not client:
            log_message(f"客户端 {client_name} 不存在")
            return api_error("客户端不存在", status=404)
        
        # 如果客户端未被禁用
        if not client.disabled:
            log_message(f"客户端 {client_name} 当前未被禁用")
            return api_success(
                message=f"客户端 {client_name} 当前未被禁用,无需启用",
                data={"client_name": client_name, "disabled": False}
            )
        
        # 获取到期时间
        expiry_time = None
        if hasattr(client, 'logical_expiry') and client.logical_expiry:
            expiry_time = client.logical_expiry
        elif client.expiry:
            expiry_time = client.expiry
        
        # 如果没有到期时间,直接启用(视为手动禁用)
        if not expiry_time:
            log_message(f"客户端 {client_name} 未设置到期时间,视为手动禁用,直接启用")
            enable_client(client_name)
            return api_success(
                message=f"客户端 {client_name} 已成功重新启用",
                data={"client_name": client_name, "action": "enabled"}
            )
        
        # 统一时区处理
        current_time = datetime.now(timezone.utc)
        if expiry_time.tzinfo is None:
            expiry_time = expiry_time.replace(tzinfo=timezone.utc)
        
        # 判断是否到期
        if expiry_time <= current_time:
            # 到期禁用 - 返回特殊状态,要求前端弹出修改到期时间页面
            log_message(f"客户端 {client_name} 因到期被禁用,需要先延长到期时间")
            
            # ⭐ 返回特殊状态码,前端根据此状态弹出修改到期时间页面
            return {
                "status": "require_expiry_update",  # 特殊状态标识
                "message": f"客户端 {client_name} 已到期,请先延长到期时间",
                "data": {
                    "client_name": client_name,
                    "current_expiry": expiry_time.isoformat(),
                    "action_required": "modify_expiry"
                }
            }, 200  # 使用 200 状态码,但返回特殊 status 字段
        else:
            # 未到期但被禁用 - 手动禁用,直接启用
            log_message(f"客户端 {client_name} 未到期但被禁用,视为手动禁用,直接启用")
            enable_client(client_name)
            return api_success(
                message=f"客户端 {client_name} 已成功重新启用",
                data={
                    "client_name": client_name, 
                    "action": "enabled",
                    "expiry_time": expiry_time.isoformat()
                }
            )
    
    except Exception as e:
        db.session.rollback()
        log_message(f"启用客户端出现意外错误: {str(e)}")
        return api_error(f"启用客户端出现意外错误: {str(e)}", status=500)