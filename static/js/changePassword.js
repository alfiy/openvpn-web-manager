// static/js/changePassword.js
import { qs, showCustomMessage } from './utils.js';
import PasswordConfirm from './password-confirm.js';
import { authFetch } from './utils.js';

function ChangePassword() {
    const form = qs('#change-pwd-form');
    if (!form || form.hasAttribute('data-bound')) return;
    form.setAttribute('data-bound', 'true');

    // 初始化密码验证组件
    const pwdConfirm = new PasswordConfirm(form, {
        passwordSel: '[name="new_pwd"]',
        confirmSel: '[name="confirm_pwd"]',
        liveCheck: true,
    });

    // 表单提交处理
    form.addEventListener('submit', function(event) {
        event.preventDefault();

        // 前端验证
        if (!pwdConfirm.validate()) {
            return;
        }

        const oldPwd = qs('[name="old_pwd"]', form).value;
        const newPwd = qs('[name="new_pwd"]', form).value;
        const confirmPwd = qs('[name="confirm_pwd"]', form).value;

        authFetch('/auth/api/change-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                old_pwd: oldPwd,
                new_pwd: newPwd,
                confirm_pwd: confirmPwd
            })
        })
        .then(data => {
            showCustomMessage(data.message || '密码修改成功！', '成功');
            
            const myModal = bootstrap.Modal.getInstance(qs('#changePwdModal'));
            if (myModal) {
                myModal.hide();
            }
            
            form.reset();
            
            form.querySelectorAll('.is-invalid').forEach(el => {
                el.classList.remove('is-invalid');
            });
            form.querySelectorAll('.invalid-feedback').forEach(el => {
                el.style.display = 'none';
            });
        })
        .catch(error => {
            console.error('密码修改失败:', error);
            const message = error.data?.message || '网络或服务器错误，请稍后重试！';
            showCustomMessage(message, '错误');
        });
    });

    // 模态框关闭时重置表单
    const modal = qs('#changePwdModal');
    if (modal) {
        modal.addEventListener('hidden.bs.modal', () => {
            form.reset();
            form.querySelectorAll('.is-invalid').forEach(el => {
                el.classList.remove('is-invalid');
            });
            form.querySelectorAll('.invalid-feedback').forEach(el => {
                el.style.display = 'none';
            });
        });
    }
}

export function init() {
    ChangePassword();
}