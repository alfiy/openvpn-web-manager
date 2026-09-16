/**
 * static/js/userManagement.js
 * 这个模块包含了用户管理的所有功能
 */
import { qs, showCustomMessage, showCustomConfirm, authFetch } from './utils.js';
import PasswordConfirm from './password-confirm.js';

// 获取模态框本身，这是我们事件绑定的目标
const userManagementModal = document.getElementById('userManagementModal');

// 统一的初始化函数，作为模块的入口
export function init() {
    // 检查模态框是否存在，如果不存在则直接返回
    if (!userManagementModal) {
        console.error('User management modal not found. Skipping initialization.');
        return;
    }

    // 我们只需要绑定一次
    if (userManagementModal.hasAttribute('data-bound')) return;
    userManagementModal.setAttribute('data-bound', 'true');

    const form = qs('#add-user-form');
    const messageDiv = qs('#add-user-message');
    const tbody = qs('#user-table-body');
    const userId = parseInt(document.body.dataset.userId);

    // 绑定模态框的显示事件
    // 当模态框被打开时，我们才去获取用户数据
    userManagementModal.addEventListener('shown.bs.modal', fetchUsers);

    // 初始化密码验证组件
    let passwordValidator = null;
    if (form) {
        passwordValidator = new PasswordConfirm(form, {
            passwordSel: '[name="password"]',
            confirmSel: '[name="confirmPassword"]'
        });
    }
    // 绑定添加用户表单
    if (form) {
        form.addEventListener('submit', async e => {
            e.preventDefault();

            const usernameInput = qs('input[name="username"]', form);
            const emailInput = qs('input[name="email"]', form);
            const passwordInput = qs('input[name="password"]', form);
            const roleInput = qs('select[name="role"]', form);

            const username = usernameInput.value.trim();
            const email = emailInput.value.trim();
            const password = passwordInput.value;
            const role = roleInput.value;

            // 先进行前端验证
            if (passwordValidator && !passwordValidator.validate()) {
                messageDiv.innerHTML = '<div class="alert alert-danger">请检查密码格式和一致性</div>';
                setTimeout(() => messageDiv.innerHTML = '', 3000);
                return;
            }

            if (!username || !email || !password) {
                messageDiv.innerHTML = '<div class="alert alert-danger">用户名、邮箱和密码不能为空</div>';
                return;
            }

            try {
                const data = await authFetch('/add_users', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, email, password, role })
                });

                    if (data.status !== 'success') {
                    console.log("data error", data);
                    // 如果后端返回了 message，则使用它，否则使用默认信息
                    throw new Error(data.message || '未知错误');
    }
                const cls = 'alert-success';
                messageDiv.innerHTML = `<div class="alert ${cls}">${data.message}</div>`;

                form.reset();
                setTimeout(() => messageDiv.innerHTML = '', 3000);
                fetchUsers(); // 成功后刷新用户列表
                
            } catch (error) {
                // 现在 catch 块可以正确捕获并显示自定义的错误信息了
                messageDiv.innerHTML = `<div class="alert alert-danger">添加用户失败: ${error.message}</div>`;
                setTimeout(() => messageDiv.innerHTML = '', 2000);
            }
        });
    }

    async function fetchUsers() {
        const tbody = qs('#user-table-body');
        if (!tbody) return;
        
        try {
            const data = await authFetch('/get_users');
            // const data = await res.json();
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
        const tbody = qs('#user-table-body');
        if (!tbody) return;
        const userId = parseInt(document.body.dataset.userId);

        if (users.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">没有用户</td></tr>';
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
                    <td>${u.email || 'N/A'}</td>
                    <td>${u.role}</td>
                    <td class="d-flex flex-wrap gap-1">${actionButtons.join('')}</td>
                </tr>`;
        }).join('');
    }

    // 事件委托处理操作按钮，绑定到模态框上
    userManagementModal.addEventListener('click', async e => {
        const target = e.target.closest('.change-role, .reset-pwd, .delete-user');
        if (!target) return;
        e.preventDefault();

        const uid = target.dataset.userId;

        // 找到当前的模态框遮罩层
        const modalBackdrop = document.querySelector('.modal-backdrop');
        
        if (target.classList.contains('change-role')) {
            const currentRole = target.dataset.currentRole;
            const newRole = currentRole === 'ADMIN' ? 'NORMAL' : 'ADMIN';

            // 临时隐藏模态框的遮罩层
            if (modalBackdrop) modalBackdrop.classList.add('d-none');

            showCustomConfirm(`确定将用户权限从 ${currentRole} 切换到 ${newRole} 吗？`, async (confirmed) => {
                // 恢复模态框的遮罩层
                if (modalBackdrop) modalBackdrop.classList.remove('d-none');
                
                if (!confirmed) return;
                try {
                    const data = await authFetch('/auth/admin/change-user-role', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ user_id: uid, new_role: newRole })
                    });
                    
                    showCustomMessage(data.message);
                    if (data.status === 'success') fetchUsers();
                } catch (error) {
                    showCustomMessage(`切换权限失败: ${error.message}`);
                }
            });
        } else if (target.classList.contains('reset-pwd')) {

            console.log('🔄 点击了重置密码按钮');
            console.log('用户ID:', uid);

            // 临时隐藏模态框的遮罩层
            if (modalBackdrop) modalBackdrop.classList.add('d-none');

            showCustomConfirm('确定要重置该用户的密码吗？', async (confirmed) => {
                // 恢复模态框的遮罩层
                if (modalBackdrop) modalBackdrop.classList.remove('d-none');

                console.log('确认结果:', confirmed);

                if (!confirmed) {
                    console.log('❌ 用户取消操作');
                    return;
                }

                 console.log('✅ 开始重置密码...');

                try {
                    const requestBody = { user_id: uid };
                    console.log('请求体:', JSON.stringify(requestBody));

                    const data = await authFetch('/auth/admin/reset-user-password', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ user_id: uid })
                    });
                    console.log('✅ 重置成功,返回数据:', data);

                    if (data.status === 'success') {
                        const pwd = data.new_password || data.data?.new_password || '';
                        showCustomMessage(
                            pwd ? `密码重置成功。\n新密码：${pwd}` : '密码重置成功。',
                            '重置密码',
                            { autoClose: false, copyText: pwd }
                        );
                        fetchUsers();
                    } else {
                        console.warn('⚠️ 后端返回非成功状态:', data);
                        // 如果失败，显示错误信息
                        showCustomMessage(`重置密码失败: ${data.message}`);
                    }
                } catch (error) {
                    console.error('❌ 重置密码捕获异常:', error);
                    console.error('错误详情:', {
                        message: error.message,
                        status: error.status,
                        data: error.data
                    });
                    showCustomMessage(`重置密码失败: ${error.message}`);
                }
            });
        } else if (target.classList.contains('delete-user')) {
            // 临时隐藏模态框的遮罩层
            if (modalBackdrop) modalBackdrop.classList.add('d-none');

            showCustomConfirm('警告：确定要删除该用户吗？此操作不可逆！', async (confirmed) => {
                // 恢复模态框的遮罩层
                if (modalBackdrop) modalBackdrop.classList.remove('d-none');
                
                if (!confirmed) return;
                try {
                    const data = await authFetch('/delete_user', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ user_id: uid })
                    });
                    
                    showCustomMessage(data.message);
                    if (data.status === 'success') fetchUsers();
                } catch (error) {
                    showCustomMessage(`删除用户失败: ${error.message}`);
                }
            });
        }
    });
}