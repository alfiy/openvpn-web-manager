/* ---------- 简写工具 ---------- */
const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

/* ---------- 带认证 + CSRF 的 fetch ---------- */
function authFetch(url, opts = {}) {
    const headers = new Headers(opts.headers || {});
    // 统一自动加上 CSRF 头（即便 GET 也无妨）
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && !headers.has('X-CSRFToken')) {
        headers.set('X-CSRFToken', meta.content);
    }
    return fetch(url, { ...opts, headers, credentials: 'same-origin' })
        .then(res => {
            if (res.status === 401) {
                location.href = '/login';
                throw new Error('未登录');
            }
            return res;
        });
}

// 定义全局变量，用于存储定时器ID，以便后续可以清除
let autoRefreshInterval;

/* ---------- 页面局部刷新 ---------- */
function refreshPage() {
    authFetch('/')
        .then(r => r.text())
        .then(html => {
            const p = new DOMParser(), doc = p.parseFromString(html, 'text/html');
            const scroll = window.scrollY;

            const curStatus = $('.card:first-child .card-body');
            const newStatus = doc.querySelector('.card:first-child .card-body');
            if (curStatus && newStatus) curStatus.innerHTML = newStatus.innerHTML;

            // const curClient = $('.col-md-6:last-child .card-body');
            // const newClient = doc.querySelector('.col-md-6:last-child .card-body');
            // if (curClient && newClient) curClient.innerHTML = newClient.innerHTML;

            window.scrollTo(0, scroll);
            bindAll();
        })
        .catch(console.error);
}

// --- 解决 Uncaught ReferenceError 的关键部分 ---

/* ---------- 自动刷新逻辑 ---------- */
function startAutoRefresh() {
    // 设置一个定时器，每隔 5 秒刷新一次页面
    autoRefreshInterval = setInterval(() => {
        refreshPage();
        // 刷新客户端列表，因为客户端列表是独立的 AJAX 模块
        if (window.clientAjax && window.clientAjax.load) {
            window.clientAjax.load();
        }
    }, 5000);
}

function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
    }
}

/* 统一绑定 */
function bindAll() {
    bindInstall();
    bindAddClient();
    bindDownload();
    bindModifyExpiry();
    bindUninstall();
    bindChangePwd();
    // 💡 你之前没有 `bindEnable`，所以这里也补上
    bindEnable(); 
}

/* ---------- 有效期单选按钮联动 ---------- */
function toggleCustomDate() {
    const customChecked = $('#expiryCustom')?.checked;
    const wrapper = $('#customDateWrapper');
    if (wrapper) wrapper.classList.toggle('d-none', !customChecked);
}

/* ---------- 安装 ---------- */
function bindInstall() {
    const btn = $('#install-btn');
    if (!btn || btn.hasAttribute('data-bound')) return;
    btn.setAttribute('data-bound', 'true');

    const modalEl = $('#installModal');
    const modal = modalEl ? new bootstrap.Modal(modalEl) : null;

    // 添加IP地址验证函数
    function isValidIP(ip) {
        const ipRegex = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
        return ipRegex.test(ip);
    }

    btn.addEventListener('click', async () => {
        if (!modal) return;
        try {
            const res = await authFetch('/get_ip_list');
            const list = await res.json();
            const sel = $('#install-ip-select');
            sel.innerHTML = '';
            list.forEach(ip => {
                const opt = document.createElement('option');
                opt.value = opt.textContent = ip;
                sel.appendChild(opt);
            });
            const manual = document.createElement('option');
            manual.value = '';
            manual.textContent = '手动输入…';
            sel.appendChild(manual);
        } catch {
            const sel = $('#install-ip-select');
            sel.innerHTML = '<option value="">手动输入…</option>';
            $('#manual-ip-wrapper').style.display = 'block';
        }
        modal.show();
    });

    $('#install-ip-select')?.addEventListener('change', function () {
        const wrapper = $('#manual-ip-wrapper');
        if (wrapper) wrapper.style.display = this.value ? 'none' : 'block';
    });

    $('#confirm-install')?.addEventListener('click', async () => {
        const port = Number($('#install-port').value);
        const sel = $('#install-ip-select');
        const ip = sel.value || $('#install-ip-input').value.trim();

        if (!Number.isInteger(port) || port < 1025 || port > 65534) {
            alert('端口号必须在 1025-65534 之间');
            return;
        }

        if (!ip) {
            alert('请选择或输入服务器 IP');
            // 改进：当没有输入IP时，将焦点设置到IP输入框
            $('#install-ip-input').focus();
            return;
        }

        // 调用新增的IP验证函数
        if (!sel.value && !isValidIP(ip)) {
            alert('您输入的IP地址格式不正确，请重新输入');
            // 改进：当IP格式不正确时，将焦点设置到IP输入框
            $('#install-ip-input').focus();
            return;
        }

        modal?.hide();
        $('#install-loader').style.display = 'block';
        const m = $('#status-message');
        m.classList.remove('d-none'); m.textContent = '正在安装 OpenVPN...';

        try {
            const res = await authFetch('/install', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ port, ip })
            });
            const data = await res.json();
            $('#install-loader').style.display = 'none';
            m.textContent = data.message;
            m.className = data.status === 'success' ? 'alert alert-success' : 'alert alert-danger';
            if (data.status === 'success') {
                setTimeout(() => {
                    location.href = data.redirect + '?ts=' + Date.now();
                }, 1000);
            }

        } catch (err) {
            $('#install-loader').style.display = 'none';
            m.textContent = '安装失败: ' + err.message;
            m.className = 'alert alert-danger';
        }
    });

    modalEl?.addEventListener('hide.bs.modal', () => {
        const wrap = $('#manual-ip-wrapper');
        if (wrap) wrap.style.display = 'none';
    });
}

