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
import {init as PasswordConfirm } from './password-confirm.js';

/**
 * 统一绑定所有模块的事件和初始化逻辑
 * 这是一个总入口，只在页面加载时调用一次
 */
function bindAll() {
    const role = document.body.dataset.role;

    // 根据角色初始化相应的模块
    if (role === 'SUPER_ADMIN') {
        initInstallUninstall();
        initClientManagement();
        initUserManagement();
    } else if (role === 'ADMIN') {
        initClientManagement();
    } else if (role === 'USER') {
        initClientManagement();
    }

    // 可以在这里绑定全局通用的事件，例如导航栏点击事件等
    PasswordConfirm();
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

    // 启动自动刷新，这是一个全局的、与具体模块无关的功能
    startAutoRefresh();
});