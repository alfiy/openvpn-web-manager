import os
import subprocess
import socket
import time
from flask import Blueprint, request, jsonify
from utils.openvpn_utils import log_message
from routes.helpers import login_required
from models import db,Client
from sqlalchemy.exc import SQLAlchemyError

# ==============================================================================
# 客户端踢出模块
# ------------------------------------------------------------------------------
# 此蓝图提供一个 API 端点，用于通过 OpenVPN 管理接口踢出特定客户端。
# ==============================================================================

kill_client_bp = Blueprint('kill_client', __name__)


RECV_CHUNK = 4096

def recv_all_until_end(sock, timeout=3.0):
    sock.settimeout(timeout)
    data = b''
    while True:
        try:
            chunk = sock.recv(RECV_CHUNK)
            if not chunk:
                break
            data += chunk
            if b'\nEND' in data or data.endswith(b'END') or b'\r\nEND' in data:
                break
        except socket.timeout:
            break
    return data.decode('utf-8', errors='ignore')

def parse_status_for_cids(status_text, common_name):
    lines = status_text.splitlines()
    header_cols = None
    client_lines = []
    for ln in lines:
        if ln.startswith('HEADER,CLIENT_LIST'):
            parts = ln.split(',')
            header_cols = parts[2:]
            continue
        if ln.startswith('CLIENT_LIST,'):
            client_lines.append(ln)

    if header_cols:
        low_headers = [h.strip().lower() for h in header_cols]
        try:
            idx_cn = low_headers.index('common name')
        except ValueError:
            idx_cn = 0
        cid_idx = None
        if 'client id' in low_headers:
            cid_idx = low_headers.index('client id')
        cids = []
        for cl in client_lines:
            parts = cl.split(',')[1:]
            name = parts[idx_cn] if idx_cn < len(parts) else ''
            cid = (parts[cid_idx] if cid_idx is not None and cid_idx < len(parts) else None)
            if name == common_name:
                if cid:
                    cids.append(cid)
                else:
                    return []
        return cids if cids else None
    for i, ln in enumerate(lines):
        if ln.startswith('Common Name,') or ln.startswith('Common Name,'):
            for dl in lines[i+1:]:
                if dl.strip() == '' or dl.startswith('ROUTING TABLE') or dl.startswith('GLOBAL STATS') or dl == 'END':
                    break
                parts = dl.split(',')
                if parts and parts[0] == common_name:
                    return []
            break
    return None

def send_and_recv(sock, cmd, wait=0.05, recv_timeout=2.0):
    sock.sendall((cmd + "\n").encode('utf-8'))
    time.sleep(wait)
    return recv_all_until_end(sock, timeout=recv_timeout)

def openvpn_client_kill(host, port, client_name, mgmt_password=None, verbose=False):
    """
    核心踢出函数，直接返回结果而不是打印到控制台。
    """
    try:
        with socket.create_connection((host, port), timeout=5) as s:
            banner = s.recv(RECV_CHUNK).decode('utf-8', errors='ignore')
            if mgmt_password:
                s.sendall(f"password {mgmt_password}\n".encode())
                time.sleep(0.05)
                _ = recv_all_until_end(s, timeout=1.0)
            
            raw_status = send_and_recv(s, "status 2", wait=0.05, recv_timeout=2.0)
            parse_res = parse_status_for_cids(raw_status, client_name)

            if parse_res is None:
                resp = send_and_recv(s, f"kill {client_name}", wait=0.05, recv_timeout=2.0)
                return True, f"未在状态中找到客户端 '{client_name}'。尝试使用 kill {client_name}。响应: {resp.strip()}"
            elif isinstance(parse_res, list) and len(parse_res) == 0:
                resp = send_and_recv(s, f"kill {client_name}", wait=0.05, recv_timeout=2.0)
                return True, f"找到了 '{client_name}' 但未找到客户端 ID。尝试使用 kill {client_name}。响应: {resp.strip()}"
            else:
                cids = parse_res
                results = []
                for cid in cids:
                    resp = send_and_recv(s, f"client-kill {cid}", wait=0.05, recv_timeout=2.0)
                    results.append(f"client-kill {cid} 响应: {resp.strip()}")
                return True, "成功踢出客户端。\n" + "\n".join(results)
            
            s.sendall(b"quit\n")

    except socket.error as e:
        return False, f"无法连接到 OpenVPN 管理接口: {e}"
    except Exception as e:
        return False, f"踢出客户端时发生错误: {e}"


