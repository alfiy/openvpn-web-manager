import subprocess
import logging
from flask import Blueprint, jsonify, request
from routes.helpers import login_required
from flask_login import current_user
from extensions import limiter


# 配置日志
logger = logging.getLogger(__name__)

restart_openvpn_bp = Blueprint('restart_openvpn', __name__)

# 允许的服务名称白名单（严格限制，防止注入如果有需要可以扩展）
ALLOWED_SERVICES = {
    'openvpn@server',
}

# 允许的操作白名单
ALLOWED_ACTIONS = {'restart', 'status'}  # 只允许特定操作


def validate_service_name(service_name: str) -> bool:
    """
    严格验证服务名称，只允许白名单中的服务
    防止路径遍历和命令注入
    """
    if not service_name or not isinstance(service_name, str):
        return False
    # 检查是否在白名单中
    return service_name in ALLOWED_SERVICES


def validate_action(action: str) -> bool:
    """验证操作类型"""
    return action in ALLOWED_ACTIONS


def execute_systemctl(action: str, service_name: str) -> dict:
    """
    安全地执行 systemctl 命令
    使用列表形式传递参数，避免 shell 注入
    """
    # 双重验证
    if not validate_action(action) or not validate_service_name(service_name):
        raise ValueError("无效的操作或服务名称")
    
    # 构建命令列表（不使用 shell=True）
    cmd = ['sudo', 'systemctl', action, service_name]
    
    try:
        result = subprocess.run(
            cmd,
            shell=False,  # ✅ 禁用 shell，防止注入
            check=True,
            capture_output=True,
            text=True,
            timeout=30,  # ✅ 添加超时，防止挂起
        )
        
        # logger.info(f"Systemctl {action} {service_name} 成功执行")
        return {
            'success': True,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'returncode': result.returncode
        }
        
    except subprocess.TimeoutExpired:
        logger.error(f"执行 systemctl {action} {service_name} 超时")
        raise TimeoutError("命令执行超时")
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Systemctl 执行失败: {e.stderr}")
        raise RuntimeError(f"服务操作失败: {e.stderr}")

@limiter.limit("1 per minute")
@restart_openvpn_bp.route("/api/restart_openvpn", methods=["POST"])
@login_required
def restart_openvpn():
    """
    安全地重启 OpenVPN 服务
    """
    # 1. 权限检查
    if not current_user.is_authenticated:
        return jsonify({
            'status': 'error',
            'message': '未授权访问'
        }), 401
    
    # 支持多种管理员角色
    allowed_roles = {'SUPER_ADMIN', 'ADMIN', 'VPN_ADMIN'}
    if current_user.role.name not in allowed_roles:
        logger.warning(f"用户 {current_user.id} 尝试越权重启 OpenVPN")
        return jsonify({
            'status': 'error',
            'message': '权限不足'
        }), 403

    # 2. 获取并验证请求参数（如果支持动态服务名）
    # 如果不需动态服务名，直接硬编码
    service_name = request.json.get('service', 'openvpn@server') if request.is_json else 'openvpn@server'
    
    if not validate_service_name(service_name):
        logger.warning(f"无效的服务名称尝试: {service_name}")
        return jsonify({
            'status': 'error',
            'message': '无效的服务名称'
        }), 400

    # 3. 执行重启
    try:
        result = execute_systemctl('restart', service_name)
        
        return jsonify({
            'success': True,
            'message': 'OpenVPN 服务已成功重启',
            'service': service_name
        }), 200

    except TimeoutError:
        return jsonify({
            'success': False,
            'message': '服务重启超时，请检查服务状态'
        }), 504
        
    except RuntimeError as e:
        # 返回通用错误信息，不暴露系统细节
        return jsonify({
            'success': False,
            'message': '服务重启失败，请联系管理员'
        }), 500
        
    except Exception as e:
        logger.exception("重启 OpenVPN 时发生未预期错误")
        return jsonify({
            'success': False,
            'message': '服务器内部错误'
        }), 500


@restart_openvpn_bp.route("/api/openvpn_status", methods=["GET"])
@login_required
def openvpn_status():
    """
    获取 OpenVPN 服务状态（只读，更安全）
    """
    if not current_user.is_authenticated:
        return jsonify({'status': 'error', 'message': '未授权'}), 401

    try:
        result = execute_systemctl('status', 'openvpn@server')
        
        # 解析状态输出
        is_active = 'Active: active (running)' in result['stdout']
        
        return jsonify({
            'success': True,
            'active': is_active,
            'raw_status': result['stdout'][:500]  # 限制输出长度
        }), 200
        
    except Exception as e:
        logger.error(f"获取状态失败: {e}")
        return jsonify({
            'success': False,
            'message': '无法获取服务状态'
        }), 500