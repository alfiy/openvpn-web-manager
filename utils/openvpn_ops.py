"""
不经过 shell 的 OpenVPN / easy-rsa / CCD 操作。
所有路径与文件名必须先经过 utils.validation 校验。
"""
import os
import socket
import subprocess
import tempfile
import time
from typing import List, Optional, Sequence, Tuple

from utils.validation import ValidationError, safe_join, validate_client_name

EASYRSA_DIR = '/etc/openvpn/easy-rsa'
EASYRSA_BIN = '/etc/openvpn/easy-rsa/easyrsa'
CLIENT_DIR = '/etc/openvpn/client'
CCD_DIR = '/etc/openvpn/ccd'
TEMPLATE = '/etc/openvpn/client-template.txt'
CA_CRT = '/etc/openvpn/easy-rsa/pki/ca.crt'
TLS_CRYPT = '/etc/openvpn/tls-crypt.key'
CRL_SRC = '/etc/openvpn/easy-rsa/pki/crl.pem'
CRL_DST = '/etc/openvpn/crl.pem'
IPP_TXT = '/etc/openvpn/ipp.txt'
INDEX_TXT = '/etc/openvpn/easy-rsa/pki/index.txt'


def _run(cmd: Sequence[str], timeout: int = 60, cwd: Optional[str] = None, env=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(cmd),
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
        check=False,
    )


def _sudo(cmd: Sequence[str], timeout: int = 60, cwd: Optional[str] = None, env=None) -> subprocess.CompletedProcess:
    return _run(['sudo', '-n', *cmd], timeout=timeout, cwd=cwd, env=env)


def path_exists(path: str) -> bool:
    """当前用户不可读的 PKI 路径用 sudo test 判断。"""
    if os.path.exists(path):
        return True
    result = _sudo(['test', '-e', path], timeout=10)
    return result.returncode == 0


def read_text(path: str) -> str:
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            return fh.read()
    except OSError:
        result = _sudo(['cat', path], timeout=10)
        if result.returncode != 0:
            raise OSError(result.stderr or f'无法读取 {path}')
        return result.stdout or ''


def build_client_cert(client_name: str, cert_expiry_days: int = 3650) -> Tuple[bool, str]:
    client_name = validate_client_name(client_name)
    env = os.environ.copy()
    env['EASYRSA_CERT_EXPIRE'] = str(int(cert_expiry_days))
    result = _sudo(
        [EASYRSA_BIN, '--batch', 'build-client-full', client_name, 'nopass'],
        timeout=60,
        cwd=EASYRSA_DIR,
        env=env,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or '').strip()
        return False, err
    return True, ''


def write_ovpn_config(client_name: str) -> Tuple[bool, str]:
    client_name = validate_client_name(client_name)
    issued = os.path.join(EASYRSA_DIR, 'pki', 'issued', f'{client_name}.crt')
    key = os.path.join(EASYRSA_DIR, 'pki', 'private', f'{client_name}.key')
    dest = safe_join(CLIENT_DIR, client_name, '.ovpn')

    try:
        template = _read_maybe_sudo(TEMPLATE)
        ca = _read_maybe_sudo(CA_CRT)
        cert = _extract_cert(_read_maybe_sudo(issued))
        priv = _read_maybe_sudo(key)
        tls = _read_maybe_sudo(TLS_CRYPT)
    except OSError as exc:
        return False, f'读取证书文件失败: {exc}'

    body = (
        template.rstrip() + '\n\n'
        '<ca>\n' + ca.rstrip() + '\n</ca>\n\n'
        '<cert>\n' + cert.rstrip() + '\n</cert>\n\n'
        '<key>\n' + priv.rstrip() + '\n</key>\n\n'
        '<tls-crypt>\n' + tls.rstrip() + '\n</tls-crypt>\n'
    )

    fd, tmp_path = tempfile.mkstemp(prefix='vpnwm-ovpn-', suffix='.ovpn')
    try:
        with os.fdopen(fd, 'w') as fh:
            fh.write(body)
        _sudo(['mkdir', '-p', CLIENT_DIR])
        result = _sudo(['cp', tmp_path, dest])
        if result.returncode != 0:
            return False, (result.stderr or '复制 ovpn 失败').strip()
        _sudo(['chmod', '644', dest])
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    return True, dest


