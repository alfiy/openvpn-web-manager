/**
 * refresh.js
 * 统一管理客户端管理页面的自动刷新、用户活跃检测、搜索恢复逻辑
 */
import { authFetch, qs } from './utils.js';
import { currentPage, loadClients } from './clientManagement.js';
import { bindInstall, bindUninstall } from './installUninstall.js';
import { bindRestart } from './restart.js';

// ---------------- 用户活跃/搜索恢复 ----------------
let lastUserActionTime = Date.now();
const INACTIVE_TIMEOUT = 30000; // 30 秒无操作

/**
 * 标记用户活跃（输入、点击、翻页等操作时调用）
 */
export function markUserActive() {
    lastUserActionTime = Date.now();
}

// 每秒检查用户是否超过 30 秒未操作
setInterval(() => {
    const now = Date.now();
    if (now - lastUserActionTime > INACTIVE_TIMEOUT) {
        // 恢复默认搜索条件
        setCurrentSearchQuery('');
        const searchInput = document.querySelector('#client-search');
        if (searchInput) searchInput.value = '';

        // 刷新第一页默认列表
        loadClients(1, '');
        markUserActive(); // 防止连续重复刷新
    }
}, 1000);

// ---------------- 自动刷新控制 ----------------
let autoRefreshInterval = null;

// 全局保存当前搜索关键字
let currentSearchQuery = '';

// ---------------- 页面局部刷新 ----------------
export function refreshPage(currentUserRole) {
    // 刷新 OpenVPN 状态
    refreshOpenVPNStatus(currentUserRole)
        .then(() => {
            // 确保 DOM 已更新后绑定事件
            bindInstall();
            bindUninstall();
            bindRestart();
        })
        .catch(err => console.error("刷新OpenVPN状态失败:", err));

    // 刷新客户端列表
    loadClients(currentPage, currentSearchQuery || '');
}


/**
 * 设置当前搜索关键字，外部可调用
 * @param {string} q
 */
export function setCurrentSearchQuery(q) {
    currentSearchQuery = (typeof q === 'string') ? q : '';
}

/**
 * 启动自动刷新（不会重复启动）
 * @param {number} ms 刷新间隔，毫秒
 * @param {string} currentUserRole 当前用户角色
 */
export function startAutoRefresh(ms = 10000, currentUserRole) {
    if (autoRefreshInterval) return; // 已经启动则不重复
    autoRefreshInterval = setInterval(() => {
        if (!document.hidden) {
            refreshPage(currentUserRole);
        }
    }, ms);
}

/**
 * 停止自动刷新
 */
export function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
    }
}

// ---------------- OpenVPN 状态刷新 ----------------
async function refreshOpenVPNStatus(currentUserRole) {
    try {
        const statusData = await authFetch('/api/status', { returnRawResponse: false });

        const statusBody = qs('#openvpn-status-body');
        const actionsContainer = qs('#openvpn-status-actions');
        if (actionsContainer) actionsContainer.innerHTML = '';

        const status = statusData.status;
        let statusText = '';
        if (status === 'running') statusText = '<span class="status-indicator status-running"></span> 正在运行';
        else if (status === 'installed') statusText = '<span class="status-indicator status-installed"></span> 已安装但未运行';
        else statusText = '<span class="status-indicator status-not-installed"></span> OpenVPN未安装';

        if (statusBody) statusBody.innerHTML = `<p>${statusText}</p>`;

        // 根据角色显示按钮
        if (currentUserRole === 'SUPER_ADMIN' && actionsContainer) {
            if (status === 'not_installed') actionsContainer.innerHTML += `<button id="install-btn" class="btn btn-primary">安装OpenVPN</button>`;
            if (status === 'running') actionsContainer.innerHTML += `<button id="restart-btn" class="btn btn-warning me-2">重启</button>`;
            if (status === 'running' || status === 'installed') actionsContainer.innerHTML += `<button id="uninstall-btn" class="btn btn-danger">卸载</button>`;
        }
    } catch (err) {
        console.error("无法获取OpenVPN状态:", err);
    }
}

// ---------------- 系统监控数据刷新 ----------------
async function refreshSystemMonitor(currentUserRole) {
    try {
        // 获取 OpenVPN 状态（使用原来的端点）
        const statusData = await authFetch('/api/openvpn_status', { 
            method: 'GET',
            returnRawResponse: false 
        });

        // 更新 OpenVPN 状态（使用原来的函数）
        updateOpenVPNStatusLegacy(statusData, currentUserRole);
        
        // 获取系统资源使用情况
        const sysData = await authFetch('/api/system_stats', { 
            method: 'GET' 
        });
        
        // 更新 CPU、内存、磁盘
        updateCPU(sysData.cpu_percent);
        updateMemory(sysData.memory);
        updateDisk(sysData.disk);

    } catch (err) {
        console.error("刷新系统监控失败:", err);
        
        // 错误时显示友好的提示
        const statusBody = qs('#openvpn-status-body');
        if (statusBody) {
            statusBody.innerHTML = '<span class="text-danger"><i class="fa-solid fa-triangle-exclamation me-2"></i>连接失败</span>';
        }
    }
}

