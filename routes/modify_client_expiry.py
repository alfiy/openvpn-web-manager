from flask import Blueprint, request, jsonify
import subprocess
import os
import re
import tempfile
import shutil
from datetime import datetime, timedelta
from utils.openvpn_utils import get_openvpn_port

modify_client_expiry_bp = Blueprint('modify_client_expiry', __name__)

# ---------- 正则提取 CN ----------
_CN_RE = re.compile(r'/CN=([^/]+)')

def _extract_cn(subject: str) -> str:
    m = _CN_RE.search(subject)
    return m.group(1) if m else ""

# ---------- 原子化清理 index.txt ----------
def _cleanup_index(index_file: str, client_name: str) -> None:
    """
    删除指定客户端且已吊销(R)的重复记录，其余行按 serial+CN 去重后写回。
    任何异常仅打印 warning，不抛出。
    """
    if not os.path.isfile(index_file):
        return

    cleaned_lines = []
    seen = set()  # (serial, cn)

    try:
        with open(index_file, "r", encoding="utf-8") as f:
            for raw_line in f:
                raw_line = raw_line.rstrip("\n")
                if not raw_line:
                    continue
                parts = raw_line.split("\t")
                if len(parts) < 6:
                    cleaned_lines.append(raw_line)
                    continue

                status, serial, subject = parts[0], parts[3], parts[5]
                cn = _extract_cn(subject)

                # 跳过「指定客户端且已吊销」的记录
                if status == "R" and cn == client_name:
                    continue

                key = (serial, cn)
                if key not in seen:
                    cleaned_lines.append(raw_line)
                    seen.add(key)

        # 原子写回
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=os.path.dirname(index_file),
            prefix="index_tmp_"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp_f:
                tmp_f.write("\n".join(cleaned_lines))
                if cleaned_lines:
                    tmp_f.write("\n")
            shutil.move(tmp_path, index_file)
        except Exception:
            os.unlink(tmp_path)
            raise
    except Exception as cleanup_err:
        print(f"Warning: failed to cleanup index.txt -> {cleanup_err}")

# ---------- 主路由 ----------
@modify_client_expiry_bp.route('/modify_client_expiry', methods=['POST'])
def modify_client_expiry():
    """Modify client certificate expiration date by revoke + reissue"""
    client_name = request.form.get('client_name')
    expiry_days = request.form.get('expiry_days')
    port = get_openvpn_port()

    if not client_name or not expiry_days:
        return jsonify({'status': 'error', 'message': 'Client name and expiry days are required'})

    client_name = client_name.strip()
    if not client_name:
        return jsonify({'status': 'error', 'message': 'Client name is required'})

    try:
        expiry_days = int(expiry_days)
        if expiry_days <= 0:
            return jsonify({'status': 'error', 'message': 'Expiry days must be positive'})
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid expiry days format'})

    easy_rsa_dir = "/etc/openvpn/easy-rsa"
    index_file = os.path.join(easy_rsa_dir, "pki/index.txt")

    try:
        # Step 1: Revoke old certificate
        revoke_cmd = [
            'sudo', 'bash', '-c',
            f'cd {easy_rsa_dir} && echo "yes" | ./easyrsa revoke "{client_name}"'
        ]
        result = subprocess.run(revoke_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return jsonify({'status': 'error', 'message': f'Failed to revoke old cert: {result.stderr or result.stdout}'})

        # Step 2: Update CRL
        subprocess.run([
            'sudo', 'bash', '-c',
            f'cd {easy_rsa_dir} && ./easyrsa gen-crl && cp pki/crl.pem /etc/openvpn/'
        ], capture_output=True, text=True)

        # Step 3: Reissue new certificate with updated expiry
        build_cmd = [
            'sudo', 'bash', '-c',
            f'cd {easy_rsa_dir} && EASYRSA_CERT_EXPIRE={expiry_days} ./easyrsa --batch build-client-full "{client_name}" nopass'
        ]
        result = subprocess.run(build_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return jsonify({'status': 'error', 'message': f'Failed to reissue cert: {result.stderr or result.stdout}'})

        # Step 4: Regenerate client configuration file
        config_cmd = [
            'sudo', 'bash', '-c', f'''
            cp /etc/openvpn/client-template.txt /etc/openvpn/client/{client_name}.ovpn
            {{
                echo "<ca>"
                cat {easy_rsa_dir}/pki/ca.crt
                echo "</ca>"
                echo "<cert>"
                awk "/BEGIN/,/END CERTIFICATE/" {easy_rsa_dir}/pki/issued/{client_name}.crt
                echo "</cert>"
                echo "<key>"
                cat {easy_rsa_dir}/pki/private/{client_name}.key
                echo "</key>"
                echo "<tls-crypt>"
                cat /etc/openvpn/tls-crypt.key
                echo "</tls-crypt>"
            }} >> /etc/openvpn/client/{client_name}.ovpn
            chmod 644 /etc/openvpn/client/{client_name}.ovpn
            '''
        ]
        result = subprocess.run(config_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return jsonify({'status': 'error', 'message': f'Failed to generate client config: {result.stderr or result.stdout}'})

        # Step 5: Reload OpenVPN to pick up new CRL
        subprocess.run([
            'sudo', 'systemctl', 'reload', 'openvpn@server'
        ], capture_output=True, text=True)

        # Step 6: Clean up index.txt (原子化、按 serial+CN 去重)
        _cleanup_index(index_file, client_name)

        # Calculate new expiry date
        new_expiry_date = datetime.now() + timedelta(days=expiry_days)
        expiry_date_str = new_expiry_date.strftime('%Y-%m-%d')

        return jsonify({
            'status': 'success',
            'message': f'Client {client_name} expiry modified successfully to {expiry_days} days (expires: {expiry_date_str}). Old cert revoked, new cert issued and index.txt cleaned.'
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to modify client expiry: {str(e)}'})
