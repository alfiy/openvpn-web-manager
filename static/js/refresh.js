/**
 * 这个模块处理自动刷新逻辑，并依赖于 clientManagement.js 中的 load 函数。
 */
import { authFetch, qs } from './utils.js';
import { loadClients } from './clientManagement.js';

let autoRefreshInterval = null;

/**
 * 更新 OpenVPN 状态卡片
 */
async function refreshOpenVPNStatus() {
    try {
        const data = await authFetch('/api/status', { returnRawResponse: false });
        const statusBody = qs('#openvpn-status-body'); // 使用新的ID

        let statusText = '';
        if (data.status === 'running') {
            statusText = '<span class="status-indicator status-running"></span> OpenVPN正在运行';
        } else if (data.status === 'installed') {
            statusText = '<span class="status-indicator status-installed"></span> OpenVPN已安装但未运行';
        } else {
            statusText = '<span class="status-indicator status-not-installed"></span> OpenVPN未安装';
        }
        
        statusBody.innerHTML = `<p>${statusText}</p>`;
        
    } catch (error) {
        console.error("无法获取OpenVPN状态:", error);
    }
}

/**
 * 局部刷新页面内容 (调用各个卡片的刷新函数)
 */
export function refreshPage() {
    console.log("in refreshPage()");
    refreshOpenVPNStatus(); // 刷新 OpenVPN 状态
    loadClients();          // 刷新客户端列表
}

/**
 * 启动自动刷新
 * @param {number} ms
 */
export function startAutoRefresh(ms = 10000) {
    console.log("startAutoRefresh");
    stopAutoRefresh();
    autoRefreshInterval = setInterval(() => !document.hidden && refreshPage(), ms);
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