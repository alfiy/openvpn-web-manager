# routes/api/auth.py
from flask import request, session
from flask_login import login_user, logout_user, current_user
from flask_limiter.util import get_remote_address
from . import api_bp
from utils.api_response import api_success, api_error
from models import User
from extensions import limiter, login_user_key

@api_bp.route('/auth/login', methods=['POST'])
@limiter.limit("10 per minute", key_func=get_remote_address)
@limiter.limit("5 per minute", key_func=login_user_key)
def api_login():
    data = request.get_json(silent=True) or request.form
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return api_error("用户名或密码不能为空", status=400)

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return api_error("用户名或密码不正确", status=401)

    if user.check_password('admin123'):
        user.must_change_password = True
        from models import db
        db.session.commit()
    login_user(user, remember=False)
    session.permanent = True
    return api_success({
        "redirect": "/",
        "must_change_password": bool(user.must_change_password),
    }, message="登录成功" if not user.must_change_password else "请先修改默认密码")
