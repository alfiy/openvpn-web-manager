from flask import Blueprint, render_template, session, request, jsonify, g, redirect, url_for
from flask_wtf.csrf import CSRFError
from routes.helpers import login_required


index_bp = Blueprint('index', __name__)

# 添加一个针对CSRF错误的自定义处理函数，确保返回JSON
@index_bp.errorhandler(CSRFError)
def handle_csrf_error(e):
    return jsonify({'success': False, 'message': 'CSRF令牌无效'}), 400

# @index_bp.route('/logout')
# def logout():
#     session.clear()
#     return jsonify({'success': True, 'message': '已退出登录'})

@index_bp.route('/')
def index():
    # 检查用户是否已登录，如果未登录，重定向到登录页
    if 'user_id' not in session:
        return redirect(url_for('index.login'))

    # g.current_user = load_user(session['user_id'])
    if not g.current_user:
        return redirect(url_for('index.login'))

    # 为了简化，我们假定OpenVPN的状态是 'not_installed'
    status = 'not_installed'
    
    # 模拟一个用户角色，在实际应用中，您会从数据库中加载
    user_role = g.current_user.role_name
    
    return render_template('index.html', status=status, user_role=user_role, current_user=g.current_user)

@index_bp.route('/get_status', methods=['GET'])
@login_required
def get_status():
    # 模拟状态，稍后会连接到实际脚本
    status = 'not_installed' 
    return jsonify({'status': status})

@index_bp.route('/api/openvpn/install', methods=['POST'])
@login_required
def install_openvpn():
    if g.current_user.role_name != '超级管理员':
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    # 模拟安装操作
    try:
        data = request.get_json()
        port = data.get('port')
        server_ip = data.get('server_ip')
        
        # 实际操作：执行安装脚本
        # ... os.system(...)
        
        return jsonify({'success': True, 'message': 'OpenVPN正在安装中...'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'安装失败: {str(e)}'}), 500

@index_bp.route('/api/openvpn/uninstall', methods=['POST'])
@login_required
def uninstall_openvpn():
    if g.current_user.role_name != '超级管理员':
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    # 模拟卸载操作
    try:
        # 实际操作：执行卸载脚本
        # ... os.system(...)
        
        return jsonify({'success': True, 'message': 'OpenVPN正在卸载中...'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'卸载失败: {str(e)}'}), 500

@index_bp.route('/api/clients', methods=['GET'])
@login_required
def get_clients():
    # 模拟客户端列表
    clients = [
        {'name': 'client1', 'online': True, 'expiry': '2025-01-01'},
        {'name': 'client2', 'online': False, 'expiry': '2024-12-31'},
    ]
    return jsonify({'success': True, 'clients': clients})

@index_bp.route('/api/clients/add', methods=['POST'])
@login_required
def add_client():
    if g.current_user.role_name not in ['管理员', '超级管理员']:
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    # 模拟添加客户端
    try:
        data = request.get_json()
        client_name = data.get('client_name')
        expiry = data.get('expiry')
        return jsonify({'success': True, 'message': f'客户端 "{client_name}" 已添加'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'添加失败: {str(e)}'}), 500

@index_bp.route('/api/clients/revoke', methods=['POST'])
@login_required
def revoke_client():
    if g.current_user.role_name not in ['管理员', '超级管理员']:
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    # 模拟吊销客户端
    try:
        data = request.get_json()
        client_name = data.get('client_name')
        return jsonify({'success': True, 'message': f'客户端 "{client_name}" 已吊销'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'吊销失败: {str(e)}'}), 500
