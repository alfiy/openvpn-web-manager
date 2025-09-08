import { qs, qsa } from './utils.js';


function ChangePassword() {
    const form = qs('#change-pwd-form');
    if (!form || form.hasAttribute('data-bound')) return;
    form.setAttribute('data-bound', 'true');

    // 依赖已在 HTML 中先加载 password-confirm.js
    PasswordConfirm(form, {
        passwordSel: '[name="password"]',
        confirmSel: '[name="confirmPassword"]',
        liveCheck: true,
        beforeSubmit: true,
        onSuccess: () => {
            const fd = new FormData(form);
            authFetch('/change_password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    old_pwd: fd.get('old_pwd'),
                    new_pwd: fd.get('password')
                })
            })
                .then(r => r.json())
                .then(d => {
                    alert(d.message || '密码修改成功！');
                    if (d.status === 'success') {
                        bootstrap.Modal.getInstance($('#changePwdModal')).hide();
                        form.reset();
                    }
                })
                .catch(error => {
                    console.error('密码修改失败:', error);
                    alert('密码修改失败，请重试！');
                });
        }
    });
}


export function init(){
  ChangePassword();
}