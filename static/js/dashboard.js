/**
 * dashboard.js
 * 只负责系统监控数据（CPU / Memory / Disk）
 * 不接管 OpenVPN 状态
 */

let dashboardTimer = null;

/* ---------------- fetch 封装（兜底 authFetch） ---------------- */

async function dashboardFetch(url, options = {}) {
    // 如果全局已经有 authFetch，直接用
    if (typeof window.authFetch === 'function') {
        return window.authFetch(url, options);
    }

    // 否则 fallback 到 fetch + CSRF
    const csrfToken = document
        .querySelector('meta[name="csrf-token"]')
        ?.getAttribute('content');

    const headers = options.headers || {};
    if (csrfToken) {
        headers['X-CSRFToken'] = csrfToken;
    }

    return fetch(url, {
        credentials: 'same-origin',
        ...options,
        headers
    });
}

/* ---------------- 工具函数 ---------------- */

function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

function setProgress(id, percent) {
    const el = document.getElementById(id);
    if (!el) return;

    const value = Math.max(0, Math.min(percent, 100));
    el.style.width = value + '%';
}

function formatGB(value) {
    if (value === undefined || value === null) return '-';
    return Number(value).toFixed(1) + ' GB';
}

/* ---------------- 核心刷新逻辑 ---------------- */

async function refreshSystemMetrics() {
    try {
        const resp = await dashboardFetch('/api/dashboard');
        if (!resp.ok) {
            console.error('[dashboard] API 返回失败:', resp.status);
            return;
        }

        const data = await resp.json();
        if (!data || !data.system) {
            console.warn('[dashboard] dashboard 数据结构异常', data);
            return;
        }

        /* -------- CPU -------- */
        if (typeof data.system.cpu === 'number') {
            setText('cpu-value', data.system.cpu.toFixed(1) + '%');
            setProgress('cpu-bar', data.system.cpu);
        }

        /* -------- Memory -------- */
        if (data.system.memory) {
            const mem = data.system.memory;

            if (typeof mem.percent === 'number') {
                setText('memory-value', mem.percent.toFixed(1) + '%');
                setProgress('memory-progress', mem.percent);
            }

            if (mem.used !== undefined && mem.total !== undefined) {
                setText(
                    'memory-detail',
                    `${formatGB(mem.used)} / ${formatGB(mem.total)}`
                );
            }
        }

        /* -------- Disk -------- */
        if (data.system.disk) {
            const disk = data.system.disk;

            if (typeof disk.percent === 'number') {
                setText('disk-usage', disk.percent.toFixed(1) + '%');
                setProgress('disk-progress', disk.percent);
            }

            if (disk.used !== undefined && disk.total !== undefined) {
                setText(
                    'disk-detail',
                    `${formatGB(disk.used)} / ${formatGB(disk.total)}`
                );
            }
        }

        /* -------- Network -------- */
        if (data.system.network) {
            const net = data.system.network;
            
            // 下载速度
            if (net.download_speed_str !== undefined) {
                setText('net-download', net.download_speed_str);
            }
            
            // 上传速度
            if (net.upload_speed_str !== undefined) {
                setText('net-upload', net.upload_speed_str);
            }
            
            // 总下载
            if (net.download_total !== undefined) {
                setText('net-total-down', net.download_total.toFixed(1) + ' MB');
            }
            
            // 总上传
            if (net.upload_total !== undefined) {
                setText('net-total-up', net.upload_total.toFixed(1) + ' MB');
            }
        }

    } catch (err) {
        console.error('[dashboard] 刷新系统监控失败:', err);
    }
}

/* ---------------- 初始化 ---------------- */

document.addEventListener('DOMContentLoaded', () => {
    refreshSystemMetrics();
    dashboardTimer = setInterval(refreshSystemMetrics, 5000);
});
