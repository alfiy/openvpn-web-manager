# routes/auth.py
from flask import Blueprint, render_template, request, jsonify, session, url_for, redirect, flash
from flask_wtf.csrf import generate_csrf
from werkzeug.security import check_password_hash
from datetime import datetime, timedelta, timezone
from flask_mail import Message
import secrets
from flask import current_app
from functools import wraps
import logging
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from itsdangerous import URLSafeTimedSerializer
import re

# 导入 Flask-Login 相关的函数
from flask_login import login_user, logout_user, current_user, login_required

# 请确保这些导入语句与你的项目结构相匹配
from models import db, User, Role

auth_bp = Blueprint('auth_bp', __name__)

@auth_bp.route('/api/csrf-token')
def get_csrf_token():
    """为前端提供CSRF令牌的API端点。"""
    return jsonify({'csrf_token': generate_csrf()})

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """处理用户注册。"""
    if request.method == 'POST':
        username = request.form['username'].strip()
        email    = request.form['email'].strip()
        password = request.form['password'].strip()

        if len(password) < 6:
            return jsonify({'status': 'error', 'message': '密码至少需要6个字符'}), 400
        if User.query.filter((User.username == username) | (User.email == email)).first():
            return jsonify({'status': 'error', 'message': '用户名或邮箱已存在'}), 400

        user = User(username=username, email=email, role=Role.NORMAL)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return jsonify({'status': 'success'})
    return render_template('register.html')

@auth_bp.route('/api/check_auth')
def check_auth():
    """检查用户是否已登录。"""
    return jsonify({'logged_in': current_user.is_authenticated})

def generate_token():
    """生成一个安全的令牌。"""
    return secrets.token_urlsafe(32)

@auth_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    """处理忘记密码请求。"""
    if request.method == 'GET':
        return render_template('forgot_password.html')

    email = request.form.get('email', '').strip()
    user  = User.query.filter_by(email=email).first()

    if not user:
        flash('邮箱未注册', 'danger')
        return redirect(url_for('auth_bp.forgot_password'))

    token = generate_token()
    user.reset_token  = token
    user.reset_expire = datetime.now(timezone.utc) + timedelta(minutes=30)
    db.session.commit()

    link = url_for('auth_bp.reset_password', token=token, _external=True)
    # 邮件发送逻辑，需要配置 mail 实例
    msg = Message('密码重置', recipients=[email])
    msg.body = f'点击链接重置密码 (30分钟内有效): {link}'
    current_app.extensions['mail'].send(msg)

    flash('密码重置邮件已发送，请检查收件箱', 'success')
    return redirect(url_for('auth_bp.login'))

@auth_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """通过令牌重置密码。"""
    user = User.query.filter_by(reset_token=token).first()
    if not user:
        flash('链接无效', 'danger')
        return redirect(url_for('auth_bp.login'))

    if user.reset_expire.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        flash('链接已过期', 'danger')
        return redirect(url_for('auth_bp.login'))

    if request.method == 'POST':
        new_pwd = request.form['password'].strip()
        if len(new_pwd) < 6:
            flash('密码至少需要6个字符', 'danger')
            return redirect(url_for('auth.reset_password', token=token))

        user.set_password(new_pwd)
        user.reset_token = None
        user.reset_expire = None
        db.session.commit()

        flash('密码已重置，请重新登录', 'success')
        return redirect(url_for('auth_bp.login'))

    return render_template('reset_password.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """处理用户登录。"""
    # GET 请求：渲染登录页面（包含 CSRF 令牌）
    if request.method == 'GET':
        return render_template('login.html', csrf_token=generate_csrf())

    # POST 请求：处理登录逻辑
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'status': 'error', 'message': '无效的 JSON 请求'}), 400

    username = data.get('username')
    password = data.get('password')

    user = User.query.filter_by(username=username).first()

    if user and user.check_password(password):
        login_user(user)
        # 登录成功后返回 JSON 响应
        return jsonify({
            'status': 'success',
            'message': '登录成功',
            'redirect': url_for('main_bp.index')
        }), 200
    else:
        # 登录失败时返回 JSON 响应
        return jsonify({
            'status': 'error',
            'message': '用户名或密码不正确'
        }), 401
    

@auth_bp.route('/change_password', methods=['POST'])
@login_required
def change_password():
    """处理用户修改密码。"""
    data = request.get_json() or {}
    old_pwd = data.get('old_pwd', '').strip()
    new_pwd = data.get('new_pwd', '').strip()

    if len(new_pwd) < 6:
        return jsonify(status='error', message='密码至少需要6个字符'), 400

    if not current_user or not current_user.check_password(old_pwd):
        return jsonify({'status': 'error', 'message': '旧密码无效'}), 400

    current_user.set_password(new_pwd)
    db.session.commit()
    return jsonify(status='success', message='密码修改成功')

