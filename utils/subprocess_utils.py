"""
subprocess_utils.py
带超时保护的 subprocess 调用工具
"""

import subprocess
import functools
import logging
from typing import List, Optional, Tuple

# 配置日志
logger = logging.getLogger(__name__)


class SubprocessTimeout(Exception):
    """Subprocess 超时异常"""
    pass


def run_command_with_timeout(
    cmd: List[str],
    timeout: int = 5,
    check: bool = False,
    capture_output: bool = True,
    text: bool = True,
    shell: bool = False
) -> subprocess.CompletedProcess:
    """
    带超时保护的命令执行
    
    Args:
        cmd: 命令列表，例如 ['sudo', 'systemctl', 'status', 'openvpn']
        timeout: 超时时间（秒），默认 5 秒
        check: 是否检查返回码
        capture_output: 是否捕获输出
        text: 是否以文本模式返回
        shell: 是否使用 shell 执行
    
    Returns:
        CompletedProcess 对象
    
    Raises:
        SubprocessTimeout: 如果命令执行超时
        subprocess.CalledProcessError: 如果 check=True 且命令返回非零
    """
    try:
        result = subprocess.run(
            cmd,
            timeout=timeout,
            check=check,
            capture_output=capture_output,
            text=text,
            shell=shell
        )
        return result
    except subprocess.TimeoutExpired as e:
        logger.warning(f"Command timeout after {timeout}s: {' '.join(cmd)}")
        raise SubprocessTimeout(f"Command timed out after {timeout} seconds: {' '.join(cmd)}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed with code {e.returncode}: {' '.join(cmd)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error running command: {e}")
        raise


# ============================================================================
# OpenVPN 相关命令的封装（带缓存）
# ============================================================================

import time
from threading import Lock

class CachedCommandExecutor:
    """带缓存的命令执行器"""
    
    def __init__(self, cache_seconds: int = 10):
        self.cache_seconds = cache_seconds
        self._cache = {}
        self._lock = Lock()
    
    def execute(self, cache_key: str, cmd: List[str], timeout: int = 5) -> Tuple[bool, str]:
        """
        执行命令并缓存结果
        
        Args:
            cache_key: 缓存键
            cmd: 命令列表
            timeout: 超时时间
        
        Returns:
            (success: bool, output: str)
        """
        now = time.time()
        
        # 检查缓存
        with self._lock:
            if cache_key in self._cache:
                cached_time, cached_result = self._cache[cache_key]
                if now - cached_time < self.cache_seconds:
                    logger.debug(f"Cache hit for {cache_key}")
                    return cached_result
        
        # 缓存失效，执行命令
        try:
            result = run_command_with_timeout(cmd, timeout=timeout)
            success = result.returncode == 0
            output = result.stdout if result.stdout else ""
            
            # 更新缓存
            with self._lock:
                self._cache[cache_key] = (now, (success, output))
            
            return success, output
            
        except SubprocessTimeout:
            logger.warning(f"Command timeout for cache key: {cache_key}")
            return False, "Command timeout"
        except Exception as e:
            logger.error(f"Command failed for cache key {cache_key}: {e}")
            return False, str(e)
    
    def clear_cache(self, cache_key: Optional[str] = None):
        """清除缓存"""
        with self._lock:
            if cache_key:
                self._cache.pop(cache_key, None)
            else:
                self._cache.clear()


# 创建全局实例
command_executor = CachedCommandExecutor(cache_seconds=10)


# ============================================================================
# 常用 OpenVPN 命令封装
# ============================================================================

def check_openvpn_status(timeout: int = 5, use_cache: bool = True) -> bool:
    """
    检查 OpenVPN 服务状态
    
    Args:
        timeout: 超时时间（秒）
        use_cache: 是否使用缓存
    
    Returns:
        bool: 服务是否运行
    """
    cmd = ['sudo', 'systemctl', 'is-active', '--quiet', 'openvpn@server.service']
    
    if use_cache:
        success, _ = command_executor.execute('openvpn_status', cmd, timeout)
        return success
    else:
        try:
            result = run_command_with_timeout(cmd, timeout=timeout)
            return result.returncode == 0
        except:
            return False


