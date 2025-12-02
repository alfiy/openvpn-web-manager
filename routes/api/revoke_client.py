# from flask import Blueprint, request, jsonify
# import os
# import subprocess
# from routes.helpers import login_required
# from models import Client,db

# revoke_client_bp = Blueprint('revoke_client', __name__)

# @revoke_client_bp.route('/revoke_client', methods=['POST'])
# @login_required
# def revoke_client():
#     """
#     精确撤销客户端证书，更新 CRL，并清理相关文件
#     """
#     data = request.get_json()
#     if not data:
#         return jsonify({'status': 'error', 'message': '请求数据格式错误'}), 400

#     client_name = data.get('client_name')
#     if not client_name:
#         return jsonify({'status': 'error', 'message': '客户端名称不能为空'})
#     client_name = client_name.strip()
#     if not client_name:
#         return jsonify({'status': 'error', 'message': '客户端名称不能为空'})

#     index_path = '/etc/openvpn/easy-rsa/pki/index.txt'
#     crt_path = f'/etc/openvpn/easy-rsa/pki/issued/{client_name}.crt'

#     try:
#         # Step 1: 检查 PKI 和证书文件
#         if not os.path.exists(index_path):
#             return jsonify({'status': 'error', 'message': 'OpenVPN PKI 不存在'})
#         if not os.path.exists(crt_path):
#             return jsonify({'status': 'error', 'message': f'证书文件 {client_name}.crt 不存在，无法撤销'})

#         # Step 2: 检查 CN 是否存在于 index.txt（精确匹配）
#         found = False
#         with open(index_path, 'r') as f:
#             for line in f:
#                 if f'CN={client_name},' in line or f'CN={client_name}\n' in line:
#                     found = True
#                     break
#         if not found:
#             return jsonify({'status': 'error', 'message': f'客户端 {client_name} 不存在于证书数据库'})

#         # Step 3: 撤销证书
#         revoke_result = subprocess.run(
#             ['sudo', 'bash', '-c', f'cd /etc/openvpn/easy-rsa && ./easyrsa --batch revoke "{client_name}"'],
#             capture_output=True, text=True, timeout=60
#         )
#         if revoke_result.returncode != 0 and 'already revoked' not in revoke_result.stderr:
#             return jsonify({'status': 'error', 'message': f'撤销失败: {revoke_result.stderr}'})

#         # Step 4: 生成 CRL
#         crl_result = subprocess.run(
#             ['sudo', 'bash', '-c', 'cd /etc/openvpn/easy-rsa && ./easyrsa gen-crl'],
#             capture_output=True, text=True, timeout=60
#         )
#         if crl_result.returncode != 0:
#             return jsonify({'status': 'error', 'message': f'生成 CRL 失败: {crl_result.stderr}'})

#         # Step 5: 更新 OpenVPN CRL
#         subprocess.run(['sudo', 'rm', '-f', '/etc/openvpn/crl.pem'], check=False)
#         subprocess.run(['sudo', 'cp', '/etc/openvpn/easy-rsa/pki/crl.pem', '/etc/openvpn/crl.pem'], check=True)
#         subprocess.run(['sudo', 'chmod', '644', '/etc/openvpn/crl.pem'], check=True)

#         # Step 6: 清理客户端文件
#         cleanup_commands = [
#             ['sudo', 'rm', '-f', f'/etc/openvpn/client/{client_name}.ovpn'],
#             ['sudo', 'sed', '-i', f'/^{client_name},/d', '/etc/openvpn/ipp.txt'],
#             ['sudo', 'rm', '-f', f'/etc/openvpn/ccd/{client_name}'],
#             ['sudo', 'rm', '-f', f'/etc/openvpn/easy-rsa/pki/issued/{client_name}.crt'],
#             ['sudo', 'rm', '-f', f'/etc/openvpn/easy-rsa/pki/private/{client_name}.key'],
#             ['sudo', 'rm', '-f', f'/etc/openvpn/easy-rsa/pki/reqs/{client_name}.req']
#         ]
#         for cmd in cleanup_commands:
#             subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)

#         # Step 6.5: 从数据库删除客户端（新增代码）
#         try:
#             client = Client.query.filter_by(name=client_name).first()
#             if client:
#                 db.session.delete(client)
#                 db.session.commit()
#         except Exception as db_err:
#             # 不中断 revoke 流程，只记录数据库异常
#             print(f"[WARN] Failed to delete client {client_name} from DB:", db_err)

#         # Step 7: 精确清理 index.txt，只删除该客户端
#         with open(index_path, 'r') as f:
#             lines = f.readlines()
#         filtered_lines = []
#         for line in lines:
#             if f'CN={client_name},' not in line and f'CN={client_name}\n' not in line:
#                 filtered_lines.append(line)
#         with open('/tmp/index.txt', 'w') as f:
#             f.writelines(filtered_lines)
#         subprocess.run(['sudo', 'mv', '/tmp/index.txt', index_path], check=True)

#         # Step 8: 重新加载 OpenVPN 配置
#         reload_result = subprocess.run(['sudo', 'killall', '-SIGUSR1', 'openvpn'],
#                                        capture_output=True, text=True, timeout=30)
#         if reload_result.returncode != 0:
#             reload_result = subprocess.run(['sudo', 'systemctl', 'reload', 'openvpn@server'],
#                                            capture_output=True, text=True, timeout=30)
#             if reload_result.returncode != 0:
#                 return jsonify({
#                     'status': 'warning',
#                     'message': f'客户端 {client_name} 已撤销，但 CRL 重新加载失败，生效将在下次客户端连接时生效'
#                 })

#         return jsonify({
#             'status': 'success',
#             'message': f'客户端 {client_name} 已成功撤销，CRL 已重新加载，在线用户未被断开'
#         })

