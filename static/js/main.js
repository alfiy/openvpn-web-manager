/* ---------- 简写工具 ---------- */
const $  = (sel, ctx = document) => ctx.querySelector(sel);
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

            const curClient = $('.col-md-6:last-child .card-body');
            const newClient = doc.querySelector('.col-md-6:last-child .card-body');
            if (curClient && newClient) curClient.innerHTML = newClient.innerHTML;

            window.scrollTo(0, scroll);
            bindAll();
        })
        .catch(console.error);
}

function startAutoRefresh() {
    autoRefreshInterval = setInterval(refreshPage, 5000);
}

/* 统一绑定 */
function bindAll() {
    bindInstall();
    bindAddClient();
    bindDownload();
    bindDisconnect();
    bindEnable();
    bindModifyExpiry();
    bindUninstall();
    bindChangePwd();
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
        const sel  = $('#install-ip-select');
        const ip   = sel.value || $('#install-ip-input').value.trim();
        if (!Number.isInteger(port) || port < 1025 || port > 65534) { alert('端口号必须在 1025-65534 之间'); return; }
        if (!ip) { alert('请选择或输入服务器 IP'); return; }

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
            if (data.status === 'success') setTimeout(refreshPage, 1200);
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

/* ---------- 添加客户端 ---------- */
function bindAddClient() {
    const form = $('#add-client-form');
    if (!form || form.hasAttribute('data-bound')) return;
    form.setAttribute('data-bound', 'true');

    $$('input[name="expiry_choice"]').forEach(r => r.addEventListener('change', toggleCustomDate));
    toggleCustomDate();

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
                setTimeout(refreshPage, 2200);
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

    const l = $('#revoke-loader') || (() => {
        const loader = document.createElement('div');
        loader.id = 'revoke-loader';
        loader.style.display = 'none';
        document.body.appendChild(loader);
        return loader;
    })();
    const m = $('#revoke-message') || (() => {
        const msg = document.createElement('div');
        msg.id = 'revoke-message';
        document.body.appendChild(msg);
        return msg;
    })();

    l.style.display = 'block';
    m.innerHTML = '';

    authFetch('/revoke_client', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_name: name })
    })
    .then(r => r.json())
    .then(d => {
        l.style.display = 'none';
        const cls = d.status === 'success' ? 'alert-success' : 'alert-danger';
        m.innerHTML = `<div class="alert ${cls}">${d.message}</div>`;
        if (d.status === 'success') setTimeout(refreshPage, 1500);
    })
    .catch(err => {
        l.style.display = 'none';
        m.innerHTML = `<div class="alert alert-danger">网络错误：${err}</div>`;
    });
});

/* ---------- 下载（可直接走超链接，因此仅在你需要按钮时使用） ---------- */
function bindDownload() {
    $$('.download-btn:not([data-bound])').forEach(btn => {
        btn.setAttribute('data-bound', 'true');
        btn.addEventListener('click', () => location.href = `/download_client/${btn.dataset.client}`);
    });
}

/* ---------- 禁用 / 启用 ---------- */
function bindDisconnect() {
    $$('.disconnect-btn:not([data-bound])').forEach(btn => {
        btn.setAttribute('data-bound', 'true');
        btn.addEventListener('click', () => {
            if (!confirm(`确认要禁用客户端 “${btn.dataset.client}” 吗？`)) return;
            authFetch('/disconnect_client', {
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
    const modalEl  = $('#modifyExpiryModal');
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
            const msg    = $('#modify-expiry-message');
            loader.style.display = 'inline-block';
            btnConfirm.disabled  = true;

            /* 先把焦点移出按钮，防止 aria-hidden 警告 */
            btnConfirm.blur();

            try {
                const res = await authFetch('/modify_client_expiry', {
                    method : 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body   : JSON.stringify({ client_name: name, expiry_days: days })
                });
                const data = await res.json();

                loader.style.display = 'none';
                btnConfirm.disabled  = false;

                const cls = data.status === 'success' ? 'alert-success' : 'alert-danger';
                msg.innerHTML = `<div class="alert ${cls}">${data.message}</div>`;

                if (data.status === 'success') {
                    /* 延迟 500ms 再关闭，让消息能被看到，也确保焦点已不在按钮上 */
                    setTimeout(() => {
                        modalIns.hide();
                        refreshPage();
                    }, 500);
                }
            } catch (err) {
                loader.style.display = 'none';
                btnConfirm.disabled  = false;
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
        passwordSel  : '[name="password"]',
        confirmSel   : '[name="confirmPassword"]',
        liveCheck    : true,
        beforeSubmit : true,
        onSuccess    : () => {
            const fd = new FormData(form);
            authFetch('/change_password', {
                method : 'POST',
                headers: { 'Content-Type': 'application/json' },
                body   : JSON.stringify({
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
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const dateInput = $('#expiry_date');
    if (dateInput) dateInput.min = tomorrow.toISOString().split('T')[0];

    bindAll();
    startAutoRefresh();

    $('#reset-btn')?.addEventListener('click', () => $('#client_name').value = '');
});
