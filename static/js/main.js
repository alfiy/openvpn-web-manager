/**
 * 这个文件负责将所有模块组合在一起，并控制页面的初始化流程
 */
import { qs, qsa } from './utils.js';
// 从 refresh.js 模块中导入自动刷新相关函数
import { startAutoRefresh } from './refresh.js';
// 从 clientManagement.js 模块中导入统一的初始化函数
import { init as initClientManagement } from './clientManagement.js';
// 从 userManagement.js 模块中导入统一的初始化函数
import { init as initUserManagement } from './userManagement.js';
// 从 installUninstall.js 模块中导入统一的初始化函数
import { init as initInstallUninstall } from './installUninstall.js';
// 可以根据需要，为其他模块创建并导入 init 函数
import { init as initPasswordConfirm } from './password-confirm.js';
import { init as ChangePassword } from './changePassword.js';

/**
 * 统一绑定所有模块的事件和初始化逻辑
 * 这是一个总入口，只在页面加载时调用一次
 */
function bindAll() {
    const role = document.body.dataset.role;
    if (role) {
        // 如果 role 存在，执行依赖角色的初始化逻辑
        const upperCaseRole = role.toUpperCase();
        if (upperCaseRole === 'SUPER_ADMIN') {
            initInstallUninstall();
            initUserManagement();
            initClientManagement();
        } else if (upperCaseRole === 'ADMIN' || upperCaseRole === 'NORMAL') {
            initClientManagement();
        }
    }
    
    // 初始化密码确认模块，这是一个通用的功能
    initPasswordConfirm();
    ChangePassword();
}

document.addEventListener('DOMContentLoaded', () => {
    const userRole = document.body.dataset.role;

    // 根据角色显示/隐藏功能
    const roleMap = {
        'SUPER_ADMIN': ['install-btn', 'uninstall-btn', 'add-client-card', 'clients-card', 'user-management-card'],
        'ADMIN': ['add-client-card', 'clients-card'],
        'USER': ['clients-card'],
    };

    // 默认隐藏所有功能卡片
    qsa('.card-main').forEach(card => card.classList.add('d-none'));

    // 根据角色显示对应的卡片
    if (roleMap[userRole]) {
        roleMap[userRole].forEach(id => {
            const element = qs('#' + id);
            if (element) element.classList.remove('d-none');
        });
    }

    // 设置日期输入框最小值（这是一个通用的初始化逻辑，可以放在这里）
    const dateInput = qs('#expiry_date');
    if (dateInput) {
        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        dateInput.min = tomorrow.toISOString().split('T')[0];
    }
    
    // 调用统一的绑定函数，启动整个应用
    bindAll();
    startAutoRefresh();
    // 启动自动刷新，只在需要它的页面上调用
    // 检查 body 标签是否有 data-page-type 属性，并且其值为 'auto-refresh'
    const pageType = document.body.dataset.pageType;
    if (pageType === 'dashboard') {
        console.log('auto refresh');
        startAutoRefresh();
    }
});