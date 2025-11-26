from flask import Blueprint

auth_bp = Blueprint('auth_bp', __name__)

# ————— 必须导入路由，否则 Flask 发现不了 —————
from . import routes_user
from . import routes_admin
from . import utils
from . import decorators