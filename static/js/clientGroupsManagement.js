/**
 * 🆕 客户端用户组管理 JavaScript 模块
 * 负责处理用户组的列表、创建、编辑、删除和成员管理
 */

import { qs, qsa, showCustomConfirm, showCustomMessage, authFetch } from './utils.js';

const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';

// ========== 模态框和 DOM 元素（延迟初始化）==========
let groupModal = null;
let groupDetailsModal = null;
let addMemberModal = null;

let currentGroupId = null;
let allClients = []; // 缓存所有客户端列表

// ========== 分页状态 ==========
let groupsDataCache = []; // 缓存所有用户组数据
let currentPage = 1;
const ITEMS_PER_PAGE = 3; // 每页显示3个

// ========== 初始化函数 ==========
export function init() {
    const groupsContainer = qs('#groupsContainer');
    if (!groupsContainer) {
        console.log('⚠️  用户组容器不存在,跳过初始化');
        return;
    }
    
    initializeModals();
    loadClientGroups();
    bindGroupEvents();
}

// ========== 初始化 Bootstrap Modal ==========
function initializeModals() {
    try {
        const groupModalEl = qs('#groupModal');
        const groupDetailsModalEl = qs('#groupDetailsModal');
        const addMemberModalEl = qs('#addMemberModal');
        
        if (groupModalEl) groupModal = new bootstrap.Modal(groupModalEl);
        if (groupDetailsModalEl) groupDetailsModal = new bootstrap.Modal(groupDetailsModalEl);
        if (addMemberModalEl) addMemberModal = new bootstrap.Modal(addMemberModalEl);
    } catch (error) {
        console.error('❌ Bootstrap Modal 初始化失败:', error);
    }
}

// ========== 加载用户组列表 ==========
async function loadClientGroups() {
    try {
        const data = await authFetch('/api/client_groups');
        
        if (data.code === 0) {
            groupsDataCache = data.data.groups || [];
            currentPage = 1; // 重置到第一页
            renderGroupsCards();
        } else {
            showCustomMessage(data.msg || '加载用户组失败');
        }
    } catch (error) {
        console.error('加载用户组失败:', error);
        showCustomMessage(`加载用户组失败: ${error.message}`);
    }
}

// ========== 渲染用户组卡片（支持分页）==========
function renderGroupsCards() {
    const container = qs('#groupsContainer');
    const placeholder = qs('#noGroupsPlaceholder');
    const paginationNav = qs('#groupsPagination');
    
    if (!container) return;
    
    // 无数据情况
    if (!groupsDataCache || groupsDataCache.length === 0) {
        if (placeholder) placeholder.style.display = 'block';
        container.innerHTML = '';
        if (paginationNav) paginationNav.style.display = 'none';
        return;
    }
    
    if (placeholder) placeholder.style.display = 'none';
    
    // 计算分页
    const totalItems = groupsDataCache.length;
    const totalPages = Math.ceil(totalItems / ITEMS_PER_PAGE);
    
    // 确保当前页有效
    if (currentPage > totalPages) currentPage = totalPages;
    if (currentPage < 1) currentPage = 1;
    
    // 获取当前页数据
    const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
    const endIndex = startIndex + ITEMS_PER_PAGE;
    const currentGroups = groupsDataCache.slice(startIndex, endIndex);
    
    // 渲染卡片
    container.innerHTML = currentGroups.map(group => `
        <div class="col-md-4">
            <div class="card group-card h-100">
                <div class="card-header bg-primary text-white d-flex justify-content-between align-items-center py-2">
                    <div class="overflow-hidden">
                        <h6 class="mb-0 text-truncate" title="${escapeHtml(group.name)}">${escapeHtml(group.name)}</h6>
                        <small class="text-light text-truncate d-block" title="${escapeHtml(group.description || '无描述')}">${escapeHtml(group.description || '无描述')}</small>
                    </div>
                    <button class="btn btn-sm btn-danger ms-2 flex-shrink-0 deleteGroupBtn" data-group-id="${group.id}" title="删除">
                        <i class="fa fa-trash"></i>
                    </button>
                </div>
                <div class="card-body py-2">
                    <div class="row text-sm">
                        <div class="col-6">
                            <div class="text-success text-truncate" title="上行: ${escapeHtml(group.upload_rate)}">
                                <i class="fa fa-arrow-up"></i> ${escapeHtml(group.upload_rate)}
                            </div>
                        </div>
                        <div class="col-6">
                            <div class="text-info text-truncate" title="下行: ${escapeHtml(group.download_rate)}">
                                <i class="fa fa-arrow-down"></i> ${escapeHtml(group.download_rate)}
                            </div>
                        </div>
                    </div>
                    <div class="mt-2">
                        <small class="text-muted">
                            <i class="fa fa-users"></i> 成员: <strong>${group.client_count || 0}</strong>
                        </small>
                    </div>
                </div>
                <div class="card-footer bg-light py-2">
                    <button class="btn btn-sm btn-outline-primary w-100 viewGroupBtn" data-group-id="${group.id}">
                        <i class="fa fa-eye"></i> 查看详情
                    </button>
                </div>
            </div>
        </div>
    `).join('');
    
    // 更新分页显示
    updatePagination(totalPages);
}

