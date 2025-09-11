/**
 * 这个模块包含了所有客户端相关的逻辑
 */
import { qs, qsa, showCustomMessage, showCustomConfirm, authFetch, toggleCustomDate } from './utils.js';

const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

let userRole = (document.body.dataset.role || '').toUpperCase();
const userId = document.body.dataset.userId;

if (userRole.startsWith('ROLE.')) userRole = userRole.replace('ROLE.', '');
if (userRole === '管理员'.toUpperCase()) userRole = 'ADMIN';
if (userRole === '超级管理员'.toUpperCase()) userRole = 'SUPER_ADMIN';
if (userRole === '普通用户'.toUpperCase()) userRole = 'USER';

const input = document.getElementById('client-search');
const tbody = document.getElementById('client-tbody');
const paging = document.getElementById('pagination');
const pageInfo = document.getElementById('page-info');
const noData = document.getElementById('no-data');
const PER_PAGE = 10;

/* 统一渲染表格 */
function render(data) {
    let clientsToRender = data.clients;
    if (userRole === 'USER') {
        clientsToRender = data.clients.filter(c => c.user_id === userId);
    }
    
    if (!clientsToRender.length) {
        
        tbody.innerHTML = '';
        paging.innerHTML = '';
        noData.style.display = 'block';
        noData.textContent = data.q ? `未找到与 “${data.q}” 相关的客户端。` : '没有客户端证书。';
        pageInfo.textContent = '';
        return;
    }
    noData.style.display = 'none';
    pageInfo.textContent = data.total_pages > 1 ? `第 ${data.page} 页，共 ${data.total_pages} 页` : '';

    tbody.innerHTML = clientsToRender.map((c, idx) => {
        const rowIdx = (data.page - 1) * PER_PAGE + idx + 1;
        const actionButtons = [];

        // 新增的业务逻辑判断
        if (c.disabled) {
            // 如果客户端被禁用，只显示“重新启用”按钮
            actionButtons.push(`<button class="btn btn-sm btn-success enable-btn" data-client="${c.name}">重新启用</button>`);
        } else {
            // 如果客户端未被禁用，则显示所有按钮（根据角色权限）
            actionButtons.push(`<a href="/download_client/${c.name}" class="btn btn-sm btn-primary">下载配置</a>`);

            if (userRole === 'SUPER_ADMIN' || userRole === 'ADMIN') {
                actionButtons.push(`<button class="btn btn-sm btn-info modify-expiry-btn"
                                            data-client="${c.name}"
                                            data-bs-toggle="modal"
                                            data-bs-target="#modifyExpiryModal">修改到期</button>`);
                                            
                actionButtons.push(`<button class="btn btn-sm btn-warning disconnect-btn" data-client="${c.name}">禁用</button>`);
                actionButtons.push(`<button class="btn btn-sm btn-danger revoke-btn" data-client="${c.name}">撤销</button>`);
            }
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
export function loadClients(page = 1, q = '') {
    authFetch(`/clients/data?page=${page}&q=${encodeURIComponent(q)}`)
        .then(render)
        .catch(console.error);
}

/* 绑定事件 */
function bindClientEvents() {
    if (input) {
        input.addEventListener('keydown', e => {
            if (e.key === 'Enter') {
                e.preventDefault();
                loadClients(1, input.value.trim());
            }
        });
    }

    if (paging) {
        paging.addEventListener('click', e => {
            if (e.target.classList.contains('page-link')) {
                e.preventDefault();
                const page = parseInt(e.target.dataset.page);
                if (page) loadClients(page, input.value.trim());
            }
        });
    }

    document.body.addEventListener('click', async e => {
        const targetBtn = e.target.closest('.revoke-btn, .disconnect-btn, .enable-btn');
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
        }
        
        showCustomConfirm(confirmMessage, async (confirmed) => {
            if (!confirmed) return;
            try {
                const data = await authFetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ client_name: clientName })
                });
                
                showCustomMessage(data.message);
                if (data.status === 'success') {
                    loadClients();
                }
            } catch (err) {
                showCustomMessage(err.message);
            }
        });
    });
}

