/* ---------- 通用工具 ---------- */
const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

let autoRefreshInterval;

/* ---------- 页面局部刷新 ---------- */
function refreshPage () {
    fetch('/')
        .then(r => r.text())
        .then(html => {
            const p = new DOMParser(), doc = p.parseFromString(html, 'text/html');
            const scroll = window.scrollY;

            // 更新状态卡片
            const curStatus = $('.card:first-child .card-body');
            const newStatus = doc.querySelector('.card:first-child .card-body');
            if (curStatus && newStatus) curStatus.innerHTML = newStatus.innerHTML;

            // 更新客户端管理
            const curClient = $('.col-md-6:last-child .card-body');
            const newClient = doc.querySelector('.col-md-6:last-child .card-body');
            if (curClient && newClient) curClient.innerHTML = newClient.innerHTML;

            window.scrollTo(0, scroll);
            bindAll();
        })
        .catch(console.error);
}

function startAutoRefresh () {
    autoRefreshInterval = setInterval(refreshPage, 5000);
}

// 统一绑定
function bindAll () {
    bindInstall();
    bindAddClient();
    bindRevoke();
    bindDownload();
    bindDisconnect();
    bindEnable();
    bindModifyExpiry();
    bindUninstall();
}

/* ---------- 有效期单选按钮联动 ---------- */
function toggleCustomDate () {
    const customChecked = $('#expiryCustom').checked;
    $('#customDateWrapper').style.display = customChecked ? 'block' : 'none';
}

/* ---------- 安装 ---------- */
function bindInstall () {
    document.addEventListener('click', e => {
        if (e.target.id === 'install-btn') {
            e.preventDefault();
            const l = $('#install-loader'), m = $('#status-message');
            l.style.display = 'block';
            m.classList.remove('d-none'); m.textContent = '正在安装OpenVPN...';
            fetch('/install', {method: 'POST'})
                .then(r => r.json())
                .then(d => {
                    l.style.display = 'none';
                    m.textContent = d.message;
                    m.className = d.status === 'success' ? 'alert alert-success' : 'alert alert-danger';
                    if (d.status === 'success') setTimeout(() => location.reload(), 5000);
                })
                .catch(err => {
                    l.style.display = 'none';
                    m.textContent = '安装失败: ' + err.message;
                    m.className = 'alert alert-danger';
                });
        }
    });
}

/* ---------- 添加客户端 ---------- */
function bindAddClient () {
    const form = $('#add-client-form');
    if (!form || form.hasAttribute('data-bound')) return;
    form.setAttribute('data-bound', 'true');

    // 单选按钮联动
    $$('input[name="expiry_choice"]').forEach(r => r.addEventListener('change', toggleCustomDate));
    toggleCustomDate(); // 初始

    form.addEventListener('submit', e => {
        e.preventDefault();
        const loader = $('#add-client-loader');
        const msgDiv = $('#add-client-message');
        const nameVal = $('#client_name').value.trim();
        if (!nameVal) { msgDiv.innerHTML = '<div class="alert alert-danger">请输入客户端名称</div>'; return; }

        loader.style.display = 'block';

        // 有效期计算
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

        const fd = new FormData();
        fd.append('client_name', nameVal);
        fd.append('expiry_days', expiryDays);

        fetch('/add_client', {method: 'POST', body: fd})
            .then(r => r.json())
            .then(data => {
                loader.style.display = 'none';
                const cls = data.status === 'success' ? 'alert-success' : 'alert-danger';
                msgDiv.innerHTML = `<div class="alert ${cls}">${data.message}</div>`;
                if (data.status === 'success') {
                    form.reset(); toggleCustomDate(); setTimeout(refreshPage, 2000);
                }
            })
            .catch(err => {
                loader.style.display = 'none';
                msgDiv.innerHTML = `<div class="alert alert-danger">${err}</div>`;
            });
    });
}

/* ---------- 撤销 ---------- */
function bindRevoke () {
    $$('.revoke-btn:not([data-bound])').forEach(btn => {
        btn.setAttribute('data-bound', 'true');
        btn.addEventListener('click', () => {
            const name = btn.dataset.client;
            if (!confirm(`确定要撤销客户端 “${name}” 的证书吗？`)) return;
            const l = $('#revoke-loader'), m = $('#revoke-message');
            l.style.display = 'block';
            const fd = new FormData(); fd.append('client_name', name);
            fetch('/revoke_client', {method: 'POST', body: fd})
                .then(r => r.json())
                .then(d => {
                    l.style.display = 'none';
                    const cls = d.status === 'success' ? 'alert-success' : 'alert-danger';
                    m.innerHTML = `<div class="alert ${cls}">${d.message}</div>`;
                    if (d.status === 'success') setTimeout(refreshPage, 2000);
                })
                .catch(err => {
                    l.style.display = 'none';
                    m.innerHTML = `<div class="alert alert-danger">${err}</div>`;
                });
        });
    });
}