/**
 * 验证IPv4地址的合法性
 * @param {string} ip - 需要验证的IP地址字符串
 * @returns {boolean} - 如果IP地址合法返回true，否则返回false
 */
function isValidIP(ip) {
    const regex = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
    return regex.test(ip);
}

/* ---------- 添加客户端 ---------- */
function bindAddClient() {
    const form = $('#add-client-form');
    if (!form || form.hasAttribute('data-bound')) return;
    form.setAttribute('data-bound', 'true');

    $$('input[name="expiry_choice"]').forEach(r => r.addEventListener('change', toggleCustomDate));
    toggleCustomDate();

    // 💡 修复：将重置按钮的绑定逻辑移到此处，确保在每次刷新时都能正确绑定
    const resetButton = $('#reset-btn');
    if (resetButton) {
        resetButton.addEventListener('click', () => {
            const clientNameInput = $('#client_name');
            if (clientNameInput) {
                clientNameInput.value = '';
            }
        });
    }

    form.addEventListener('submit', e => {
        e.preventDefault();
        const loader = $('#add-client-loader');
        const msgDiv = $('#add-client-message');
        const nameVal = $('#client_name').value.trim();
        if (!nameVal) { msgDiv.innerHTML = '<div class="alert alert-danger">请输入客户端名称</div>'; return; }

        loader.style.display = 'block';

        let expiryDays;
        const choice = $('input[name="expiry_choice"]:checked').value;
        if (choice === 'custom') {
            const d = $('#expiry_date').value;
            if (!d) { msgDiv.innerHTML = '<div class="alert alert-danger">请选择到期日期</div>'; loader.style.display = 'none'; return; }
            const diff = Math.ceil((new Date(d) - new Date()) / 86400000);
            if (diff <= 0) { msgDiv.innerHTML = '<div class="alert alert-danger">到期日期必须是将来的日期</div>'; loader.style.display = 'none'; return; }
            expiryDays = diff.toString();
        } else {
            expiryDays = choice;
        }

        authFetch('/add_client', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ client_name: nameVal, expiry_days: expiryDays })
        })
            .then(r => r.json())
            .then(data => {
                loader.style.display = 'none';
                const cls = data.status === 'success' ? 'alert-success' : 'alert-danger';
                msgDiv.innerHTML = `<div class="alert ${cls}">${data.message}</div>`;
                if (data.status === 'success') {
                    form.reset();
                    toggleCustomDate();
                    setTimeout(() => msgDiv.innerHTML = '', 2000);
                    window.clientAjax.load();
                }
            })
            .catch(err => {
                loader.style.display = 'none';
                msgDiv.innerHTML = `<div class="alert alert-danger">${err}</div>`;
            });
    });
}

/* ---------- 撤销客户端（事件委托） ---------- */
document.addEventListener('click', e => {
    if (!e.target.classList.contains('revoke-btn')) return;
    const name = e.target.dataset.client;
    if (!confirm(`确定撤销客户端 “${name}” 的证书吗？此操作不可恢复！`)) return;

    const msg = $('#client-revoke-msg');
    msg.innerHTML = '<div class="spinner-border spinner-border-sm"></div> 撤销中...';

    authFetch('/revoke_client', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_name: name })
    })
        .then(r => r.json())
        .then(d => {
            const cls = d.status === 'success' ? 'alert-success' : 'alert-danger';
            msg.innerHTML = `<div class="alert ${cls}">${d.message}</div>`;
            if (d.status === 'success') {
                toggleCustomDate();
                window.clientAjax.load();
            }
            // 成功或失败的提示都在 5 秒后自动消失
            setTimeout(() => msg.innerHTML = '', 5000);
        })
        .catch(err => {
            msg.innerHTML = `<div class="alert alert-danger">${err}</div>`;
            // 确保错误提示也能自动消失
            setTimeout(() => msg.innerHTML = '', 5000);
        });
});

