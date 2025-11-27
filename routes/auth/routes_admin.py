from flask import jsonify,request
from flask_login import login_required, current_user
from .decorators import admin_required
from . import auth_bp
from models import db, User, Role
from .utils import generate_strong_password
import logging
from datetime import timedelta
import logging

# 配置日志级别
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@auth_bp.route('/admin/change-user-role', methods=['POST'])
@login_required
@admin_required
def change_user_role():
    logging.info('User %s is attempting to change a user role', current_user.id)
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'status': 'error', 'message': '请求需要是JSON'}), 400

    try:
        user_id = int(data.get('user_id'))
    except Exception:
        return jsonify({'status': 'error', 'message': '用户ID无效'}), 400

    new_role_str = (data.get('new_role') or '').upper()
    if not new_role_str or new_role_str not in {r.name for r in Role}:
        return jsonify({'status': 'error', 'message': '新角色无效'}), 400

    target = User.query.get(user_id)
    if not target:
        return jsonify({'status': 'error', 'message': '用户不存在'}), 404

    # Admins cannot modify SUPER_ADMIN
    if current_user.role == Role.ADMIN and target.role == Role.SUPER_ADMIN:
        return jsonify({'status': 'error', 'message': '您无权修改超级管理员的权限'}), 403

    if target.id == current_user.id:
        return jsonify({'status': 'error', 'message': '无法修改自己的权限'}), 403

    try:
        target.role = Role[new_role_str]
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logging.exception('修改权限失败: %s', e)
        return jsonify({'status': 'error', 'message': '服务器内部错误'}), 500

    return jsonify({'status': 'success', 'message': f'用户 {target.username} 的权限已切换为 {new_role_str}'}), 200


@auth_bp.route('/admin/reset-user-password', methods=['POST'])
@login_required
@admin_required
def reset_user_password():
    # logger.info('=' * 50)
    # logger.info('重置密码请求开始')
    # logger.info('当前用户 ID: %s', current_user.id)
    # logger.info('请求方法: %s', request.method)
    # logger.info('请求头: %s', dict(request.headers))
    
    data = request.get_json(silent=True)
    # logger.info('接收到的数据: %s', data)
    
    if not data:
        logger.error('❌ 请求体不是 JSON 格式')
        return jsonify({'status': 'error', 'message': '请求需要是JSON'}), 400

    try:
        user_id = int(data.get('user_id'))
        # logger.info('目标用户 ID: %s', user_id)
    except Exception as e:
        logger.error('❌ 用户ID解析失败: %s', e)
        return jsonify({'status': 'error', 'message': '用户ID无效'}), 400

    target = User.query.get(user_id)
    if not target:
        logger.error('❌ 用户不存在: %s', user_id)
        return jsonify({'status': 'error', 'message': '用户不存在'}), 404

    # logger.info('找到目标用户: %s (role=%s)', target.username, target.role)

    if current_user.role == Role.ADMIN and target.role == Role.SUPER_ADMIN:
        # logger.warning('⚠️ ADMIN 尝试重置 SUPER_ADMIN 密码')
        return jsonify({'status': 'error', 'message': '您无权重置超级管理员的密码'}), 403

    if target.id == current_user.id:
        # logger.warning('⚠️ 用户尝试重置自己的密码')
        return jsonify({'status': 'error', 'message': '无法重置自己的密码'}), 403

    new_password = generate_strong_password(16)
    # logger.info('生成新密码 (长度: %d)', len(new_password))
    
    try:
        target.set_password(new_password)
        db.session.commit()
        # logger.info('✅ 密码重置成功')
    except Exception as e:
        db.session.rollback()
        logger.exception('❌ 数据库操作失败: %s', e)
        return jsonify({'status': 'error', 'message': '服务器内部错误'}), 500

    # logger.info('=' * 50)
    return jsonify({'status': 'success', 'message': '密码已重置', 'new_password': new_password}), 200