def revoke_client_cert(client_name: str) -> Tuple[bool, str]:
    client_name = validate_client_name(client_name)
    result = _sudo(
        [EASYRSA_BIN, '--batch', 'revoke', client_name],
        timeout=60,
        cwd=EASYRSA_DIR,
    )
    err = (result.stderr or result.stdout or '').strip()
    if result.returncode != 0 and 'already revoked' not in err.lower():
        return False, err
    return True, err


def generate_and_install_crl() -> Tuple[bool, str]:
    result = _sudo([EASYRSA_BIN, 'gen-crl'], timeout=60, cwd=EASYRSA_DIR)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or 'gen-crl 失败').strip()
    _sudo(['rm', '-f', CRL_DST])
    cp = _sudo(['cp', CRL_SRC, CRL_DST])
    if cp.returncode != 0:
        return False, (cp.stderr or '复制 CRL 失败').strip()
    _sudo(['chmod', '644', CRL_DST])
    return True, ''


def cleanup_client_files(client_name: str) -> None:
    client_name = validate_client_name(client_name)
    paths = [
        safe_join(CLIENT_DIR, client_name, '.ovpn'),
        safe_join(CCD_DIR, client_name, ''),
        os.path.join(EASYRSA_DIR, 'pki', 'issued', f'{client_name}.crt'),
        os.path.join(EASYRSA_DIR, 'pki', 'private', f'{client_name}.key'),
        os.path.join(EASYRSA_DIR, 'pki', 'reqs', f'{client_name}.req'),
    ]
    for path in paths:
        _sudo(['rm', '-f', path], timeout=15)
    if os.path.isfile(IPP_TXT):
        _sudo(['sed', '-i', f'/^{client_name},/d', IPP_TXT], timeout=15)


def kick_client_sessions(client_name: str) -> Tuple[bool, str]:
    """通过 management 口踢掉该 CN 的全部会话，并复查 status 2。"""
    client_name = validate_client_name(client_name)
    host = os.environ.get('OPENVPN_MGMT_HOST', '127.0.0.1')
    port = int(os.environ.get('OPENVPN_MGMT_PORT', '7505'))
    password = os.environ.get('OPENVPN_MGMT_PASSWORD')
    notes = []
    try:
        with socket.create_connection((host, port), timeout=5) as sock:
            sock.settimeout(4)
            banner = sock.recv(4096)
            if banner and b'PASSWORD' in banner.upper():
                sock.sendall(((password or '') + '\r\n').encode())
                sock.recv(4096)

            def command(cmd: str, until_end: bool = False) -> str:
                sock.sendall((cmd + '\r\n').encode())
                chunks = []
                end = time.time() + (3.0 if until_end else 1.2)
                while time.time() < end:
                    try:
                        piece = sock.recv(8192)
                    except socket.timeout:
                        break
                    if not piece:
                        break
                    chunks.append(piece)
                    blob = b''.join(chunks)
                    if until_end and (b'\nEND' in blob or blob.rstrip().endswith(b'END')):
                        break
                    if not until_end and (b'SUCCESS' in blob or b'ERROR' in blob):
                        break
                return b''.join(chunks).decode('utf-8', errors='ignore')

            status = command('status 2', until_end=True)
            targets = []
            for line in status.splitlines():
                if not line.startswith('CLIENT_LIST,'):
                    continue
                parts = line.split(',')
                if len(parts) < 3:
                    continue
                cn = parts[1].strip()
                if cn.lower() != client_name.lower():
                    continue
                real_addr = parts[2].strip()
                cid = parts[10].strip() if len(parts) > 10 else ''
                targets.append((cn, real_addr, cid))
            if not targets:
                try:
                    sock.sendall(b'quit\r\n')
                except OSError:
                    pass
                return True, '管理口中已无该客户端会话'

            for cn, real_addr, cid in targets:
                if cid.isdigit():
                    notes.append(command(f'client-kill {cid}'))
                notes.append(command(f'kill {cn}'))
                if real_addr:
                    notes.append(command(f'kill {real_addr}'))

            time.sleep(0.4)
            remain = command('status 2', until_end=True)
            still_now = [
                line for line in remain.splitlines()
                if line.startswith('CLIENT_LIST,') and line.split(',')[1].strip().lower() == client_name.lower()
            ]
            if still_now:
                for line in still_now:
                    parts = line.split(',')
                    cid = parts[10].strip() if len(parts) > 10 else ''
                    if cid.isdigit():
                        notes.append(command(f'client-kill {cid}'))
                    notes.append(command(f'kill {client_name}'))
                time.sleep(0.4)
                remain = command('status 2', until_end=True)
            still = []
            for line in remain.splitlines():
                if line.startswith('CLIENT_LIST,') and line.split(',')[1].strip().lower() == client_name.lower():
                    still.append(line)
            try:
                sock.sendall(b'quit\r\n')
            except OSError:
                pass
            if still:
                return False, '已发送踢出命令，但会话仍在: ' + '; '.join(notes)
            return True, '已通过管理口踢出: ' + '; '.join(notes)
    except OSError as exc:
        return False, f'无法连接管理口 {host}:{port}: {exc}'


