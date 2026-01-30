/**
 * restart openvpn service
 */
import { qs,authFetch } from './utils.js'
import { refreshPage } from './refresh.js';

export function bindRestart(){
    const restartBtn = qs('#restart-btn');
    if (restartBtn) {
        restartBtn.addEventListener('click', async () => {
            // console.log('in restart btn js');
            const restartBtnText = restartBtn.innerHTML;
            restartBtn.disabled = true;
            restartBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> 正在重启...';
            try {
                await authFetch('/api/restart_openvpn', {
                    method: 'POST',
                    returnRawResponse: false
                });
                alert('OpenVPN服务已重启！');
            } catch (error) {
                console.error('重启OpenVPN失败:', error);
                alert('重启OpenVPN失败: ' + error.message);
            } finally {
                restartBtn.disabled = false;
                restartBtn.innerHTML = restartBtnText;
                refreshPage(window.currentUserRole); // 重启后刷新页面状态
            }
        });
    }

}

export function init(){
    bindRestart();
}