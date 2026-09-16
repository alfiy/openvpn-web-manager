"""
🆕 客户端用户组管理 API
负责用户组的 CRUD 操作和限速配置
"""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from models import db, ClientGroup, Client, Role
from routes.helpers import role_required
from utils.api_response import api_success, api_error
from utils.validation import ValidationError, validate_client_name, validate_group_name, validate_rate
from utils.tc_config_exporter import export_tc_config
from openvpn_monitor.tc_hotreload import notify_user_update, notify_role_update
import logging

logger = logging.getLogger(__name__)

client_groups_bp = Blueprint('client_groups', __name__)

# ==================== 获取所有用户组 ====================
@client_groups_bp.route('/api/client_groups', methods=['GET'])
@login_required
def get_client_groups():
    """获取所有用户组列表"""
    try:
        # ⭐ 最彻底的方式：关闭当前会话，强制全新查询
        db.session.close()
        
        # 重新查询所有组
        groups = ClientGroup.query.all()
        
        # ⭐ 关键：强制重新加载每个组的 clients 关联
        result = []
        for group in groups:
            # 强制刷新组对象
            db.session.refresh(group)
            
            # ⭐ 关键：显式查询该组的客户端数量（完全绕过缓存）
            count = db.session.query(Client).filter_by(group_id=group.id).count()
            
            result.append({
                'id': group.id,
                'name': group.name,
                'description': group.description,
                'upload_rate': group.upload_rate,
                'download_rate': group.download_rate,
                'is_default': group.name.lower() == 'default',
                'client_count': count,  # 使用显式查询的计数
                'created_at': group.created_at.isoformat() if group.created_at else None
            })
        
        return api_success({
            'groups': result,
            'total': len(result)
        })
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
        try:
            name = validate_group_name((data.get('name') or '').strip())
            upload_rate = validate_rate((data.get('upload_rate') or '2Mbit').strip())
            download_rate = validate_rate((data.get('download_rate') or '2Mbit').strip())
        except ValidationError as exc:
            return api_error(str(exc))
        description = (data.get('description') or '').strip()
        
        # 检查用户组名称是否已存在
        if ClientGroup.query.filter_by(name=name).first():
            return api_error(f'用户组 "{name}" 已存在')
        
        # 创建用户组
        group = ClientGroup(
            name=name,
            description=description,
            upload_rate=upload_rate,
            download_rate=download_rate
        )
        
        db.session.add(group)
        db.session.commit()
        
        # 🆕 导出 TC 配置
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
        
        # 🆕 记录是否修改了速率
        rate_changed = False
        old_upload = group.upload_rate
        old_download = group.download_rate
        
        # 更新字段
        if 'name' in data:
            try:
                new_name = validate_group_name((data['name'] or '').strip())
            except ValidationError as exc:
                return api_error(str(exc))
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
            try:
                upload_rate = validate_rate(upload_rate)
            except ValidationError as exc:
                return api_error(str(exc))
            if group.upload_rate != upload_rate:
                rate_changed = True
            group.upload_rate = upload_rate
        
        if 'download_rate' in data:
            download_rate = (data['download_rate'] or '2Mbit').strip()
            try:
                download_rate = validate_rate(download_rate)
            except ValidationError as exc:
                return api_error(str(exc))
            if group.download_rate != download_rate:
                rate_changed = True
            group.download_rate = download_rate
        
        db.session.commit()
        
        # 🆕 导出配置文件
        export_tc_config()
        
        # 🆕 如果速率有变化，通知守护进程热更新
        if rate_changed:
            success = notify_role_update(group.name)
            logger.info(
                f"用户组 {group.name} 速率已更新: "
                f"{old_upload}/{old_download} → {group.upload_rate}/{group.download_rate}，"
                f"热更新{'成功' if success else '失败'}"
            )
        
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
        
        # 🆕 导出更新后的配置
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
        try:
            client_name = validate_client_name((data.get('client_name') or '').strip())
        except ValidationError as exc:
            return api_error(str(exc))
        
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
        
        # 🆕 导出配置
        export_tc_config()
        
        # 🆕 如果客户端在线，发送热更新信号
        if client.online and client.vpn_ip:
            success = notify_user_update(client.name, client.vpn_ip)
            logger.info(
                f"客户端 {client_name} 添加到用户组 {group.name}，"
                f"热更新{'成功' if success else '失败'}"
            )
        else:
            logger.info(f"客户端 {client_name} 添加到用户组 {group.name}（离线）")
        
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
        try:
            client_name = validate_client_name((data.get('client_name') or '').strip())
        except ValidationError as exc:
            return api_error(str(exc))
        
        client = Client.query.filter_by(name=client_name).first()
        if not client:
            return api_error(f'客户端 "{client_name}" 不存在')
        
        if client.group_id != group_id:
            return api_error(f'客户端不在 "{group.name}" 组中')
        
        client.group_id = None
        db.session.commit()
        
        # 🆕 导出配置
        export_tc_config()
        
        # 🆕 如果客户端在线，发送热更新信号（移除限速）
        if client.online and client.vpn_ip:
            success = notify_user_update(client.name, client.vpn_ip)
            logger.info(
                f"客户端 {client_name} 从用户组 {group.name} 移除，"
                f"热更新{'成功' if success else '失败'}"
            )
        else:
            logger.info(f"客户端 {client_name} 从用户组 {group.name} 移除（离线）")
        
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

