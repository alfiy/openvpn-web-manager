/**
 * 这个模块包含了安装和卸载的逻辑
 */
import { qs, showCustomMessage, showCustomConfirm, authFetch, isValidIP } from './utils.js';
import { stopAutoRefresh, startAutoRefresh } from './refresh.js';

export function bindInstall() {
    const btn = qs('#install-btn');
    // 移除 'data-bound' 检查，因为按钮在每次刷新时都会被重新创建
    if (!btn) return;

    const modalEl = qs('#installModal');
    const modal = modalEl ? bootstrap.Modal.getOrCreateInstance(modalEl) : null;

    btn.addEventListener('click', async () => {
        if (!modal) return;
        const sel = qs('#install-ip-select');
        const wrap = qs('#manual-ip-wrapper');
        sel.innerHTML = '<option disabled selected>正在获取…</option>';
        wrap && (wrap.style.display = 'none');

        try {
            // authFetch 直接返回 JSON 数据，无需再调用 .json()
            const list = await authFetch('/get_ip_list');
            sel.innerHTML = '';
            list.forEach(ip => sel.appendChild(new Option(ip, ip)));
            sel.appendChild(new Option('手动输入…', ''));
        } catch {
            sel.innerHTML = '<option value="">手动输入…</option>';
            wrap && (wrap.style.display = 'block');
        }
        modal.show();
    });

    qs('#install-ip-select')?.addEventListener('change', function () {
        const wrap = qs('#manual-ip-wrapper');
        wrap && (wrap.style.display = this.value ? 'none' : 'block');
    });

    qs('#confirm-install')?.addEventListener('click', async () => {
        const port = Number(qs('#install-port').value);
        const sel = qs('#install-ip-select');
        const ip = sel.value || qs('#install-ip-input').value.trim();

        if (!Number.isInteger(port) || port < 1025 || port > 65534) {
            return showCustomMessage('端口号必须在 1025-65534 之间');
        }
        if (!ip) return showCustomMessage('请选择或输入服务器 IP');
        if (!sel.value && !isValidIP(ip)) return showCustomMessage('IP 格式不正确');

        modal?.hide();
        const loader = qs('#install-loader');
        const msg = qs('#status-message');

        // 在开始安装时停止自动刷新
        stopAutoRefresh();

        loader && (loader.style.display = 'block');
        msg && (msg.className = 'alert alert-info', msg.textContent = '正在安装 OpenVPN...', msg.classList.remove('d-none'));

        try {
            // authFetch 直接返回 JSON 数据
            const data = await authFetch('/install', {
                method: 'POST',
                body: JSON.stringify({ port, ip })
            });

            loader && (loader.style.display = 'none');
            if (msg) {
                msg.textContent = data.message;
                msg.className = data.status === 'success' ? 'alert alert-success' : 'alert alert-danger';
            }
            if (data.status === 'success') {
                // 在安装成功后也恢复自动刷新
                // startAutoRefresh(10000, window.currentUserRole); 
                setTimeout(() => location.href = (data.redirect || '/'), 1000);
            }
        } catch (err) {
            loader && (loader.style.display = 'none');
            if (msg) { 
                msg.textContent = '安装失败: ' + err; 
                msg.className = 'alert alert-danger'; 
                
            }
        } finally{
            // 无论成功或失败，都在安装流程结束时恢复自动刷新
            startAutoRefresh(10000, window.currentUserRole);
        }
    });

    modalEl?.addEventListener('hide.bs.modal', () => qs('#manual-ip-wrapper') && (qs('#manual-ip-wrapper').style.display = 'none'));
}

export function bindUninstall() {
    // console.log('in bindUninstall(): ');
    const btn = qs('#uninstall-btn');
    if (!btn || btn.hasAttribute('data-bound')) {
        // console.log('in bindUninstall(): ', btn);
        return;
    }
    btn.setAttribute('data-bound', 'true');

    btn.addEventListener('click', () => {
        showCustomConfirm('确定要卸载OpenVPN吗? 所有客户端配置将被删除!', async (ok) => {
            if (!ok) {
                return;
            }

            const loader = qs('#uninstall-loader');
            const msg = qs('#status-message');

            if (loader) {
                loader.style.display = 'block';
            }
            if (msg) {
                msg.className = 'alert alert-info';
                msg.textContent = '正在卸载OpenVPN...';
                msg.classList.remove('d-none');
            }

            try {
                // authFetch 直接返回 JSON 数据
                const data = await authFetch('/uninstall', { method: 'POST' });
                
                if (loader) {
                    loader.style.display = 'none';
                }
                if (msg) {
                    msg.textContent = data.message;
                    msg.className = data.status === 'success' ? 'alert alert-success' : 'alert alert-danger';
                }
                
                if (data.status === 'success') {
                    setTimeout(() => location.reload(), 1200);
                }
            } catch (err) {
                if (loader) {
                    loader.style.display = 'none';
                }
                if (msg) {
                    msg.textContent = '卸载失败: ' + err;
                    msg.className = 'alert alert-danger';
                }
            }
        });
    });
}

export function init() {
    bindInstall();
    bindUninstall();
}