"""
🆕 TC 配置导出工具
将数据库中的用户组和限速配置导出到 /etc/openvpn/tc-users.conf 和 tc-roles.map
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
    生成两个文件：
    1. tc-users.conf: 定义用户组速率和直接用户速率
       格式: 
         alice=2Mbit 5Mbit          # 直接配置（未分组客户端）
         @vip=20Mbit 50Mbit         # 角色定义（用户组）
    
    2. tc-roles.map: 客户端到用户组的映射
       格式:
         alice=@vip                  # 客户端alice属于vip组
         bob=@normal                 # 客户端bob属于normal组
    """
    try:
        # 查询所有用户组和客户端
        groups = ClientGroup.query.all()
        clients = Client.query.all()
        
        # ========== 生成 tc-users.conf ==========
        users_lines = [
            "# 自动生成的 TC 用户限速配置",
            "# 生成时间: 由 openvpn-web-manager 自动导出",
            "# 格式: 用户/用户组=上行速率 下行速率",
            ""
        ]
        
        # 1. 导出未分组的客户端（直接配置）
        ungrouped_clients = [c for c in clients if not c.group_id]
        if ungrouped_clients:
            users_lines.append("# ========== 直接配置（未分组客户端）==========")
            for client in ungrouped_clients:
                users_lines.append(f"{client.name}=2Mbit 5Mbit")
            users_lines.append("")
        
        # 2. 导出用户组定义（角色定义，使用 @ 前缀）
        if groups:
            users_lines.append("# ========== 角色定义（用户组）==========")
            for group in groups:
                users_lines.append(f"@{group.name}={group.upload_rate} {group.download_rate}")
            users_lines.append("")
        
        users_content = "\n".join(users_lines)
        
        # ========== 生成 tc-roles.map ==========
        roles_lines = [
            "# 自动生成的客户端角色映射",
            "# 生成时间: 由 openvpn-web-manager 自动导出",
            "# 格式: 客户端名=@用户组名",
            ""
        ]
        
        # 导出分组客户端的映射关系
        grouped_clients = [c for c in clients if c.group_id]
        if grouped_clients:
            roles_lines.append("# ========== 客户端到用户组的映射 ==========")
            for client in grouped_clients:
                group = ClientGroup.query.get(client.group_id)
                if group:
                    roles_lines.append(f"{client.name}=@{group.name}")
            roles_lines.append("")
        else:
            roles_lines.append("# 当前没有客户端分配到用户组")
            roles_lines.append("")
        
        roles_content = "\n".join(roles_lines)
        
        # ========== 写入本地备份 ==========
        os.makedirs(os.path.dirname(TC_USERS_CONF_LOCAL), exist_ok=True)
        
        with open(TC_USERS_CONF_LOCAL, 'w') as f:
            f.write(users_content)
        
        with open(TC_ROLES_MAP_LOCAL, 'w') as f:
            f.write(roles_content)
        
        # logger.info(f"TC 配置已导出到本地备份: {TC_USERS_CONF_LOCAL} 和 {TC_ROLES_MAP_LOCAL}")
        
        # ========== 尝试写入系统目录（如果有权限）==========
        import subprocess
        
        success_count = 0
        
        # 写入 tc-users.conf
        try:
            result = subprocess.run(
                ['sudo', 'tee', TC_USERS_CONF_PATH],
                input=users_content.encode(),
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                # logger.info(f"✅ TC 用户配置已导出到系统: {TC_USERS_CONF_PATH}")
                success_count += 1
            else:
                logger.warning(f"⚠️ 写入 {TC_USERS_CONF_PATH} 失败: {result.stderr.decode()}")
        except Exception as e:
            logger.warning(f"⚠️ 无法写入 {TC_USERS_CONF_PATH}: {str(e)}")
        
        # 写入 tc-roles.map
        try:
            result = subprocess.run(
                ['sudo', 'tee', TC_ROLES_MAP_PATH],
                input=roles_content.encode(),
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                # logger.info(f"✅ TC 角色映射已导出到系统: {TC_ROLES_MAP_PATH}")
                success_count += 1
            else:
                logger.warning(f"⚠️ 写入 {TC_ROLES_MAP_PATH} 失败: {result.stderr.decode()}")
        except Exception as e:
            logger.warning(f"⚠️ 无法写入 {TC_ROLES_MAP_PATH}: {str(e)}")
        
        return success_count > 0
        
    except Exception as e:
        logger.error(f"❌ 导出 TC 配置失败: {str(e)}")
        return False


def get_tc_config_preview():
    """获取 TC 配置预览（用于前端显示）"""
    try:
        groups = ClientGroup.query.all()
        clients = Client.query.all()
        
        lines = [
            "# ==================== tc-users.conf ====================",
            "# TC 用户限速配置预览",
            ""
        ]
        
        # 未分组客户端
        ungrouped = [c for c in clients if not c.group_id]
        if ungrouped:
            lines.append("# 直接配置（未分组客户端）")
            for client in ungrouped:
                lines.append(f"{client.name}=2Mbit 5Mbit")
            lines.append("")
        
        # 用户组定义
        if groups:
            lines.append("# 角色定义（用户组）")
            for group in groups:
                lines.append(f"@{group.name}={group.upload_rate} {group.download_rate}")
            lines.append("")
        
        lines.append("")
        lines.append("# ==================== tc-roles.map ====================")
        lines.append("# 客户端角色映射预览")
        lines.append("")
        
        # 分组客户端映射
        grouped = [c for c in clients if c.group_id]
        if grouped:
            lines.append("# 客户端到用户组的映射")
            for client in grouped:
                group = ClientGroup.query.get(client.group_id)
                if group:
                    lines.append(f"{client.name}=@{group.name}")
        else:
            lines.append("# 当前没有客户端分配到用户组")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"获取配置预览失败: {str(e)}")
        return f"错误: {str(e)}"


def reload_tc_daemon():
    """
    重新加载 TC 守护进程（可选）
    如果配置文件更新后需要通知守护进程重新读取
    """
    try:
        import subprocess
        # 发送 HUP 信号让守护进程重新加载配置
        result = subprocess.run(
            ['sudo', 'systemctl', 'reload', 'vpn-tc-daemon.service'],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            logger.info("✅ TC 守护进程已重新加载配置")
            return True
        else:
            logger.warning(f"⚠️ 重新加载 TC 守护进程失败: {result.stderr.decode()}")
            return False
    except Exception as e:
        logger.warning(f"⚠️ 无法重新加载 TC 守护进程: {str(e)}")
        return False