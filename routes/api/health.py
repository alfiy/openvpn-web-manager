# routes/api/health.py
"""
健康检查和性能监控 API
"""
from flask import Blueprint, jsonify
from models import db
from sqlalchemy import text
import time
import logging

logger = logging.getLogger(__name__)

health_bp = Blueprint('health', __name__, url_prefix='/api')


def init_health_monitor(redis_client, concurrent_limiter, request_monitor):
    """
    初始化健康监控器
    
    Args:
        redis_client: Redis 客户端实例
        concurrent_limiter: 并发限制器实例
        request_monitor: 请求监控器实例
    """
    health_bp.redis_client = redis_client
    health_bp.concurrent_limiter = concurrent_limiter
    health_bp.request_monitor = request_monitor


@health_bp.route('/health', methods=['GET'])
def health_check():
    """
    健康检查端点
    
    检查系统各组件的运行状态：
    - 数据库连接
    - Redis 连接
    - 并发请求数
    
    Returns:
        JSON: {
            "status": "ok" | "degraded" | "error",
            "timestamp": 时间戳,
            "components": {
                "database": "ok" | "error: ...",
                "redis": "ok" | "error: ...",
                "concurrent_requests": 当前并发数
            }
        }
    """
    health_status = {
        'status': 'ok',
        'timestamp': time.time(),
        'components': {}
    }
    
    # 检查数据库连接
    try:
        db.session.execute(text('SELECT 1'))
        health_status['components']['database'] = 'ok'
    except Exception as e:
        logger.error(f"Database health check failed: {e}", exc_info=True)
        health_status['components']['database'] = f'error: {str(e)[:100]}'
        health_status['status'] = 'degraded'
    
    # 检查 Redis 连接
    redis_client = getattr(health_bp, 'redis_client', None)
    if redis_client:
        try:
            redis_client.ping()
            health_status['components']['redis'] = 'ok'
        except Exception as e:
            logger.error(f"Redis health check failed: {e}", exc_info=True)
            health_status['components']['redis'] = f'error: {str(e)[:100]}'
            health_status['status'] = 'degraded'
    else:
        health_status['components']['redis'] = 'not configured'
    
    # 获取并发请求数
    concurrent_limiter = getattr(health_bp, 'concurrent_limiter', None)
    if concurrent_limiter:
        health_status['components']['concurrent_requests'] = concurrent_limiter.current
        health_status['components']['max_concurrent'] = concurrent_limiter.max_concurrent
    
    # 根据状态返回不同的 HTTP 状态码
    status_code = 200 if health_status['status'] == 'ok' else 503
    
    return jsonify(health_status), status_code


@health_bp.route('/metrics', methods=['GET'])
def metrics():
    """
    性能指标端点
    
    返回系统性能指标：
    - 并发请求统计
    - 慢请求列表
    - 监控统计信息
    
    Returns:
        JSON: {
            "concurrent": {...},
            "slow_requests": [...],
            "monitor_stats": {...}
        }
    """
    metrics_data = {}
    
    # 获取并发统计
    concurrent_limiter = getattr(health_bp, 'concurrent_limiter', None)
    if concurrent_limiter:
        metrics_data['concurrent'] = concurrent_limiter.get_stats()
    
    # 获取慢请求列表
    request_monitor = getattr(health_bp, 'request_monitor', None)
    if request_monitor:
        metrics_data['slow_requests'] = request_monitor.get_slow_requests(
            threshold=3.0,  # 3秒以上算慢请求
            limit=20        # 最多返回 20 条
        )
        metrics_data['monitor_stats'] = request_monitor.get_stats()
    
    return jsonify(metrics_data), 200


@health_bp.route('/metrics/slow-requests', methods=['GET'])
def slow_requests():
    """
    获取慢请求详情
    
    可以通过查询参数自定义：
    - threshold: 慢请求阈值（秒），默认 3.0
    - limit: 返回数量限制，默认 50
    
    Returns:
        JSON: {
            "requests": [...],
            "total": 总数,
            "threshold": 阈值
        }
    """
    from flask import request
    
    # 获取查询参数
    threshold = float(request.args.get('threshold', 3.0))
    limit = int(request.args.get('limit', 50))
    
    request_monitor = getattr(health_bp, 'request_monitor', None)
    if not request_monitor:
        return jsonify({
            'error': 'Request monitor not configured'
        }), 503
    
    slow_reqs = request_monitor.get_slow_requests(threshold=threshold, limit=limit)
    
    return jsonify({
        'requests': slow_reqs,
        'total': len(slow_reqs),
        'threshold': threshold
    }), 200


@health_bp.route('/metrics/reset', methods=['POST'])
def reset_metrics():
    """
    重置监控数据
    
    需要管理员权限
    
    Returns:
        JSON: {"message": "Metrics reset successfully"}
    """
    # TODO: 添加权限检查
    # from flask_login import login_required, current_user
    # if not current_user.is_authenticated or current_user.role != Role.SUPER_ADMIN:
    #     return jsonify({'error': 'Permission denied'}), 403
    
    request_monitor = getattr(health_bp, 'request_monitor', None)
    if request_monitor:
        request_monitor.clear()
        logger.info("Metrics reset by admin")
        return jsonify({'message': 'Metrics reset successfully'}), 200
    
    return jsonify({'error': 'Request monitor not configured'}), 503


@health_bp.route('/status', methods=['GET'])
def system_status():
    """
    系统状态概览
    
    整合健康检查和性能指标，提供完整的系统状态视图
    
    Returns:
        JSON: 完整的系统状态信息
    """
    status_data = {}
    
    # 健康状态
    health_status = {
        'overall': 'ok',
        'components': {}
    }
    
    # 数据库
    try:
        db.session.execute(text('SELECT 1'))
        health_status['components']['database'] = 'ok'
    except Exception as e:
        health_status['components']['database'] = 'error'
        health_status['overall'] = 'degraded'
    
    # Redis
    redis_client = getattr(health_bp, 'redis_client', None)
    if redis_client:
        try:
            redis_client.ping()
            health_status['components']['redis'] = 'ok'
        except:
            health_status['components']['redis'] = 'error'
            health_status['overall'] = 'degraded'
    
    status_data['health'] = health_status
    
    # 性能指标
    concurrent_limiter = getattr(health_bp, 'concurrent_limiter', None)
    request_monitor = getattr(health_bp, 'request_monitor', None)
    
    if concurrent_limiter:
        status_data['concurrent'] = concurrent_limiter.get_stats()
    
    if request_monitor:
        status_data['performance'] = request_monitor.get_stats()
        # 只显示最近 5 个慢请求
        status_data['recent_slow_requests'] = request_monitor.get_slow_requests(
            threshold=3.0, 
            limit=5
        )
    
    status_data['timestamp'] = time.time()
    
    return jsonify(status_data), 200