# ==================== 修改客户端所属用户组 ====================
@client_groups_bp.route('/api/clients/modify_group', methods=['POST'])
@login_required
@role_required([Role.ADMIN, Role.SUPER_ADMIN])
def modify_client_group():
    """
    修改客户端所属的用户组
    请求体：
    {
        "client_name": "client_001",
        "group": "普通用户组"  // 空字符串或 null 表示移出分组
    }
    """
    try:
        data = request.get_json(silent=True) or {}
        try:
            client_name = validate_client_name((data.get('client_name') or '').strip())
        except ValidationError as exc:
            return api_error(str(exc))
        group_name = data.get('group')
        
        # 查找客户端
        client = Client.query.filter_by(name=client_name).first()
        if not client:
            return api_error(f'客户端 "{client_name}" 不存在')
        
        # 如果 group 为空字符串或 null，表示移出分组
        if not group_name or group_name.strip() == '':
            old_group_name = client.group.name if client.group else '无'
            client.group_id = None
            db.session.commit()
            
            # 🆕 导出配置文件
            export_tc_config()
            
            # 🆕 如果客户端在线，发送热更新信号
            if client.online and client.vpn_ip:
                success = notify_user_update(client.name, client.vpn_ip)
                logger.info(
                    f"客户端 {client_name} 从用户组 {old_group_name} 移出，"
                    f"热更新{'成功' if success else '失败'}"
                )
            else:
                logger.info(f"客户端 {client_name} 从用户组 {old_group_name} 移出（离线）")
            
            return api_success(
                {'client': client.to_dict()},
                message=f'客户端 "{client_name}" 已移出用户组'
            )
        
        # 查找目标用户组
        group_name = group_name.strip()
        group = ClientGroup.query.filter_by(name=group_name).first()
        if not group:
            return api_error(f'用户组 "{group_name}" 不存在')
        
        # 检查是否已经在该组
        if client.group_id == group.id:
            return api_error(f'客户端已在 "{group_name}" 组中')
        
        # 更新用户组
        old_group_name = client.group.name if client.group else '无'
        client.group_id = group.id
        db.session.commit()
        
        # 🆕 导出配置文件
        export_tc_config()
        
        # 🆕 如果客户端在线，发送热更新信号
        if client.online and client.vpn_ip:
            success = notify_user_update(client.name, client.vpn_ip)
            logger.info(
                f"客户端 {client_name} 从 {old_group_name} 移动到 {group_name}，"
                f"热更新{'成功' if success else '失败'}"
            )
        else:
            logger.info(f"客户端 {client_name} 从 {old_group_name} 移动到 {group_name}（离线）")
        
        return api_success(
            {'client': client.to_dict()},
            # message=f'客户端 "{client_name}" 已移动到 "{group_name}"'
        )
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"修改客户端用户组失败: {str(e)}")
        return api_error(f'修改用户组失败: {str(e)}')
    
    
# ==================== 未分组客户端 ====================
@client_groups_bp.route('/api/clients/unassigned', methods=['GET'])
@login_required
def get_unassigned_clients():
    """获取所有未分组的客户端"""
    clients = Client.query.filter(Client.group_id.is_(None)).all()
    return api_success({
        'clients': [
            {'id': c.id, 'name': c.name, 'description': c.description}
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