/**
 * 恢复原来的 OpenVPN 状态更新逻辑
 * 保持与原有代码兼容
 */
function updateOpenVPNStatusLegacy(statusData, currentUserRole) {
    const statusBody = qs('#openvpn-status-body');
    const actionsContainer = qs('#openvpn-status-actions');
    
    if (!statusBody) return;
    
    // 清空操作按钮容器
    if (actionsContainer) actionsContainer.innerHTML = '';

    // 获取状态（兼容不同的返回格式）
    const status = statusData.status || statusData;
    
    let statusText = '';
    let statusClass = '';
    
    if (status === 'running') {
        statusText = '<span class="status-indicator status-running"></span> OpenVPN正在运行';
        statusClass = 'text-success';
    } else if (status === 'installed') {
        statusText = '<span class="status-indicator status-installed"></span> OpenVPN已安装但未运行';
        statusClass = 'text-warning';
    } else if (status === 'not_installed') {
        statusText = '<span class="status-indicator status-not-installed"></span> OpenVPN未安装';
        statusClass = 'text-secondary';
    } else {
        statusText = '<span class="status-indicator status-unknown"></span> 状态未知';
        statusClass = 'text-muted';
    }

    statusBody.innerHTML = `<p class="${statusClass} mb-2">${statusText}</p>`;

    // 根据角色显示操作按钮（SUPER_ADMIN 才能操作）
    if (currentUserRole === 'SUPER_ADMIN' && actionsContainer) {
        const buttons = [];
        
        if (status === 'not_installed') {
            buttons.push(`<button id="install-btn" class="btn btn-primary btn-sm"><i class="fa-solid fa-download me-1"></i>安装OpenVPN</button>`);
        }
        if (status === 'running') {
            buttons.push(`<button id="restart-btn" class="btn btn-warning btn-sm me-2"><i class="fa-solid fa-rotate me-1"></i>重启OpenVPN</button>`);
        }
        if (status === 'running' || status === 'installed') {
            buttons.push(`<button id="uninstall-btn" class="btn btn-danger btn-sm"><i class="fa-solid fa-trash me-1"></i>卸载OpenVPN</button>`);
        }
        
        actionsContainer.innerHTML = buttons.join('');
        
        // 绑定事件（调用原来的 bind 函数）
        bindInstall();
        bindUninstall();
        bindRestart();
    }
}

// CPU、内存、磁盘更新函数保持不变
function updateCPU(percent) {
    const usageEl = qs('#cpu-usage');
    const barEl = qs('#cpu-bar');
    
    if (usageEl) usageEl.textContent = (percent || 0) + '%';
    if (barEl) {
        barEl.style.width = (percent || 0) + '%';
        barEl.classList.remove('bg-success', 'bg-warning', 'bg-danger');
        if (percent < 50) barEl.classList.add('bg-success');
        else if (percent < 80) barEl.classList.add('bg-warning');
        else barEl.classList.add('bg-danger');
    }
}

function updateMemory(memData) {
    const percentEl = qs('#mem-percent');
    const usageEl = qs('#mem-usage');
    const barEl = qs('#mem-bar');
    
    if (percentEl) percentEl.textContent = (memData?.percent || 0) + '%';
    if (usageEl) usageEl.textContent = `${memData?.used || '-'} / ${memData?.total || '-'}`;
    if (barEl) barEl.style.width = (memData?.percent || 0) + '%';
}

function updateDisk(diskData) {
    const percentEl = qs('#disk-percent');
    const usageEl = qs('#disk-usage');
    const barEl = qs('#disk-bar');
    
    if (percentEl) percentEl.textContent = (diskData?.percent || 0) + '%';
    if (usageEl) usageEl.textContent = `${diskData?.used || '-'} / ${diskData?.total || '-'}`;
    if (barEl) barEl.style.width = (diskData?.percent || 0) + '%';
}

// ---------------- 页面用户操作事件 ----------------
// 所有用户操作都应调用 markUserActive() 来更新活跃状态
document.addEventListener('click', markUserActive);
document.addEventListener('keydown', markUserActive);
document.addEventListener('mousemove', markUserActive);
document.addEventListener('touchstart', markUserActive);
