"""
配置文件
"""

import os


class Config:
    """OpenVPN监控系统配置"""
    
    # OpenVPN配置
    OPENVPN_CONFIG_DIR = '/etc/openvpn'
    OPENVPN_STATUS_FILE = '/var/log/openvpn/openvpn-status.log'
    OPENVPN_SERVICE_NAME = 'openvpn@server'  # 修改为带实例名的服务名
    
    # 网络接口
    VPN_INTERFACE = 'tun0'
    
    # 带宽限制范围 (Mbps)
    MIN_BANDWIDTH_MBPS = 1.0
    MAX_BANDWIDTH_MBPS = 100.0
    
    # 日志配置
    LOG_DIR = '/var/log/openvpn'
    LOG_FILE = os.path.join(LOG_DIR, 'monitor.log')
    
    # 刷新间隔 (秒)
    REFRESH_INTERVAL = 5

    @classmethod
    def validate(cls):
        """验证配置"""
        errors = []
        
        if not os.path.exists(cls.OPENVPN_CONFIG_DIR):
            errors.append(f"OpenVPN配置目录不存在: {cls.OPENVPN_CONFIG_DIR}")
        
        if cls.MIN_BANDWIDTH_MBPS <= 0 or cls.MAX_BANDWIDTH_MBPS <= cls.MIN_BANDWIDTH_MBPS:
            errors.append("带宽限制配置无效")
        
        return errors