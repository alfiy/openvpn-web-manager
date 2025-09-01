# routes/auth.py
from flask import Blueprint, render_template, request, jsonify, session, url_for, redirect, flash
from flask_wtf.csrf import generate_csrf
from werkzeug.security import check_password_hash
from datetime import datetime, timedelta, timezone
from flask_mail import Message
import secrets
from flask import current_app

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

@auth_bp.route('/api/check_auth')
def check_auth():
    """检查用户是否已登录。"""
    return jsonify({'logged_in': current_user.is_authenticated})