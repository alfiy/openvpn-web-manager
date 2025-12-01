# routes/api/auth.py
from flask import request
from flask_login import login_user, logout_user, current_user
from . import api_bp
from utils.api_response import api_success, api_error
from models import User
from werkzeug.security import check_password_hash

@api_bp.route('/auth/login', methods=['POST'])
def api_login():
    data = request.get_json(silent=True) or request.form
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return api_error("用户名或密码不能为空", status=400)

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return api_error("用户名或密码不正确", status=401)

    login_user(user)
    return api_success({"redirect": "/"}, msg="登录成功")
