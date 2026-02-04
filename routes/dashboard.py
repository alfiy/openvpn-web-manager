# """
# Dashboard 仪表板路由
# 系统监控数据接口（含网络速率）
# """

# from flask import Blueprint, jsonify
# from routes.helpers import login_required
# from openvpn_monitor.system_monitor import SystemMonitor
# from openvpn_monitor.config import Config
# import time

# dashboard_bp = Blueprint('dashboard', __name__)

# # 全局变量存储上次网络数据用于计算速率
# _last_net_stats = None
# _last_net_time = None


# def get_network_with_speed(vpn_interface: str = 'tun0' ) -> dict:
#     """
#     获取网络统计并计算上传/下载速率
#     """
#     global _last_net_stats, _last_net_time
    
#     # 获取当前原始数据
#     current_stats = SystemMonitor.get_network_stats(vpn_interface)
#     current_time = time.time()
    
#     # 构建结果
#     result = {
#         'upload_total': round(current_stats['bytes_sent'] / 1024 / 1024, 2),    # MB
#         'download_total': round(current_stats['bytes_recv'] / 1024 / 1024, 2),  # MB
#         'upload_speed': 0,      # KB/s
#         'download_speed': 0,    # KB/s
#         'upload_speed_str': '0 KB/s',
#         'download_speed_str': '0 KB/s'
#     }
    
#     # 计算速率
#     if _last_net_stats is not None and _last_net_time is not None:
#         time_delta = current_time - _last_net_time
        
#         if time_delta > 0:
#             # 计算速度 (bytes -> KB/s)
#             upload_speed = (current_stats['bytes_sent'] - _last_net_stats['bytes_sent']) / time_delta / 1024
#             download_speed = (current_stats['bytes_recv'] - _last_net_stats['bytes_recv']) / time_delta / 1024
            
#             result['upload_speed'] = round(upload_speed, 2)
#             result['download_speed'] = round(download_speed, 2)
#             result['upload_speed_str'] = format_speed(upload_speed)
#             result['download_speed_str'] = format_speed(download_speed)
    
#     # 更新全局变量
#     _last_net_stats = current_stats.copy()
#     _last_net_time = current_time
    
#     return result


# def format_speed(speed_kbps: float) -> str:
#     """格式化速度显示"""
#     if speed_kbps < 0:
#         speed_kbps = 0
    
#     if speed_kbps < 1024:
#         return f"{speed_kbps:.1f} KB/s"
#     else:
#         return f"{speed_kbps/1024:.2f} MB/s"


# @dashboard_bp.route("/api/dashboard", methods=["GET"])
# @login_required
# def get_dashboard_data():
#     """
#     获取仪表板系统监控数据（含网络速率）
#     """
#     try:
#         # 系统资源（CPU、内存、磁盘、网络基础数据）
#         system_stats = SystemMonitor.get_all_stats(Config.VPN_INTERFACE)
        
#         # 替换网络数据为带速率的版本
#         system_stats['network'] = get_network_with_speed(Config.VPN_INTERFACE)

#         return jsonify({
#             "success": True,
#             "system": system_stats,
#             "config": {
#                 "refresh_interval": getattr(Config, 'REFRESH_INTERVAL', 5000),
#             }
#         })

#     except Exception as e:
#         import traceback
#         return jsonify({
#             "success": False,
#             "error": str(e),
#             "traceback": traceback.format_exc()
#         }), 500


# @dashboard_bp.route("/api/dashboard/health", methods=["GET"])
# def monitor_status():
#     """健康检查端点"""
#     try:
#         system_stats = SystemMonitor.get_all_stats(Config.VPN_INTERFACE)
#         system_stats['network'] = get_network_with_speed(Config.VPN_INTERFACE)
        
#         return jsonify({
#             "status": "ok",
#             "system": system_stats,
#             "msg": "dashboard module running"
#         })
#     except Exception as e:
#         return jsonify({
#             "status": "error",
#             "msg": str(e)
#         }), 500

"""
Dashboard 仪表板路由
系统监控数据接口（含网络速率）
"""
from flask import Blueprint, jsonify, request
from routes.helpers import login_required
from openvpn_monitor.system_monitor import SystemMonitor
from openvpn_monitor.config import Config
import time

dashboard_bp = Blueprint('dashboard', __name__)

# 全局变量存储上次网络数据用于计算速率
_last_net_stats = None
_last_net_time = None

