import subprocess
from flask import Blueprint, jsonify, request
from routes.helpers import login_required
from flask_login import current_user

# 创建一个蓝图，用于组织和管理与OpenVPN服务相关的路由
restart_openvpn_bp = Blueprint('restart_openvpn', __name__)

# --- 后端逻辑 ---

@restart_openvpn_bp.route("/api/restart_openvpn", methods=["POST"])
@login_required
def restart_openvpn():
    """
    处理重启OpenVPN服务的API请求。
    该路由通过POST请求触发，执行一个系统命令来重启openvpn@server服务。
    """

    # 确保只有具有适当权限（例如 SUPER_ADMIN）的用户才能执行此操作。
    if not current_user.is_authenticated or current_user.role.name != 'SUPER_ADMIN':
        return jsonify({
            'status': 'error',
            'message': '权限不足，无法执行此操作。'
        }), 403 # 返回 403 Forbidden 状态码
    
    try:
        # 使用subprocess.run()执行命令。
        # 'sudo'是必需的，因为重启服务通常需要root权限。
        # check=True 将在命令返回非零退出代码时抛出 CalledProcessError。
        # capture_output=True 将捕获 stdout 和 stderr。
        # text=True 将以文本模式处理输出，而不是字节。
        command = "sudo systemctl restart openvpn@server"
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True
        )

        # 命令成功执行，返回成功响应
        print(f"OpenVPN服务重启成功。\n输出: {result.stdout}")
        return jsonify({"success": True, "message": "OpenVPN服务已成功重启"})

    except subprocess.CalledProcessError as e:
        # 命令执行失败时捕获错误
        error_message = f"执行命令时出错: {e.stderr.strip()}"
        print(error_message)
        return jsonify({"success": False, "message": f"重启服务失败: {e.stderr.strip()}"}), 500

    except Exception as e:
        # 捕获其他所有可能的异常
        print(f"发生未知错误: {e}")
        return jsonify({"success": False, "message": "发生未知错误"}), 500