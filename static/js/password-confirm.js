/**
 * PasswordConfirm v1.1
 * 通用的「密码 + 确认密码」一致性校验组件
 * @param {HTMLFormElement} form        要校验的表单
 * @param {Object} opts                配置项
 */
function PasswordConfirm(form, opts = {}) {
    // 参数合并
    const cfg = Object.assign({
        passwordSel      : '[name="password"]',
        confirmSel       : '[name="confirmPassword"]',
        mismatchMsg      : '两次输入的密码不一致',
        passwordStrengthMsg: '密码需包含大小写字母、数字和特殊字符（@!%?&），至少8位',
        passwordPattern  : /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@!%?&])[A-Za-z\d@$!%?&]{8,}$/,
        errorClass       : 'is-invalid',
        msgClass         : 'invalid-feedback',
        liveCheck        : true,           // 实时校验
        beforeSubmit     : true,           // 提交前再校验一次
        onError          : null,           // 自定义错误回调
        onSuccess        : null            // 自定义成功回调
    }, opts);

    // 获取节点
    const pwd   = form.querySelector(cfg.passwordSel);
    const cpwd  = form.querySelector(cfg.confirmSel);
    if (!pwd || !cpwd) return;

    // 创建/获取密码强度提示节点
    let pwdTip = pwd.parentNode.querySelector(`.${cfg.msgClass}`);
    if (!pwdTip) {
        pwdTip = document.createElement('div');
        pwdTip.className = cfg.msgClass;
        pwdTip.style.display = 'none';
        pwd.parentNode.appendChild(pwdTip);
    }
    pwdTip.textContent = cfg.passwordStrengthMsg;

    // 创建/获取确认密码不一致提示节点
    let cpwdTip = cpwd.parentNode.querySelector(`.${cfg.msgClass}`);
    if (!cpwdTip) {
        cpwdTip = document.createElement('div');
        cpwdTip.className = cfg.msgClass;
        cpwdTip.style.display = 'none';
        cpwd.parentNode.appendChild(cpwdTip);
    }
    cpwdTip.textContent = cfg.mismatchMsg;


    // 校验逻辑
    const validate = () => {
        // 1. 校验密码格式
        const isPwdValid = cfg.passwordPattern.test(pwd.value);
        if (!isPwdValid) {
            pwd.classList.add(cfg.errorClass);
            pwdTip.style.display = 'block';
            cpwd.classList.remove(cfg.errorClass);
            cpwdTip.style.display = 'none';
            return false;
        } else {
            pwd.classList.remove(cfg.errorClass);
            pwdTip.style.display = 'none';
        }

        // 2. 校验两次密码是否一致
        const isMatch = pwd.value === cpwd.value;
        if (isMatch) {
            cpwd.classList.remove(cfg.errorClass);
            cpwdTip.style.display = 'none';
            cfg.onSuccess && cfg.onSuccess(pwd, cpwd);
        } else {
            cpwd.classList.add(cfg.errorClass);
            cpwdTip.style.display = 'block';
            cfg.onError && cfg.onError(pwd, cpwd);
        }
        
        return isPwdValid && isMatch;
    };

    // 绑定事件
    if (cfg.liveCheck) {
        [pwd, cpwd].forEach(el => el.addEventListener('input', validate));
    }
    if (cfg.beforeSubmit) {
        form.addEventListener('submit', e => {
            if (!validate()) {
                e.preventDefault();
                // 焦点定位到第一个不合法的输入框
                if (!cfg.passwordPattern.test(pwd.value)) {
                    pwd.focus();
                } else {
                    cpwd.focus();
                }
            }
        });
    }
}

/**
 * 统一的初始化入口
 * 在 main.js 中被调用
 */
export function init() {
    document.querySelectorAll('form[data-pwd-confirm]').forEach(form => {
        // 通过 data-* 属性传参
        const opts = {};
        if (form.dataset.pwdConfirmMsg) opts.mismatchMsg = form.dataset.pwdConfirmMsg;
        if (form.dataset.pwdLive === 'false') opts.liveCheck = false;
        if (form.dataset.pwdStrengthMsg) opts.passwordStrengthMsg = form.dataset.pwdStrengthMsg;
        if (form.dataset.pwdPattern)      opts.passwordPattern = new RegExp(form.dataset.pwdPattern);

        // 调用核心函数
        PasswordConfirm(form, opts);
    });
}