# --- 路由定义 ---
@kill_client_bp.route('/kill_client', methods=['POST'])
@login_required
def kill_client():
    """
    通过 API 请求踢出客户端
    """
    data = request.json
    client_name = data.get('client_name')
    if not client_name:
        log_message("缺少 'client_name' 参数")
        return jsonify({"status": 'error', "message": "缺少 'client_name' 参数"}), 400

    # 1. 在 /etc/openvpn/ccd/ 目录下创建禁用文件并写入指令
    ccd_dir = '/etc/openvpn/ccd'
    disable_file_path = os.path.join(ccd_dir, client_name)
    
    try:
        # 使用 subprocess.run 安全地创建文件并写入内容
        # 确保目录存在
        os.makedirs(ccd_dir, exist_ok=True)
        # 使用 sudo 写入文件，因为 OpenVPN 的 ccd 目录可能需要 root 权限
        cmd = ['sudo', 'sh', '-c', f'echo "disable" > {disable_file_path}']
        log_message(f"执行命令以禁用客户端：{' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        log_message(f"禁用文件创建成功：{result.stdout.strip()}")
        # 修复文件权限，确保 OpenVPN 可以读取
        os.system(f"sudo chown root:root {disable_file_path}")
        os.system(f"sudo chmod 644 {disable_file_path}")

    except subprocess.CalledProcessError as e:
        log_message(f"创建禁用文件失败：{e.stderr}")
        return jsonify({"status": 'error', "message": f"创建禁用文件失败：{e.stderr}"}), 500

    # 2. 调用核心踢出逻辑，强制断开客户端的在线连接
    host = os.environ.get('OPENVPN_MGMT_HOST', '127.0.0.1')
    port = int(os.environ.get('OPENVPN_MGMT_PORT', 7505))
    password = os.environ.get('OPENVPN_MGMT_PASSWORD')

    log_message(f"正在通过管理接口踢出客户端: {client_name}")
    success, message = openvpn_client_kill(host, port, client_name, mgmt_password=password)

    if success:
                # 3. 踢出成功后，更新数据库中的 'disabled' 字段
        try:
            client = Client.query.filter_by(name=client_name).first()
            if client:
                client.disabled = True
                db.session.commit()
                log_message(f"成功将客户端 {client_name} 的 'disabled' 状态更新为 True。")
            else:
                log_message(f"数据库中未找到客户端 {client_name}。")
                
        except SQLAlchemyError as e:
            db.session.rollback()
            log_message(f"数据库更新失败：{e}")
            return jsonify({"status": 'error', "message": f"数据库更新失败：{e}"}), 500

        log_message(f"成功踢出客户端 {client_name}。")
        return jsonify({"status": 'success', "message": f"客户端 {client_name} 已成功禁用并断开连接。"})
    else:
        log_message(f"踢出客户端 {client_name} 失败: {message}")
        return jsonify({"status": 'error', "message": f"客户端已禁用，但踢出失败: {message}"}), 500


# """
# OpenVPN 客户端踢出模块 - 重构版本
# 提供安全、可靠的客户端禁用和踢出功能
# """

# import os
# import re
# import socket
# import time
# import logging
# from pathlib import Path
# from threading import Lock
# from contextlib import contextmanager
# from dataclasses import dataclass
# from typing import Optional, Tuple, List
# from functools import wraps

# from flask import Blueprint, request, jsonify
# from sqlalchemy.exc import SQLAlchemyError
# import subprocess

# from utils.openvpn_utils import log_message
# from routes.helpers import login_required
# from models import db, Client


# # ==============================================================================
# # 配置管理
# # ==============================================================================

# @dataclass
# class OpenVPNConfig:
#     """OpenVPN 配置类"""
#     mgmt_host: str = '127.0.0.1'
#     mgmt_port: int = 7505
#     mgmt_password: Optional[str] = None
#     ccd_dir: str = '/etc/openvpn/ccd'
#     socket_timeout: float = 5.0
#     recv_timeout: float = 2.0
#     recv_chunk_size: int = 4096
#     max_client_name_length: int = 64
    
#     @classmethod
#     def from_env(cls) -> 'OpenVPNConfig':
#         """从环境变量加载配置"""
#         return cls(
#             mgmt_host=os.getenv('OPENVPN_MGMT_HOST', cls.mgmt_host),
#             mgmt_port=int(os.getenv('OPENVPN_MGMT_PORT', str(cls.mgmt_port))),
#             mgmt_password=os.getenv('OPENVPN_MGMT_PASSWORD'),
#             ccd_dir=os.getenv('OPENVPN_CCD_DIR', cls.ccd_dir)
#         )


# # 全局配置实例
# config = OpenVPNConfig.from_env()


# # ==============================================================================
# # 日志配置
# # ==============================================================================

# logger = logging.getLogger('kill_client')
# logger.setLevel(logging.INFO)

# # 如果还没有处理器，添加一个
# if not logger.handlers:
#     handler = logging.StreamHandler()
#     formatter = logging.Formatter(
#         '[%(asctime)s] [%(levelname)s] %(name)s: %(message)s',
#         datefmt='%Y-%m-%d %H:%M:%S'
#     )
#     handler.setFormatter(formatter)
#     logger.addHandler(handler)


# # ==============================================================================
# # 并发控制
# # ==============================================================================

# class ClientOperationLockManager:
#     """客户端操作锁管理器"""
    
#     def __init__(self):
#         self._locks = {}
#         self._dict_lock = Lock()
    
#     def get_lock(self, client_name: str) -> Lock:
#         """获取指定客户端的锁"""
#         with self._dict_lock:
#             if client_name not in self._locks:
#                 self._locks[client_name] = Lock()
#             return self._locks[client_name]
    
#     def cleanup_old_locks(self, max_locks: int = 1000):
#         """清理过多的锁对象"""
#         with self._dict_lock:
#             if len(self._locks) > max_locks:
#                 # 简单策略：清空所有锁
#                 self._locks.clear()


# lock_manager = ClientOperationLockManager()


# # ==============================================================================
# # 输入验证
# # ==============================================================================

# class ValidationError(Exception):
#     """验证错误异常"""
#     pass


# def validate_client_name(client_name: str) -> str:
#     """
#     验证客户端名称
    
#     Args:
#         client_name: 要验证的客户端名称
        
#     Returns:
#         清理后的客户端名称
        
#     Raises:
#         ValidationError: 如果验证失败
#     """
#     if not client_name or not client_name.strip():
#         raise ValidationError("客户端名称不能为空")
    
#     client_name = client_name.strip()
    
#     # 检查长度
#     if len(client_name) > config.max_client_name_length:
#         raise ValidationError(
#             f"客户端名称长度不能超过 {config.max_client_name_length} 个字符"
#         )
    
#     # 只允许字母、数字、下划线、连字符
#     if not re.match(r'^[a-zA-Z0-9_-]+$', client_name):
#         raise ValidationError(
#             "客户端名称只能包含字母、数字、下划线和连字符"
#         )
    
#     return client_name

# def require_client_name(f):
#     """装饰器：从 JSON / form / query 中读取 client_name，并验证"""
#     @wraps(f)
#     def decorated_function(*args, **kwargs):
#         try:
#             client_name = None

#             # 1. JSON body
#             if request.is_json:
#                 json_data = request.get_json(silent=True) or {}
#                 client_name = json_data.get('client_name')

#             # 2. Form data
#             if not client_name:
#                 client_name = request.form.get('client_name')

#             # 3. Query string
#             if not client_name:
#                 client_name = request.args.get('client_name')

#             # 4. 最终检查
#             client_name = validate_client_name(client_name or '')

#             # 注入到视图函数
#             kwargs['client_name'] = client_name
#             return f(*args, **kwargs)

#         except ValidationError as e:
#             logger.warning(f"客户端名称验证失败: {e}")
#             return jsonify({
#                 "status": 'error',
#                 "message": str(e)
#             }), 400

#     return decorated_function


# # ==============================================================================
# # 文件操作
# # ==============================================================================

# @contextmanager
# def disable_file_transaction(client_name: str):
#     """
#     禁用文件事务上下文管理器
#     如果操作失败，自动回滚（删除文件）
#     """
#     disable_file_path = None
#     created = False
    
#     try:
#         disable_file_path = create_disable_file(client_name)
#         created = True
#         yield disable_file_path
        
#     except Exception as e:
#         # 如果发生异常且文件已创建，尝试删除
#         if created and disable_file_path:
#             try:
#                 remove_disable_file(client_name)
#                 logger.info(f"已回滚禁用文件: {disable_file_path}")
#             except Exception as rollback_error:
#                 logger.error(f"回滚禁用文件失败: {rollback_error}")
#         raise


# def create_disable_file(client_name: str) -> str:
#     """
#     安全地创建客户端禁用文件
    
#     Args:
#         client_name: 客户端名称（已验证）
        
#     Returns:
#         创建的文件路径
        
#     Raises:
#         Exception: 如果创建失败
#     """
#     ccd_dir = Path(config.ccd_dir)
#     disable_file = ccd_dir / client_name
    
#     # 防止路径遍历攻击
#     try:
#         resolved_file = disable_file.resolve()
#         resolved_dir = ccd_dir.resolve()
#         if not str(resolved_file).startswith(str(resolved_dir)):
#             raise ValidationError("检测到路径遍历攻击")
#     except Exception as e:
#         raise ValidationError(f"路径验证失败: {e}")
    
#     try:
#         # 确保目录存在
#         ccd_dir.mkdir(parents=True, exist_ok=True)
        
#         # 创建临时文件
#         temp_file = disable_file.with_suffix('.tmp')
#         temp_file.write_text("disable\n", encoding='utf-8')
        
#         # 修改权限和所有者
#         subprocess.run(
#             ['sudo', 'chown', 'root:root', str(temp_file)],
#             check=True,
#             capture_output=True,
#             text=True,
#             timeout=5
#         )
        
#         subprocess.run(
#             ['sudo', 'chmod', '644', str(temp_file)],
#             check=True,
#             capture_output=True,
#             text=True,
#             timeout=5
#         )
        
#         # 原子性重命名
#         subprocess.run(
#             ['sudo', 'mv', str(temp_file), str(disable_file)],
#             check=True,
#             capture_output=True,
#             text=True,
#             timeout=5
#         )
        
#         logger.info(f"成功创建禁用文件: {disable_file}")
#         return str(disable_file)
        
#     except subprocess.CalledProcessError as e:
#         error_msg = f"创建禁用文件失败: {e.stderr if e.stderr else str(e)}"
#         logger.error(error_msg)
#         # 清理可能残留的临时文件
#         if temp_file.exists():
#             try:
#                 temp_file.unlink()
#             except:
#                 pass
#         raise Exception(error_msg)
    
#     except Exception as e:
#         logger.error(f"创建禁用文件时发生未预期错误: {e}")
#         raise


# def remove_disable_file(client_name: str) -> bool:
#     """
#     安全地删除客户端禁用文件
    
#     Args:
#         client_name: 客户端名称（已验证）
        
#     Returns:
#         是否成功删除
#     """
#     disable_file_path = Path(config.ccd_dir) / client_name
    
#     try:
#         result = subprocess.run(
#             ['sudo', 'rm', '-f', str(disable_file_path)],
#             check=True,
#             capture_output=True,
#             text=True,
#             timeout=5
#         )
#         logger.info(f"成功删除禁用文件: {disable_file_path}")
#         return True
        
#     except subprocess.CalledProcessError as e:
#         logger.error(f"删除禁用文件失败: {e.stderr}")
#         return False
#     except Exception as e:
#         logger.error(f"删除禁用文件时发生错误: {e}")
#         return False


# # ==============================================================================
# # OpenVPN 管理接口通信
# # ==============================================================================

# def recv_all_until_end(sock: socket.socket, timeout: float = 3.0) -> str:
#     """从 socket 接收所有数据直到 END 标记"""
#     sock.settimeout(timeout)
#     data = b''
    
#     while True:
#         try:
#             chunk = sock.recv(config.recv_chunk_size)
#             if not chunk:
#                 break
#             data += chunk
#             # 检查是否收到 END 标记
#             if b'\nEND' in data or data.endswith(b'END') or b'\r\nEND' in data:
#                 break
#         except socket.timeout:
#             break
#         except Exception as e:
#             logger.error(f"接收数据时发生错误: {e}")
#             break
    
#     return data.decode('utf-8', errors='ignore')


# def send_and_recv(sock: socket.socket, cmd: str, wait: float = 0.05, 
#                   recv_timeout: float = 2.0) -> str:
#     """发送命令并接收响应"""
#     try:
#         sock.sendall((cmd + "\n").encode('utf-8'))
#         time.sleep(wait)
#         return recv_all_until_end(sock, timeout=recv_timeout)
#     except Exception as e:
#         logger.error(f"发送命令 '{cmd}' 时发生错误: {e}")
#         raise


# def parse_status_for_cids(status_text: str, common_name: str) -> Optional[List[str]]:
#     """
#     从 status 输出中解析客户端 ID
    
#     Returns:
#         None: 未找到客户端
#         []: 找到客户端但没有 client_id
#         [cid1, cid2, ...]: 找到的 client_id 列表
#     """
#     lines = status_text.splitlines()
#     header_cols = None
#     client_lines = []
    
#     # 解析 CSV 格式的状态输出
#     for ln in lines:
#         if ln.startswith('HEADER,CLIENT_LIST'):
#             parts = ln.split(',')
#             header_cols = parts[2:]
#             continue
#         if ln.startswith('CLIENT_LIST,'):
#             client_lines.append(ln)
    
#     if header_cols:
#         low_headers = [h.strip().lower() for h in header_cols]
        
#         # 查找 common name 和 client id 列索引
#         try:
#             idx_cn = low_headers.index('common name')
#         except ValueError:
#             idx_cn = 0
        
#         cid_idx = None
#         if 'client id' in low_headers:
#             cid_idx = low_headers.index('client id')
        
#         cids = []
#         found_client = False
        
#         for cl in client_lines:
#             parts = cl.split(',')[1:]  # 跳过 "CLIENT_LIST,"
#             name = parts[idx_cn] if idx_cn < len(parts) else ''
            
#             if name == common_name:
#                 found_client = True
#                 if cid_idx is not None and cid_idx < len(parts):
#                     cid = parts[cid_idx]
#                     if cid:
#                         cids.append(cid)
        
#         if found_client:
#             return cids if cids else []
#         return None
    
#     # 旧格式兼容处理
#     for i, ln in enumerate(lines):
#         if ln.startswith('Common Name,'):
#             for dl in lines[i+1:]:
#                 if (dl.strip() == '' or dl.startswith('ROUTING TABLE') or 
#                     dl.startswith('GLOBAL STATS') or dl == 'END'):
#                     break
#                 parts = dl.split(',')
#                 if parts and parts[0] == common_name:
#                     return []
#             break
    
#     return None


# def openvpn_client_kill(host: str, port: int, client_name: str, 
#                         mgmt_password: Optional[str] = None) -> Tuple[bool, str]:
#     """
#     通过 OpenVPN 管理接口踢出客户端
    
#     Args:
#         host: 管理接口地址
#         port: 管理接口端口
#         client_name: 客户端名称
#         mgmt_password: 管理接口密码（可选）
        
#     Returns:
#         (success, message): 是否成功和详细消息
#     """
#     try:
#         with socket.create_connection((host, port), timeout=config.socket_timeout) as s:
#             # 接收欢迎信息
#             banner = s.recv(config.recv_chunk_size).decode('utf-8', errors='ignore')
#             logger.debug(f"管理接口欢迎信息: {banner[:100]}")
            
#             # 如果需要密码认证
#             if mgmt_password:
#                 s.sendall(f"password {mgmt_password}\n".encode())
#                 time.sleep(0.05)
#                 auth_resp = recv_all_until_end(s, timeout=1.0)
#                 if 'SUCCESS' not in auth_resp.upper():
#                     return False, f"管理接口认证失败: {auth_resp}"
            
#             # 获取状态信息
#             raw_status = send_and_recv(s, "status 2", wait=0.05, 
#                                       recv_timeout=config.recv_timeout)
#             parse_res = parse_status_for_cids(raw_status, client_name)
            
#             # 根据解析结果选择踢出方式
#             if parse_res is None:
#                 # 未找到客户端（可能已断开）
#                 resp = send_and_recv(s, f"kill {client_name}", wait=0.05, 
#                                    recv_timeout=config.recv_timeout)
#                 logger.info(f"客户端 '{client_name}' 未在线，尝试 kill 命令")
#                 return True, f"客户端可能未在线。kill 命令响应: {resp.strip()}"
                
#             elif isinstance(parse_res, list) and len(parse_res) == 0:
#                 # 找到客户端但没有 client_id（旧版本 OpenVPN）
#                 resp = send_and_recv(s, f"kill {client_name}", wait=0.05, 
#                                    recv_timeout=config.recv_timeout)
#                 logger.info(f"使用 kill {client_name} (无 client_id)")
#                 return True, f"成功执行 kill 命令。响应: {resp.strip()}"
                
#             else:
#                 # 找到 client_id，使用 client-kill
#                 cids = parse_res
#                 results = []
#                 all_success = True
                
#                 for cid in cids:
#                     resp = send_and_recv(s, f"client-kill {cid}", wait=0.05, 
#                                        recv_timeout=config.recv_timeout)
#                     resp_clean = resp.strip()
#                     results.append(f"client-kill {cid}: {resp_clean}")
                    
#                     if 'SUCCESS' not in resp_clean.upper():
#                         all_success = False
                
#                 logger.info(f"踢出客户端 {client_name}，CID: {cids}")
                
#                 status = "成功" if all_success else "部分成功"
#                 return all_success, f"{status}踢出客户端。\n" + "\n".join(results)
            
#             # 发送 quit 命令
#             s.sendall(b"quit\n")
            
#     except socket.timeout:
#         error_msg = f"连接管理接口超时: {host}:{port}"
#         logger.error(error_msg)
#         return False, error_msg
        
#     except socket.error as e:
#         error_msg = f"无法连接到 OpenVPN 管理接口 {host}:{port}: {e}"
#         logger.error(error_msg)
#         return False, error_msg
        
#     except Exception as e:
#         error_msg = f"踢出客户端时发生错误: {e}"
#         logger.error(error_msg)
#         return False, error_msg


# # ==============================================================================
# # 数据库操作
# # ==============================================================================

# def get_client_from_db(client_name: str) -> Optional[Client]:
#     """
#     从数据库获取客户端
    
#     Returns:
#         Client 对象或 None
        
#     Raises:
#         SQLAlchemyError: 数据库错误
#     """
#     try:
#         return Client.query.filter_by(name=client_name).first()
#     except SQLAlchemyError as e:
#         logger.error(f"数据库查询失败: {e}")
#         raise


# def update_client_disabled_status(client_name: str, disabled: bool) -> bool:
#     """
#     更新客户端的禁用状态
    
#     Args:
#         client_name: 客户端名称
#         disabled: 禁用状态
        
#     Returns:
#         是否成功更新
        
#     Raises:
#         SQLAlchemyError: 数据库错误
#     """
#     try:
#         client = get_client_from_db(client_name)
#         if not client:
#             logger.warning(f"数据库中未找到客户端 {client_name}")
#             return False
        
#         client.disabled = disabled
#         db.session.commit()
        
#         status_text = "禁用" if disabled else "启用"
#         logger.info(f"成功将客户端 {client_name} 标记为{status_text}")
#         return True
        
#     except SQLAlchemyError as e:
#         db.session.rollback()
#         logger.error(f"更新客户端 {client_name} 状态失败: {e}")
#         raise


# # ==============================================================================
# # Flask 蓝图和路由
# # ==============================================================================

# kill_client_bp = Blueprint('kill_client', __name__)


# @kill_client_bp.route('/kill_client', methods=['POST'])
# @login_required
# @require_client_name
# def kill_client(client_name: str):
#     """
#     踢出并禁用客户端
    
#     工作流程:
#     1. 验证客户端名称
#     2. 检查数据库中是否存在
#     3. 获取操作锁（防止并发）
#     4. 创建禁用文件
#     5. 通过管理接口踢出客户端
#     6. 更新数据库状态
#     """
#     # 获取客户端操作锁
#     client_lock = lock_manager.get_lock(client_name)
    
#     if not client_lock.acquire(blocking=False):
#         logger.warning(f"客户端 {client_name} 正在被其他操作处理")
#         return jsonify({
#             "status": 'error',
#             "message": f"客户端 {client_name} 正在被其他操作处理，请稍后重试"
#         }), 409
    
#     try:
#         # 1. 检查数据库中是否存在该客户端
#         try:
#             client = get_client_from_db(client_name)
            
#             if not client:
#                 logger.warning(f"尝试踢出不存在的客户端: {client_name}")
#                 return jsonify({
#                     "status": 'error',
#                     "message": f"客户端 {client_name} 不存在于数据库中"
#                 }), 404
            
#             # 检查是否已经被禁用
#             if client.disabled:
#                 logger.info(f"客户端 {client_name} 已经处于禁用状态")
#                 return jsonify({
#                     "status": 'warning',
#                     "message": f"客户端 {client_name} 已经处于禁用状态"
#                 }), 200
                
#         except SQLAlchemyError as e:
#             return jsonify({
#                 "status": 'error',
#                 "message": "数据库查询失败"
#             }), 500
        
#         # 2. 使用事务创建禁用文件
#         try:
#             with disable_file_transaction(client_name) as disable_file_path:
#                 logger.info(f"成功创建禁用文件: {disable_file_path}")
                
#                 # 3. 踢出在线客户端
#                 kill_success, kill_message = openvpn_client_kill(
#                     config.mgmt_host,
#                     config.mgmt_port,
#                     client_name,
#                     mgmt_password=config.mgmt_password
#                 )
                
#                 # 4. 更新数据库
#                 try:
#                     db_updated = update_client_disabled_status(client_name, True)
                    
#                     if not db_updated:
#                         # 如果数据库更新失败，抛出异常触发事务回滚
#                         raise Exception("数据库更新失败：客户端不存在")
                    
#                     # 记录操作日志
#                     log_message(
#                         f"成功禁用客户端 {client_name} "
#                         f"[踢出: {'成功' if kill_success else '失败'}]"
#                     )
                    
#                     # 返回成功响应
#                     return jsonify({
#                         "status": 'success' if kill_success else 'partial_success',
#                         "message": (
#                             f"客户端 {client_name} 已成功禁用。"
#                             f"{'已从 VPN 断开连接。' if kill_success else '但踢出操作失败（可能未在线）。'}"
#                         ),
#                         "details": {
#                             "client_name": client_name,
#                             "disabled_in_db": True,
#                             "disable_file_created": True,
#                             "kicked_from_vpn": kill_success,
#                             "kick_message": kill_message
#                         }
#                     }), 200
                    
#                 except SQLAlchemyError as e:
#                     # 数据库错误，触发回滚
#                     raise Exception(f"数据库更新失败: {e}")
        
#         except Exception as e:
#             # 任何错误都会触发禁用文件的回滚
#             logger.error(f"踢出客户端 {client_name} 失败: {e}")
#             return jsonify({
#                 "status": 'error',
#                 "message": f"操作失败: {str(e)}"
#             }), 500
    
#     finally:
#         # 释放锁
#         client_lock.release()






