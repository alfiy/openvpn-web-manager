"""
Dashboard 仪表板路由
系统监控数据接口（含网络速率）
"""

from flask import Blueprint, jsonify
from routes.helpers import login_required
from openvpn_monitor.system_monitor import SystemMonitor
from openvpn_monitor.config import Config
import time

dashboard_bp = Blueprint('dashboard', __name__)

# 全局变量存储上次网络数据用于计算速率
_last_net_stats = None
_last_net_time = None


def get_network_with_speed(vpn_interface: str = 'tun0') -> dict:
    """
    获取网络统计并计算上传/下载速率
    """
    global _last_net_stats, _last_net_time
    
    # 获取当前原始数据
    current_stats = SystemMonitor.get_network_stats(vpn_interface)
    current_time = time.time()
    
    # 构建结果
    result = {
        'upload_total': round(current_stats['bytes_sent'] / 1024 / 1024, 2),    # MB
        'download_total': round(current_stats['bytes_recv'] / 1024 / 1024, 2),  # MB
        'upload_speed': 0,      # KB/s
        'download_speed': 0,    # KB/s
        'upload_speed_str': '0 KB/s',
        'download_speed_str': '0 KB/s'
    }
    
    # 计算速率
    if _last_net_stats is not None and _last_net_time is not None:
        time_delta = current_time - _last_net_time
        
        if time_delta > 0:
            # 计算速度 (bytes -> KB/s)
            upload_speed = (current_stats['bytes_sent'] - _last_net_stats['bytes_sent']) / time_delta / 1024
            download_speed = (current_stats['bytes_recv'] - _last_net_stats['bytes_recv']) / time_delta / 1024
            
            result['upload_speed'] = round(upload_speed, 2)
            result['download_speed'] = round(download_speed, 2)
            result['upload_speed_str'] = format_speed(upload_speed)
            result['download_speed_str'] = format_speed(download_speed)
    
    # 更新全局变量
    _last_net_stats = current_stats.copy()
    _last_net_time = current_time
    
    return result


def format_speed(speed_kbps: float) -> str:
    """格式化速度显示"""
    if speed_kbps < 0:
        speed_kbps = 0
    
    if speed_kbps < 1024:
        return f"{speed_kbps:.1f} KB/s"
    else:
        return f"{speed_kbps/1024:.2f} MB/s"


@dashboard_bp.route("/api/dashboard", methods=["GET"])
@login_required
def get_dashboard_data():
    """
    获取仪表板系统监控数据（含网络速率）
    """
    try:
        # 系统资源（CPU、内存、磁盘、网络基础数据）
        system_stats = SystemMonitor.get_all_stats(Config.VPN_INTERFACE)
        
        # 替换网络数据为带速率的版本
        system_stats['network'] = get_network_with_speed(Config.VPN_INTERFACE)

        return jsonify({
            "success": True,
            "system": system_stats,
            "config": {
                "refresh_interval": getattr(Config, 'REFRESH_INTERVAL', 5000),
            }
        })

    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@dashboard_bp.route("/api/dashboard/health", methods=["GET"])
def monitor_status():
    """健康检查端点"""
    try:
        system_stats = SystemMonitor.get_all_stats(Config.VPN_INTERFACE)
        system_stats['network'] = get_network_with_speed(Config.VPN_INTERFACE)
        
        return jsonify({
            "status": "ok",
            "system": system_stats,
            "msg": "dashboard module running"
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "msg": str(e)
        }), 500