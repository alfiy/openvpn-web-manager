#!/usr/bin/env python3
"""systemd timer 入口：证书/禁用/在线状态写入 SQLite。

Web 请求路径不再调用同步写库，只读 DB + 7505/ping overlay。
"""
import os
import sys
import traceback

os.environ['VPNWM_SYNC_MODE'] = '1'
os.environ.setdefault('FLASK_ENV', 'production')

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _load_env_file(path):
    if not os.path.isfile(path):
        return
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, val = line.partition('=')
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except OSError:
        pass


def _log(msg):
    print(msg, flush=True)
    try:
        log_path = os.path.join(os.environ.get('VPNWM_DATA_DIR', os.path.join(ROOT, 'data')), 'sync.log')
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, 'a', encoding='utf-8') as fh:
            fh.write(msg + '\n')
    except OSError:
        pass


def main():
    _load_env_file(os.path.join(ROOT, '.env'))
    # app.py 在 import 时已经 create_app()，不能再调第二遍
    from app import app
    from utils.openvpn_utils import (
        sync_openvpn_clients_to_db,
        sync_online_state_to_db,
        log_message,
    )

    with app.app_context():
        sync_openvpn_clients_to_db()
        sync_online_state_to_db()
        log_message('sync ok')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        _log(traceback.format_exc())
        raise
