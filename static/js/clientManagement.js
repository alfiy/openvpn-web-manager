/**
 * 这个模块包含了所有客户端相关的逻辑
 */
import { qs, qsa, showCustomConfirm, authFetch, toggleCustomDate } from './utils.js';
import { setCurrentSearchQuery,markUserActive } from './refresh.js';
import { refreshGroupsAfterClientMove } from './client_groups.js';


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

// 在文件顶部添加一个检查,确保所有 DOM 元素都存在
const elementsExist = tbody && paging && pageInfo && noData;

// 全局变量当前页为第1页
export let currentPage = 1;

let showOnlyOnline = false;  // 是否只显示在线用户

/* 统一渲染表格 */
function render(data) {
    if (!elementsExist) {
        console.warn("客户端管理DOM元素不存在,停止渲染。");
        return;
    }

    // ⭐ 添加调试：查看第一个客户端的数据结构
    // if (data.clients && data.clients.length > 0) {
    //     console.log('第一个客户端数据:', data.clients[0]);
    // }

    let clientsToRender = data.clients;

    if (userRole === 'USER') {
        clientsToRender = data.clients.filter(c => c.user_id === userId);
    }

    // ⭐ 新增：在线用户筛选
    if (showOnlyOnline) {
        clientsToRender = clientsToRender.filter(c => c.online === true);
    }

    if (!clientsToRender.length) {
        tbody.innerHTML = '';
        paging.innerHTML = '';
        noData.style.display = 'block';

        // 根据状态显示不同的提示信息
        if (showOnlyOnline) {
            noData.textContent = '当前无客户端在线。';
        } else if (data.q) {
            noData.textContent = `未找到与 "${data.q}" 相关的客户端。`;
        } else {
            noData.textContent = '没有客户端证书。';
        }

        pageInfo.textContent = '';
        return;
    }

    noData.style.display = 'none';
    pageInfo.textContent = data.total_pages > 1 ? `第 ${data.page} 页, 共 ${data.total_pages} 页` : '';

    tbody.innerHTML = clientsToRender.map((c, idx) => {
        const rowIdx = (data.page - 1) * PER_PAGE + idx + 1;
        const actionButtons = [];

        if (c.disabled) {
            actionButtons.push(`<button class="btn btn-sm btn-success enable-btn" data-client="${c.name}">重新启用</button>`);
        } else {
            actionButtons.push(`<a href="/download_client/${c.name}" class="btn btn-sm btn-primary">下载配置</a>`);

            if (userRole === 'SUPER_ADMIN' || userRole === 'ADMIN') {
                const currentGroupName = c.group || '未分组';
                actionButtons.push(`
                    <button class="btn btn-sm btn-secondary modify-group-btn"
                            data-client="${c.name}"                                  
                            data-current-group="${currentGroupName}"
                            data-action="modify-group">
                        <i class="fa-solid fa-layer-group me-1"></i>用户组
                    </button>
                `);

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
                <td class="align-middle">${rowIdx}</td>
                <td class="align-middle">
                    <div><strong>${c.name}</strong></div>
                    ${c.description ? `<div class="text-muted small">${c.description}</div>` : ''}
                </td>
                <td class="align-middle">
                    ${c.online
                        ? `<span class="badge bg-success"><i class="fa fa-circle"></i> 在线</span>
                           ${c.vpn_ip ? `<br><small class="text-success">VPN: ${c.vpn_ip}</small>` : ''}
                           ${c.real_ip ? `<br><small class="text-muted">来源: ${c.real_ip}</small>` : ''}
                           ${c.duration ? `<br><small class="text-info">时长: ${c.duration}</small>` : ''}`
                        : `<span class="badge bg-secondary"><i class="fa fa-circle"></i> 离线</span>`
                    }
                </td>
                <td class="align-middle"><small class="text-muted">${c.expiry || '未知'}</small></td>
                <td class="align-middle">
                    <div class="btn-group" role="group">
                        ${actionButtons.join('')}
                    </div>
                </td>
            </tr>`;
    }).join('');

    // ---------- 分页 ----------
    paging.innerHTML = '';
    if (data.total_pages <= 1) return;

    const makePageItem = (page, text, disabled = false, active = false) =>
        `<li class="page-item ${disabled ? 'disabled' : ''} ${active ? 'active' : ''}">
            <a class="page-link" href="#" data-page="${page}">${text}</a>
        </li>`;

    // 上一页
    paging.innerHTML += makePageItem(data.page - 1, '«', data.page <= 1);

    const start = Math.max(1, data.page - 2);
    const end = Math.min(data.total_pages, data.page + 2);

    if (start > 1) paging.innerHTML += makePageItem(1, 1);
    if (start > 2) paging.innerHTML += `<li class="page-item disabled"><span class="page-link">...</span></li>`;

    for (let p = start; p <= end; p++) paging.innerHTML += makePageItem(p, p, false, p === data.page);

    if (end < data.total_pages - 1) paging.innerHTML += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
    if (end < data.total_pages) paging.innerHTML += makePageItem(data.total_pages, data.total_pages);

    // 下一页
    paging.innerHTML += makePageItem(data.page + 1, '»', data.page >= data.total_pages);
}


/* AJAX 拉数据 */
export function loadClients(page = currentPage, q = '') {
    // 在这里再次进行检查,确保函数在合适的页面被调用
    if (!elementsExist) {
        return;
    }

    // ⭐ 仅在 q 是 null/undefined 时重置，而不是用 typeof 判断
    if (q == null) {   // null 或 undefined 时
        q = '';
    }

    // ⭐ 保留搜索功能
    if (typeof q === 'string') {
        q = q.trim();
    } else {
        // 作为兜底（很罕见）
        q = String(q).trim();
    }

    currentPage = Number(page) || 1;

    authFetch(`/clients/data?page=${currentPage}&q=${encodeURIComponent(q)}`)
        .then(render)
        .catch(console.error);
}


/* 处理启用客户端的逻辑 */
async function handleEnableClient(clientName) {
    const msgDiv = qs('#client-revoke-msg');
    msgDiv.innerHTML = '';

    try {
        const data = await authFetch('/api/clients/enable', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body: JSON.stringify({ client_name: clientName })
        });

        // 判断是否需要强制修改到期时间
        if (data.status === 'require_expiry_update') {
            // 客户端已到期,强制弹出修改到期时间 Modal
            showForceExpiryUpdateModal(data.data);
        } else {
            // 直接启用成功或其他情况
            const success = data.code === 0 || data.status === 'success';
            const message = (data.data && data.data.message) || data.msg || data.message || '操作完成';
            const cls = success ? 'alert-success' : 'alert-danger';

            msgDiv.innerHTML = `<div class="alert ${cls}">${message}</div>`;
            setTimeout(() => { msgDiv.innerHTML = ''; }, success ? 2000 : 3000);

            if (success) loadClients();
        }

    } catch (err) {
        msgDiv.innerHTML = `<div class="alert alert-danger">请求失败:${err}</div>`;
        setTimeout(() => { msgDiv.innerHTML = ''; }, 3000);
    }
}


/* 显示强制修改到期时间的 Modal */
function showForceExpiryUpdateModal(data) {
    const clientName = data.client_name;
    const currentExpiry = data.current_expiry;

    // 创建 Modal (如果不存在)
    let modalEl = qs('#forceExpiryUpdateModal');
    if (!modalEl) {
        const modalHtml = `
            <div class="modal fade" id="forceExpiryUpdateModal" tabindex="-1" data-bs-backdrop="static" data-bs-keyboard="false">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header bg-warning text-dark">
                            <h5 class="modal-title">⚠️ 客户端已到期</h5>
                        </div>
                        <div class="modal-body">
                            <div class="alert alert-warning" role="alert">
                                <strong>注意:</strong> 该客户端已到期被禁用,必须先延长到期时间才能启用。
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label"><strong>客户端名称:</strong></label>
                                <p class="form-control-plaintext" id="forceModalClientName"></p>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label"><strong>当前到期时间:</strong></label>
                                <p class="form-control-plaintext text-danger" id="forceModalCurrentExpiry"></p>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">选择延长方式 <span class="text-danger">*</span></label>
                                <div class="form-check">
                                    <input class="form-check-input" type="radio" name="force_expiry_choice" id="forceExpiry30" value="30" checked>
                                    <label class="form-check-label" for="forceExpiry30">30天</label>
                                </div>
                                <div class="form-check">
                                    <input class="form-check-input" type="radio" name="force_expiry_choice" id="forceExpiry90" value="90">
                                    <label class="form-check-label" for="forceExpiry90">90天</label>
                                </div>
                                <div class="form-check">
                                    <input class="form-check-input" type="radio" name="force_expiry_choice" id="forceExpiry180" value="180">
                                    <label class="form-check-label" for="forceExpiry180">180天</label>
                                </div>
                                <div class="form-check">
                                    <input class="form-check-input" type="radio" name="force_expiry_choice" id="forceExpiry365" value="365">
                                    <label class="form-check-label" for="forceExpiry365">365天</label>
                                </div>
                                <div class="form-check">
                                    <input class="form-check-input" type="radio" name="force_expiry_choice" id="forceExpiryCustom" value="custom">
                                    <label class="form-check-label" for="forceExpiryCustom">自定义日期</label>
                                </div>
                            </div>
                            
                            <div class="mb-3 d-none" id="forceCustomDateWrapper">
                                <label for="forceExpiryDate" class="form-label">选择到期日期</label>
                                <input type="date" class="form-control" id="forceExpiryDate">
                            </div>
                            
                            <div id="forceExpiryMessage"></div>
                            <div id="forceExpiryLoader" style="display:none;">
                                <div class="spinner-border spinner-border-sm text-primary" role="status">
                                    <span class="visually-hidden">处理中...</span>
                                </div>
                                <span class="ms-2">正在处理...</span>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-primary" id="confirmForceExpiryUpdate">
                                <i class="fa fa-check"></i> 确认修改并启用
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        modalEl = qs('#forceExpiryUpdateModal');

        // ⭐ 绑定自定义日期切换事件
        qsa('input[name="force_expiry_choice"]').forEach(radio => {
            radio.addEventListener('change', () => {
                const wrapper = qs('#forceCustomDateWrapper');
                if (qs('#forceExpiryCustom').checked) {
                    wrapper.classList.remove('d-none');
                } else {
                    wrapper.classList.add('d-none');
                }
            });
        });

        // ⭐ 绑定确认按钮事件
        const btnConfirm = qs('#confirmForceExpiryUpdate');
        btnConfirm.addEventListener('click', () => submitForceExpiryUpdate());
    }

    // 填充数据
    qs('#forceModalClientName').textContent = clientName;
    qs('#forceModalCurrentExpiry').textContent = currentExpiry ? new Date(currentExpiry).toLocaleString('zh-CN') : '未知';
    
    // 重置表单
    qs('#forceExpiry30').checked = true;
    qs('#forceCustomDateWrapper').classList.add('d-none');
    qs('#forceExpiryDate').value = '';
    qs('#forceExpiryMessage').innerHTML = '';

    // 显示 Modal
    const modalIns = bootstrap.Modal.getOrCreateInstance(modalEl);
    modalIns.show();
}


/* 提交强制修改到期时间 */
async function submitForceExpiryUpdate() {
    const clientName = qs('#forceModalClientName').textContent;
    const loader = qs('#forceExpiryLoader');
    const msgDiv = qs('#forceExpiryMessage');
    const btnConfirm = qs('#confirmForceExpiryUpdate');

    // 获取选择的到期时间
    let expiryDays;
    const choice = document.querySelector('input[name="force_expiry_choice"]:checked').value;
    
    if (choice === 'custom') {
        const dateVal = qs('#forceExpiryDate').value;
        if (!dateVal) {
            msgDiv.innerHTML = '<div class="alert alert-danger">请选择到期日期</div>';
            setTimeout(() => msgDiv.innerHTML = '', 3000);
            return;
        }
        const diff = Math.ceil((new Date(dateVal) - new Date()) / 86400000);
        if (diff <= 0) {
            msgDiv.innerHTML = '<div class="alert alert-danger">到期日期必须是将来的日期</div>';
            setTimeout(() => msgDiv.innerHTML = '', 3000);
            return;
        }
        expiryDays = diff.toString();
    } else {
        expiryDays = choice;
    }

    loader.style.display = 'block';
    btnConfirm.disabled = true;
    msgDiv.innerHTML = '';

    try {
        // 1. 先调用修改到期时间接口
        const modifyData = await authFetch('/api/clients/modify_expiry', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body: JSON.stringify({ client_name: clientName, expiry_days: expiryDays })
        });

        if (modifyData.status === 'success') {
            // 2. 修改成功后,再次调用启用接口
            const enableData = await authFetch('/api/clients/enable', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify({ client_name: clientName })
            });

            loader.style.display = 'none';
            btnConfirm.disabled = false;

            const success = enableData.code === 0 || enableData.status === 'success';
            const message = success 
                ? `客户端 ${clientName} 到期时间已更新并成功启用` 
                : (enableData.msg || enableData.message || '启用失败');
            
            const cls = success ? 'alert-success' : 'alert-danger';
            msgDiv.innerHTML = `<div class="alert ${cls}">${message}</div>`;

            if (success) {
                setTimeout(() => {
                    const modalEl = qs('#forceExpiryUpdateModal');
                    const modalIns = bootstrap.Modal.getInstance(modalEl);
                    modalIns.hide();
                    loadClients();
                    
                    // 显示全局成功消息
                    const globalMsg = qs('#client-revoke-msg');
                    globalMsg.innerHTML = `<div class="alert alert-success">${message}</div>`;
                    setTimeout(() => globalMsg.innerHTML = '', 2000);
                }, 1500);
            }
        } else {
            throw new Error(modifyData.message || '修改到期时间失败');
        }

    } catch (err) {
        loader.style.display = 'none';
        btnConfirm.disabled = false;
        msgDiv.innerHTML = `<div class="alert alert-danger">操作失败: ${err}</div>`;
        setTimeout(() => msgDiv.innerHTML = '', 3000);
    }
}


/* ------------------ 修改用户组 Modal ------------------ */
function ensureModifyGroupModal() {
    let modalEl = qs('#modifyGroupModal');

    if (!modalEl) {
        const modalHtml = `
            <div class="modal fade" id="modifyGroupModal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">修改用户组</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="关闭"></button>
                        </div>
                        <div class="modal-body">
                            <!-- 客户端名称（只读） -->
                            <div class="mb-3">
                                <label class="form-label">客户端名称</label>
                                <input type="text" id="modifyGroupClientName" class="form-control" readonly>
                            </div>
                            
                            <!-- 当前分组（只读显示） -->
                            <div class="mb-3">
                                <label class="form-label">当前分组</label>
                                <input type="text" id="modifyGroupCurrentGroup" class="form-control" readonly>
                            </div>
                            
                            <!-- 移动到分组（下拉选择） -->
                            <div class="mb-3">
                                <label class="form-label">移动到分组</label>
                                <select id="groupSelect" class="form-select">
                                    <option value="">-- 未分组 --</option>
                                </select>
                            </div>
                            
                            <div id="modifyGroupMessage"></div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                            <button type="button" class="btn btn-primary" id="confirmModifyGroup">
                                <i class="fa fa-check"></i> 确认修改
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        modalEl = qs('#modifyGroupModal');

        // 绑定确认按钮事件
        const btnConfirm = qs('#confirmModifyGroup');
        const inputClientName = qs('#modifyGroupClientName');
        const selectGroup = qs('#groupSelect');
        const msgDiv = qs('#modifyGroupMessage');

        if (btnConfirm && inputClientName && selectGroup && msgDiv) {
            btnConfirm.addEventListener('click', async () => {
                const clientName = inputClientName.value;
                const group = selectGroup.value;

                try {
                    const data = await authFetch('/api/clients/modify_group', {
                        method: 'POST',
                        headers: { 
                            'Content-Type': 'application/json', 
                            'X-CSRFToken': csrfToken 
                        },
                        body: JSON.stringify({ 
                            client_name: clientName, 
                            group: group
                        })
                    });

                    const success = data.code === 0 || data.status === 'success';
                    const cls = success ? 'alert-success' : 'alert-danger';
                    const message = data.msg || data.message || (success ? '操作成功' : '操作失败');
                    
                    msgDiv.innerHTML = `<div class="alert ${cls}">${message}</div>`;

                    if (success) {
                        setTimeout(() => {
                            const modalIns = bootstrap.Modal.getInstance(modalEl);
                            if (modalIns) modalIns.hide();
                            
                            // 刷新客户端列表
                            loadClients();
                            
                            // ⭐ 关键：触发用户组管理选项卡刷新
                            refreshGroupsAfterClientMove();
                            
                            msgDiv.innerHTML = '';
                        }, 1000);
                    }
                } catch (err) {
                    msgDiv.innerHTML = `<div class="alert alert-danger">操作失败: ${err.message || err}</div>`;
                }
            });
        } else {
            console.error('修改用户组 Modal 内部元素不存在!');
        }
    }

    return modalEl;
}


/* 绑定客户端操作事件 */
export function bindClientEvents() {
    // 全局标记用户活跃
    document.addEventListener('mousedown', markUserActive);
    document.addEventListener('keydown', markUserActive);
    document.addEventListener('scroll', markUserActive);

    // 在线/显示全部切换按钮
    const filterOnlineBtn = qs('#filter-online-btn');
    const showAllBtn = qs('#show-all-btn');

    if (filterOnlineBtn) {
        filterOnlineBtn.addEventListener('click', () => {
            showOnlyOnline = true;
            currentPage = 1;

            filterOnlineBtn.style.display = 'none';
            showAllBtn.style.display = 'block';

            if (input) input.placeholder = '当前仅显示在线用户，点击"显示全部"查看所有客户端...';
            loadClients(currentPage, input ? input.value.trim() : '');
        });
    }

    if (showAllBtn) {
        showAllBtn.addEventListener('click', () => {
            showOnlyOnline = false;
            currentPage = 1;

            showAllBtn.style.display = 'none';
            filterOnlineBtn.style.display = 'block';

            if (input) input.placeholder = '搜索客户端名称或描述信息后回车...';
            loadClients(currentPage, input ? input.value.trim() : '');
        });
    }

    // 搜索框回车
    if (input) {
        input.addEventListener('keydown', e => {
            if (e.key === 'Enter') {
                e.preventDefault();
                const q = input.value.trim();
                currentPage = 1;
                setCurrentSearchQuery(q);
                loadClients(1, q);
            }
        });
    }

    // 分页
    if (paging) {
        paging.addEventListener('click', e => {
            if (e.target.classList.contains('page-link')) {
                e.preventDefault();
                const page = parseInt(e.target.dataset.page);
                if (page) loadClients(page, input.value.trim());
            }
        });
    }

    const msgDiv = qs('#client-revoke-msg');

    // 统一处理客户端按钮点击事件
    document.body.addEventListener('click', async e => {
        const btn = e.target.closest('[data-action], .revoke-btn, .disconnect-btn, .enable-btn, .modify-group-btn');
        if (!btn) return;

        const clientName = btn.dataset.client;


        // 在 bindClientEvents 函数中的用户组按钮点击处理
        if (btn.classList.contains('modify-group-btn')) {
            // 获取当前分组，如果是"未分组"则显示为"未分组"
            let currentGroup = btn.dataset.currentGroup || '';
            if (currentGroup === '未分组' || currentGroup === '') {
                currentGroup = '未分组';
            }
            
            const modalEl = ensureModifyGroupModal();
            const modal = bootstrap.Modal.getOrCreateInstance(modalEl);

            // 设置客户端名称
            qs('#modifyGroupClientName').value = clientName;
            
            // 设置当前分组显示
            const currentGroupInput = qs('#modifyGroupCurrentGroup');
            if (currentGroupInput) {
                currentGroupInput.value = currentGroup;
            }
            
            qs('#modifyGroupMessage').innerHTML = '';

            const select = qs('#groupSelect');
            select.innerHTML = '<option value="">-- 未分组 --</option>';

            try {
                // 获取所有用户组列表
                const data = await authFetch('/api/client_groups');
                const groups = data.data?.groups || [];
                
                groups.forEach(g => {
                    const option = document.createElement('option');
                    option.value = g.name;
                    
                    // 如果该组是当前分组，在下拉框中标记但不选中
                    if (g.name === currentGroup || (currentGroup === '未分组' && g.name === btn.dataset.currentGroup)) {
                        option.textContent = `${g.name} (当前)`;
                        option.disabled = true; // 禁用当前分组选项，防止重复选择
                    } else {
                        option.textContent = g.name;
                    }
                    select.appendChild(option);
                });
                
                modal.show();
            } catch (err) {
                console.error('加载用户组失败:', err);
                select.innerHTML = '<option value="">加载失败</option>';
                showCustomMessage('加载用户组列表失败', 'error');
            }
            return;
        }

        // ---------------- 启用客户端 ----------------
        if (btn.classList.contains('enable-btn')) {
            showCustomConfirm(`确认要重新启用客户端 "${clientName}" 吗?`, (confirmed) => {
                if (confirmed) handleEnableClient(clientName);
            });
            return;
        }

        // ---------------- 禁用/撤销 ----------------
        let url = '', confirmMessage = '';

        if (btn.classList.contains('revoke-btn')) {
            url = '/api/clients/revoke';
            confirmMessage = `确定撤销客户端 "${clientName}" 的证书吗?此操作不可恢复!`;
        } else if (btn.classList.contains('disconnect-btn')) {
            url = '/api/clients/disable';
            confirmMessage = `确认要禁用客户端 "${clientName}" 吗?`;
        } else {
            return;
        }

        showCustomConfirm(confirmMessage, async (confirmed) => {
            if (!confirmed) return;

            msgDiv.innerHTML = '';
            try {
                const data = await authFetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify({ client_name: clientName, confirm: true })
                });

                const success = data.code === 0;
                const message = (data.data && data.data.message) || data.msg || '操作完成';
                const cls = success ? 'alert-success' : 'alert-danger';
                msgDiv.innerHTML = `<div class="alert ${cls}">${message}</div>`;

                setTimeout(() => { msgDiv.innerHTML = ''; }, success ? 2000 : 3000);
                if (success) loadClients();

            } catch (err) {
                msgDiv.innerHTML = `<div class="alert alert-danger">请求失败:${err}</div>`;
                setTimeout(() => { msgDiv.innerHTML = ''; }, 3000);
            }
        });
    });
}



// 绑定添加客户端事件
export function bindAddClient() {
    const form = qs('#add-client-form');
    if (!form || form.hasAttribute('data-bound')) return;
    form.setAttribute('data-bound', 'true');

    // 绑定到期选择变化事件
    qsa('input[name="expiry_choice"]').forEach(r => r.addEventListener('change', () => toggleCustomDate('expiry')));
    toggleCustomDate('expiry');

    // 重置按钮
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
        if (!nameVal) {
            msgDiv.innerHTML = '<div class="alert alert-danger">请输入客户端名称</div>';
            setTimeout(() => msgDiv.innerHTML = '', 4000);
            return;
        }

        const descVal = qs('#client_description')?.value.trim() || "";

        loader.style.display = 'block';
        msgDiv.innerHTML = '';

        // 计算到期天数
        let expiryDays;
        const choice = qs('input[name="expiry_choice"]:checked').value;
        if (choice === 'custom') {
            const d = qs('#expiry_date').value;
            if (!d) {
                loader.style.display = 'none';
                msgDiv.innerHTML = '<div class="alert alert-danger">请选择到期日期</div>';
                setTimeout(() => msgDiv.innerHTML = '', 4000);
                return;
            }
            const diff = Math.ceil((new Date(d) - new Date()) / 86400000);
            if (diff <= 0) {
                loader.style.display = 'none';
                msgDiv.innerHTML = '<div class="alert alert-danger">到期日期必须是将来的日期</div>';
                setTimeout(() => msgDiv.innerHTML = '', 4000);
                return;
            }
            expiryDays = diff.toString();
        } else {
            expiryDays = choice;
        }

        try {
            const data = await authFetch('/api/clients/add', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({
                    client_name: nameVal,
                    description: descVal,   // ⭐ 已新增
                    expiry_days: expiryDays
                })
            });

            loader.style.display = 'none';

            // ⭐ 添加调试日志
            // console.log('API 响应数据:', data);

            const success = data.code === 0;
            
            // ⭐ 修改消息提取逻辑，支持多层嵌套
            let message = '操作完成';
            
            if (!success) {
                // 尝试多种可能的错误信息路径
                message = data?.data?.error ||      // 你的后端格式
                         data?.error ||             
                         data?.message ||           
                         data?.msg ||               
                         data?.data?.message ||
                         '操作失败';
            } else {
                message = data?.data?.message || 
                         data?.message || 
                         data?.msg || 
                         '操作完成';
            }

            const cls = success ? 'alert-success' : 'alert-danger';
            msgDiv.innerHTML = `<div class="alert ${cls}">${message}</div>`;

            if (success) {
                form.reset();
                toggleCustomDate('expiry');
                loadClients?.();
                setTimeout(() => msgDiv.innerHTML = '', 2000);
            } else {
                setTimeout(() => msgDiv.innerHTML = '', 4000);
            }

        } catch (err) {
            loader.style.display = 'none';

            // ⭐ 添加调试日志
            // console.log('捕获到错误:', err);

            // ⭐ 直接使用 err.message，因为 authFetch 已经提取了正确的错误信息
            let msg = err.message || '请求失败，请稍后重试';

            msgDiv.innerHTML = `<div class="alert alert-danger">${msg}</div>`;
            setTimeout(() => msgDiv.innerHTML = '', 4000);
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
                const data = await authFetch('/api/clients/modify_expiry', {
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
                    }, 1500);
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

// 统一的初始化函数,用于在页面加载时调用
export function init() {
    loadClients(currentPage);
    bindClientEvents();
    bindAddClient();
    bindModifyExpiry();
}