/**
 * 这个模块包含了安装和卸载的逻辑
 */
import { qs, showCustomMessage, showCustomConfirm, authFetch, isValidIP } from './utils.js';
import { stopAutoRefresh, startAutoRefresh } from './refresh.js';


export function bindInstall() {
    const actionsContainer = qs('#openvpn-status-actions');
    if (!actionsContainer) return;

    // 使用事件委托，绑定到容器而不是按钮
    // 先移除旧的事件监听器（防止重复绑定）
    const newContainer = actionsContainer.cloneNode(true);
    actionsContainer.parentNode.replaceChild(newContainer, actionsContainer);

    // 绑定点击事件委托
    newContainer.addEventListener('click', async (e) => {
        // 检查点击的是否是安装按钮
        const btn = e.target.closest('#install-btn');
        if (!btn) return;

        // 阻止默认行为
        e.preventDefault();
        e.stopPropagation();

        const modalEl = qs('#installModal');
        const modal = modalEl ? bootstrap.Modal.getOrCreateInstance(modalEl) : null;
        if (!modal) {
            console.error('找不到 installModal');
            return;
        }

        // 以下逻辑保持不变...
        const sel = qs('#install-ip-select');
        const wrap = qs('#manual-ip-wrapper');
        if (sel) sel.innerHTML = '<option disabled selected>正在获取…</option>';
        if (wrap) wrap.style.display = 'none';

        try {
            const list = await authFetch('/get_ip_list');
            if (sel) {
                sel.innerHTML = '';
                list.forEach(ip => sel.appendChild(new Option(ip, ip)));
                sel.appendChild(new Option('手动输入…', ''));
            }
        } catch {
            if (sel) sel.innerHTML = '<option value="">手动输入…</option>';
            if (wrap) wrap.style.display = 'block';
        }
        modal.show();
    });

    // 绑定其他相关事件（这些元素不在 actionsContainer 内，不需要委托）
    bindInstallModalEvents();
}

// 分离 Modal 内部事件绑定（这些元素不会被频繁重建）
function bindInstallModalEvents() {
    const modalEl = qs('#installModal');
    if (!modalEl) return;

    // IP 选择变化事件
    const ipSelect = qs('#install-ip-select');
    if (ipSelect && !ipSelect.dataset.bound) {
        ipSelect.dataset.bound = 'true';
        ipSelect.addEventListener('change', function () {
            const wrap = qs('#manual-ip-wrapper');
            if (wrap) wrap.style.display = this.value ? 'none' : 'block';
        });
    }

    // 确认安装按钮事件
    const confirmBtn = qs('#confirm-install');
    if (confirmBtn && !confirmBtn.dataset.bound) {
        confirmBtn.dataset.bound = 'true';
        confirmBtn.addEventListener('click', async () => {
            const modal = bootstrap.Modal.getInstance(qs('#installModal'));
            
            const port = Number(qs('#install-port')?.value);
            const sel = qs('#install-ip-select');
            const ip = sel?.value || qs('#install-ip-input')?.value?.trim();

            if (!Number.isInteger(port) || port < 1025 || port > 65534) {
                return showCustomMessage('端口号必须在 1025-65534 之间');
            }
            if (!ip) return showCustomMessage('请选择或输入服务器 IP');
            if (!sel?.value && !isValidIP(ip)) return showCustomMessage('IP 格式不正确');

            modal?.hide();
            const loader = qs('#install-loader');
            const msg = qs('#status-message');

            stopAutoRefresh();

            if (loader) loader.style.display = 'block';
            if (msg) {
                msg.className = 'alert alert-info';
                msg.textContent = '正在安装 OpenVPN...';
                msg.classList.remove('d-none');
            }

            try {
                const data = await authFetch('/install', {
                    method: 'POST',
                    body: JSON.stringify({ port, ip })
                });

                if (loader) loader.style.display = 'none';
                if (msg) {
                    msg.textContent = data.message;
                    msg.className = data.status === 'success' ? 'alert alert-success' : 'alert alert-danger';
                }
                if (data.status === 'success') {
                    setTimeout(() => location.href = (data.redirect || '/'), 1000);
                }
            } catch (err) {
                if (loader) loader.style.display = 'none';
                if (msg) {
                    msg.textContent = '安装失败: ' + err;
                    msg.className = 'alert alert-danger';
                }
            } finally {
                startAutoRefresh(10000, window.currentUserRole);
            }
        });
    }

    // Modal 隐藏事件
    if (!modalEl.dataset.bound) {
        modalEl.dataset.bound = 'true';
        modalEl.addEventListener('hide.bs.modal', () => {
            const wrap = qs('#manual-ip-wrapper');
            if (wrap) wrap.style.display = 'none';
        });
    }
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