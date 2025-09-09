// changePassword.js
import { qs, showCustomMessage } from './utils.js'; 
import PasswordConfirm from './password-confirm.js';
import { authFetch } from './utils.js'; // 注意：这里从 utils.js 导入 authFetch

function ChangePassword() {
    const form = qs('#change-pwd-form');
    if (!form || form.hasAttribute('data-bound')) return;
    form.setAttribute('data-bound', 'true');

    // 实例化密码确认模块
    const pwdConfirm = new PasswordConfirm(form, {
        passwordSel: '[name="new_pwd"]',
        confirmSel: '[name="confirm_pwd"]',
        liveCheck: true, // 启用实时校验
    });

    // 监听表单提交事件
    form.addEventListener('submit', function(event) {
        event.preventDefault(); // 阻止表单的默认提交行为

        // 使用 PasswordConfirm 模块进行校验
        if (pwdConfirm.validate()) {
            // 如果校验通过，执行密码修改逻辑
            const oldPwd = qs('[name="old_pwd"]', form).value;
            const newPwd = qs('[name="new_pwd"]', form).value;

            // 调用 authFetch 发送请求
            authFetch('/change_password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    old_pwd: oldPwd,
                    new_pwd: newPwd
                })
            })
            .then(data => {
                // 根据后端返回的数据进行处理
                if (data.status === 'success') {
                    showCustomMessage(data.message || '密码修改成功！', '成功');
                    // 假设你使用 Bootstrap
                    const myModal = bootstrap.Modal.getInstance(qs('#changePwdModal'));
                    if (myModal) {
                        myModal.hide();
                    }
                    form.reset();
                } else {
                    showCustomMessage(data.message || '密码修改失败，请重试！', '错误');
                }
            })
            .catch(error => {
                // 捕获网络错误或 HTTP 错误
                console.error('密码修改失败:', error);
                showCustomMessage('网络或服务器错误，请稍后重试！', '错误');
            });
        }
    });
}

export function init() {
    ChangePassword();
}