def release_first_wins_lock(client_name: str) -> None:
    """踢人后清掉 first-wins 锁，否则同一证书会一直 DENY。"""
    try:
        name = validate_client_name(client_name)
    except ValidationError:
        return
    safe = ''.join(ch if ch.isalnum() or ch in '._-' else '_' for ch in name)
    lock = f'/etc/openvpn/first-wins/locks/{safe}.lock'
    _sudo(['rm', '-f', lock], timeout=10)


def set_ccd_disabled(client_name: str, disabled: bool) -> Tuple[bool, str]:
    client_name = validate_client_name(client_name)
    dest = safe_join(CCD_DIR, client_name, '')
    if not disabled:
        result = _sudo(['rm', '-f', dest], timeout=15)
        if result.returncode != 0:
            return False, (result.stderr or '删除 CCD 禁用文件失败').strip()
        return True, dest

    _sudo(['mkdir', '-p', CCD_DIR], timeout=15)
    fd, tmp_path = tempfile.mkstemp(prefix='vpnwm-ccd-')
    try:
        with os.fdopen(fd, 'w') as fh:
            fh.write('disable\n')
        result = _sudo(['cp', tmp_path, dest], timeout=15)
        if result.returncode != 0:
            return False, (result.stderr or '写入 CCD 禁用文件失败').strip()
        _sudo(['chown', 'root:root', dest], timeout=15)
        _sudo(['chmod', '644', dest], timeout=15)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    return True, dest


def ovpn_download_path(client_name: str) -> str:
    client_name = validate_client_name(client_name)
    return safe_join(CLIENT_DIR, client_name, '.ovpn')


def _extract_cert(pem: str) -> str:
    lines = pem.splitlines()
    out: List[str] = []
    capture = False
    for line in lines:
        if 'BEGIN CERTIFICATE' in line:
            capture = True
        if capture:
            out.append(line)
        if 'END CERTIFICATE' in line:
            break
    return '\n'.join(out) if out else pem


def _read_maybe_sudo(path: str) -> str:
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            return fh.read()
    except OSError:
        result = _sudo(['cat', path], timeout=10)
        if result.returncode != 0:
            raise OSError(result.stderr or f'无法读取 {path}')
        return result.stdout
