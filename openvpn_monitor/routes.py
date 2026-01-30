"""
OpenVPN 路由模块
提供API接口供前端调用
"""

from flask import jsonify, request, render_template, current_app
import os
from . import openvpn_bp, module_dir
from .openvpn_manager import OpenVPNManager
from .system_monitor import SystemMonitor
from .network_limiter import NetworkLimiter
from .config import Config


# 初始化管理器
openvpn_manager = OpenVPNManager(
    service_name=Config.OPENVPN_SERVICE_NAME,
    status_file=Config.OPENVPN_STATUS_FILE
)
network_limiter = NetworkLimiter(interface=Config.VPN_INTERFACE)


# ==================== 健康检查路由 ====================

@openvpn_bp.get("/status")
def monitor_status():
    """健康检查端点"""
    status = openvpn_manager.get_service_status()
    return jsonify({
        "status": "ok" if status['running'] else "error",
        "service": status,
        "msg": "monitor module running"
    })


# ==================== API 路由 ====================

@openvpn_bp.get("/api/dashboard")
def get_dashboard_data():
    """
    获取仪表板完整数据
    """
    try:
        # OpenVPN状态
        service_status = openvpn_manager.get_service_status()
        clients = openvpn_manager.get_connected_clients()
        
        # 系统资源
        system_stats = SystemMonitor.get_all_stats(Config.VPN_INTERFACE)
        
        # 网络限速状态
        current_limit = network_limiter.get_current_limit()
        
        return jsonify({
            "success": True,
            "openvpn": {
                "status": service_status,
                "clients": clients
            },
            "system": system_stats,
            "bandwidth_limit": current_limit,
            "config": {
                "refresh_interval": Config.REFRESH_INTERVAL,
                "min_bandwidth": Config.MIN_BANDWIDTH_MBPS,
                "max_bandwidth": Config.MAX_BANDWIDTH_MBPS
            }
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@openvpn_bp.post("/api/service/<action>")
def control_service(action):
    """控制OpenVPN服务"""
    if action not in ['start', 'stop', 'restart']:
        return jsonify({
            "success": False,
            "message": f"无效的操作: {action}"
        }), 400
    
    if action == 'start':
        result = openvpn_manager.start_service()
    elif action == 'stop':
        result = openvpn_manager.stop_service()
    else:
        result = openvpn_manager.restart_service()
    
    return jsonify(result)


@openvpn_bp.get("/api/service/status")
def get_service_status():
    """获取OpenVPN服务状态"""
    status = openvpn_manager.get_service_status()
    return jsonify({
        "success": True,
        "data": status
    })


@openvpn_bp.get("/api/clients")
def get_clients():
    """获取已连接的客户端列表"""
    clients = openvpn_manager.get_connected_clients()
    return jsonify({
        "success": True,
        "count": len(clients),
        "clients": clients
    })


@openvpn_bp.post("/api/clients/<client_name>/disconnect")
def disconnect_client(client_name):
    """断开指定客户端连接"""
    result = openvpn_manager.disconnect_client(client_name)
    return jsonify(result)


@openvpn_bp.post("/api/bandwidth/limit")
def set_bandwidth_limit():
    """设置带宽限制"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "message": "请求体不能为空"
            }), 400
        
        download = data.get('download')
        upload = data.get('upload')
        
        if download is None or upload is None:
            return jsonify({
                "success": False,
                "message": "缺少必要参数: download 和 upload"
            }), 400
        
        if not network_limiter.validate_bandwidth(download, Config.MIN_BANDWIDTH_MBPS, Config.MAX_BANDWIDTH_MBPS):
            return jsonify({
                "success": False,
                "message": f"下载速度必须在 {Config.MIN_BANDWIDTH_MBPS} 到 {Config.MAX_BANDWIDTH_MBPS} Mbps 之间"
            }), 400
            
        if not network_limiter.validate_bandwidth(upload, Config.MIN_BANDWIDTH_MBPS, Config.MAX_BANDWIDTH_MBPS):
            return jsonify({
                "success": False,
                "message": f"上传速度必须在 {Config.MIN_BANDWIDTH_MBPS} 到 {Config.MAX_BANDWIDTH_MBPS} Mbps 之间"
            }), 400
        
        result = network_limiter.set_bandwidth_limit(download, upload)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"设置失败: {str(e)}"
        }), 500


@openvpn_bp.delete("/api/bandwidth/limit")
def remove_bandwidth_limit():
    """移除带宽限制"""
    result = network_limiter.remove_bandwidth_limit()
    return jsonify(result)


@openvpn_bp.get("/api/bandwidth/status")
def get_bandwidth_status():
    """获取当前带宽限制状态"""
    limit = network_limiter.get_current_limit()
    return jsonify({
        "success": True,
        "limited": limit is not None,
        "details": limit
    })


@openvpn_bp.get("/api/system/stats")
def get_system_stats():
    """获取系统资源统计"""
    stats = SystemMonitor.get_all_stats(Config.VPN_INTERFACE)
    return jsonify({
        "success": True,
        "data": stats
    })


# ==================== 页面路由 ====================

@openvpn_bp.get("/dashboard")
def dashboard_page():
    """Serve the dashboard HTML页面 - 使用templates目录"""
    return render_template('dashboard.html')


# 根路径重定向到dashboard
@openvpn_bp.get("/")
def index():
    """根路径 - 返回API信息或重定向到dashboard"""
    accept_header = request.headers.get('Accept', '')
    
    if 'text/html' in accept_header:
        return dashboard_page()
    
    return jsonify({
        "name": "OpenVPN Monitor API",
        "version": "1.0.0",
        "endpoints": {
            "status": "/openvpn/status",
            "dashboard_data": "/openvpn/api/dashboard",
            "dashboard_page": "/openvpn/dashboard",
            "service_control": "/openvpn/api/service/<action>",
            "clients": "/openvpn/api/clients",
            "bandwidth": "/openvpn/api/bandwidth/limit",
            "system_stats": "/openvpn/api/system/stats"
        }
    })