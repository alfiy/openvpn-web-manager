#!/usr/bin/env python3
"""systemd timer 入口：证书/禁用/在线状态写入 SQLite。

Web 请求路径不再调用同步写库，只读 DB + 7505/ping overlay。
"""
import os
import sys

os.environ.setdefault('FLASK_ENV', 'production')
os.environ['VPNWM_SYNC_MODE'] = '1'

# 保证 /opt/vpnwm 在 path 中
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main():
    from app import create_app
    from utils.openvpn_utils import (
        sync_openvpn_clients_to_db,
        sync_online_state_to_db,
        log_message,
    )

    application = create_app()
    with application.app_context():
        try:
            sync_openvpn_clients_to_db()
            sync_online_state_to_db()
        except Exception as exc:
            log_message(f'同步失败: {exc}')
            raise


if __name__ == '__main__':
    main()
