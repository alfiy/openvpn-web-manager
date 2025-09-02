/**
 * 这个模块处理自动刷新逻辑，并依赖于 clientManagement.js 中的 load 函数。
 */
import { authFetch, qs } from './utils.js';

let autoRefreshInterval = null;

/**
 * 局部刷新页面内容
 */
export function refreshPage() {
    return authFetch('/')
        .then(r => r.text())
        .then(html => {
            const p = new DOMParser(), doc = p.parseFromString(html, 'text/html');
            const scroll = window.scrollY;
            const cur = qs('.card:first-child .card-body');
            const next = doc.querySelector('.card:first-child .card-body');
            if (cur && next) cur.innerHTML = next.innerHTML;
            window.scrollTo(0, scroll);
            
        })
        .catch(console.error);
}

/**
 * 启动自动刷新
 * @param {number} ms
 */
export function startAutoRefresh(ms = 10000) {
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