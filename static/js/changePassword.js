// changePassword.js
import { qs, showCustomMessage } from './utils.js';
import PasswordConfirm from './password-confirm.js';
import { authFetch } from './utils.js';

function ChangePassword() {
    const form = qs('#change-pwd-form');
    if (!form || form.hasAttribute('data-bound')) return;
    form.setAttribute('data-bound', 'true');

    const pwdConfirm = new PasswordConfirm(form, {
        passwordSel: '[name="new_pwd"]',
        confirmSel: '[name="confirm_pwd"]',
        liveCheck: true,
    });

    form.addEventListener('submit', function(event) {
        event.preventDefault();

        if (pwdConfirm.validate()) {
            const oldPwd = qs('[name="old_pwd"]', form).value;
            const newPwd = qs('[name="new_pwd"]', form).value;

            authFetch('/change_password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    old_pwd: oldPwd,
                    new_pwd: newPwd
                })
            })
            .then(data => {
                // 现在，.then() 只处理成功的响应
                showCustomMessage(data.message || '密码修改成功！', '成功');
                const myModal = bootstrap.Modal.getInstance(qs('#changePwdModal'));
                if (myModal) {
                    myModal.hide();
                }
                form.reset();
            })
            .catch(error => {
                // .catch() 现在可以捕获所有的非 2xx 响应，包括 400
                console.error('密码修改失败:', error);

                // 优先使用后端返回的错误信息
                const message = error.data?.message || '网络或服务器错误，请稍后重试！';
                showCustomMessage(message, '错误');
            });
        }
    });
}

export function init() {
    ChangePassword();
}