// ========== 更新分页控件 ==========
function updatePagination(totalPages) {
    const paginationNav = qs('#groupsPagination');
    const prevBtn = qs('#prevPageBtn');
    const nextBtn = qs('#nextPageBtn');
    const pageInfo = qs('#pageInfo');
    
    if (!paginationNav) return;
    
    // 只有一页时不显示分页
    if (totalPages <= 1) {
        paginationNav.style.display = 'none';
        return;
    }
    
    paginationNav.style.display = 'block';
    
    // 更新页码信息
    if (pageInfo) {
        pageInfo.textContent = `${currentPage} / ${totalPages}`;
    }
    
    // 更新上一页按钮状态
    if (prevBtn) {
        if (currentPage <= 1) {
            prevBtn.classList.add('disabled');
        } else {
            prevBtn.classList.remove('disabled');
        }
    }
    
    // 更新下一页按钮状态
    if (nextBtn) {
        if (currentPage >= totalPages) {
            nextBtn.classList.add('disabled');
        } else {
            nextBtn.classList.remove('disabled');
        }
    }
}

// ========== 切换页面 ==========
function goToPage(page) {
    currentPage = page;
    renderGroupsCards();
}

// ========== 绑定事件 ==========
function bindGroupEvents() {
    // 添加用户组
    const addGroupBtn = qs('#addGroupBtn');
    if (addGroupBtn) {
        addGroupBtn.addEventListener('click', openAddGroupModal);
    }
    
    // 保存用户组
    const saveGroupBtn = qs('#saveGroupBtn');
    if (saveGroupBtn) {
        saveGroupBtn.addEventListener('click', saveGroup);
    }
    
    // 动态绑定卡片事件（使用事件委托）
    const groupsContainer = qs('#groupsContainer');
    if (groupsContainer) {
        groupsContainer.addEventListener('click', (e) => {
            if (e.target.closest('.viewGroupBtn')) {
                const groupId = e.target.closest('.viewGroupBtn').dataset.groupId;
                openGroupDetailsModal(groupId);
            }
            if (e.target.closest('.deleteGroupBtn')) {
                const groupId = e.target.closest('.deleteGroupBtn').dataset.groupId;
                deleteGroup(groupId);
            }
        });
    }
    
    // 分页事件
    const prevPageBtn = qs('#prevPageBtn');
    const nextPageBtn = qs('#nextPageBtn');
    
    if (prevPageBtn) {
        prevPageBtn.addEventListener('click', (e) => {
            e.preventDefault();
            if (currentPage > 1) {
                goToPage(currentPage - 1);
            }
        });
    }
    
    if (nextPageBtn) {
        nextPageBtn.addEventListener('click', (e) => {
            e.preventDefault();
            const totalPages = Math.ceil(groupsDataCache.length / ITEMS_PER_PAGE);
            if (currentPage < totalPages) {
                goToPage(currentPage + 1);
            }
        });
    }
    
    // 保存限速设置
    const groupDetailsForm = qs('#groupDetailsForm');
    if (groupDetailsForm) {
        groupDetailsForm.addEventListener('submit', (e) => {
            e.preventDefault();
            updateGroupRates();
        });
    }
    
    // 删除用户组
    const deleteGroupBtn = qs('#deleteGroupBtn');
    if (deleteGroupBtn) {
        deleteGroupBtn.addEventListener('click', () => {
            deleteGroup(currentGroupId);
        });
    }
    
    // 添加成员
    const addMemberBtn = qs('#addMemberBtn');
    if (addMemberBtn) {
        addMemberBtn.addEventListener('click', openAddMemberModal);
    }
    
    const confirmAddMemberBtn = qs('#confirmAddMemberBtn');
    if (confirmAddMemberBtn) {
        confirmAddMemberBtn.addEventListener('click', addMemberToGroup);
    }
}

