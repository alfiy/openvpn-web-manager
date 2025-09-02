/* ---------- 原生选择器简写（避免与 jQuery 冲突） ---------- */
const qs = (sel, ctx = document) => ctx.querySelector(sel);
const qsa = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

/* ---------- 自定义消息和确认框模态框 ---------- */
const createModal = (id, title, bodyContent) => {
    return `
    <div class="modal fade" id="${id}" tabindex="-1" aria-labelledby="${id}Label" aria-hidden="true">
        <div class="modal-dialog modal-dialog-centered">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title" id="${id}Label">${title}</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body">${bodyContent}</div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                    <button type="button" class="btn btn-primary d-none" id="${id}-confirm-btn">确定</button>
                </div>
            </div>
        </div>
    </div>`;
};

// 在页面加载时添加模态框元素
document.addEventListener('DOMContentLoaded', () => {
    if (!qs("#custom-modal-container")) {
        const container = document.createElement('div');
        container.id = 'custom-modal-container';
        container.innerHTML = createModal('messageModal', '提示', '');
        container.innerHTML += createModal('confirmModal', '请确认', '');
        document.body.appendChild(container);
    }
});

function showCustomMessage(message, title = '提示') {
    const modalEl = qs('#messageModal');
    qs('#messageModal .modal-title').textContent = title;
    qs('#messageModal .modal-body').textContent = message;
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
}


function showCustomConfirm(message, callback) {
    const modalEl = qs('#confirmModal');
    const body = qs('#confirmModal .modal-body');
    const okBtn = qs('#confirmModal-confirm-btn');
    body.textContent = message;
    okBtn.classList.remove('d-none');

    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    okBtn.onclick = () => {
        modal.hide();
        callback(true);
    };
    modalEl.addEventListener('hide.bs.modal', () => {
        okBtn.onclick = null;
        okBtn.classList.add('d-none');
    }, { once: true });
    modal.show();
}

/* ---------- 带认证 + CSRF 的 fetch ---------- */
function authFetch(url, opts = {}) {
    const headers = new Headers(opts.headers || {});
    const meta = qs('meta[name="csrf-token"]');
    if (meta && !headers.has('X-CSRFToken')) headers.set('X-CSRFToken', meta.content);
    return fetch(url, { ...opts, headers, credentials: 'same-origin' })
        .then(r => {
            if (r.status === 401) { location.href = '/login'; throw new Error('未登录'); }
            if (!r.ok) return r.json().then(e => Promise.reject(e.message || '服务器错误'));
            return r;
        });
}


/* ---------- 页面局部刷新 ---------- */
let autoRefreshInterval = null;
function refreshPage() {
    return authFetch('/')
        .then(r => r.text())
        .then(html => {
            const p = new DOMParser(), doc = p.parseFromString(html, 'text/html');
            const scroll = window.scrollY;
            const cur = qs('.card:first-child .card-body');
            const next = doc.querySelector('.card:first-child .card-body');
            if (cur && next) cur.innerHTML = next.innerHTML;
            window.scrollTo(0, scroll);
            
            /* 重新绑定按钮事件，防止局部刷新后失效 */
            bindInstall();
            bindUninstall();

            /* 其它需要重新绑定的也放这里 */
            bindAll();   // 如果 bindAll 里已经包含 install/uninstall，可以只保留这一行
        })
        .catch(console.error);
}

function startAutoRefresh(ms = 10000) {
    stopAutoRefresh();
    autoRefreshInterval = setInterval(() => !document.hidden && refreshPage(), ms);
}

function stopAutoRefresh() {
    if (autoRefreshInterval) { clearInterval(autoRefreshInterval); autoRefreshInterval = null; }
}

document.addEventListener('visibilitychange', () => document.hidden ? stopAutoRefresh() : startAutoRefresh());



/**
 * 验证IPv4地址的合法性
 * @param {string} ip - 需要验证的IP地址字符串
 * @returns {boolean} - 如果IP地址合法返回true，否则返回false
 */
function isValidIP(ip) {
    const regex = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
    return regex.test(ip);
}

