"""
🆕 TC 配置导出工具
将数据库中的用户组和限速配置导出到 /etc/openvpn/tc-users.conf
供 vpn-tc-daemon.sh 脚本读取
"""
import os
import logging
from models import ClientGroup, Client, db

logger = logging.getLogger(__name__)

# TC 配置文件路径（需要 sudo 权限写入）
TC_USERS_CONF_PATH = "/etc/openvpn/tc-users.conf"
TC_ROLES_MAP_PATH = "/etc/openvpn/tc-roles.map"

# 本地备份路径（不需要 sudo）
TC_USERS_CONF_LOCAL = "/opt/vpnwm/data/tc-users.conf"
TC_ROLES_MAP_LOCAL = "/opt/vpnwm/data/tc-roles.map"


def export_tc_config():
    """
    导出 TC 配置到文件
    生成 tc-users.conf 格式：
        用户组=上行速率 下行速率
        alice=5Mbit 10Mbit
        bob=2Mbit 5Mbit
    """
    try:
        # 查询所有用户组和客户端
        groups = ClientGroup.query.all()
        clients = Client.query.all()
        
        # 生成配置内容
        config_lines = [
            "# 自动生成的 TC 用户限速配置",
            "# 生成时间: 由 openvpn-web-manager 自动导出",
            "# 格式: 用户组或客户端=上行速率 下行速率",
            ""
        ]
        
        # 1. 导出用户组定义（使用 @groupname 格式作为角色定义）
        if groups:
            config_lines.append("# ========== 用户组定义 ==========")
            for group in groups:
                config_lines.append(f"@{group.name}={group.upload_rate} {group.download_rate}")
            config_lines.append("")
        
        # 2. 导出客户端映射（每个客户端映射到用户组或直接定义速率）
        if clients:
            config_lines.append("# ========== 客户端限速配置 ==========")
            for client in clients:
                if client.group_id:
                    # 客户端属于某个组，使用组的角色映射
                    group = ClientGroup.query.get(client.group_id)
                    if group:
                        config_lines.append(f"{client.name}=@{group.name}")
                else:
                    # 客户端没有分组，使用默认速率
                    config_lines.append(f"{client.name}=2Mbit 5Mbit")
            config_lines.append("")
        
        config_content = "\n".join(config_lines)
        
        # 写入本地备份
        os.makedirs(os.path.dirname(TC_USERS_CONF_LOCAL), exist_ok=True)
        with open(TC_USERS_CONF_LOCAL, 'w') as f:
            f.write(config_content)
        
        # logger.info(f"TC 配置已导出到本地备份: {TC_USERS_CONF_LOCAL}")
        
        # 尝试写入系统目录（如果有权限）
        try:
            import subprocess
            # 使用 sudo tee 写入系统配置
            result = subprocess.run(
                ['sudo', 'tee', TC_USERS_CONF_PATH],
                input=config_content.encode(),
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                logger.info(f"TC 配置已导出到系统: {TC_USERS_CONF_PATH}")
            else:
                logger.warning(f"写入系统配置失败: {result.stderr.decode()}")
        except Exception as e:
            logger.warning(f"无法写入系统配置 {TC_USERS_CONF_PATH}: {str(e)}")
        
        return True
    except Exception as e:
        logger.error(f"导出 TC 配置失败: {str(e)}")
        return False


def get_tc_config_preview():
    """获取 TC 配置预览（用于前端显示）"""
    try:
        groups = ClientGroup.query.all()
        clients = Client.query.all()
        
        lines = [
            "# TC 用户限速配置预览",
            ""
        ]
        
        if groups:
            lines.append("# ========== 用户组定义 ==========")
            for group in groups:
                lines.append(f"@{group.name}={group.upload_rate} {group.download_rate}")
            lines.append("")
        
        if clients:
            lines.append("# ========== 客户端限速配置 ==========")
            for client in clients:
                if client.group_id:
                    group = ClientGroup.query.get(client.group_id)
                    if group:
                        lines.append(f"{client.name}=@{group.name}")
                else:
                    lines.append(f"{client.name}=2Mbit 5Mbit")
        
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"获取配置预览失败: {str(e)}")
        return f"错误: {str(e)}"