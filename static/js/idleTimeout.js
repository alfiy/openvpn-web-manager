/**
 * 管理页空闲超时：15 分钟无鼠标/键盘/触摸操作则退出登录。
 * 仪表盘自动刷新不算用户操作，不重置计时。
 */
const IDLE_MS = 15 * 60 * 1000;
const EVENTS = ['click', 'keydown', 'mousemove', 'mousedown', 'scroll', 'touchstart'];

export function initIdleTimeout(logoutUrl) {
    if (!logoutUrl) return;
    let timer = null;

    function leave() {
        window.location.href = logoutUrl;
    }

    function bump() {
        if (timer) clearTimeout(timer);
        timer = setTimeout(leave, IDLE_MS);
    }

    EVENTS.forEach((name) => {
        document.addEventListener(name, bump, { passive: true });
    });
    bump();
}