// ========== 打开添加用户组模态框 ==========
function openAddGroupModal() {
    const groupIdInput = qs('#groupId');
    const groupForm = qs('#groupForm');
    const groupModalTitle = qs('#groupModalTitle');
    const groupFormMessage = qs('#groupFormMessage');
    
    if (groupIdInput) groupIdInput.value = '';
    if (groupForm) groupForm.reset();
    if (groupModalTitle) groupModalTitle.textContent = '添加用户组';
    if (groupFormMessage) groupFormMessage.innerHTML = '';
    
    if (groupModal) {
        groupModal.show();
    }
}

// ========== 保存用户组 ==========
async function saveGroup() {
    const groupId = qs('#groupId')?.value;
    const name = qs('#groupName')?.value.trim();
    const desc = qs('#groupDesc')?.value.trim();
    const uploadRate = qs('#uploadRate')?.value.trim() + 'Mbit';
    const downloadRate = qs('#downloadRate')?.value.trim() + 'Mbit';
    
    const messageDiv = qs('#groupFormMessage');
    
    if (!name) {
        if (messageDiv) {
            messageDiv.innerHTML = '<div class="alert alert-danger">请输入用户组名称</div>';
        }
        return;
    }
    
    try {
        const method = groupId ? 'PUT' : 'POST';
        const url = groupId ? `/api/client_groups/${groupId}` : '/api/client_groups';
        
        const data = await authFetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({
                name,
                description: desc,
                upload_rate: uploadRate,
                download_rate: downloadRate
            })
        });
        
        if (data.code === 0) {
            if (messageDiv) {
                messageDiv.innerHTML = '<div class="alert alert-success">' + data.msg + '</div>';
            }
            setTimeout(() => {
                if (groupModal) groupModal.hide();
                loadClientGroups();
            }, 1500);
        } else {
            if (messageDiv) {
                messageDiv.innerHTML = '<div class="alert alert-danger">' + (data.msg || '操作失败') + '</div>';
            }
        }
    } catch (error) {
        if (messageDiv) {
            messageDiv.innerHTML = '<div class="alert alert-danger">保存失败: ' + error.message + '</div>';
        }
    }
}

// ========== 打开用户组详情模态框 ==========
async function openGroupDetailsModal(groupId) {
    currentGroupId = groupId;
    
    try {
        const groupsData = await authFetch('/api/client_groups');
        const group = groupsData.data.groups.find(g => g.id === parseInt(groupId));
        
        if (!group) {
            showCustomMessage('用户组不存在');
            return;
        }
        
        // 填充基本信息
        const detailsTitle = qs('#groupDetailsTitle');
        if (detailsTitle) detailsTitle.textContent = `${group.name} - 详情`;
        
        const detailsName = qs('#detailsName');
        if (detailsName) detailsName.textContent = group.name;
        
        const detailsDesc = qs('#detailsDesc');
        if (detailsDesc) detailsDesc.textContent = group.description || '无';
        
        const detailsUpload = qs('#detailsUpload');
        if (detailsUpload) detailsUpload.textContent = group.upload_rate;
        
        const detailsDownload = qs('#detailsDownload');
        if (detailsDownload) detailsDownload.textContent = group.download_rate;
        
        const detailsMemberCount = qs('#detailsMemberCount');
        if (detailsMemberCount) detailsMemberCount.textContent = group.client_count || 0;
        
        // 填充限速修改表单
        const detailsGroupId = qs('#detailsGroupId');
        if (detailsGroupId) detailsGroupId.value = groupId;
        
        const detailsUploadRate = qs('#detailsUploadRate');
        if (detailsUploadRate) detailsUploadRate.value = group.upload_rate.replace('Mbit', '');
        
        const detailsDownloadRate = qs('#detailsDownloadRate');
        if (detailsDownloadRate) detailsDownloadRate.value = group.download_rate.replace('Mbit', '');
        
        // 加载成员列表
        loadGroupMembers(groupId);
        
        if (groupDetailsModal) {
            groupDetailsModal.show();
        }
    } catch (error) {
        showCustomMessage('加载用户组详情失败: ' + error.message);
    }
}

