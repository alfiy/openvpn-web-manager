# utils/api_response.py
from flask import jsonify

def api_success(data=None, msg="ok", code=0, status=200):
    payload = {"code": code, "msg": msg, "data": data if data is not None else {}}
    return jsonify(payload), status

def api_error(msg="error", code=1, status=400, data=None):
    payload = {"code": code, "msg": msg, "data": data}
    return jsonify(payload), status
