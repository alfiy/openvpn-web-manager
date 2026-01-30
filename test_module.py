"""
测试脚本 - 验证OpenVPN监控模块功能
"""

import sys
from openvpn_monitor.system_monitor import SystemMonitor
from openvpn_monitor.openvpn_manager import OpenVPNManager
from openvpn_monitor.network_limiter import NetworkLimiter
from openvpn_monitor.config import Config


def test_system_monitor():
    """测试系统监控"""
    print("\n" + "="*50)
    print("测试系统监控模块")
    print("="*50)
    
    monitor = SystemMonitor()
    
    print(f"✓ CPU使用率: {monitor.get_cpu_usage():.1f}%")
    
    mem = monitor.get_memory_usage()
    print(f"✓ 内存使用: {mem['used']:.1f}GB / {mem['total']:.1f}GB ({mem['percent']:.1f}%)")
    
    disk = monitor.get_disk_usage()
    print(f"✓ 磁盘使用: {disk['used']:.1f}GB / {disk['total']:.1f}GB ({disk['percent']:.1f}%)")
    
    net = monitor.get_network_stats('tun0')
    print(f"✓ 网络统计: 发送 {net['bytes_sent']} 字节, 接收 {net['bytes_recv']} 字节")


def test_openvpn_manager():
    """测试OpenVPN管理"""
    print("\n" + "="*50)
    print("测试OpenVPN管理模块")
    print("="*50)
    
    manager = OpenVPNManager()
    
    status = manager.get_service_status()
    print(f"✓ 服务状态: {status['status']}")
    
    clients = manager.get_connected_clients()
    print(f"✓ 连接客户端数: {len(clients)}")
    
    if clients:
        for client in clients:
            print(f"  - {client['common_name']} ({client['real_address']})")


def test_network_limiter():
    """测试网络限速"""
    print("\n" + "="*50)
    print("测试网络限速模块")
    print("="*50)
    
    limiter = NetworkLimiter('tun0')
    
    current = limiter.get_current_limit()
    if current:
        print(f"✓ 当前限速: 已启用")
    else:
        print(f"✓ 当前限速: 未启用")
    
    # 测试带宽验证
    print(f"✓ 带宽验证 (10 Mbps): {limiter.validate_bandwidth(10)}")
    print(f"✓ 带宽验证 (200 Mbps): {limiter.validate_bandwidth(200)}")


def test_config():
    """测试配置"""
    print("\n" + "="*50)
    print("测试配置模块")
    print("="*50)
    
    errors = Config.validate()
    if errors:
        print("⚠️  配置验证失败:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("✓ 配置验证通过")
    
    print(f"✓ OpenVPN配置目录: {Config.OPENVPN_CONFIG_DIR}")
    print(f"✓ 状态文件: {Config.OPENVPN_STATUS_FILE}")
    print(f"✓ VPN接口: {Config.VPN_INTERFACE}")


def main():
    """运行所有测试"""
    print("\n" + "="*50)
    print("OpenVPN 监控模块功能测试")
    print("="*50)
    
    try:
        test_config()
        test_system_monitor()
        test_openvpn_manager()
        test_network_limiter()
        
        print("\n" + "="*50)
        print("✅ 所有测试完成")
        print("="*50)
        print("\n提示:")
        print("- 如果OpenVPN服务未运行,某些测试可能显示空数据")
        print("- 网络限速功能需要sudo权限")
        print("- 运行 'sudo bash deploy.sh' 完成系统配置")
        print()
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()