/* ---------- 安装 ---------- */
function bindInstall() {
    const btn = qs('#install-btn');
    if (!btn || btn.hasAttribute('data-bound')) return;
    btn.setAttribute('data-bound', 'true');

    const modalEl = qs('#installModal');
    const modal = modalEl ? bootstrap.Modal.getOrCreateInstance(modalEl) : null;

    // 打开安装模态框时拉取 IP
    btn.addEventListener('click', async () => {
        if (!modal) return;
        const sel = qs('#install-ip-select');
        const wrap = qs('#manual-ip-wrapper');
        sel.innerHTML = '<option disabled selected>正在获取…</option>';
        wrap && (wrap.style.display = 'none');

        try {
            const list = await authFetch('/get_ip_list').then(r => r.json());
            sel.innerHTML = '';
            list.forEach(ip => sel.appendChild(new Option(ip, ip)));
            sel.appendChild(new Option('手动输入…', ''));
        } catch {
            sel.innerHTML = '<option value="">手动输入…</option>';
            wrap && (wrap.style.display = 'block');
        }
        modal.show();
    });

    // 下拉框切换
    qs('#install-ip-select')?.addEventListener('change', function () {
        const wrap = qs('#manual-ip-wrapper');
        wrap && (wrap.style.display = this.value ? 'none' : 'block');
    });

    // 确认安装
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
        const msg  = qs('#status-message');
        loader && (loader.style.display = 'block');
        msg && (msg.className = 'alert alert-info', msg.textContent = '正在安装 OpenVPN...', msg.classList.remove('d-none'));

        try {
            const res = await authFetch('/install', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ port, ip })
            });
            const data = await res.json();
            loader && (loader.style.display = 'none');
            if (msg) {
                msg.textContent = data.message;
                msg.className = data.status === 'success' ? 'alert alert-success' : 'alert alert-danger';
            }
            if (data.status === 'success') setTimeout(() => location.href = (data.redirect || '/'), 1000);
        } catch (err) {
            loader && (loader.style.display = 'none');
            if (msg) { msg.textContent = '安装失败: ' + err; msg.className = 'alert alert-danger'; }
        }
    });

    modalEl?.addEventListener('hide.bs.modal', () => qs('#manual-ip-wrapper') && (qs('#manual-ip-wrapper').style.display = 'none'));
}

/* 卸载按钮：事件委托写法，只需执行一次 */
function bindUninstall() {
    // 绑定一次即可
    document.addEventListener('click', e => {
        const btn = e.target.closest('#uninstall-btn');
        if (!btn) return;

        showCustomConfirm('确定要卸载OpenVPN吗? 所有客户端配置将被删除!', async ok => {
            if (!ok) return;
            const loader = qs('#uninstall-loader');
            const msg   = qs('#status-message');
            loader && (loader.style.display = 'block');
            msg && (msg.className = 'alert alert-info', msg.textContent = '正在卸载OpenVPN...', msg.classList.remove('d-none'));

            try {
                const data = await authFetch('/uninstall', { method: 'POST' }).then(r => r.json());
                loader.style.display = 'none';
                msg.textContent = data.message;
                msg.className = data.status === 'success' ? 'alert alert-success' : 'alert alert-danger';
                if (data.status === 'success') setTimeout(() => location.reload(), 1200);
            } catch (err) {
                loader.style.display = 'none';
                msg.textContent = '卸载失败: ' + err;
                msg.className = 'alert alert-danger';
            }
        });
    });
}

/* ---------- 有效期单选按钮联动 ---------- */
function toggleCustomDate(prefix) {
    const wrapper = qs(`#${prefix}DateWrapper`);
    if (wrapper) wrapper.classList.toggle('d-none', !qs(`#${prefix}Custom`).checked);
}


