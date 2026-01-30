import {authFetch} from "./utils.js";
async function loadOpenVPNStatus() {
    const badge = document.getElementById('ovpn-status-badge');
    const text = document.getElementById('ovpn-status-text');

    // ⭐ 关键：如果页面没有这个组件，直接退出
    if (!badge || !text) {
        return;
    }

    try {
        const res = await authFetch('/api/status');
        const data = await res.json();

        switch (data.status) {
            case 'running':
                text.textContent = '运行中';
                badge.className = 'badge bg-success';
                break;

            case 'installed':
                text.textContent = '已安装';
                badge.className = 'badge bg-warning text-dark';
                break;

            case 'not_installed':
            default:
                text.textContent = '未安装';
                badge.className = 'badge bg-danger';
                break;
        }

    } catch (e) {
        console.error('获取 OpenVPN 状态失败', e);
        text.textContent = '异常';
        badge.className = 'badge bg-danger';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    loadOpenVPNStatus();
    setInterval(loadOpenVPNStatus, 5000);
});