/* ---------- 下载（可直接走超链接，因此仅在你需要按钮时使用） ---------- */
function bindDownload() {
    $$('.download-btn:not([data-bound])').forEach(btn => {
        btn.setAttribute('data-bound', 'true');
        btn.addEventListener('click', () => location.href = `/download_client/${btn.dataset.client}`);
    });
}

function bindEnable() {
    $$('.enable-btn:not([data-bound])').forEach(btn => {
        btn.setAttribute('data-bound', 'true');
        btn.addEventListener('click', () => {
            if (!confirm(`确认要重新启用客户端 “${btn.dataset.client}” 吗？`)) return;
            authFetch('/enable_client', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ client_name: btn.dataset.client })
            })
                .then(r => r.json())
                .then(d => { alert(d.message); if (d.status === 'success') refreshPage(); })
                .catch(console.error);
        });
    });
}

/* ---------- 修改到期 ---------- */
function bindModifyExpiry() {
    /* 全局只创建一个实例，避免重复 new */
    const modalEl = $('#modifyExpiryModal');
    const modalIns = bootstrap.Modal.getOrCreateInstance(modalEl);

    /* 事件委托：打开弹窗 */
    document.body.addEventListener('click', e => {
        if (e.target.classList.contains('modify-expiry-btn')) {
            $('#modify-client-name').value = e.target.dataset.client;
            modalIns.show();
        }
    });
    /* 确认按钮只绑一次 */
    const btnConfirm = $('#confirm-modify-expiry');
    if (btnConfirm && !btnConfirm.hasAttribute('data-bound')) {
        btnConfirm.setAttribute('data-bound', 'true');

        btnConfirm.addEventListener('click', async () => {
            const name = $('#modify-client-name').value;

            let days;
            if ($('#modify-expiryCustom').checked) {
                const d = $('#modify-expiry-date').value;
                if (!d) {
                    $('#modify-expiry-message').innerHTML =
                        '<div class="alert alert-danger">请选择到期日期</div>';
                    return;
                }
                days = Math.ceil((new Date(d) - new Date()) / 86400000).toString();
            } else {
                const selected = document.querySelector('input[name="modify_expiry_choice"]:checked');
                days = selected ? selected.value : '30';
            }

            const loader = $('#modify-expiry-loader');
            const msg = $('#modify-expiry-message');
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
                    /* 延迟 500ms 再关闭，让消息能被看到，也确保焦点已不在按钮上 */
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

        /* 自定义日期联动 */
        $$('input[name="modify_expiry_choice"]').forEach(radio => {
            radio.addEventListener('change', () => {
                $('#modifyCustomDateWrapper')
                    .classList.toggle('d-none', !$('#modify-expiryCustom').checked);
            });
        });

        /* 弹窗完全隐藏后清空提示文字 */
        modalEl.addEventListener('hidden.bs.modal', () => {
            $('#modify-expiry-message').innerHTML = '';
            $('#modify-expiry-date').value = '';
            $('#modify-expiryCustom').checked = false;
            $('#modifyCustomDateWrapper').classList.add('d-none');
        });
    }
}

/* ---------- 卸载 ---------- */
function bindUninstall() {
    const btn = $('#uninstall-btn');
    if (btn && !btn.hasAttribute('data-bound')) {
        btn.setAttribute('data-bound', 'true');
        btn.addEventListener('click', () => {
            if (!confirm('确定要卸载OpenVPN吗? 所有客户端配置将被删除!')) return;
            const l = $('#uninstall-loader'), m = $('#status-message');
            l.style.display = 'block';
            m.classList.remove('d-none'); m.textContent = '正在卸载OpenVPN...';
            authFetch('/uninstall', { method: 'POST' })
                .then(r => r.json())
                .then(d => {
                    l.style.display = 'none';
                    m.textContent = d.message;
                    m.className = d.status === 'success' ? 'alert alert-success' : 'alert alert-danger';
                    if (d.status === 'success') setTimeout(refreshPage, 1200);
                })
                .catch(err => {
                    l.style.display = 'none';
                    m.textContent = '卸载失败: ' + err.message;
                    m.className = 'alert alert-danger';
                });
        });
    }
}

/* ---------- 修改密码 ---------- */
function bindChangePwd() {
    const form = $('#change-pwd-form');
    if (!form || form.hasAttribute('data-bound')) return;
    form.setAttribute('data-bound', 'true');

    // 依赖已在 HTML 中先加载 password-confirm.js
    PasswordConfirm(form, {
        passwordSel: '[name="password"]',
        confirmSel: '[name="confirmPassword"]',
        liveCheck: true,
        beforeSubmit: true,
        onSuccess: () => {
            const fd = new FormData(form);
            authFetch('/change_password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    old_pwd: fd.get('old_pwd'),
                    new_pwd: fd.get('password')
                })
            })
                .then(r => r.json())
                .then(d => {
                    alert(d.message || '密码修改成功！');
                    if (d.status === 'success') {
                        bootstrap.Modal.getInstance($('#changePwdModal')).hide();
                        form.reset();
                    }
                })
                .catch(alert);
        }
    });
}

