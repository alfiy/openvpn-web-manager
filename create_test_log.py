#!/usr/bin/env python3
"""
创建测试日志文件以模拟异地登录场景
"""
import os
from datetime import datetime, timedelta

def create_test_logs():
    """创建包含异地登录模式的测试日志"""
    
    # 创建日志目录
    os.makedirs('/tmp/openvpn_test', exist_ok=True)
    
    # 模拟异地登录日志内容
    now = datetime.now()
    time1 = now.strftime('%Y-%m-%d %H:%M:%S')
    time2 = (now + timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
    time3 = (now + timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')
    
    test_log_content = f"""
{time1} 192.168.50.1:55121 [mxb] Peer Connection Initiated with [AF_INET]192.168.50.1:55121
{time1} MULTI: new connection by client 'mxb' will cause previous active sessions by this client to be dropped.
{time1} MULTI_sva: pool returned IPv4=10.8.0.2, IPv6=(Not enabled)
{time1} MULTI: Learn: 10.8.0.2 -> mxb/192.168.50.1:55121

{time2} 203.0.113.45:33456 [mxb] Peer Connection Initiated with [AF_INET]203.0.113.45:33456
{time2} MULTI: new connection by client 'mxb' will cause previous active sessions by this client to be dropped.
{time2} MULTI_sva: pool returned IPv4=10.8.0.3, IPv6=(Not enabled)
{time2} MULTI: Learn: 10.8.0.3 -> mxb/203.0.113.45:33456

{time3} 198.51.100.67:44789 [mxb] Peer Connection Initiated with [AF_INET]198.51.100.67:44789
{time3} MULTI: new connection by client 'mxb' will cause previous active sessions by this client to be dropped.
{time3} MULTI_sva: pool returned IPv4=10.8.0.4, IPv6=(Not enabled)
{time3} MULTI: Learn: 10.8.0.4 -> mxb/198.51.100.67:44789
"""
    
    # 写入测试日志文件
    test_log_path = '/tmp/openvpn_test/openvpn.log'
    with open(test_log_path, 'w') as f:
        f.write(test_log_content.strip())
    
    print(f"✅ 测试日志已创建: {test_log_path}")
    print("📋 日志内容:")
    print(test_log_content)
    
    return test_log_path

if __name__ == "__main__":
    create_test_logs()
