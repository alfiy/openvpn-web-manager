/* ---------- 通用工具 ---------- */
const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

/* ---------- 认证工具 ---------- */
function authFetch(url, opts = {}) {
    return fetch(url, { ...opts, credentials: 'same-origin' })
        .then(res => {
            if (res.status === 401) {
                location.href = '/login';          // 未登录直接跳转
                throw new Error('未登录');
            }
            return res;
        });
}

let autoRefreshInterval;

/* ---------- 页面局部刷新 ---------- */
function refreshPage () {
    authFetch('/')
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
    bindChangePwd();
}

/* ---------- 有效期单选按钮联动 ---------- */
function toggleCustomDate () {
    const customChecked = $('#expiryCustom').checked;
    $('#customDateWrapper').style.display = customChecked ? 'block' : 'none';
}



/* ---------- 安装 ---------- */
function bindInstall () {
    const btn = document.getElementById('install-btn');
    if (!btn || btn.hasAttribute('data-bound')) return;
    btn.setAttribute('data-bound', 'true');

    const modal = new bootstrap.Modal('#installModal');

    // 按钮打开
    btn.addEventListener('click', async () => {
        // 拉取 IP
        try {
            const res = await authFetch('/get_ip_list');
            const list = await res.json();
            const sel = document.getElementById('install-ip-select');
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
            // 失败时只允许手动输入
            const sel = document.getElementById('install-ip-select');
            sel.innerHTML = '<option value="">手动输入…</option>';
            document.getElementById('manual-ip-wrapper').style.display = 'block';
        }
        modal.show();
    });

    // 下拉切换
    document.getElementById('install-ip-select').addEventListener('change', function () {
        const wrapper = document.getElementById('manual-ip-wrapper');
        wrapper.style.display = this.value ? 'none' : 'block';
    });

    // 确认安装
    document.getElementById('confirm-install').addEventListener('click', async () => {
        const port = Number(document.getElementById('install-port').value);
        const sel  = document.getElementById('install-ip-select');
        const ip   = sel.value || document.getElementById('install-ip-input').value.trim();
        if (!Number.isInteger(port) || port < 1025 || port > 65534) {
            alert('端口号必须在 1025-65534 之间'); return;
        }
        if (!ip) {
            alert('请选择或输入服务器 IP'); return;
        }

        modal.hide(); // 关闭弹窗
        // 下面是你已有的「开始安装」逻辑
        document.getElementById('install-loader').style.display = 'block';
        const m = document.getElementById('status-message');
        m.classList.remove('d-none'); m.textContent = '正在安装 OpenVPN...';

        try {
            const res = await authFetch('/install', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ port, ip })
            });
            const data = await res.json();
            document.getElementById('install-loader').style.display = 'none';
            m.textContent = data.message;
            m.className = data.status === 'success' ? 'alert alert-success' : 'alert alert-danger';
            if (data.status === 'success') setTimeout(refreshPage,1200);
        } catch (err) {
            document.getElementById('install-loader').style.display = 'none';
            m.textContent = '安装失败: ' + err.message;
            m.className = 'alert alert-danger';
        }
    });

    // 点击“取消”或点击灰色遮罩 → 仅关闭弹窗，不刷新页面
    document.getElementById('installModal').addEventListener('hide.bs.modal', () => {
        document.getElementById('manual-ip-wrapper').style.display = 'none'; // 隐藏手动框
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

        authFetch('/add_client', {method: 'POST', body: fd})
            .then(r => r.json())
            .then(data => {
                loader.style.display = 'none';
                const cls = data.status === 'success' ? 'alert-success' : 'alert-danger';
                msgDiv.innerHTML = `<div class="alert ${cls}">${data.message}</div>`;
                if (data.status === 'success') {
                    form.reset(); 
					toggleCustomDate(); 
					setTimeout(()=> msgDiv.innerHTML = '', 2000);
					setTimeout(refreshPage, 2200);
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
            authFetch('/revoke_client', {method: 'POST', body: fd})
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
            authFetch('/disconnect_client', {
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
            authFetch('/enable_client', {
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
    // 绑定“修改到期时间”按钮
    $$('.modify-expiry-btn:not([data-bound])').forEach(btn => {
        btn.setAttribute('data-bound', 'true');
        btn.addEventListener('click', () => {
            $('#modify-client-name').value = btn.dataset.client;
            const modal = new bootstrap.Modal($('#modifyExpiryModal'));
            modal.show();
        });
    });

    // 绑定确认按钮
    const btn = $('#confirm-modify-expiry');
    if (btn && !btn.hasAttribute('data-bound')) {
        btn.setAttribute('data-bound', 'true');
        btn.addEventListener('click', () => {
            const name = $('#modify-client-name').value;

            // 判断是选定天数还是自定义日期
            let days;
            if ($('#modify-expiryCustom').checked) {
                const d = $('#modify-expiry-date').value;
                if (!d) {
                    $('#modify-expiry-message').innerHTML='<div class="alert alert-danger">请选择到期日期</div>';
                    return;
                }
                days = Math.ceil((new Date(d) - new Date()) / 86400000).toString();
            } else {
                // 获取选中的 radio（30 / 60 / 90）
                const selected = document.querySelector('input[name="modify_expiry_choice"]:checked');
                days = selected ? selected.value : '30';
            }

            const l = $('#modify-expiry-loader'), m = $('#modify-expiry-message');
            l.style.display = 'inline-block'; btn.disabled = true;

            const fd = new FormData();
            fd.append('client_name', name);
            fd.append('expiry_days', days);

            authFetch('/modify_client_expiry', {method: 'POST', body: fd})
                .then(r => r.json())
                .then(d => {
                    l.style.display = 'none'; btn.disabled = false;
                    const cls = d.status === 'success' ? 'alert-success' : 'alert-danger';
                    m.innerHTML = `<div class="alert ${cls}">${d.message}</div>`;
                    if (d.status === 'success') {
                        setTimeout(() => {
                            bootstrap.Modal.getInstance($('#modifyExpiryModal')).hide();
                            refreshPage();
                        }, 2000);
                    }
                })
                .catch(err => {
                    l.style.display = 'none'; btn.disabled = false;
                    m.innerHTML = `<div class="alert alert-danger">${err}</div>`;
                });
        });
    }

    // 切换日期选择框的显示/隐藏
    $$('input[name="modify_expiry_choice"]').forEach(radio => {
        radio.addEventListener('change', () => {
            if ($('#modify-expiryCustom').checked) {
                $('#modifyCustomDateWrapper').style.display = 'block';
            } else {
                $('#modifyCustomDateWrapper').style.display = 'none';
            }
        });
    });
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
            authFetch('/uninstall', {method: 'POST'})
                .then(r => r.json())
                .then(d => {
                    l.style.display = 'none';
                    m.textContent = d.message;
                    m.className = d.status === 'success' ? 'alert alert-success' : 'alert alert-danger';
                    if (d.status === 'success') setTimeout(refreshPage,1200);
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

    $('#reset-btn')?.addEventListener('click', () => {
    $('#client_name').value = '';
    });
});


/* ---------- 修改用户密码 ---------- */
function bindChangePwd() {
  const form = $('#change-pwd-form');
  if (!form || form.hasAttribute('data-bound')) return;
  form.setAttribute('data-bound', 'true');

  form.addEventListener('submit', e => {
    e.preventDefault();
    const pwd = $('#new_pwd').value.trim();
    if (pwd.length < 6) {
      alert('密码至少 6 位'); return;
    }

    authFetch('/change_password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ new_pwd: pwd })
    })
    .then(r => r.json())
    .then(d => {
      alert(d.message);
      if (d.status === 'success') {
        bootstrap.Modal.getInstance('#changePwdModal').hide();
        form.reset();
      }
    })
    .catch(err => alert(err));
  });
}