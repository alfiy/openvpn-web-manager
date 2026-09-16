"""
不经过 shell 的 OpenVPN / easy-rsa / CCD 操作。
所有路径与文件名必须先经过 utils.validation 校验。
"""
import os
import subprocess
import tempfile
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
