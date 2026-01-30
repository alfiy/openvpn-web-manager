"""
OpenVPN管理模块
服务控制和客户端管理
"""

import subprocess
import re
from typing import Dict, List, Optional
from datetime import datetime


class OpenVPNManager:
    """OpenVPN服务管理器"""
    
    def __init__(self, service_name: str = 'openvpn@server', status_file: str = '/var/log/openvpn/openvpn-status.log'):
        self.service_name = service_name
        self.status_file = status_file
    
    def get_service_status(self) -> Dict:
        """获取OpenVPN服务状态"""
        try:
            result = subprocess.run(
                ['systemctl', 'is-active', self.service_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            is_active = result.stdout.strip() == 'active'
            
            # 获取服务详细信息
            result = subprocess.run(
                ['systemctl', 'status', self.service_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            return {
                'running': is_active,
                'status': 'running' if is_active else 'stopped',
                'details': result.stdout
            }
        except Exception as e:
            return {
                'running': False,
                'status': 'unknown',
                'error': str(e)
            }
    
    def start_service(self) -> Dict:
        """启动OpenVPN服务"""
        try:
            subprocess.run(
                ['sudo', 'systemctl', 'start', self.service_name],
                capture_output=True,
                text=True,
                timeout=10,
                check=True
            )
            return {'success': True, 'message': '服务启动成功'}
        except subprocess.CalledProcessError as e:
            return {'success': False, 'message': f'启动失败: {e.stderr}'}
        except Exception as e:
            return {'success': False, 'message': f'启动失败: {str(e)}'}
    
    def stop_service(self) -> Dict:
        """停止OpenVPN服务"""
        try:
            subprocess.run(
                ['sudo', 'systemctl', 'stop', self.service_name],
                capture_output=True,
                text=True,
                timeout=10,
                check=True
            )
            return {'success': True, 'message': '服务停止成功'}
        except subprocess.CalledProcessError as e:
            return {'success': False, 'message': f'停止失败: {e.stderr}'}
        except Exception as e:
            return {'success': False, 'message': f'停止失败: {str(e)}'}
    
    def restart_service(self) -> Dict:
        """重启OpenVPN服务"""
        try:
            subprocess.run(
                ['sudo', 'systemctl', 'restart', self.service_name],
                capture_output=True,
                text=True,
                timeout=10,
                check=True
            )
            return {'success': True, 'message': '服务重启成功'}
        except subprocess.CalledProcessError as e:
            return {'success': False, 'message': f'重启失败: {e.stderr}'}
        except Exception as e:
            return {'success': False, 'message': f'重启失败: {str(e)}'}
    
    def get_connected_clients(self) -> List[Dict]:
        """获取已连接的客户端列表"""
        clients = []
        
        try:
            with open(self.status_file, 'r') as f:
                content = f.read()
            
            # 解析客户端连接信息
            client_section = False
            for line in content.split('\n'):
                if 'Common Name,Real Address,Bytes Received,Bytes Sent,Connected Since' in line:
                    client_section = True
                    continue
                
                if client_section:
                    if line.strip() == '' or line.startswith('ROUTING TABLE'):
                        break
                    
                    parts = line.split(',')
                    if len(parts) >= 5:
                        clients.append({
                            'common_name': parts[0],
                            'real_address': parts[1],
                            'bytes_received': int(parts[2]) if parts[2].isdigit() else 0,
                            'bytes_sent': int(parts[3]) if parts[3].isdigit() else 0,
                            'connected_since': parts[4]
                        })
        
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"解析客户端列表失败: {e}")
        
        return clients
    
    def disconnect_client(self, client_name: str) -> Dict:
        """断开指定客户端连接"""
        # 注意：这需要OpenVPN管理接口支持
        # 这里提供一个基本实现框架
        try:
            # 实际实现需要通过OpenVPN管理接口或重启服务
            return {
                'success': False,
                'message': '此功能需要配置OpenVPN管理接口'
            }
        except Exception as e:
            return {'success': False, 'message': str(e)}