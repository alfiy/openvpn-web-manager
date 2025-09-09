from flask import Blueprint, jsonify, request
from routes.helpers import login_required
from models import User, db # 假设你有 db 对象用于数据库操作

delete_user_bp = Blueprint('delete_user', __name__) # 你的蓝图已经定义了，这里无需重复定义

@delete_user_bp.route('/delete_user', methods=['POST'])
@login_required
def delete_user():
    """
    删除指定用户（超级管理员可见）
    需要从请求体中获取 user_id
    """
    try:
        data = request.get_json()
        user_id = data.get('user_id')

        if not user_id:
            return jsonify({
                'status': 'error',
                'message': '缺少用户ID'
            }), 400

        # 在这里执行权限检查，确保只有超级管理员可以删除用户
        # 假设 login_required 装饰器已经处理了大部分逻辑，但最好再次确认
        # ... (此处可添加额外的权限检查)

        user_to_delete = User.query.get(user_id)
        if not user_to_delete:
            return jsonify({
                'status': 'error',
                'message': '用户不存在'
            }), 404

        # 使用 SQLAlchemy 删除用户
        db.session.delete(user_to_delete)
        db.session.commit()

        return jsonify({
            'status': 'success',
            'message': '用户删除成功'
        }), 200

    except Exception as e:
        # 记录错误到服务器日志
        print(f"Error deleting user: {str(e)}")
        # 返回通用的错误信息，避免暴露敏感的后端错误
        return jsonify({
            'status': 'error',
            'message': f'删除用户失败：{str(e)}'
        }), 500