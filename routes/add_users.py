# routes/add_users.py
from flask import Blueprint, request, jsonify
from routes.helpers import login_required, role_required
from models import db, User, Role
from utils.password_validator import PasswordValidator


add_users_bp = Blueprint('add_users', __name__)

@add_users_bp.route('/add_users', methods=['POST'])
@login_required
@role_required([Role.SUPER_ADMIN])
def add_users():
    """
    新增用户接口（JSON）
    """
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({'status': 'error', 'message': '请求需要是JSON'}), 400
    
    username = (data.get('username') or '').strip()
    email = (data.get('email') or '').strip()
    password = (data.get('password') or '').strip()
    # 原始的字符串角色名
    role_str = (data.get('role') or 'NORMAL').strip()

    if not username or not email or not password:
        return jsonify({'status': 'error', 'message': '用户名、邮箱和密码不能为空'}), 400
    
    # 验证密码强度（前端已验证一致性）
    is_valid, error_msg = PasswordValidator.validate_strength(password)
    if not is_valid:
        return jsonify({'status': 'error', 'message': error_msg}), 400

    # ✅ 修复：将字符串转换为 Role 枚举成员
    try:
        role = Role[role_str]
    except KeyError:
        return jsonify({'status': 'error', 'message': '角色无效'}), 400

    # 检查用户名或邮箱是否已存在
    if User.query.filter((User.username == username) | (User.email == email)).first():
        return jsonify({'status': 'error', 'message': '用户名或邮箱已存在'}), 400

    try:
        # ✅ 修复：将转换后的 role 枚举对象传递给 User 构造函数
        user = User(username=username, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return jsonify({'status': 'success', 'message': f'用户 {username} 已成功创建'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': f'创建用户失败: {str(e)}'}), 500