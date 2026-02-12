# utils/request_timeout.py
"""
请求超时处理模块
"""
import signal
from functools import wraps


class RequestTimeout(Exception):
    """请求超时异常"""
    pass


def timeout_handler(signum, frame):
    """超时信号处理器"""
    raise RequestTimeout("Request processing timeout")


def request_timeout(seconds=30):
    """
    请求超时装饰器
    为每个请求设置超时限制，防止长时间阻塞
    
    Args:
        seconds: 超时时间（秒）
    
    Usage:
        @app.route('/api/long-task')
        @request_timeout(seconds=60)
        def long_task():
            # 最多执行 60 秒
            ...
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # 设置超时信号
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(seconds)
            
            try:
                result = f(*args, **kwargs)
            except RequestTimeout:
                # 请求超时，抛出异常让全局错误处理器处理
                raise
            finally:
                # 取消超时信号
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
            
            return result
        return wrapper
    return decorator