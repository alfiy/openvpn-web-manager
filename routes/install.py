from flask import Blueprint, request, jsonify
import os
import subprocess
import time
# 导入CSRF验证所需模块
from flask_wtf.csrf import validate_csrf
from functools import wraps

# JSON请求CSRF验证装饰器
def json_csrf_protect(f):
    """专门用于JSON格式POST请求的CSRF验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 获取请求头中的CSRF令牌
        csrf_token = request.headers.get('X-CSRFToken')
        
        # 检查令牌是否存在
        if not csrf_token:
            return jsonify({'status': 'error', 'message': '缺少CSRF令牌'}), 403
        
        # 验证令牌有效性
        try:
            validate_csrf(csrf_token)
        except Exception:
            return jsonify({'status': 'error', 'message': 'CSRF令牌验证失败，请刷新页面重试'}), 403
            
        return f(*args, **kwargs)
    return decorated_function

install_bp = Blueprint('install', __name__)

SCRIPT_PATH = './ubuntu-openvpn-install.sh'

@install_bp.route('/install', methods=['POST'])
@json_csrf_protect  # 应用CSRF保护装饰器
def install():
    # 1. 检查脚本是否存在
    if not os.path.exists(SCRIPT_PATH):
        return jsonify({
            'status': 'error',
            'message': f'OpenVPN安装脚本不存在: {SCRIPT_PATH}。请确保ubuntu-openvpn-install.sh文件存在于工作目录中。'
        })

    # 2. 检查 sudo 可用
    try:
        subprocess.run(['which', 'sudo'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return jsonify({
            'status': 'error',
            'message': 'sudo命令不可用。OpenVPN安装需要管理员权限。请确保在支持sudo的环境中运行此应用程序。'
        })

    # 3. 解析前端参数
    data = request.get_json()
    port = data.get('port', 1194)
    try:
        port = int(port)
        if not (1024 < port < 65535):
            return jsonify({'status': 'error', 'message': '端口号必须在 1025 到 65534 之间'})
    except ValueError:
        return jsonify({'status': 'error', 'message': '端口号必须是整数'})

    # 4. 取得用户选择或自动检测的 IP
    def get_internal_ip():
        try:
            result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip().split()[0]
            result = subprocess.run(['ip', 'route', 'get', '8.8.8.8'], capture_output=True, text=True)
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if 'src' in line:
                        return line.split('src')[1].strip().split()[0]
            return '10.0.0.1'
        except:
            return '10.0.0.1'

    server_ip = data.get('ip', '').strip() or get_internal_ip()

    # 5. 启动脚本（参数：端口 + IP）
    try:
        process = subprocess.Popen(
            ['sudo', 'bash', SCRIPT_PATH, str(port), server_ip],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # 安装脚本交互输入（端口已作为第 1 参数，IP 已作为第 2 参数）
        inputs = [
            '1\n',               # UDP
            '1\n',               # DNS
            '\n',                # 默认客户端名
            '1\n'                # 无密码
        ]
        for cmd in inputs:
            process.stdin.write(cmd)
            process.stdin.flush()
            time.sleep(0.5)

        stdout, stderr = process.communicate(timeout=300)
        if process.returncode == 0:
            return jsonify({
                'status': 'success',
                'message': f'OpenVPN 安装成功，服务器 IP: {server_ip}，端口: {port}',
                'redirect': '/' # 告诉前端刷新到根路径
            })
        else:
            return jsonify({'status': 'error', 'message': f'安装失败: {stderr}'})

    except subprocess.TimeoutExpired:
        process.kill()
        return jsonify({'status': 'timeout', 'message': '安装超时（5 分钟）'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'安装错误: {str(e)}'})