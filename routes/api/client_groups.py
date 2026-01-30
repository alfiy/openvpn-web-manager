"""
🆕 客户端用户组管理 API
负责用户组的 CRUD 操作和限速配置
"""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from models import db, ClientGroup, Client, Role
from routes.helpers import role_required
from utils.api_response import api_success, api_error
from utils.tc_config_exporter import export_tc_config
import logging

logger = logging.getLogger(__name__)

client_groups_bp = Blueprint('client_groups', __name__)


# ==================== 获取所有用户组 ====================
@client_groups_bp.route('/api/client_groups', methods=['GET'])
@login_required
def get_client_groups():
    """获取所有用户组列表"""
    try:
        groups = ClientGroup.query.all()
        data = {
            'groups': [group.to_dict() for group in groups],
            'total': len(groups)
        }
        return api_success(data)
    except Exception as e:
        logger.error(f"获取用户组列表失败: {str(e)}")
        return api_error(f"获取用户组列表失败: {str(e)}")


# ==================== 创建用户组 ====================
@client_groups_bp.route('/api/client_groups', methods=['POST'])
@login_required
@role_required([Role.ADMIN, Role.SUPER_ADMIN])
def create_client_group():
    """
    创建新用户组
    请求体：
    {
        "name": "VIP用户组",
        "description": "VIP客户端用户组",
        "upload_rate": "20Mbit",
        "download_rate": "50Mbit"
    }
    """
    try:
        data = request.get_json(silent=True) or {}
        
        # 参数验证
        name = (data.get('name') or '').strip()
        description = (data.get('description') or '').strip()
        upload_rate = (data.get('upload_rate') or '2Mbit').strip()
        download_rate = (data.get('download_rate') or '2Mbit').strip()
        
        if not name:
            return api_error('用户组名称不能为空')
        
        # 检查用户组名称是否已存在
        if ClientGroup.query.filter_by(name=name).first():
            return api_error(f'用户组 "{name}" 已存在')
        
        # 验证速率格式 (例如: 2Mbit, 5Mbit, 10kbit)
        if not validate_rate_format(upload_rate):
            return api_error('上行速率格式无效，应为数字+单位(如：5Mbit)')
        
        if not validate_rate_format(download_rate):
            return api_error('下行速率格式无效，应为数字+单位(如：50Mbit)')
        
        # 创建用户组
        group = ClientGroup(
            name=name,
            description=description,
            upload_rate=upload_rate,
            download_rate=download_rate
        )
        
        db.session.add(group)
        db.session.commit()
        
        # 导出 TC 配置
        export_tc_config()
        
        logger.info(f"用户组创建成功: {name} (上行:{upload_rate}, 下行:{download_rate})")
        return api_success(
            {'group': group.to_dict()},
            message=f'用户组 "{name}" 创建成功'
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"创建用户组失败: {str(e)}")
        return api_error(f'创建用户组失败: {str(e)}')


# ==================== 更新用户组 ====================
@client_groups_bp.route('/api/client_groups/<int:group_id>', methods=['PUT'])
@login_required
@role_required([Role.ADMIN, Role.SUPER_ADMIN])
def update_client_group(group_id):
    """
    更新用户组信息和限速参数
    请求体：
    {
        "name": "新名称",
        "description": "新描述",
        "upload_rate": "10Mbit",
        "download_rate": "30Mbit"
    }
    """
    try:
        group = ClientGroup.query.get(group_id)
        if not group:
            return api_error('用户组不存在', code=404)
        
        data = request.get_json(silent=True) or {}
        
        # 更新字段
        if 'name' in data:
            new_name = (data['name'] or '').strip()
            if not new_name:
                return api_error('用户组名称不能为空')
            # 检查新名称是否被其他组占用
            if new_name.lower() != group.name.lower():
                existing = ClientGroup.query.filter_by(name=new_name).first()
                if existing:
                    return api_error(f'用户组名称 "{new_name}" 已存在')
            group.name = new_name
        
        if 'description' in data:
            group.description = (data['description'] or '').strip()
        
        if 'upload_rate' in data:
            upload_rate = (data['upload_rate'] or '2Mbit').strip()
            if not validate_rate_format(upload_rate):
                return api_error('上行速率格式无效')
            group.upload_rate = upload_rate
        
        if 'download_rate' in data:
            download_rate = (data['download_rate'] or '2Mbit').strip()
            if not validate_rate_format(download_rate):
                return api_error('下行速率格式无效')
            group.download_rate = download_rate
        
        db.session.commit()
        
        # 更新后导出配置
        export_tc_config()
        
        logger.info(f"用户组更新成功: {group.name}")
        return api_success(
            {'group': group.to_dict()},
            message=f'用户组 "{group.name}" 更新成功'
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"更新用户组失败: {str(e)}")
        return api_error(f'更新用户组失败: {str(e)}')


