# utils/api_response.py
from flask import jsonify
import logging

logger = logging.getLogger(__name__)


def api_success(data=None, message="ok", code=0, status=200):
    """
    统一成功响应格式
    """
    payload = {
        "success": True,         # ⭐ 增加业务成功标识
        "code": code,
        "msg": message,          # ⭐ 保留 msg（兼容旧前端）
        "message": message,      # ⭐ 标准字段：前端使用 message
        "data": data if data is not None else {}
    }
    return jsonify(payload), status


def api_error(message="error", code=1, status=400, data=None):
    """
    统一错误响应格式
    """
    payload = {
        "success": False,       # ⭐ 失败标识
        "code": code,
        "msg": message,
        "message": message,     # ⭐ 前端 alert/toast 统一读 message
        "data": data if data is not None else {}  # ⭐ 保持 data 为对象，避免 null
    }
    return jsonify(payload), status


# ============================================================================
# 全局错误处理器注册
# ============================================================================

def register_error_handlers(app):
    """
    注册全局错误处理器
    
    Args:
        app: Flask 应用实例
    """
    
    @app.errorhandler(400)
    def handle_400(e):
        """处理 400 Bad Request"""
        logger.warning(f"400 Bad Request: {e}")
        return api_error("请求参数错误", code=400, status=400)

    @app.errorhandler(401)
    def handle_401(e):
        """处理 401 Unauthorized"""
        logger.warning(f"401 Unauthorized: {e}")
        return api_error("未授权访问", code=401, status=401)

    @app.errorhandler(403)
    def handle_403(e):
        """处理 403 Forbidden"""
        logger.warning(f"403 Forbidden: {e}")
        return api_error("禁止访问", code=403, status=403)

    @app.errorhandler(404)
    def handle_404(e):
        """处理 404 Not Found"""
        logger.info(f"404 Not Found: {e}")
        return api_error("资源不存在", code=404, status=404)

    @app.errorhandler(405)
    def handle_405(e):
        """处理 405 Method Not Allowed"""
        logger.warning(f"405 Method Not Allowed: {e}")
        return api_error("请求方法不允许", code=405, status=405)

    @app.errorhandler(500)
    def handle_500(e):
        """处理 500 Internal Server Error"""
        logger.error(f"500 Internal Server Error: {e}", exc_info=True)
        return api_error("服务器内部错误", code=500, status=500)

    @app.errorhandler(503)
    def handle_503(e):
        """处理 503 Service Unavailable"""
        logger.error(f"503 Service Unavailable: {e}")
        return api_error("服务暂时不可用，请稍后重试", code=503, status=503)

    @app.errorhandler(504)
    def handle_504(e):
        """处理 504 Gateway Timeout"""
        logger.error(f"504 Gateway Timeout: {e}")
        return api_error("请求处理超时", code=504, status=504)

    # 处理自定义超时异常
    from utils.request_timeout import RequestTimeout
    
    @app.errorhandler(RequestTimeout)
    def handle_timeout(e):
        """处理请求超时"""
        logger.warning(f"Request Timeout: {e}")
        return api_error("请求处理超时，请稍后重试", code=504, status=504)

    # 处理 CSRF 错误
    try:
        from flask_wtf.csrf import CSRFError
        
        @app.errorhandler(CSRFError)
        def handle_csrf_error(e):
            """处理 CSRF 错误"""
            logger.warning(f"CSRF Error: {e}")
            return api_error("安全令牌无效，请刷新页面后重试", code=400, status=400)
    except ImportError:
        pass  # 如果没有安装 flask_wtf，跳过

    logger.info("✅ 全局错误处理器已注册")


# ============================================================================
# 请求生命周期处理器注册
# ============================================================================

def register_request_handlers(app, concurrent_limiter, request_monitor):
    """
    注册请求生命周期处理器
    
    Args:
        app: Flask 应用实例
        concurrent_limiter: 并发限制器实例
        request_monitor: 请求监控器实例
    """
    import time
    from flask import g, request
    
    @app.before_request
    def before_request():
        """请求前处理：并发控制 + 计时"""
        # 记录请求开始时间
        g.request_start_time = time.time()
        
        # 并发请求限制
        if not concurrent_limiter.acquire():
            return api_error("服务器繁忙，请稍后重试", code=503, status=503)
    
    @app.after_request
    def after_request(response):
        """请求后处理：释放资源 + 性能监控"""
        # 释放并发槽位
        concurrent_limiter.release()
        
        # 计算请求处理时间
        if hasattr(g, 'request_start_time'):
            duration = time.time() - g.request_start_time
            
            # 记录慢请求（超过 5 秒）
            if duration > 5.0:
                request_monitor.log_slow_request(
                    path=request.path,
                    duration=duration,
                    method=request.method
                )
                logger.warning(
                    f"Slow request detected: {request.method} {request.path} "
                    f"took {duration:.2f}s"
                )
            
            # 添加响应头显示处理时间
            response.headers['X-Request-Duration'] = f"{duration:.3f}s"
        
        return response
    
    @app.teardown_request
    def teardown_request(exception=None):
        """请求清理：确保资源释放"""
        if exception:
            logger.error(f"Request error: {exception}", exc_info=True)
            # 确保并发槽位被释放
            concurrent_limiter.release()
    
    logger.info("✅ 请求生命周期处理器已注册")