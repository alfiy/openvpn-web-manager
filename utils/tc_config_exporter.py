"""
TC 配置文件导出工具
负责将数据库中的用户组和客户端数据导出为守护进程可读的配置文件
"""
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# 配置文件路径
USER_RATE_CONF = "/etc/openvpn/tc-users.conf"
USER_ROLE_MAP = "/etc/openvpn/tc-roles.map"


def export_tc_config():
    """
    导出 TC 配置文件
    
    生成两个文件:
    1. /etc/openvpn/tc-users.conf - 用户组速率配置
       格式: group_name=upload_rate download_rate
       例如: vip_users=10Mbit 50Mbit
    
    2. /etc/openvpn/tc-roles.map - 客户端→用户组映射
       格式: client_name=group_name
       例如: alice=vip_users
    
    Returns:
        bool: 是否导出成功
    """
    try:
        # 延迟导入，避免循环依赖
        from models import db, ClientGroup, Client
        
        # ========== 生成 tc-users.conf ==========
        groups = ClientGroup.query.all()
        
        lines_conf = []
        for group in groups:
            # 提取速率值（去掉可能的单位，统一格式）
            upload = group.upload_rate.strip()
            download = group.download_rate.strip()
            
            # 格式: group_name=upload download
            lines_conf.append(f"{group.name}={upload} {download}")
        
        # 确保目录存在
        conf_path = Path(USER_RATE_CONF)
        conf_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 写入文件
        with open(USER_RATE_CONF, 'w') as f:
            f.write('\n'.join(lines_conf) + '\n')
        
        # logger.info(f"✅ 已导出 {len(groups)} 个用户组到 {USER_RATE_CONF}")
        
        # ========== 生成 tc-roles.map ==========
        # 只导出有分组的客户端
        clients = Client.query.filter(Client.group_id.isnot(None)).all()
        
        lines_map = []
        for client in clients:
            if client.group:  # 确保有关联的用户组
                lines_map.append(f"{client.name}={client.group.name}")
        
        # 确保目录存在
        map_path = Path(USER_ROLE_MAP)
        map_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 写入文件
        with open(USER_ROLE_MAP, 'w') as f:
            if lines_map:
                f.write('\n'.join(lines_map) + '\n')
            else:
                # 如果没有任何客户端分组，写入空文件
                f.write('')
        
        # logger.info(f"✅ 已导出 {len(clients)} 个客户端映射到 {USER_ROLE_MAP}")
        
        return True
        
    except PermissionError as e:
        logger.error(f"❌ 权限不足，无法写入配置文件: {e}")
        logger.error(f"   请确保 Flask 应用有权限写入 {USER_RATE_CONF} 和 {USER_ROLE_MAP}")
        return False
        
    except Exception as e:
        logger.error(f"❌ 导出 TC 配置失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def ensure_config_files_writable():
    """
    检查配置文件是否可写（用于启动时健康检查）
    
    Returns:
        bool: 是否可写
    """
    try:
        for path in [USER_RATE_CONF, USER_ROLE_MAP]:
            # 确保目录存在
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            
            # 尝试创建或打开文件
            Path(path).touch(exist_ok=True)
            
            # 检查是否可写
            if not os.access(path, os.W_OK):
                logger.error(f"❌ 配置文件不可写: {path}")
                return False
        
        logger.info("✅ TC 配置文件可写性检查通过")
        return True
        
    except Exception as e:
        logger.error(f"❌ 配置文件可写性检查失败: {e}")
        return False


def get_client_rate_from_config(client_name: str) -> tuple:
    """
    从配置文件读取客户端的速率配置（用于调试）
    
    Args:
        client_name: 客户端名称
        
    Returns:
        tuple: (upload_rate, download_rate) 或 None
    """
    try:
        # 读取用户→组映射
        if not os.path.exists(USER_ROLE_MAP):
            return None
        
        group_name = None
        with open(USER_ROLE_MAP, 'r') as f:
            for line in f:
                if line.strip().startswith(f"{client_name}="):
                    group_name = line.strip().split('=')[1]
                    break
        
        if not group_name:
            return None
        
        # 读取组速率
        if not os.path.exists(USER_RATE_CONF):
            return None
        
        with open(USER_RATE_CONF, 'r') as f:
            for line in f:
                if line.strip().startswith(f"{group_name}="):
                    rates = line.strip().split('=')[1].split()
                    if len(rates) == 2:
                        return (rates[0], rates[1])
        
        return None
        
    except Exception as e:
        logger.error(f"❌ 读取客户端速率配置失败: {e}")
        return None