// ========== 加载用户组成员 ==========
async function loadGroupMembers(groupId) {
    const membersList = qs('#membersList');
    
    try {
        const data = await authFetch(`/api/client_groups/${groupId}/members`);
        
        if (data.code === 0) {
            renderMembersList(data.data.members, groupId);
        }
    } catch (error) {
        if (membersList) {
            membersList.innerHTML = '<div class="text-danger p-3">加载失败</div>';
        }
    }
}

// ========== 渲染成员列表 ==========
function renderMembersList(members, groupId) {
    const container = qs('#membersList');
    
    if (!container) return;
    
    if (!members || members.length === 0) {
        container.innerHTML = '<div class="text-center text-muted p-3">组内暂无成员</div>';
        return;
    }
    
    container.innerHTML = `
        <table class="table table-sm mb-0">
            <tbody>
                ${members.map(m => `
                    <tr>
                        <td>
                            <strong>${escapeHtml(m.name)}</strong>
                            ${m.description ? `<br><small class="text-muted">${escapeHtml(m.description)}</small>` : ''}
                        </td>
                        <td class="text-end">
                            ${m.online 
                                ? '<span class="badge bg-success">在线</span>' 
                                : '<span class="badge bg-secondary">离线</span>'
                            }
                        </td>
                        <td class="text-end">
                            <button class="btn btn-sm btn-danger removeMemberBtn" data-client-id="${m.id}" data-client-name="${escapeHtml(m.name)}" data-group-id="${groupId}">
                                <i class="fa fa-times"></i>
                            </button>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
    
    // 绑定移除成员事件
    qsa('.removeMemberBtn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const clientName = btn.dataset.clientName;
            const groupId = btn.dataset.groupId;
            removeMemberFromGroup(groupId, clientName);
        });
    });
}

// ========== 打开添加成员模态框 ==========
async function openAddMemberModal() {
    try {
        // 加载所有客户端
        const clientsData = await authFetch('/clients/data?page=1');
        allClients = clientsData.clients;
        
        // 过滤出未分组的客户端
        const ungroupedClients = allClients.filter(c => !c.group_id);
        
        const select = qs('#clientSelect');
        if (!select) return;
        
        select.innerHTML = '<option value="">-- 选择客户端 --</option>';
        
        if (ungroupedClients.length === 0) {
            select.innerHTML += '<option disabled>没有可用的客户端</option>';
            showCustomMessage('所有客户端都已分组');
            return;
        }
        
        ungroupedClients.forEach(client => {
            const option = document.createElement('option');
            option.value = client.name;
            option.textContent = `${client.name}${client.description ? ' (' + client.description + ')' : ''}`;
            select.appendChild(option);
        });
        
        const addMemberMessage = qs('#addMemberMessage');
        if (addMemberMessage) addMemberMessage.innerHTML = '';
        
        if (addMemberModal) {
            addMemberModal.show();
        }
    } catch (error) {
        showCustomMessage('加载客户端列表失败: ' + error.message);
    }
}