/* ---------- 添加客户端 ---------- */
function bindAddClient() {
    const form = qs('#add-client-form');
    if (!form || form.hasAttribute('data-bound')) return;
    form.setAttribute('data-bound', 'true');

    qsa('input[name="expiry_choice"]').forEach(r => r.addEventListener('change', () => toggleCustomDate('expiry')));
    toggleCustomDate('expiry');

    // 重置按钮
    const resetButton = qs('#reset-btn');
    if (resetButton) {
        resetButton.addEventListener('click', () => {
            const clientNameInput = qs('#client_name');
            form.reset();
            toggleCustomDate('expiry'); // 确保自定义日期输入框状态正确
        });
    }

    form.addEventListener('submit', async e => {
        e.preventDefault();
        const loader = qs('#add-client-loader');
        const msgDiv = qs('#add-client-message');
        const nameVal = qs('#client_name').value.trim();
        if (!nameVal) { msgDiv.innerHTML = '<div class="alert alert-danger">请输入客户端名称</div>'; return; }

        loader.style.display = 'block';

        let expiryDays;
        const choice = qs('input[name="expiry_choice"]:checked').value;
        if (choice === 'custom') {
            const d = qs('#expiry_date').value;
            if (!d) { msgDiv.innerHTML = '<div class="alert alert-danger">请选择到期日期</div>'; loader.style.display = 'none'; return; }
            const diff = Math.ceil((new Date(d) - new Date()) / 86400000);
            if (diff <= 0) { msgDiv.innerHTML = '<div class="alert alert-danger">到期日期必须是将来的日期</div>'; loader.style.display = 'none'; return; }
            expiryDays = diff.toString();
        } else {
            expiryDays = choice;
        }

        try {
            const res = await authFetch('/add_client', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ client_name: nameVal, expiry_days: expiryDays })
            });
            const data = await res.json();
            
            loader.style.display = 'none';
            const cls = data.status === 'success' ? 'alert-success' : 'alert-danger';
            msgDiv.innerHTML = `<div class="alert ${cls}">${data.message}</div>`;
            if (data.status === 'success') {
                form.reset();
                toggleCustomDate('expiry');
                setTimeout(() => msgDiv.innerHTML = '', 2000);
                window.clientAjax.load();
            }
        } catch(err) {
            loader.style.display = 'none';
            msgDiv.innerHTML = `<div class="alert alert-danger">${err}</div>`;
        }
    });
}

    // 页面加载完成后绑定事件
    document.addEventListener('DOMContentLoaded', () => {
        bindAddClient();
        // bindUserManagement();  
        // bindAddUserForm();     
    });

/* ---------- 修改到期 ---------- */
function bindModifyExpiry() {
    /* 全局只创建一个实例，避免重复 new */
    const modalEl = qs('#modifyExpiryModal');
    const modalIns = bootstrap.Modal.getOrCreateInstance(modalEl);

        /* 事件委托：打开弹窗 */
    document.body.addEventListener('click', e => {
        if (e.target.classList.contains('modify-expiry-btn')) {
            qs('#modify-client-name').value = e.target.dataset.client;
            modalIns.show();
        }
    });

    /* 自定义日期联动 */
    qsa('input[name="modify_expiry_choice"]').forEach(radio => {
        radio.addEventListener('change', () => {
            qs('#modifyCustomDateWrapper').classList.toggle('d-none', !qs('#modify-expiryCustom').checked);
        });
    });

    /* 确认按钮只绑一次 */
    const btnConfirm = qs('#confirm-modify-expiry');
    
    if (btnConfirm && !btnConfirm.hasAttribute('data-bound')) {
        btnConfirm.setAttribute('data-bound', 'true'); // 修复代码中的注释，确保只绑定一次
        
        btnConfirm.addEventListener('click', async () => {
            // 将获取 name 变量的代码移动到这里
            const name = qs('#modify-client-name').value;

            let days;
            if (qs('#modify-expiryCustom').checked) {
                const d = qs('#modify-expiry-date').value;
                if (!d) {
                    qs('#modify-expiry-message').innerHTML =
                        '<div class="alert alert-danger">请选择到期日期</div>';
                    return;
                }
                days = Math.ceil((new Date(d) - new Date()) / 86400000).toString();
            } else {
                const selected = document.querySelector('input[name="modify_expiry_choice"]:checked');
                days = selected ? selected.value : '30';
            }

            const loader = qs('#modify-expiry-loader');
            const msg = qs('#modify-expiry-message');
            loader.style.display = 'inline-block';
            btnConfirm.disabled = true;

            /* 先把焦点移出按钮，防止 aria-hidden 警告 */
            btnConfirm.blur();

            try {
                const res = await authFetch('/modify_client_expiry', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ client_name: name, expiry_days: days })
                });
                const data = await res.json();

                loader.style.display = 'none';
                btnConfirm.disabled = false;

                const cls = data.status === 'success' ? 'alert-success' : 'alert-danger';
                msg.innerHTML = `<div class="alert ${cls}">${data.message}</div>`;

                if (data.status === 'success') {
                    setTimeout(() => {
                        modalIns.hide();
                        window.clientAjax.load();
                    }, 500);
                }
            } catch (err) {
                loader.style.display = 'none';
                btnConfirm.disabled = false;
                msg.innerHTML = `<div class="alert alert-danger">${err}</div>`;
            }
        });
    }

    /* 弹窗完全隐藏后清空提示文字 */
    modalEl.addEventListener('hidden.bs.modal', () => {
        qs('#modify-expiry-message').innerHTML = '';
        qs('#modify-expiry-date').value = '';
        qs('#modify-expiryCustom').checked = false;
        qs('#modifyCustomDateWrapper').classList.add('d-none');
    });
}