/* ---------- 下载 ---------- */
function bindDownload () {
    $$('.download-btn:not([data-bound])').forEach(btn => {
        btn.setAttribute('data-bound', 'true');
        btn.addEventListener('click', () => location.href = `/download_client/${btn.dataset.client}`);
    });
}

/* ---------- 禁用 / 启用 ---------- */
function bindDisconnect () {
    $$('.disconnect-btn:not([data-bound])').forEach(btn => {
        btn.setAttribute('data-bound', 'true');
        btn.addEventListener('click', () => {
            if (!confirm(`确认要禁用客户端 “${btn.dataset.client}” 吗？`)) return;
            fetch('/disconnect_client', {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: `client_name=${encodeURIComponent(btn.dataset.client)}`
            })
                .then(r => r.json())
                .then(d => { alert(d.message); if (d.status === 'success') refreshPage(); })
                .catch(console.error);
        });
    });
}
function bindEnable () {
    $$('.enable-btn:not([data-bound])').forEach(btn => {
        btn.setAttribute('data-bound', 'true');
        btn.addEventListener('click', () => {
            if (!confirm(`确认要重新启用客户端 “${btn.dataset.client}” 吗？`)) return;
            fetch('/enable_client', {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: `client_name=${encodeURIComponent(btn.dataset.client)}`
            })
                .then(r => r.json())
                .then(d => { alert(d.message); if (d.status === 'success') refreshPage(); })
                .catch(console.error);
        });
    });
}

/* ---------- 修改到期 ---------- */
function bindModifyExpiry () {
    $$('.modify-expiry-btn:not([data-bound])').forEach(btn => {
        btn.setAttribute('data-bound', 'true');
        btn.addEventListener('click', () => {
            $('#modify-client-name').value = btn.dataset.client;
            const modal = new bootstrap.Modal($('#modifyExpiryModal'));
            modal.show();
        });
    });
    const btn = $('#confirm-modify-expiry');
    if (btn && !btn.hasAttribute('data-bound')) {
        btn.setAttribute('data-bound', 'true');
        btn.addEventListener('click', () => {
            const name = $('#modify-client-name').value;
            const type = $('#modify-expiry-type').value;
            let days;
            if (type === 'preset') {
                days = $('#modify-expiry-days').value;
            } else {
                const d = $('#modify-expiry-date').value;
                if (!d) { $('#modify-expiry-message').innerHTML='<div class="alert alert-danger">请选择到期日期</div>'; return; }
                days = Math.ceil((new Date(d) - new Date()) / 86400000).toString();
            }
            const l = $('#modify-expiry-loader'), m = $('#modify-expiry-message');
            l.style.display = 'inline-block'; btn.disabled = true;
            const fd = new FormData(); fd.append('client_name', name); fd.append('expiry_days', days);
            fetch('/modify_client_expiry', {method: 'POST', body: fd})
                .then(r => r.json())
                .then(d => {
                    l.style.display = 'none'; btn.disabled = false;
                    const cls = d.status === 'success' ? 'alert-success' : 'alert-danger';
                    m.innerHTML = `<div class="alert ${cls}">${d.message}</div>`;
                    if (d.status === 'success') setTimeout(() => { bootstrap.Modal.getInstance($('#modifyExpiryModal')).hide(); refreshPage(); }, 2000);
                })
                .catch(err => {
                    l.style.display = 'none'; btn.disabled = false;
                    m.innerHTML = `<div class="alert alert-danger">${err}</div>`;
                });
        });
    }
}

/* ---------- 卸载 ---------- */
function bindUninstall () {
    const btn = $('#uninstall-btn');
    if (btn && !btn.hasAttribute('data-bound')) {
        btn.setAttribute('data-bound', 'true');
        btn.addEventListener('click', () => {
            if (!confirm('确定要卸载OpenVPN吗? 所有客户端配置将被删除!')) return;
            const l = $('#uninstall-loader'), m = $('#status-message');
            l.style.display = 'block';
            m.classList.remove('d-none'); m.textContent = '正在卸载OpenVPN...';
            fetch('/uninstall', {method: 'POST'})
                .then(r => r.json())
                .then(d => {
                    l.style.display = 'none';
                    m.textContent = d.message;
                    m.className = d.status === 'success' ? 'alert alert-success' : 'alert alert-danger';
                    if (d.status === 'success') setTimeout(() => location.reload(), 3000);
                })
                .catch(err => {
                    l.style.display = 'none';
                    m.textContent = '卸载失败: ' + err.message;
                    m.className = 'alert alert-danger';
                });
        });
    }
}

/* ---------- 初始化 ---------- */
document.addEventListener('DOMContentLoaded', () => {
    const tomorrow = new Date(); tomorrow.setDate(tomorrow.getDate() + 1);
    const dateInput = $('#expiry_date');
    if (dateInput) dateInput.min = tomorrow.toISOString().split('T')[0];
    bindAll();
    startAutoRefresh();
});