def get_openvpn_clients(timeout: int = 5, use_cache: bool = True) -> str:
    """
    获取 OpenVPN 客户端列表
    
    Args:
        timeout: 超时时间（秒）
        use_cache: 是否使用缓存
    
    Returns:
        str: 客户端列表内容
    """
    cmd = ['sudo', 'cat', '/etc/openvpn/easy-rsa/pki/index.txt']
    
    if use_cache:
        success, output = command_executor.execute('openvpn_clients', cmd, timeout)
        return output if success else ""
    else:
        try:
            result = run_command_with_timeout(cmd, timeout=timeout)
            return result.stdout if result.returncode == 0 else ""
        except:
            return ""


def restart_openvpn_service(timeout: int = 30) -> Tuple[bool, str]:
    """
    重启 OpenVPN 服务
    
    Args:
        timeout: 超时时间（秒）
    
    Returns:
        (success: bool, message: str)
    """
    cmd = ['sudo', 'systemctl', 'restart', 'openvpn@server.service']
    
    try:
        result = run_command_with_timeout(cmd, timeout=timeout)
        # 清除状态缓存
        command_executor.clear_cache('openvpn_status')
        return True, "Service restarted successfully"
    except SubprocessTimeout:
        return False, f"Restart timeout after {timeout}s"
    except Exception as e:
        return False, str(e)


def start_openvpn_service(timeout: int = 30) -> Tuple[bool, str]:
    """
    启动 OpenVPN 服务
    
    Args:
        timeout: 超时时间（秒）
    
    Returns:
        (success: bool, message: str)
    """
    cmd = ['sudo', 'systemctl', 'start', 'openvpn@server.service']
    
    try:
        result = run_command_with_timeout(cmd, timeout=timeout)
        command_executor.clear_cache('openvpn_status')
        return True, "Service started successfully"
    except SubprocessTimeout:
        return False, f"Start timeout after {timeout}s"
    except Exception as e:
        return False, str(e)


def stop_openvpn_service(timeout: int = 30) -> Tuple[bool, str]:
    """
    停止 OpenVPN 服务
    
    Args:
        timeout: 超时时间（秒）
    
    Returns:
        (success: bool, message: str)
    """
    cmd = ['sudo', 'systemctl', 'stop', 'openvpn@server.service']
    
    try:
        result = run_command_with_timeout(cmd, timeout=timeout)
        command_executor.clear_cache('openvpn_status')
        return True, "Service stopped successfully"
    except SubprocessTimeout:
        return False, f"Stop timeout after {timeout}s"
    except Exception as e:
        return False, str(e)


def get_service_status_detailed(service_name: str = 'openvpn@server.service', timeout: int = 5) -> Tuple[bool, str]:
    """
    获取服务详细状态
    
    Args:
        service_name: 服务名称
        timeout: 超时时间（秒）
    
    Returns:
        (success: bool, status_output: str)
    """
    cmd = ['sudo', 'systemctl', 'status', service_name, '--no-pager']
    
    try:
        result = run_command_with_timeout(cmd, timeout=timeout, check=False)
        return True, result.stdout
    except SubprocessTimeout:
        return False, f"Status check timeout after {timeout}s"
    except Exception as e:
        return False, str(e)


# ============================================================================
# 使用示例
# ============================================================================

if __name__ == '__main__':
    # 配置日志
    logging.basicConfig(level=logging.INFO)
    
    print("测试 OpenVPN 状态检查...")
    
    # 测试状态检查（带缓存）
    for i in range(3):
        start = time.time()
        status = check_openvpn_status(use_cache=True)
        duration = time.time() - start
        print(f"第 {i+1} 次检查: {status} (耗时: {duration:.3f}s)")
    
    print("\n测试客户端列表获取...")
    clients = get_openvpn_clients(use_cache=True)
    print(f"客户端数量: {len(clients.splitlines())}")
    
    print("\n测试详细状态...")
    success, status = get_service_status_detailed()
    if success:
        print("状态获取成功")
    else:
        print(f"状态获取失败: {status}")