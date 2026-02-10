"""
TC 热更新模块
用于向守护进程发送速率变更信号，实现不断线的实时限速调整
"""

import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 信号文件路径（与守护脚本中的 RELOAD_SIGNAL 保持一致）
RELOAD_SIGNAL = "/var/run/openvpn-tc/reload.signal"


def _write_signal(signal_line: str) -> bool:
    """
    写入信号到文件
    
    Args:
        signal_line: 信号内容（格式: ACTION=value）
        
    Returns:
        bool: 是否写入成功
    """
    try:
        # 确保目录存在
        signal_path = Path(RELOAD_SIGNAL)
        signal_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 追加写入信号
        with open(RELOAD_SIGNAL, 'a') as f:
            f.write(f"{signal_line}\n")
        
        logger.info(f"✅ 热更新信号已发送: {signal_line}")
        return True
        
    except PermissionError:
        logger.error(f"❌ 权限不足，无法写入信号文件: {RELOAD_SIGNAL}")
        logger.error(f"   请执行: sudo chown -R $USER:$USER /var/run/openvpn-tc")
        return False
    except Exception as e:
        logger.error(f"❌ 发送热更新信号失败: {e}")
        return False


def notify_user_update(username: str, vpn_ip: str) -> bool:
    """
    通知守护进程：某用户需要更新速率
    
    使用场景:
    - 用户从 A 组移动到 B 组
    - 单独修改某用户的速率配置
    
    Args:
        username: 用户名（客户端名称）
        vpn_ip: VPN IP 地址（例如: 10.8.0.23）
        
    Returns:
        bool: 是否发送成功
        
    Example:
        >>> notify_user_update("alice", "10.8.0.23")
        True
    """
    if not username or not vpn_ip:
        logger.warning("⚠️ 用户名或 IP 为空，跳过热更新")
        return False
    
    signal = f"UPDATE_USER={username}|{vpn_ip}"
    return _write_signal(signal)


def notify_role_update(role_name: str) -> bool:
    """
    通知守护进程：某角色（用户组）的速率已更新
    
    使用场景:
    - 修改"普通用户组"的上下行速率
    - 修改"VIP 用户组"的限速配置
    
    守护进程会自动找出所有属于该角色的在线用户并更新
    
    Args:
        role_name: 角色名称（对应 tc-roles.map 中的角色）
        
    Returns:
        bool: 是否发送成功
        
    Example:
        >>> notify_role_update("normal_users")
        True
    """
    if not role_name:
        logger.warning("⚠️ 角色名为空，跳过热更新")
        return False
    
    signal = f"UPDATE_ROLE={role_name}"
    return _write_signal(signal)


def check_signal_file_writable() -> bool:
    """
    检查信号文件是否可写（用于健康检查）
    
    Returns:
        bool: 是否可写
    """
    try:
        signal_path = Path(RELOAD_SIGNAL)
        signal_path.parent.mkdir(parents=True, exist_ok=True)
        signal_path.touch(exist_ok=True)
        return os.access(RELOAD_SIGNAL, os.W_OK)
    except Exception as e:
        logger.error(f"❌ 信号文件不可写: {e}")
        return False


def clear_signal_file():
    """
    清空信号文件（用于调试或重置）
    """
    try:
        with open(RELOAD_SIGNAL, 'w') as f:
            f.write('')
        logger.info("✅ 信号文件已清空")
        return True
    except Exception as e:
        logger.error(f"❌ 清空信号文件失败: {e}")
        return False


def get_pending_signals() -> list:
    """
    读取待处理的信号（用于调试）
    
    Returns:
        list: 信号列表
    """
    try:
        if not os.path.exists(RELOAD_SIGNAL):
            return []
        
        with open(RELOAD_SIGNAL, 'r') as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        logger.error(f"❌ 读取信号文件失败: {e}")
        return []