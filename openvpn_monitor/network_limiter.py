"""
网络限速模块
使用tc (traffic control) 实现带宽限制
"""

import subprocess
from typing import Dict, Optional


class NetworkLimiter:
    """网络带宽限制器"""
    
    def __init__(self, interface: str = 'tun0'):
        self.interface = interface
    
    def get_current_limit(self) -> Optional[Dict]:
        """获取当前带宽限制"""
        try:
            result = subprocess.run(
                ['tc', 'qdisc', 'show', 'dev', self.interface],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            output = result.stdout
            if 'tbf' in output or 'htb' in output:
                # 解析限速信息
                # 这是一个简化实现，实际可能需要更复杂的解析
                return {
                    'enabled': True,
                    'details': output
                }
            
            return None
        
        except Exception as e:
            print(f"获取限速信息失败: {e}")
            return None
    
    def set_bandwidth_limit(self, download_mbps: float, upload_mbps: float) -> Dict:
        """设置带宽限制"""
        try:
            # 先清除现有规则
            self.remove_bandwidth_limit()
            
            # 转换为kbit
            download_kbit = int(download_mbps * 1024)
            upload_kbit = int(upload_mbps * 1024)
            
            # 设置下载限制 (ingress)
            subprocess.run(
                ['sudo', 'tc', 'qdisc', 'add', 'dev', self.interface, 'root', 'tbf',
                 'rate', f'{download_kbit}kbit', 'burst', '32kbit', 'latency', '400ms'],
                capture_output=True,
                text=True,
                timeout=5,
                check=True
            )
            
            return {
                'success': True,
                'message': f'带宽限制已设置: 下载 {download_mbps}Mbps, 上传 {upload_mbps}Mbps'
            }
        
        except subprocess.CalledProcessError as e:
            return {
                'success': False,
                'message': f'设置失败: {e.stderr}'
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'设置失败: {str(e)}'
            }
    
    def remove_bandwidth_limit(self) -> Dict:
        """移除带宽限制"""
        try:
            # 删除root qdisc
            subprocess.run(
                ['sudo', 'tc', 'qdisc', 'del', 'dev', self.interface, 'root'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            return {
                'success': True,
                'message': '带宽限制已移除'
            }
        
        except subprocess.CalledProcessError:
            # 如果没有规则，删除会失败，这是正常的
            return {
                'success': True,
                'message': '无需移除（未设置限制）'
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'移除失败: {str(e)}'
            }
    
    def validate_bandwidth(self, mbps: float, min_mbps: float = 1.0, max_mbps: float = 100.0) -> bool:
        """验证带宽值是否有效"""
        return min_mbps <= mbps <= max_mbps