#!/usr/bin/env python3
"""
测试异地登录检测功能的脚本
"""
import subprocess
import time
from datetime import datetime

def create_test_log():
    """创建测试日志文件"""
    test_log_content = f"""
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 192.168.1.100:45123 [testuser] Peer Connection Initiated with [AF_INET]192.168.1.100:45123
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} MULTI: new connection by client 'testuser' will cause previous active sessions by this client to be dropped
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 10.0.0.50:33456 [testuser] Peer Connection Initiated with [AF_INET]10.0.0.50:33456
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} MULTI_sva: pool returned IPv4=10.8.0.2, IPv6=(Not enabled)
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} MULTI: Learn: 10.8.0.2 -> testuser/10.0.0.50:33456
"""
    
    # 创建测试日志文件
    subprocess.run(['sudo', 'mkdir', '-p', '/var/log/openvpn'], check=False)
    with open('/tmp/test_openvpn.log', 'w') as f:
        f.write(test_log_content)
    
    # 复制到OpenVPN日志位置
    subprocess.run(['sudo', 'cp', '/tmp/test_openvpn.log', '/var/log/openvpn/openvpn.log'], check=False)
    subprocess.run(['sudo', 'chmod', '644', '/var/log/openvpn/openvpn.log'], check=False)
    
    print("✅ 测试日志文件已创建")
    print("日志内容:")
    print(test_log_content)

def test_detection():
    """测试检测功能"""
    print("\n🔍 测试异地登录检测功能...")
    
    # 发送请求到检测接口
    import requests
    try:
        response = requests.get('http://localhost:8080/')
        print(f"✅ Web服务响应正常: {response.status_code}")
        
        # 检查通知
        response = requests.get('http://localhost:8080/notifications')
        if response.status_code == 200:
            notifications = response.json().get('notifications', [])
            print(f"📋 发现 {len(notifications)} 个安全通知")
            for i, notif in enumerate(notifications[:3]):
                print(f"  {i+1}. {notif.get('client_name')} - {notif.get('message', '')[:100]}...")
        else:
            print(f"❌ 无法获取通知: {response.status_code}")
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")

if __name__ == "__main__":
    print("🧪 OpenVPN异地登录检测测试")
    print("=" * 50)
    
    create_test_log()
    time.sleep(2)
    test_detection()
    
    print("\n✅ 测试完成！请查看Web界面: http://localhost:8080")