/* ---------- 初始化 ---------- */
document.addEventListener('DOMContentLoaded', () => {
    // 💡 确保 dateInput 元素存在
    const dateInput = $('#expiry_date');
    if (dateInput) {
        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        dateInput.min = tomorrow.toISOString().split('T')[0];
    }

    bindAll();
    startAutoRefresh(); // 现在这个函数已经定义了，不会报错了
});

/* ---------- 客户端搜索 ---------- */
(() => {
    const input = document.getElementById('client-search');
    const tbody = document.getElementById('client-tbody');
    const paging = document.getElementById('pagination');
    const pageInfo = document.getElementById('page-info');
    const noData = document.getElementById('no-data');
    const PER_PAGE = 10;

    /* 统一渲染 */
    function render(data) {
        pageInfo.textContent = data.total_pages > 1 ? `第 ${data.page} 页，共 ${data.total_pages} 页` : '';
        if (!data.clients.length) {
            tbody.innerHTML = '';
            paging.innerHTML = '';
            noData.style.display = 'block';
            noData.textContent = data.q ? `未找到与 “${data.q}” 相关的客户端。` : '没有客户端证书。';
            return;
        }
        noData.style.display = 'none';

        tbody.innerHTML = data.clients.map((c, idx) => {
            const rowIdx = (data.page - 1) * PER_PAGE + idx + 1;

            // 根据客户端状态动态生成按钮
            let actionButtonsHTML = '';
            if (c.disabled) {
                // 如果客户端被禁用，只显示“重新启用”按钮
                actionButtonsHTML = `
                    <button class="btn btn-sm btn-success enable-btn" data-client="${c.name}">重新启用</button>
                `;
            } else {
                // 如果客户端未被禁用，同时显示“下载、修改、禁用和撤销”按钮
                actionButtonsHTML = `
                    <a href="/download_client/${c.name}" class="btn btn-sm btn-primary">下载配置</a>
                    <button class="btn btn-sm btn-info modify-expiry-btn"
                            data-client="${c.name}"
                            data-bs-toggle="modal"
                            data-bs-target="#modifyExpiryModal">修改到期</button>
                    <button class="btn btn-sm btn-warning disconnect-btn" data-client="${c.name}">禁用</button>
                    <button class="btn btn-sm btn-danger revoke-btn" data-client="${c.name}">撤销</button>
                `;
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
                    <td class="d-flex flex-wrap gap-1">
                    ${actionButtonsHTML}
                    </td>
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
        fetch(`/clients/data?page=${page}&q=${encodeURIComponent(q)}`)
            .then(r => r.json())
            .then(render)
            .catch(console.error);
    }

    /* 事件 */
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

    // 💡 修复：使用事件委托处理禁用和启用按钮的点击事件
    if (tbody) {
        tbody.addEventListener('click', e => {
            const disconnectBtn = e.target.closest('.disconnect-btn');
            const enableBtn = e.target.closest('.enable-btn');
            let url = '';
            let clientName = '';
            let confirmationMessage = '';

            if (disconnectBtn) {
                url = '/disconnect_client';
                clientName = disconnectBtn.dataset.client;
                confirmationMessage = `确认要禁用客户端 “${clientName}” 吗？`;
            } else if (enableBtn) {
                url = '/enable_client'; // 假设您有这个后端端点
                clientName = enableBtn.dataset.client;
                confirmationMessage = `确认要重新启用客户端 “${clientName}” 吗？`;
            } else {
                return; // 如果点击的不是这两个按钮，则返回
            }

            if (!confirm(confirmationMessage)) return;

            authFetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ client_name: clientName })
            })
                .then(r => r.json())
                .then(d => {
                    alert(d.message);
                    if (d.status === 'success') {
                        load(); // 操作成功后刷新页面以更新按钮状态
                    }
                })
                .catch(console.error);
        });
    }

    /* 首次加载 */
    load();

    /* 把 load 暴露到全局，供撤销按钮调用 */
    window.clientAjax = { load };
})();