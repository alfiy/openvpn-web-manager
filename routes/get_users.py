from flask import Blueprint, jsonify
from routes.helpers import login_required
from models import User

user_bp = Blueprint('user', __name__)

@user_bp.route('/get_users', methods=['GET'])
@login_required
def get_users():
    """
    获取所有用户信息（超级管理员可见）
    返回 JSON 对象，包含 status 和 users
    """
    try:
        users = User.query.all()
        user_list = [{
            'id': user.id,
            'username': user.username,
            'email': user.email,
            # 将 user.role 对象转换为字符串，例如访问它的 name 属性
            'role': user.role.name  # <-- 关键改动在这里
        } for user in users]

        return jsonify({
            'status': 'success',
            'users': user_list
        }), 200
    except Exception as e:
        print(f"Error fetching users: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'获取用户列表失败，请检查服务器日志。错误信息：{str(e)}'
        }), 500