// ========== 添加成员到用户组 ==========
async function addMemberToGroup() {
    const clientSelect = qs('#clientSelect');
    const clientName = clientSelect?.value;
    const messageDiv = qs('#addMemberMessage');
    
    if (!clientName) {
        if (messageDiv) {
            messageDiv.innerHTML = '<div class="alert alert-danger">请选择客户端</div>';
        }
        return;
    }
    
    try {
        const data = await authFetch(`/api/client_groups/${currentGroupId}/add_member`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({ client_name: clientName })
        });
        
        if (data.code === 0) {
            if (messageDiv) {
                messageDiv.innerHTML = '<div class="alert alert-success">' + data.msg + '</div>';
            }
            setTimeout(() => {
                if (addMemberModal) addMemberModal.hide();
                loadGroupMembers(currentGroupId);
                loadClientGroups();
            }, 1500);
        } else {
            if (messageDiv) {
                messageDiv.innerHTML = '<div class="alert alert-danger">' + (data.msg || '添加失败') + '</div>';
            }
        }
    } catch (error) {
        if (messageDiv) {
            messageDiv.innerHTML = '<div class="alert alert-danger">添加失败: ' + error.message + '</div>';
        }
    }
}

// ========== 从用户组移除成员 ==========
async function removeMemberFromGroup(groupId, clientName) {
    showCustomConfirm(`确定要从用户组中移除客户端 "${clientName}" 吗?`, async (confirmed) => {
        if (!confirmed) return;
        
        try {
            const data = await authFetch(`/api/client_groups/${groupId}/remove_member`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({ client_name: clientName })
            });
            
            if (data.code === 0) {
                showCustomMessage('成员已移除');
                loadGroupMembers(groupId);
                loadClientGroups();
            } else {
                showCustomMessage(data.msg || '移除失败', 'error');
            }
        } catch (error) {
            showCustomMessage('移除失败: ' + error.message, 'error');
        }
    });
}

// ========== 更新用户组限速设置 ==========
async function updateGroupRates() {
    const detailsGroupId = qs('#detailsGroupId');
    const groupId = detailsGroupId?.value;
    
    const detailsUploadRate = qs('#detailsUploadRate');
    const detailsDownloadRate = qs('#detailsDownloadRate');
    
    const uploadRate = detailsUploadRate?.value.trim() + 'Mbit';
    const downloadRate = detailsDownloadRate?.value.trim() + 'Mbit';
    
    const messageDiv = qs('#groupDetailsMessage');
    
    if (!uploadRate || !downloadRate) {
        if (messageDiv) {
            messageDiv.innerHTML = '<div class="alert alert-danger">请填写速率值</div>';
        }
        return;
    }
    
    try {
        const data = await authFetch(`/api/client_groups/${groupId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({
                upload_rate: uploadRate,
                download_rate: downloadRate
            })
        });
        
        if (data.code === 0) {
            if (messageDiv) {
                messageDiv.innerHTML = '<div class="alert alert-success">限速设置已保存</div>';
            }
            setTimeout(() => {
                loadClientGroups();
                loadGroupMembers(groupId);
            }, 1500);
        } else {
            if (messageDiv) {
                messageDiv.innerHTML = '<div class="alert alert-danger">' + (data.msg || '保存失败') + '</div>';
            }
        }
    } catch (error) {
        if (messageDiv) {
            messageDiv.innerHTML = '<div class="alert alert-danger">保存失败: ' + error.message + '</div>';
        }
    }
}

// ========== 删除用户组 ==========
function deleteGroup(groupId) {
    showCustomConfirm('确定要删除这个用户组吗?组内的客户端不会被删除,只是移出分组。', async (confirmed) => {
        if (!confirmed) return;
        
        try {
            const data = await authFetch(`/api/client_groups/${groupId}`, {
                method: 'DELETE',
                headers: {
                    'X-CSRFToken': csrfToken
                }
            });
            
            if (data.code === 0) {
                showCustomMessage('用户组已删除');
                if (groupDetailsModal) groupDetailsModal.hide();
                loadClientGroups();
            } else {
                showCustomMessage(data.msg || '删除失败', 'error');
            }
        } catch (error) {
            showCustomMessage('删除失败: ' + error.message, 'error');
        }
    });
}

// ========== 辅助函数: HTML 转义 ==========
function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}