/**
 * 这个模块包含了用户管理的所有功能
 */
import { qs, showCustomMessage, showCustomConfirm, authFetch } from './utils.js';

// 统一的初始化函数，作为模块的入口
export function init() {
    const card = qs('#user-management-card');
    if (!card || card.hasAttribute('data-bound')) return;
    card.setAttribute('data-bound', 'true');

    const form = qs('#add-user-form');
    const messageDiv = qs('#add-user-message');
    const tbody = qs('#user-table-body');
    const userId = parseInt(document.body.dataset.userId);

    // 绑定添加用户表单
    if (form && !form.hasAttribute('data-bound')) {
        form.setAttribute('data-bound', 'true');
        form.addEventListener('submit', async e => {
            e.preventDefault();
            const usernameInput = qs('#username');
            const passwordInput = qs('#password');
            const roleInput = qs('#role');
            const username = usernameInput.value.trim();
            const password = passwordInput.value;
            const role = roleInput.value;

            if (!username || !password) {
                messageDiv.innerHTML = '<div class="alert alert-danger">用户名和密码不能为空</div>';
                return;
            }

            try {
                const res = await authFetch('/add_user', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password, role })
                });
                const data = await res.json();
                const cls = data.status === 'success' ? 'alert-success' : 'alert-danger';
                messageDiv.innerHTML = `<div class="alert ${cls}">${data.message}</div>`;

                if (data.status === 'success') {
                    form.reset();
                    setTimeout(() => messageDiv.innerHTML = '', 3000);
                    fetchUsers(); // 成功后刷新用户列表
                }
            } catch (error) {
                messageDiv.innerHTML = `<div class="alert alert-danger">添加用户失败: ${error.message}</div>`;
            }
        });
    }

    async function fetchUsers() {
        try {
            const res = await authFetch('/get_users');
            const data = await res.json();
            if (data.status === 'success') {
                renderUsers(data.users);
            } else {
                showCustomMessage(`获取用户列表失败: ${data.message}`);
            }
        } catch (error) {
            showCustomMessage(`获取用户列表失败: ${error.message}`);
        }
    }

    function renderUsers(users) {
        if (!tbody) return;
        if (users.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center">没有用户</td></tr>';
            return;
        }

        tbody.innerHTML = users.map((u, index) => {
            // 过滤掉当前用户，防止用户删除自己
            if (u.id === userId) return ''; 

            const actionButtons = [];
            actionButtons.push(`<button class="btn btn-sm btn-info change-role" data-user-id="${u.id}" data-current-role="${u.role}">切换权限</button>`);
            actionButtons.push(`<button class="btn btn-sm btn-warning reset-pwd" data-user-id="${u.id}">重置密码</button>`);
            actionButtons.push(`<button class="btn btn-sm btn-danger delete-user" data-user-id="${u.id}">删除</button>`);

            return `
                <tr>
                    <td>${index + 1}</td>
                    <td>${u.username}</td>
                    <td>${u.role}</td>
                    <td class="d-flex flex-wrap gap-1">${actionButtons.join('')}</td>
                </tr>`;
        }).join('');
    }

    // 事件委托处理操作按钮
    card.addEventListener('click', async e => {
        const target = e.target.closest('.change-role, .reset-pwd, .delete-user');
        if (!target) return;
        e.preventDefault();

        const uid = target.dataset.userId;

        if (target.classList.contains('change-role')) {
            const currentRole = target.dataset.currentRole;
            const newRole = currentRole === 'ADMIN' ? 'USER' : 'ADMIN';
            showCustomConfirm(`确定将用户权限从 ${currentRole} 切换到 ${newRole} 吗？`, async (confirmed) => {
                if (!confirmed) return;
                try {
                    const res = await authFetch('/change_user_role', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ user_id: uid, new_role: newRole })
                    });
                    const data = await res.json();
                    showCustomMessage(data.message);
                    if (data.status === 'success') fetchUsers();
                } catch (error) {
                    showCustomMessage(`切换权限失败: ${error.message}`);
                }
            });
        } else if (target.classList.contains('reset-pwd')) {
            showCustomConfirm('确定要重置该用户的密码吗？', async (confirmed) => {
                if (!confirmed) return;
                try {
                    const res = await authFetch('/reset_user_password', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ user_id: uid })
                    });
                    const data = await res.json();
                    showCustomMessage(data.message);
                } catch (error) {
                    showCustomMessage(`重置密码失败: ${error.message}`);
                }
            });
        } else if (target.classList.contains('delete-user')) {
            showCustomConfirm('警告：确定要删除该用户吗？此操作不可逆！', async (confirmed) => {
                if (!confirmed) return;
                try {
                    const res = await authFetch('/delete_user', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ user_id: uid })
                    });
                    const data = await res.json();
                    showCustomMessage(data.message);
                    if (data.status === 'success') fetchUsers();
                } catch (error) {
                    showCustomMessage(`删除用户失败: ${error.message}`);
                }
            });
        }
    });

    // 在模块初始化时自动获取并渲染用户列表
    fetchUsers();
}