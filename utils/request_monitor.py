# utils/request_monitor.py
"""
请求监控和并发控制模块
"""
import threading
import time


class ConcurrentRequestLimiter:
    """并发请求限制器"""
    
    def __init__(self, max_concurrent=10):
        """
        初始化并发限制器
        
        Args:
            max_concurrent: 最大并发请求数
        """
        self.max_concurrent = max_concurrent
        self.current = 0
        self.lock = threading.Lock()
    
    def acquire(self):
        """
        尝试获取请求槽位
        
        Returns:
            bool: 是否成功获取槽位
        """
        with self.lock:
            if self.current >= self.max_concurrent:
                return False
            self.current += 1
            return True
    
    def release(self):
        """释放请求槽位"""
        with self.lock:
            if self.current > 0:
                self.current -= 1
    
    def get_stats(self):
        """
        获取统计信息
        
        Returns:
            dict: 包含当前并发数和最大并发数
        """
        with self.lock:
            return {
                'current': self.current,
                'max': self.max_concurrent,
                'utilization': f"{(self.current / self.max_concurrent * 100):.1f}%"
            }


class RequestMonitor:
    """请求性能监控器"""
    
    def __init__(self, max_records=100):
        """
        初始化监控器
        
        Args:
            max_records: 保留的最大记录数
        """
        self.max_records = max_records
        self.slow_requests = []
        self.lock = threading.Lock()
    
    def log_slow_request(self, path, duration, method='GET'):
        """
        记录慢请求
        
        Args:
            path: 请求路径
            duration: 处理时间（秒）
            method: HTTP 方法
        """
        with self.lock:
            self.slow_requests.append({
                'path': path,
                'method': method,
                'duration': round(duration, 3),
                'timestamp': time.time()
            })
            # 只保留最近的记录
            if len(self.slow_requests) > self.max_records:
                self.slow_requests.pop(0)
    
    def get_slow_requests(self, threshold=5.0, limit=10):
        """
        获取慢请求列表
        
        Args:
            threshold: 慢请求阈值（秒）
            limit: 返回的最大记录数
        
        Returns:
            list: 慢请求列表
        """
        with self.lock:
            filtered = [
                r for r in self.slow_requests 
                if r['duration'] > threshold
            ]
            # 按时间倒序，返回最近的
            return sorted(filtered, key=lambda x: x['timestamp'], reverse=True)[:limit]
    
    def get_stats(self):
        """
        获取监控统计信息
        
        Returns:
            dict: 统计信息
        """
        with self.lock:
            if not self.slow_requests:
                return {
                    'total_records': 0,
                    'avg_duration': 0,
                    'max_duration': 0,
                    'min_duration': 0
                }
            
            durations = [r['duration'] for r in self.slow_requests]
            return {
                'total_records': len(self.slow_requests),
                'avg_duration': round(sum(durations) / len(durations), 3),
                'max_duration': round(max(durations), 3),
                'min_duration': round(min(durations), 3)
            }
    
    def clear(self):
        """清空所有记录"""
        with self.lock:
            self.slow_requests.clear()