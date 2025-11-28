/**
 * 这个模块处理自动刷新逻辑，并依赖于 clientManagement.js 中的 load 函数。
 */
import { authFetch, qs } from './utils.js';
import { currentPage,loadClients } from './clientManagement.js';
import { bindInstall, bindUninstall } from './installUninstall.js';
import { bindRestart } from './restart.js';

let autoRefreshInterval = null;


/**
 * 更新 OpenVPN 状态卡片和按钮。
 * @param {string} currentUserRole 当前用户的角色，例如 '超级管理员'。
 */
async function refreshOpenVPNStatus(currentUserRole) {
    try {
        const statusData = await authFetch('/api/status', { returnRawResponse: false });
        
        // 获取用于显示状态和按钮的 DOM 元素
        const statusBody = qs('#openvpn-status-body');
        const actionsContainer = qs('#openvpn-status-actions');

        // 如果找到了按钮容器，则清空它，准备重新渲染
        if (actionsContainer) {
            actionsContainer.innerHTML = '';
        }

        let statusText = '';
        const status = statusData.status;


        // 根据 OpenVPN 状态设置显示文本
        if (status === 'running') {
            statusText = '<span class="status-indicator status-running"></span> OpenVPN正在运行';
            
        } else if (status === 'installed') {
            statusText = '<span class="status-indicator status-installed"></span> OpenVPN已安装但未运行';
        } else {
            statusText = '<span class="status-indicator status-not-installed"></span> OpenVPN未安装';
        }

        // 更新状态文本
        if (statusBody) {
            statusBody.innerHTML = `<p>${statusText}</p>`;
        }

        // 核心逻辑：根据用户角色和 OpenVPN 状态动态添加按钮
        if (currentUserRole === 'SUPER_ADMIN' && actionsContainer) {
            if (status === 'not_installed') {
                const installBtn = `<button id="install-btn" class="btn btn-primary" data-bs-toggle="modal" data-bs-target="#installModal">安装OpenVPN</button>`;
                actionsContainer.innerHTML += installBtn;
            }

            if (status === 'running') { 
                const restartBtn = `<button id="restart-btn" class="btn btn-warning me-2">重启OpenVPN</button>`;
                actionsContainer.innerHTML += restartBtn;
            }

            if (status === 'running' || status === 'installed') {
                const uninstallBtn = `<button id="uninstall-btn" class="btn btn-danger">卸载OpenVPN</button>`;
                actionsContainer.innerHTML += uninstallBtn;
            }
        }
    } catch (error) {
        console.error("无法获取OpenVPN状态:", error);
    }
}


/**
 * 局部刷新页面内容 (调用各个卡片的刷新函数)。
 * @param {string} currentUserRole 当前用户的角色。
 */
export function refreshPage(currentUserRole) {
    // 刷新 OpenVPN 状态
    refreshOpenVPNStatus(currentUserRole)
        .then(() => {
            // 确保 DOM 已经更新后再绑定事件
            bindInstall();
            bindUninstall();
            bindRestart();
        })
        .catch(error => {
            console.error("刷新OpenVPN状态失败:", error);
        });
    loadClients(currentPage); // 刷新客户端列表
}

/**
 * 启动自动刷新。
 * @param {number} ms 刷新间隔，单位为毫秒。
 * @param {string} currentUserRole 当前用户的角色。
 */
export function startAutoRefresh(ms = 10000, currentUserRole) {
    stopAutoRefresh();
    autoRefreshInterval = setInterval(() => !document.hidden && refreshPage(currentUserRole), ms);
}

/**
 * 停止自动刷新。
 */
export function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
    }
}