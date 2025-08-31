# routes/uninstall.py
from flask import Blueprint, request, jsonify
import subprocess
# ✅ 确保导入了 current_user 来获取当前登录用户
from flask_login import current_user
from routes.helpers import json_csrf_protect, login_required

uninstall_bp = Blueprint('uninstall', __name__)

@uninstall_bp.route('/uninstall', methods=['POST'])
@login_required
@json_csrf_protect
def uninstall():
    """
    通过运行一系列命令来卸载 OpenVPN 服务器。
    """
    
    # ✅ 关键修复：在执行任何命令之前，进行角色权限检查
    # 确保只有超级管理员可以执行此操作
    if not current_user.is_authenticated or current_user.role.name != 'SUPER_ADMIN':
        return jsonify({
            'status': 'error',
            'message': '权限不足，无法执行此操作。'
        }), 403 # 返回 403 Forbidden 状态码

    try:
        # 要执行的命令列表
        commands = [
            # 停止和禁用 OpenVPN 服务
            ['sudo', 'systemctl', 'stop', 'openvpn@server'],
            ['sudo', 'systemctl', 'disable', 'openvpn@server'],
            # 停止和禁用 iptables 服务
            ['sudo', 'systemctl', 'stop', 'iptables-openvpn'],
            ['sudo', 'systemctl', 'disable', 'iptables-openvpn'],
            # 移除 systemd 服务文件
            ['sudo', 'rm', '-f', '/etc/systemd/system/iptables-openvpn.service'],
            # 重新加载 systemd
            ['sudo', 'systemctl', 'daemon-reload'],
            # 移除 iptables 脚本
            ['sudo', 'rm', '-f', '/etc/iptables/add-openvpn-rules.sh'],
            ['sudo', 'rm', '-f', '/etc/iptables/rm-openvpn-rules.sh'],
            # 移除 OpenVPN 软件包
            ['sudo', 'apt-get', 'remove', '--purge', '-y', 'openvpn'],
            # 清理配置文件和目录
            ['sudo', 'rm', '-rf', '/etc/openvpn'],
            ['sudo', 'rm', '-f', '/etc/sysctl.d/99-openvpn.conf'],
            ['sudo', 'rm', '-rf', '/var/log/openvpn'],
            # 恢复 IP 转发设置
            ['sudo', 'sysctl', '-w', 'net.ipv4.ip_forward=0'],
        ]

        failed_commands = []
        for cmd in commands:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                # systemctl 命令在服务不存在时可能会失败，但这不是严重错误
                if result.returncode != 0 and 'systemctl' not in cmd[0]:
                    failed_commands.append(f"{' '.join(cmd)}: {result.stderr}")
            except subprocess.TimeoutExpired:
                failed_commands.append(f"{' '.join(cmd)}: Command timed out")
            except Exception as cmd_error:
                failed_commands.append(f"{' '.join(cmd)}: {str(cmd_error)}")

        if failed_commands:
            return jsonify({
                'status': 'warning',
                'message': f'OpenVPN 部分卸载完成。部分命令失败：{"; ".join(failed_commands)}'
            })
        else:
            return jsonify({
                'status': 'success',
                'message': 'OpenVPN 成功完全卸载。',
                'redirect': '/'
            })

    except Exception as e:
        return jsonify({'status': 'error', 'message': f'卸载时发生错误：{str(e)}'})