/* ---------- 修改密码 ---------- */
function bindChangePwd() {
    const form = qs('#change-pwd-form');
    if (!form || form.hasAttribute('data-bound')) return;
    form.setAttribute('data-bound', 'true');

    // 依赖已在 HTML 中先加载 password-confirm.js
    PasswordConfirm(form, {
        passwordSel: '[name="password"]',
        confirmSel: '[name="confirmPassword"]',
        liveCheck: true,
        beforeSubmit: true,
        onSuccess: async () => {
            const fd = new FormData(form);
            try {
                const r = await authFetch('/change_password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        old_pwd: fd.get('old_pwd'),
                        new_pwd: fd.get('password')
                    })
                });
                const d = await r.json();
                showCustomMessage(d.message || '密码修改成功！');
                if (d.status === 'success') {
                    bootstrap.Modal.getInstance(qs('#changePwdModal')).hide();
                    form.reset();
                }
            } catch (err) {
                showCustomMessage(err.message);
            }
        }
    });
}



/* ---------- 客户端搜索和管理（AJAX） ---------- */
(() => {
    let userRole = (document.body.dataset.role || '').toUpperCase();
    const userId = document.body.dataset.userId;

    const input = document.getElementById('client-search');
    const tbody = document.getElementById('client-tbody');
    const paging = document.getElementById('pagination');
    const pageInfo = document.getElementById('page-info');
    const noData = document.getElementById('no-data');
    const PER_PAGE = 10;

    // 去掉 ROLE. 前缀
    if (userRole.startsWith('ROLE.')) userRole = userRole.replace('ROLE.', '');

    // 中文映射
    if (userRole === '管理员'.toUpperCase()) userRole = 'ADMIN';
    if (userRole === '超级管理员'.toUpperCase()) userRole = 'SUPER_ADMIN';
    if (userRole === '普通用户'.toUpperCase()) userRole = 'USER';

    /* 统一渲染表格 */
    function render(data) {
        // 对于普通用户，只显示自己的客户端
        let clientsToRender = data.clients;
        if (userRole === 'USER') {
            clientsToRender = data.clients.filter(c => c.user_id === userId); // 假设后端返回了 user_id
        }

        pageInfo.textContent = data.total_pages > 1 ? `第 ${data.page} 页，共 ${data.total_pages} 页` : '';
        if (!clientsToRender.length) {
            tbody.innerHTML = '';
            paging.innerHTML = '';
            noData.style.display = 'block';
            noData.textContent = data.q ? `未找到与 “${data.q}” 相关的客户端。` : '没有客户端证书。';
            return;
        }
        noData.style.display = 'none';

        tbody.innerHTML = clientsToRender.map((c, idx) => {
            const rowIdx = (data.page - 1) * PER_PAGE + idx + 1;
            const actionButtons = [];

            // 下载配置按钮对所有有权限查看的用户可见
            actionButtons.push(`<a href="/download_client/${c.name}" class="btn btn-sm btn-primary">下载配置</a>`);

            // 管理员和超级管理员可见的管理按钮
            if (userRole === 'SUPER_ADMIN' || userRole === 'ADMIN') {
                actionButtons.push(`<button class="btn btn-sm btn-info modify-expiry-btn"
                                            data-client="${c.name}"
                                            data-bs-toggle="modal"
                                            data-bs-target="#modifyExpiryModal">修改到期</button>`);

                // 禁用/启用按钮
                const actionButton = c.disabled
                    ? `<button class="btn btn-sm btn-success enable-btn" data-client="${c.name}">重新启用</button>`
                    : `<button class="btn btn-sm btn-warning disconnect-btn" data-client="${c.name}">禁用</button>`;
                actionButtons.push(actionButton);
                
                // 撤销按钮
                actionButtons.push(`<button class="btn btn-sm btn-danger revoke-btn" data-client="${c.name}">撤销</button>`);
            }

            return `
                <tr>
                    <td>${rowIdx}</td>
                    <td>${c.name}</td>
                    <td>
                        ${c.online
                            ? `<span class="badge bg-success"><i class="fa fa-circle"></i> 在线</span>
                                ${c.vpn_ip ? `<br><small class="text-success">VPN: ${c.vpn_ip}</small>` : ''}
                                ${c.real_ip ? `<br><small class="text-muted">来源: ${c.real_ip}</small>` : ''}
                                ${c.duration ? `<br><small class="text-info">时长: ${c.duration}</small>` : ''}`
                            : `<span class="badge bg-secondary"><i class="fa fa-circle"></i> 离线</span>`
                        }
                    </td>
                    <td><small class="text-muted">${c.expiry || '未知'}</small></td>
                    <td class="d-flex flex-wrap gap-1">${actionButtons.join('')}</td>
                </tr>`;
        }).join('');

        /* 分页按钮 */
        paging.innerHTML = '';
        if (data.total_pages <= 1) return;

        const make = (page, text, disabled = false, active = false) =>
            `<li class="page-item ${disabled ? 'disabled' : ''} ${active ? 'active' : ''}">
                <a class="page-link" href="#" data-page="${page}">${text}</a>
              </li>`;

        paging.innerHTML += make(data.page - 1, '«', data.page <= 1);
        const start = Math.max(1, data.page - 2);
        const end = Math.min(data.total_pages, data.page + 2);
        if (start > 1) paging.innerHTML += make(1, 1);
        if (start > 2) paging.innerHTML += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
        for (let p = start; p <= end; p++) paging.innerHTML += make(p, p, false, p === data.page);
        if (end < data.total_pages - 1) paging.innerHTML += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
        if (end < data.total_pages) paging.innerHTML += make(data.total_pages, data.total_pages);
        paging.innerHTML += make(data.page + 1, '»', data.page >= data.total_pages);
    }

    /* AJAX 拉数据 */
    function load(page = 1, q = '') {
        authFetch(`/clients/data?page=${page}&q=${encodeURIComponent(q)}`)
            .then(r => r.json())
            .then(render)
            .catch(console.error);
    }

    /* 事件绑定 */
    if (input) {
        input.addEventListener('keydown', e => {
            if (e.key === 'Enter') {
                e.preventDefault();
                load(1, input.value.trim());
            }
        });
    }

    if (paging) {
        paging.addEventListener('click', e => {
            if (e.target.classList.contains('page-link')) {
                e.preventDefault();
                const page = parseInt(e.target.dataset.page);
                if (page) load(page, input.value.trim());
            }
        });
    }

    // 使用事件委托处理所有客户端管理按钮的点击事件
    document.body.addEventListener('click', async e => {
        const targetBtn = e.target.closest('.revoke-btn, .disconnect-btn, .enable-btn, .modify-expiry-btn');
        if (!targetBtn) return;

        const clientName = targetBtn.dataset.client;
        let url = '';
        let confirmMessage = '';

        if (targetBtn.classList.contains('revoke-btn')) {
            url = '/revoke_client';
            confirmMessage = `确定撤销客户端 “${clientName}” 的证书吗？此操作不可恢复！`;
        } else if (targetBtn.classList.contains('disconnect-btn')) {
            url = '/disconnect_client';
            confirmMessage = `确认要禁用客户端 “${clientName}” 吗？`;
        } else if (targetBtn.classList.contains('enable-btn')) {
            url = '/enable_client';
            confirmMessage = `确认要重新启用客户端 “${clientName}” 吗？`;
        } else if (targetBtn.classList.contains('modify-expiry-btn')) {
             // 这种按钮已经有专门的绑定函数来处理 modal，这里只需要返回
             return;
        }

        if (url) {
            showCustomConfirm(confirmMessage, async (confirmed) => {
                if (!confirmed) return;
                try {
                    const res = await authFetch(url, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ client_name: clientName })
                    });
                    const d = await res.json();
                    showCustomMessage(d.message);
                    if (d.status === 'success') {
                        load(); // 操作成功后刷新表格数据
                    }
                } catch (err) {
                    showCustomMessage(err.message);
                }
            });
        }
    });

    // 首次加载
    load();

    // 把 load 暴露到全局，供其他函数调用
    window.clientAjax = { load };
})();