#     except subprocess.TimeoutExpired:
#         return jsonify({'status': 'error', 'message': '操作超时'})
#     except subprocess.CalledProcessError as e:
#         return jsonify({'status': 'error', 'message': f'命令执行失败: {e}'})
#     except Exception as e:
#         return jsonify({'status': 'error', 'message': f'撤销异常: {str(e)}'})


# routes/api/revoke_client.py
import os
import subprocess
from flask import Blueprint, request
from routes.helpers import login_required
from models import Client, db
from utils.api_response import api_success, api_error

revoke_client_bp = Blueprint('revoke_client', __name__)

@revoke_client_bp.route('/api/clients/revoke', methods=['POST'])
@login_required
def api_revoke_client():
    """
    精确撤销客户端证书，更新 CRL，并清理相关文件
    """
    data = request.get_json()
    if not data:
        return api_error("请求数据格式错误", code=400)

    client_name = (data.get('client_name') or '').strip()
    if not client_name:
        return api_error("客户端名称不能为空", code=400)

    index_path = '/etc/openvpn/easy-rsa/pki/index.txt'
    crt_path = f'/etc/openvpn/easy-rsa/pki/issued/{client_name}.crt'

    try:
        # Step 1: 检查 PKI 和证书文件
        if not os.path.exists(index_path):
            return api_error("OpenVPN PKI 不存在", code=500)
        if not os.path.exists(crt_path):
            return api_error(f"证书文件 {client_name}.crt 不存在，无法撤销", code=500)

        # Step 2: 检查 CN 是否存在于 index.txt
        found = False
        with open(index_path, 'r') as f:
            for line in f:
                if f'CN={client_name},' in line or f'CN={client_name}\n' in line:
                    found = True
                    break
        if not found:
            return api_error(f"客户端 {client_name} 不存在于证书数据库", code=404)

        # Step 3: 撤销证书
        revoke_result = subprocess.run(
            ['sudo', 'bash', '-c', f'cd /etc/openvpn/easy-rsa && ./easyrsa --batch revoke "{client_name}"'],
            capture_output=True, text=True, timeout=60
        )
        if revoke_result.returncode != 0 and 'already revoked' not in revoke_result.stderr:
            return api_error(f"撤销失败: {revoke_result.stderr}", code=500)

        # Step 4: 生成 CRL
        crl_result = subprocess.run(
            ['sudo', 'bash', '-c', 'cd /etc/openvpn/easy-rsa && ./easyrsa gen-crl'],
            capture_output=True, text=True, timeout=60
        )
        if crl_result.returncode != 0:
            return api_error(f"生成 CRL 失败: {crl_result.stderr}", code=500)

        # Step 5: 更新 OpenVPN CRL
        subprocess.run(['sudo', 'rm', '-f', '/etc/openvpn/crl.pem'], check=False)
        subprocess.run(['sudo', 'cp', '/etc/openvpn/easy-rsa/pki/crl.pem', '/etc/openvpn/crl.pem'], check=True)
        subprocess.run(['sudo', 'chmod', '644', '/etc/openvpn/crl.pem'], check=True)

        # Step 6: 清理客户端文件
        cleanup_commands = [
            ['sudo', 'rm', '-f', f'/etc/openvpn/client/{client_name}.ovpn'],
            ['sudo', 'sed', '-i', f'/^{client_name},/d', '/etc/openvpn/ipp.txt'],
            ['sudo', 'rm', '-f', f'/etc/openvpn/ccd/{client_name}'],
            ['sudo', 'rm', '-f', f'/etc/openvpn/easy-rsa/pki/issued/{client_name}.crt'],
            ['sudo', 'rm', '-f', f'/etc/openvpn/easy-rsa/pki/private/{client_name}.key'],
            ['sudo', 'rm', '-f', f'/etc/openvpn/easy-rsa/pki/reqs/{client_name}.req']
        ]
        for cmd in cleanup_commands:
            subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)

        # Step 6.5: 从数据库删除客户端
        try:
            client = Client.query.filter_by(name=client_name).first()
            if client:
                db.session.delete(client)
                db.session.commit()
        except Exception as db_err:
            print(f"[WARN] Failed to delete client {client_name} from DB:", db_err)

        # Step 7: 精确清理 index.txt
        with open(index_path, 'r') as f:
            lines = f.readlines()
        filtered_lines = [line for line in lines if f'CN={client_name},' not in line and f'CN={client_name}\n' not in line]
        with open('/tmp/index.txt', 'w') as f:
            f.writelines(filtered_lines)
        subprocess.run(['sudo', 'mv', '/tmp/index.txt', index_path], check=True)

        # Step 8: 重新加载 OpenVPN 配置
        reload_result = subprocess.run(['sudo', 'killall', '-SIGUSR1', 'openvpn'],
                                       capture_output=True, text=True, timeout=30)
        if reload_result.returncode != 0:
            reload_result = subprocess.run(['sudo', 'systemctl', 'reload', 'openvpn@server'],
                                           capture_output=True, text=True, timeout=30)
            if reload_result.returncode != 0:
                return api_success(
                    data={"message": f"客户端 {client_name} 已撤销，但 CRL 重新加载失败，生效将在下次客户端连接时生效"}
                )

        return api_success(
            data={"message": f"客户端 {client_name} 已成功撤销，CRL 已重新加载，在线用户未被断开"}
        )

    except subprocess.TimeoutExpired:
        return api_error("操作超时", code=500)
    except subprocess.CalledProcessError as e:
        return api_error(f"命令执行失败: {e}", code=500)
    except Exception as e:
        return api_error(f"撤销异常: {str(e)}", code=500)
