"""
系统监控模块
监控CPU、内存、磁盘使用率
"""

import psutil
from typing import Dict


class SystemMonitor:
    """系统资源监控器"""
    
    @staticmethod
    def get_cpu_usage() -> float:
        """获取CPU使用率"""
        return psutil.cpu_percent(interval=1)
    
    @staticmethod
    def get_memory_usage() -> Dict[str, float]:
        """获取内存使用情况"""
        mem = psutil.virtual_memory()
        return {
            'total': mem.total / (1024 ** 3),  # GB
            'used': mem.used / (1024 ** 3),
            'percent': mem.percent
        }
    
    @staticmethod
    def get_disk_usage(path: str = '/') -> Dict[str, float]:
        """获取磁盘使用情况"""
        disk = psutil.disk_usage(path)
        return {
            'total': disk.total / (1024 ** 3),  # GB
            'used': disk.used / (1024 ** 3),
            'percent': disk.percent
        }
    
    @staticmethod
    def get_network_stats(interface: str = 'tun0') -> Dict[str, int]:
        """获取网络接口统计"""
        try:
            stats = psutil.net_io_counters(pernic=True)
            if interface in stats:
                net = stats[interface]
                return {
                    'bytes_sent': net.bytes_sent,
                    'bytes_recv': net.bytes_recv,
                    'packets_sent': net.packets_sent,
                    'packets_recv': net.packets_recv
                }
        except Exception:
            pass
        
        return {
            'bytes_sent': 0,
            'bytes_recv': 0,
            'packets_sent': 0,
            'packets_recv': 0
        }
    
    @classmethod
    def get_all_stats(cls, vpn_interface: str = 'tun0') -> Dict:
        """获取所有系统统计信息"""
        return {
            'cpu': cls.get_cpu_usage(),
            'memory': cls.get_memory_usage(),
            'disk': cls.get_disk_usage(),
            'network': cls.get_network_stats(vpn_interface)
        }