# ==================== 删除用户组 ====================
@client_groups_bp.route('/api/client_groups/<int:group_id>', methods=['DELETE'])
@login_required
@role_required([Role.ADMIN, Role.SUPER_ADMIN])
def delete_client_group(group_id):
    """
    删除用户组
    删除时，该组内的客户端会被移出分组（group_id 置为 NULL）
    """
    try:
        group = ClientGroup.query.get(group_id)
        if not group:
            return api_error('用户组不存在', code=404)
        
        group_name = group.name
        
        # 清除该组内所有客户端的 group_id
        Client.query.filter_by(group_id=group_id).update({'group_id': None})
        db.session.delete(group)
        db.session.commit()
        
        # 导出更新后的配置
        export_tc_config()
        
        logger.info(f"用户组删除成功: {group_name}")
        return api_success(
            message=f'用户组 "{group_name}" 已删除'
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"删除用户组失败: {str(e)}")
        return api_error(f'删除用户组失败: {str(e)}')


# ==================== 向用户组添加成员（客户端）====================
@client_groups_bp.route('/api/client_groups/<int:group_id>/add_member', methods=['POST'])
@login_required
@role_required([Role.ADMIN, Role.SUPER_ADMIN])
def add_group_member(group_id):
    """
    将客户端添加到用户组
    请求体：
    {
        "client_name": "client_001"
    }
    """
    try:
        group = ClientGroup.query.get(group_id)
        if not group:
            return api_error('用户组不存在', code=404)
        
        data = request.get_json(silent=True) or {}
        client_name = (data.get('client_name') or '').strip()
        
        if not client_name:
            return api_error('客户端名称不能为空')
        
        client = Client.query.filter_by(name=client_name).first()
        if not client:
            return api_error(f'客户端 "{client_name}" 不存在')
        
        # 检查客户端是否已在该组
        if client.group_id == group_id:
            return api_error(f'客户端已在 "{group.name}" 组中')
        
        # 如果客户端已在其他组，先移出
        if client.group_id is not None:
            return api_error(
                f'客户端 "{client.name}" 已属于其他用户组，请先移除后再添加'
            )

        client.group_id = group_id
        db.session.commit()
        
        # 导出配置
        export_tc_config()
        
        logger.info(f"客户端 {client_name} 添加到用户组 {group.name}")
        return api_success(
            {'group': group.to_dict()},
            message=f'客户端 "{client_name}" 已添加到组 "{group.name}"'
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"添加成员失败: {str(e)}")
        return api_error(f'添加成员失败: {str(e)}')


# ==================== 从用户组移除成员（客户端）====================
@client_groups_bp.route('/api/client_groups/<int:group_id>/remove_member', methods=['POST'])
@login_required
@role_required([Role.ADMIN, Role.SUPER_ADMIN])
def remove_group_member(group_id):
    """
    将客户端从用户组移除
    请求体：
    {
        "client_name": "client_001"
    }
    """
    try:
        group = ClientGroup.query.get(group_id)
        if not group:
            return api_error('用户组不存在', code=404)
        
        data = request.get_json(silent=True) or {}
        client_name = (data.get('client_name') or '').strip()
        
        if not client_name:
            return api_error('客户端名称不能为空')
        
        client = Client.query.filter_by(name=client_name).first()
        if not client:
            return api_error(f'客户端 "{client_name}" 不存在')
        
        if client.group_id != group_id:
            return api_error(f'客户端不在 "{group.name}" 组中')
        
        client.group_id = None
        db.session.commit()
        
        # 导出配置
        export_tc_config()
        
        logger.info(f"客户端 {client_name} 从用户组 {group.name} 移除")
        return api_success(
            {'group': group.to_dict()},
            message=f'客户端 "{client_name}" 已从组 "{group.name}" 移除'
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"移除成员失败: {str(e)}")
        return api_error(f'移除成员失败: {str(e)}')


# ==================== 获取用户组的成员列表 ====================
@client_groups_bp.route('/api/client_groups/<int:group_id>/members', methods=['GET'])
@login_required
def get_group_members(group_id):
    """获取用户组内的所有客户端"""
    try:
        group = ClientGroup.query.get(group_id)
        if not group:
            return api_error('用户组不存在', code=404)
        
        members = [{
            'id': c.id,
            'name': c.name,
            'description': c.description,
            'online': c.online,
            'disabled': c.disabled,
            'vpn_ip': c.vpn_ip,
        } for c in group.clients]
        
        return api_success({
            'group_id': group_id,
            'group_name': group.name,
            'members': members,
            'total': len(members)
        })
    except Exception as e:
        logger.error(f"获取用户组成员失败: {str(e)}")
        return api_error(f'获取用户组成员失败: {str(e)}')

# ==================== 未分组客户端 ====================
@client_groups_bp.route('/api/clients/unassigned', methods=['GET'])
@login_required
def get_unassigned_clients():
    clients = Client.query.filter(Client.group_id.is_(None)).all()
    return api_success({
        'clients': [
            {'id': c.id, 'name': c.name}
            for c in clients
        ]
    })

# ==================== 辅助函数 ====================
def validate_rate_format(rate_str):
    """
    验证速率格式是否正确
    支持格式: 5Mbit, 10kbit, 100Mbit 等
    """
    import re
    pattern = r'^\d+(\.\d+)?(bit|kbit|Mbit|Gbit)$'
    return bool(re.match(pattern, rate_str))