// === 用户管理 JS (仅超级管理员可见) ===
function bindUserManagement() {
    const card = qs('#user-management-card');
    if (!card || card.hasAttribute('data-bound')) return;
    card.setAttribute('data-bound', 'true');

    // 获取 DOM
    const form = qs('#add-user-form');
    const messageDiv = qs('#add-user-message');
    const tbody = qs('#user-table-body');
    const userId = parseInt(document.body.dataset.userId);

    // 绑定添加用户表单
    if (form && !form.hasAttribute('data-bound')) {
        form.setAttribute('data-bound', 'true');
        form.addEventListener('submit', async e => {
            e.preventDefault(); // 阻止默认跳转

            const formData = new FormData(form);
            const payload = {
                username: formData.get('username').trim(),
                email: formData.get('email').trim(),
                password: formData.get('password').trim(),
                role: formData.get('role')
            };

            messageDiv.textContent = '';

            try {
                const res = await authFetch('/add_users', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                messageDiv.textContent = data.message;

                if (data.status === 'success') {
                    form.reset();
                    fetchUsers();
                }
            } catch (err) {
                console.error(err);
                messageDiv.textContent = '添加用户失败，请稍后重试';
            }
        });
    }

    // 获取用户列表
    async function fetchUsers() {
        try {
            const res = await authFetch('/get_users');
            const users = await res.json();
            renderUsers(users);
        } catch (err) {
            console.error(err);
            showCustomMessage('获取用户列表失败', '错误');
        }
    }

    // 渲染用户表格
    function renderUsers(users) {
        tbody.innerHTML = users.map(user => {
            const isSelf = user.id === userId;
            const actions = isSelf ? `<span class="text-muted">不可操作</span>` : `
                <div class="dropdown">
                    <button class="btn btn-sm btn-secondary dropdown-toggle" type="button" data-bs-toggle="dropdown">
                        修改权限
                    </button>
                    <ul class="dropdown-menu">
                        <li><a class="dropdown-item change-role" href="#" data-user-id="${user.id}" data-role="NORMAL">普通用户</a></li>
                        <li><a class="dropdown-item change-role" href="#" data-user-id="${user.id}" data-role="ADMIN">管理员</a></li>
                        <li><a class="dropdown-item change-role" href="#" data-user-id="${user.id}" data-role="SUPER_ADMIN">超级管理员</a></li>
                        <li><hr class="dropdown-divider"></li>
                        <li><a class="dropdown-item reset-pwd" href="#" data-user-id="${user.id}">重置密码</a></li>
                        <li><hr class="dropdown-divider"></li>
                        <li><a class="dropdown-item delete-user" href="#" data-user-id="${user.id}">删除用户</a></li>
                    </ul>
                </div>
            `;
            return `
                <tr>
                    <td>${user.id}</td>
                    <td>${user.username}</td>
                    <td>${user.email}</td>
                    <td>${user.role}</td>
                    <td>${actions}</td>
                </tr>
            `;
        }).join('');
    }

    // 事件委托处理操作按钮
    card.addEventListener('click', async e => {
        const target = e.target.closest('.change-role, .reset-pwd, .delete-user');
        if (!target) return;
        e.preventDefault();

        const uid = target.dataset.userId;

        if (target.classList.contains('change-role')) {
            const newRole = target.dataset.role;
            showCustomConfirm(`确定将用户权限更改为 ${newRole} 吗？`, async confirmed => {
                if (!confirmed) return;
                try {
                    const res = await authFetch('/change_user_role', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ user_id: uid, new_role: newRole })
                    });
                    const data = await res.json();
                    showCustomMessage(data.message);
                    if (data.status === 'success') fetchUsers();
                } catch (err) {
                    console.error(err);
                    showCustomMessage('修改权限失败');
                }
            });
        } else if (target.classList.contains('reset-pwd')) {
            showCustomConfirm('确定重置该用户密码吗？', async confirmed => {
                if (!confirmed) return;
                try {
                    const res = await authFetch('/reset_user_password', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ user_id: uid })
                    });
                    const data = await res.json();
                    showCustomMessage(data.message);
                } catch (err) {
                    console.error(err);
                    showCustomMessage('重置密码失败');
                }
            });
        } else if (target.classList.contains('delete-user')) {
            showCustomConfirm('确定删除该用户吗？此操作不可恢复！', async confirmed => {
                if (!confirmed) return;
                try {
                    const res = await authFetch('/delete_user', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ user_id: uid })
                    });
                    const data = await res.json();
                    showCustomMessage(data.message);
                    if (data.status === 'success') fetchUsers();
                } catch (err) {
                    console.error(err);
                    showCustomMessage('删除用户失败');
                }
            });
        }
    });

    // 页面加载后拉取一次用户列表
    fetchUsers();
}

