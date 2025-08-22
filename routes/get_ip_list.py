import re
import subprocess
from flask import Blueprint, jsonify

ip_bp = Blueprint('ip', __name__)

@ip_bp.route('/get_ip_list', methods=['GET'])
def get_ip_list():
    ip_set = set()

    # 1. 内网 IPv4
    try:
        # hostname -I 可能返回 IPv6，先过滤
        out = subprocess.check_output(['hostname', '-I'], text=True, timeout=2)
        for ip in out.strip().split():
            if re.match(r'^\d+\.\d+\.\d+\.\d+$', ip):
                ip_set.add(ip)
    except Exception:
        pass

    # 2. ip route 兜底
    try:
        out = subprocess.check_output(['ip', 'route', 'get', '8.8.8.8'], text=True, timeout=2)
        m = re.search(r'src (\d+\.\d+\.\d+\.\d+)', out)
        if m:
            ip_set.add(m.group(1))
    except Exception:
        pass

    # 3. 公网 IPv4（可选，失败不报错）
    try:
        out = subprocess.check_output(['curl', '-s', '--connect-timeout', '3', 'ifconfig.me'], text=True, timeout=3)
        if re.match(r'^\d+\.\d+\.\d+\.\d+$', out.strip()):
            ip_set.add(out.strip())
    except Exception:
        pass

    # 4. 保底：如果什么都没有，给个 127.0.0.1（前端会提示用户手动输入）
    if not ip_set:
        ip_set.add('127.0.0.1')

    return jsonify(sorted(ip_set))