def get_network_with_speed(vpn_interface: str = None) -> dict:
    """
    获取网络统计并计算上传/下载速率
    """
    global _last_net_stats, _last_net_time
    
    # 如果未指定接口，使用配置文件中的接口
    if vpn_interface is None:
        vpn_interface = Config.VPN_INTERFACE
    
    # 获取当前原始数据
    try:
        current_stats = SystemMonitor.get_network_stats(vpn_interface)
    except Exception as e:
        # 如果获取失败，返回空数据
        return {
            'upload_total': 0,
            'download_total': 0,
            'upload_speed': 0,
            'download_speed': 0,
            'upload_speed_str': '0 KB/s',
            'download_speed_str': '0 KB/s',
            'interface': vpn_interface,
            'error': str(e)
        }
    
    current_time = time.time()
    
    # 构建结果
    result = {
        'upload_total': round(current_stats['bytes_sent'] / 1024 / 1024, 2),    # MB
        'download_total': round(current_stats['bytes_recv'] / 1024 / 1024, 2),  # MB
        'upload_speed': 0,      # KB/s
        'download_speed': 0,    # KB/s
        'upload_speed_str': '0 KB/s',
        'download_speed_str': '0 KB/s',
        'interface': vpn_interface  # 添加接口名称
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
                "vpn_interface": Config.VPN_INTERFACE  # 返回当前接口
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

# 🆕 获取当前网络接口配置
@dashboard_bp.route("/api/dashboard/network-interface", methods=["GET"])
@login_required
def get_network_interface():
    """获取当前网络监控接口配置"""
    try:
        return jsonify({
            "code": 0,
            "data": {
                "interface": Config.VPN_INTERFACE
            },
            "msg": "获取成功"
        })
    except Exception as e:
        return jsonify({
            "code": 1,
            "msg": f"获取失败: {str(e)}"
        }), 500

# 🆕 设置网络接口并写入配置文件
@dashboard_bp.route("/api/dashboard/network-interface", methods=["POST"])
@login_required
def set_network_interface():
    """设置网络监控接口并写入配置文件"""
    try:
        data = request.get_json()
        interface_name = data.get('interface', '').strip()
        
        if not interface_name:
            return jsonify({
                "code": 1,
                "msg": "接口名称不能为空"
            }), 400
        
        # 验证接口是否存在
        try:
            SystemMonitor.get_network_stats(interface_name)
        except Exception as e:
            return jsonify({
                "code": 1,
                "msg": f"网络接口 '{interface_name}' 不存在或无法访问: {str(e)}"
            }), 400
        
        # 🆕 修改配置文件
        import os
        config_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'openvpn_monitor', 'config.py')
        
        try:
            # 读取配置文件
            with open(config_file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 查找并修改 VPN_INTERFACE 行
            modified = False
            for i, line in enumerate(lines):
                if line.strip().startswith('VPN_INTERFACE'):
                    lines[i] = f"    VPN_INTERFACE = '{interface_name}'\n"
                    modified = True
                    break
            
            if not modified:
                return jsonify({
                    "code": 1,
                    "msg": "配置文件中未找到 VPN_INTERFACE 配置项"
                }), 500
            
            # 写回配置文件
            with open(config_file_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            
            # 🆕 更新运行时配置
            Config.VPN_INTERFACE = interface_name
            
            # 🆕 重置网络统计缓存
            global _last_net_stats, _last_net_time
            _last_net_stats = None
            _last_net_time = None
            
            return jsonify({
                "code": 0,
                "msg": f"网络监控接口已更新为: {interface_name}，配置已保存",
                "data": {
                    "interface": interface_name,
                    "need_reload": True  # 提示需要重启服务
                }
            })
            
        except Exception as e:
            import traceback
            return jsonify({
                "code": 1,
                "msg": f"写入配置文件失败: {str(e)}",
                "traceback": traceback.format_exc()
            }), 500
            
    except Exception as e:
        import traceback
        return jsonify({
            "code": 1,
            "msg": f"设置失败: {str(e)}",
            "traceback": traceback.format_exc()
        }), 500

# 🆕 获取可用的网络接口列表
@dashboard_bp.route("/api/dashboard/network-interfaces", methods=["GET"])
@login_required
def get_available_interfaces():
    """获取系统中所有可用的网络接口"""
    try:
        import psutil
        interfaces = []
        
        # 获取所有网络接口
        net_if_addrs = psutil.net_if_addrs()
        net_if_stats = psutil.net_if_stats()
        
        for interface_name, addrs in net_if_addrs.items():
            # 获取接口状态
            is_up = net_if_stats.get(interface_name).isup if interface_name in net_if_stats else False
            
            # 获取IP地址
            ipv4_addr = None
            for addr in addrs:
                if addr.family == 2:  # AF_INET (IPv4)
                    ipv4_addr = addr.address
                    break
            
            interfaces.append({
                'name': interface_name,
                'is_up': is_up,
                'ipv4': ipv4_addr,
                'is_current': interface_name == Config.VPN_INTERFACE
            })
        
        return jsonify({
            "code": 0,
            "data": {
                "interfaces": interfaces,
                "current": Config.VPN_INTERFACE
            },
            "msg": "获取成功"
        })
    except Exception as e:
        import traceback
        return jsonify({
            "code": 1,
            "msg": f"获取失败: {str(e)}",
            "traceback": traceback.format_exc()
        }), 500