/* ---------- 统一绑定入口 ---------- */
function bindAll() {
    bindChangePwd();
    const role = document.body.dataset.role;
    if (role === 'SUPER_ADMIN') { bindInstall(); bindUninstall(); }
    if (role === 'SUPER_ADMIN' || role === 'ADMIN') { bindAddClient(); bindModifyExpiry(); }
}

/* ---------- 初始化和权限控制 ---------- */
document.addEventListener('DOMContentLoaded', () => {
    // 获取当前用户角色
    const userRole = document.body.dataset.role;

    // 根据角色显示/隐藏功能
    const roleMap = {
        'SUPER_ADMIN': ['install-btn', 'uninstall-btn', 'add-client-card', 'clients-card', 'user-management-card'],
        'ADMIN': ['add-client-card', 'clients-card'],
        'USER': ['clients-card'],
    };

    // 默认隐藏所有卡片
    qsa('.card-main').forEach(card => card.classList.add('d-none'));

    // 显示当前角色可见的卡片
    if (roleMap[userRole]) {
        roleMap[userRole].forEach(id => {
            const element = qs('#' + id);
            if (element) element.classList.remove('d-none');
        });
    }

    // 设置日期输入框最小值
    const dateInput = qs('#expiry_date');
    if (dateInput) {
        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        dateInput.min = tomorrow.toISOString().split('T')[0];
    }

    // 绑定所有事件
    bindAll();

    // 启动自动刷新
    startAutoRefresh();

    bindUserManagement();
    // === SUPER_ADMIN 额外绑定用户管理 ===
    if (userRole === 'SUPER_ADMIN') {
        bindUserManagement(); // 内部已经包含 fetchUsers + bindAddUserForm
    }
});