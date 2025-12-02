# utils/api_response.py
from flask import jsonify

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