@auth_bp.route('/logout')
def logout():
    """处理用户注销。"""
    # 使用 Flask-Login 的 logout_user 函数
    logout_user()
    return redirect(url_for('auth_bp.login'))

def admin_required(f):
    """
    一个自定义装饰器，用于限制只有管理员才能访问的路由。
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 如果用户未登录或角色不是管理员或超级管理员，则返回 JSON 错误
        if not current_user.is_authenticated or (current_user.role != Role.ADMIN and current_user.role != Role.SUPER_ADMIN):
            # 返回一个 403 Forbidden 错误，并附带 JSON 消息
            return jsonify({'status': 'error', 'message': '权限不足'}), 403
        return f(*args, **kwargs)
    return decorated_function

@auth_bp.route('/change_user_role', methods=['POST'])
@login_required
@admin_required
def change_user_role():
    """
    管理员或超级管理员切换用户的权限。
    """
    # 记录日志，便于调试
    logging.info(f"User {current_user.id} is attempting to change a user's role.")
    
    try:
        data = request.get_json()
        if not data:
            # 如果请求体不是 JSON，返回错误
            return jsonify({'status': 'error', 'message': '请求需要是JSON格式'}), 400

        user_id = data.get('user_id')
        new_role_str = data.get('new_role')

        if not user_id or not new_role_str:
            return jsonify({'status': 'error', 'message': '缺少用户ID或新角色'}), 400

        # 验证用户ID是否为整数
        try:
            user_id = int(user_id)
        except ValueError:
            return jsonify({'status': 'error', 'message': '用户ID无效'}), 400

        # 检查新角色是否是有效的枚举值
        new_role = new_role_str.upper()
        if new_role not in [role.name for role in Role]:
            return jsonify({'status': 'error', 'message': '新角色无效'}), 400

        # 查找目标用户
        user_to_change = User.query.get(user_id)
        if not user_to_change:
            return jsonify({'status': 'error', 'message': '用户不存在'}), 404

        # 阻止管理员修改超级管理员的权限
        if current_user.role == Role.ADMIN and user_to_change.role == Role.SUPER_ADMIN:
             return jsonify({'status': 'error', 'message': '您无权修改超级管理员的权限'}), 403

        # 阻止用户修改自己的权限
        if user_to_change.id == current_user.id:
            return jsonify({'status': 'error', 'message': '无法修改自己的权限'}), 403

        # 更新用户的角色
        user_to_change.role = Role[new_role]
        db.session.commit()
        
        logging.info(f"User {current_user.id} successfully changed the role of user {user_id} to {new_role}.")
        
        # 返回成功响应
        return jsonify({
            'status': 'success',
            'message': f'用户 {user_to_change.username} 的权限已成功切换到 {new_role}'
        }), 200

    except Exception as e:
        # 捕获所有其他异常，并返回通用错误消息
        logging.error(f"Error changing user role: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': f'服务器内部错误: {str(e)}'}), 500

@auth_bp.route('/reset_user_password', methods=['POST'])
@login_required
@admin_required
def reset_user_password():
    """
    管理员或超级管理员重置用户的密码。
    成功后返回生成的明文密码。
    """
    logging.info(f"User {current_user.id} is attempting to reset a user's password.")
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': '请求需要是JSON格式'}), 400

        user_id = data.get('user_id')
        if not user_id:
            return jsonify({'status': 'error', 'message': '缺少用户ID'}), 400

        # 查找目标用户
        user_to_reset = User.query.get(user_id)
        if not user_to_reset:
            return jsonify({'status': 'error', 'message': '用户不存在'}), 404

        # 阻止管理员重置超级管理员的密码
        if current_user.role == Role.ADMIN and user_to_reset.role == Role.SUPER_ADMIN:
            return jsonify({'status': 'error', 'message': '您无权重置超级管理员的密码'}), 403

        # 阻止用户重置自己的密码
        if user_to_reset.id == current_user.id:
            return jsonify({'status': 'error', 'message': '无法重置自己的密码'}), 403

        # 生成一个16位的复杂密码
        new_password = secrets.token_urlsafe(16)
        
        # 重置密码
        user_to_reset.set_password(new_password)
        db.session.commit()

        logging.info(f"User {current_user.id} successfully reset the password for user {user_to_reset.id}.")
        
        # 返回成功响应，并在消息中包含明文密码
        return jsonify({
            'status': 'success',
            'message': f'密码已成功重置！新密码是: {new_password}',
            'new_password': new_password
        }), 200

    except Exception as e:
        logging.error(f"Error resetting user password: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': f'服务器内部错误: {str(e)}'}), 500