// 绑定添加客户端事件
export function bindAddClient() {
    const form = qs('#add-client-form');
    if (!form || form.hasAttribute('data-bound')) return;
    form.setAttribute('data-bound', 'true');

    qsa('input[name="expiry_choice"]').forEach(r => r.addEventListener('change', () => toggleCustomDate('expiry')));
    toggleCustomDate('expiry');

    const resetButton = qs('#reset-btn');
    if (resetButton) {
        resetButton.addEventListener('click', () => {
            form.reset();
            toggleCustomDate('expiry');
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
            const data = await authFetch('/add_client', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                 },
                body: JSON.stringify({ client_name: nameVal, expiry_days: expiryDays })
            });
            
            
            loader.style.display = 'none';
            const cls = data.status === 'success' ? 'alert-success' : 'alert-danger';
            msgDiv.innerHTML = `<div class="alert ${cls}">${data.message}</div>`;
            if (data.status === 'success') {
                form.reset();
                toggleCustomDate('expiry');
                setTimeout(() => msgDiv.innerHTML = '', 2000);
                loadClients();
            }
        } catch(err) {
            loader.style.display = 'none';
            msgDiv.innerHTML = `<div class="alert alert-danger">${err}</div>`;
            setTimeout(() => msgDiv.innerHTML = '', 2000);
        }
    });
}

// 绑定修改到期时间事件
export function bindModifyExpiry() {
    const modalEl = qs('#modifyExpiryModal');
    if (!modalEl) return;
    const modalIns = bootstrap.Modal.getOrCreateInstance(modalEl);

    document.body.addEventListener('click', e => {
        const btn = e.target.closest('.modify-expiry-btn');
        if (btn) {
            qs('#modify-client-name').value = btn.dataset.client;
            modalIns.show();
        }
    });

    qsa('input[name="modify_expiry_choice"]').forEach(radio => {
        radio.addEventListener('change', () => {
            toggleCustomDate('modify-expiry');
        });
    });

    const btnConfirm = qs('#confirm-modify-expiry');
    if (btnConfirm && !btnConfirm.hasAttribute('data-bound')) {
        btnConfirm.setAttribute('data-bound', 'true');
        btnConfirm.addEventListener('click', async () => {
            const name = qs('#modify-client-name').value;
            let days;
            if (qs('#modify-expiryCustom').checked) {
                const d = qs('#modify-expiry-date').value;
                if (!d) {
                    qs('#modify-expiry-message').innerHTML = '<div class="alert alert-danger">请选择到期日期</div>';
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

            btnConfirm.blur();

            try {
                const data = await authFetch('/modify_client_expiry', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ client_name: name, expiry_days: days })
                });

                loader.style.display = 'none';
                btnConfirm.disabled = false;

                const cls = data.status === 'success' ? 'alert-success' : 'alert-danger';
                msg.innerHTML = `<div class="alert ${cls}">${data.message}</div>`;

                if (data.status === 'success') {
                    setTimeout(() => {
                        modalIns.hide();
                        loadClients();
                    }, 500);
                }
            } catch (err) {
                loader.style.display = 'none';
                btnConfirm.disabled = false;
                msg.innerHTML = `<div class="alert alert-danger">${err}</div>`;
                setTimeout(() => msg.innerHTML = '', 2000);
            }
        });
    }

    modalEl.addEventListener('hidden.bs.modal', () => {
        qs('#modify-expiry-message').innerHTML = '';
        qs('#modify-expiry-date').value = '';
        qs('#modify-expiryCustom').checked = false;
        qs('#modifyCustomDateWrapper').classList.add('d-none');
        qs('#modify-client-name').value = '';
    });
}

// 统一的初始化函数，用于在页面加载时调用
export function init() {
    loadClients();
    bindClientEvents();
    bindAddClient();
    bindModifyExpiry();
}