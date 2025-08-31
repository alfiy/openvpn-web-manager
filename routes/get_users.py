from flask import Blueprint, jsonify
from routes.helpers import login_required
from models import User  # 假设你有 SQLAlchemy User 模型

user_bp = Blueprint('user', __name__)

@user_bp.route('/get_users', methods=['GET'])
@login_required
def get_users():
    """
    获取所有用户信息（超级管理员可见）
    返回 JSON 数组，每个用户包含 id, username, role
    """
    try:
        # 从数据库获取所有用户
        users = User.query.all()
        user_list = [{
            'id': user.id,
            'username': user.username,
            'role': user.role
        } for user in users]

        return jsonify(user_list)
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'获取用户列表失败: {str(e)}'
        }), 500
