from flask import render_template, request, jsonify, url_for, redirect, flash, current_app
from flask_wtf.csrf import generate_csrf
from flask_login import login_user, logout_user, current_user, login_required
from models import db, User, Role
from .utils import generate_token, hash_token, utc_now, send_mail
from werkzeug.exceptions import BadRequest
from . import auth_bp
import logging
from datetime import timedelta


# NOTE: web endpoints and API endpoints are separated for clarity.

@auth_bp.route('/csrf-token')
@login_required
def get_csrf_token():
    """Return a CSRF token for the logged-in user's session."""
    return jsonify({'csrf_token': generate_csrf()})

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')


    # Expect form POST for regular website registration
    form = request.form
    username = form.get('username', '').strip()
    email = form.get('email', '').strip().lower()
    password = form.get('password', '')

    if not username or not email or not password:
        return jsonify({'status': 'error', 'message': '缺少字段'}), 400

    if len(password) < 6:
        return jsonify({'status': 'error', 'message': '密码至少需要6个字符'}), 400

    # rely on DB uniqueness constraints and handle IntegrityError
    from sqlalchemy.exc import IntegrityError
    try:
        user = User(username=username, email=email, role=Role.NORMAL)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        current_app.logger.info('注册时冲突: %s', e)
        return jsonify({'status': 'error', 'message': '用户名或邮箱已存在'}), 400

    return jsonify({'status': 'success'}), 201

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # Render login page that posts to /login (form) or calls /api/login for JSON
    return render_template('login.html', csrf_token=generate_csrf())

@auth_bp.route('/api/login', methods=['POST'])
def api_login():
    """API endpoint for JSON login (usage for SPA)."""
    data = request.get_json(silent=True)
    if not data:
        raise BadRequest('请求需要是JSON')

    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'status': 'error', 'message': '缺少用户名或密码'}), 400


    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        login_user(user)
        current_app.logger.info('用户 %s 登录', username)
        return jsonify({'status': 'success', 'redirect': url_for('main_bp.index')}), 200

    # Note: don't reveal whether username exists
    return jsonify({'status': 'error', 'message': '用户名或密码不正确'}), 401

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth_bp.login'))

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'GET':
        return render_template('forgot_password.html')


    email = request.form.get('email', '').strip().lower()
    if not email:
        flash('请填写邮箱', 'danger')
        return redirect(url_for('auth_bp.forgot_password'))

    user = User.query.filter_by(email=email).first()
    if not user:
        # Do not reveal whether email exists — show generic message
        flash('如果该邮箱已注册，重置邮件会在稍后发送', 'info')
        return redirect(url_for('auth_bp.login'))

    raw_token = generate_token(32)
    user.reset_token = hash_token(raw_token)
    user.reset_expire = utc_now() + timedelta(minutes=30)
    db.session.commit()


    link = url_for('auth_bp.reset_password_page', token=raw_token, _external=True)
    body = f'点击链接重置密码 (30分钟内有效): {link}\n\n如果不是你本人请求，请忽略此邮件。'
    try:
        send_mail('密码重置', [email], body)
    except Exception as e:
        current_app.logger.exception('发送重置邮件失败: %s', e)
        flash('邮件发送失败，请稍后重试', 'danger')
        return redirect(url_for('auth_bp.forgot_password'))

    flash('如果该邮箱已注册，重置邮件会在稍后发送', 'success')
    return redirect(url_for('auth_bp.login'))


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password_page(token):
    # token is the raw token user received via email
    if request.method == 'GET':
        return render_template('reset_password.html', token=token)

    password = request.form.get('password', '')
    if len(password) < 6:
        flash('密码至少需要6个字符', 'danger')
        return redirect(url_for('auth_bp.reset_password_page', token=token))

    hashed = hash_token(token)
    user = User.query.filter_by(reset_token=hashed).first()
    if not user:
        flash('链接无效或已使用', 'danger')
        return redirect(url_for('auth_bp.login'))

    if not user.reset_expire or user.reset_expire < utc_now():
        flash('链接已过期', 'danger')
        return redirect(url_for('auth_bp.login'))

    user.set_password(password)
    user.reset_token = None
    user.reset_expire = None
    db.session.commit()

    flash('密码已重置，请重新登录', 'success')
    return redirect(url_for('auth_bp.login'))

@auth_bp.route('/api/change-password', methods=['POST'])
@login_required
def api_change_password():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'status': 'error', 'message': '请求需要是JSON'}), 400

    old_pwd = data.get('old_pwd', '')
    new_pwd = data.get('new_pwd', '')

    if len(new_pwd) < 6:
        return jsonify({'status': 'error', 'message': '密码至少需要6个字符'}), 400

    if not current_user.check_password(old_pwd):
        return jsonify({'status': 'error', 'message': '旧密码无效'}), 400

    current_user.set_password(new_pwd)
    db.session.commit()
    return jsonify({'status': 'success', 'message': '密码修改成功'})