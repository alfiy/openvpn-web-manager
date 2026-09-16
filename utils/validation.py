"""输入校验：客户端名、用户组名、速率、路径、IP。"""
import ipaddress
import os
import re
from typing import Optional, Tuple

CLIENT_NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$')
GROUP_NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$')
RATE_RE = re.compile(r'^\d+(\.\d+)?(bit|kbit|Mbit|Gbit)$')
RESERVED_CLIENT_NAMES = {'server', 'ca', '.', '..'}


class ValidationError(ValueError):
    pass


def validate_client_name(name: str) -> str:
    if not name or not isinstance(name, str):
        raise ValidationError('客户端名称不能为空')
    name = name.strip()
    if name.lower() in RESERVED_CLIENT_NAMES:
        raise ValidationError('客户端名称受保护，不可使用')
    if not CLIENT_NAME_RE.match(name):
        raise ValidationError(
            '客户端名称仅允许字母、数字、点、下划线和短横线，且必须以字母或数字开头，最长 63 字符'
        )
    if '..' in name:
        raise ValidationError('客户端名称非法')
    return name


def validate_group_name(name: str) -> str:
    if not name or not isinstance(name, str):
        raise ValidationError('用户组名称不能为空')
    name = name.strip()
    if not GROUP_NAME_RE.match(name):
        raise ValidationError(
            '用户组名称仅允许字母、数字、点、下划线和短横线，且必须以字母或数字开头，最长 63 字符'
        )
    if '..' in name:
        raise ValidationError('用户组名称非法')
    return name


def validate_rate(rate_str: str) -> str:
    if not rate_str or not isinstance(rate_str, str):
        raise ValidationError('速率不能为空')
    rate_str = rate_str.strip()
    if not RATE_RE.match(rate_str):
        raise ValidationError('速率格式无效，应为数字+单位（如 5Mbit、10kbit）')
    return rate_str


def validate_ipv4(ip: str) -> str:
    if not ip or not isinstance(ip, str):
        raise ValidationError('IP 不能为空')
    ip = ip.strip()
    try:
        addr = ipaddress.IPv4Address(ip)
    except ipaddress.AddressValueError as exc:
        raise ValidationError('IP 地址格式无效') from exc
    return str(addr)


def safe_join(base_dir: str, filename: str, suffix: str = '') -> str:
    """
    将文件名拼到目录下，拒绝路径穿越。
    suffix 例如 '.ovpn'；filename 不得包含路径分隔符。
    """
    if not filename or '/' in filename or '\\' in filename or filename in ('.', '..'):
        raise ValidationError('非法文件名')
    if os.path.basename(filename) != filename:
        raise ValidationError('非法文件名')
    target = os.path.realpath(os.path.join(base_dir, filename + suffix))
    base = os.path.realpath(base_dir)
    if target != base and not target.startswith(base + os.sep):
        raise ValidationError('路径越界')
    return target


def parse_client_name_or_error(name: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    try:
        return validate_client_name(name or ''), None
    except ValidationError as exc:
        return None, str(exc)
