/**
 * PasswordConfirm v1.2
 * 通用的「密码 + 确认密码」一致性校验组件
 * @param {HTMLFormElement} form        要校验的表单
 * @param {Object} opts                配置项
 */
export default class PasswordConfirm {
    constructor(form, opts = {}) {
        // 参数合并
        this.cfg = Object.assign({
            passwordSel: '[name="password"]',
            confirmSel: '[name="confirmPassword"]',
            mismatchMsg: '两次输入的密码不一致',
            passwordStrengthMsg: '密码需包含大小写字母、数字和特殊字符（@!%?&），至少8位',
            passwordPattern: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@!%?&])[A-Za-z\d@$!%?&]{8,}$/,
            errorClass: 'is-invalid',
            msgClass: 'invalid-feedback',
            liveCheck: true,
            onError: null,
            onSuccess: null,
        }, opts);

        this.form = form;
        this.pwd = this.form.querySelector(this.cfg.passwordSel);
        this.cpwd = this.form.querySelector(this.cfg.confirmSel);
        if (!this.pwd || !this.cpwd) return;

        this.pwdTip = this._getOrCreateTip(this.pwd.parentNode, this.cfg.msgClass);
        this.pwdTip.textContent = this.cfg.passwordStrengthMsg;

        this.cpwdTip = this._getOrCreateTip(this.cpwd.parentNode, this.cfg.msgClass);
        this.cpwdTip.textContent = this.cfg.mismatchMsg;

        if (this.cfg.liveCheck) {
            this.pwd.addEventListener('input', () => this.validate());
            this.cpwd.addEventListener('input', () => this.validate());
        }
    }

    _getOrCreateTip(parent, className) {
        let tip = parent.querySelector(`.${className}`);
        if (!tip) {
            tip = document.createElement('div');
            tip.className = className;
            tip.style.display = 'none';
            parent.appendChild(tip);
        }
        return tip;
    }

    /**
     * 执行校验并返回结果
     * @returns {boolean}
     */
    validate() {
        const isPwdValid = this.cfg.passwordPattern.test(this.pwd.value);
        if (!isPwdValid) {
            this._showError(this.pwd, this.pwdTip);
            this._hideError(this.cpwd, this.cpwdTip);
            return false;
        } else {
            this._hideError(this.pwd, this.pwdTip);
        }

        const isMatch = this.pwd.value === this.cpwd.value;
        if (isMatch) {
            this._hideError(this.cpwd, this.cpwdTip);
            if (this.cfg.onSuccess) this.cfg.onSuccess(this.pwd, this.cpwd);
        } else {
            this._showError(this.cpwd, this.cpwdTip);
            if (this.cfg.onError) this.cfg.onError(this.pwd, this.cpwd);
        }

        return isPwdValid && isMatch;
    }

    _showError(el, tip) {
        el.classList.add(this.cfg.errorClass);
        tip.style.display = 'block';
    }

    _hideError(el, tip) {
        el.classList.remove(this.cfg.errorClass);
        tip.style.display = 'none';
    }
}

// 导出 init 函数，它负责找到表单并创建 PasswordConfirm 实例
export function init() {
    // console.log('password-confirm init');
    // 找到所有带有 data-validate-pwd 属性的表单
    const forms = document.querySelectorAll('form[data-pwd-confirm]');
    forms.forEach(form => {
        // console.log('password-confirm init in form');
        // 为每个找到的表单创建一个 PasswordConfirm 实例
        new PasswordConfirm(form);
    });
}