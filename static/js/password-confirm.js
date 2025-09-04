/**
 * PasswordConfirm  v1.0
 * 通用的「密码 + 确认密码」一致性校验组件
 * @param {HTMLFormElement} form      要校验的表单
 * @param {Object} opts               配置项
 */
function PasswordConfirm(form, opts = {}) {
  // 参数合并
  const cfg = Object.assign({
    passwordSel   : '[name="password"]',
    confirmSel    : '[name="confirmPassword"]',
    mismatchMsg   : '两次输入的密码不一致',
    errorClass    : 'is-invalid',
    msgClass      : 'invalid-feedback',
    liveCheck     : true,          // 实时校验
    beforeSubmit  : true,          // 提交前再校验一次
    onError       : null,          // 自定义错误回调
    onSuccess     : null           // 自定义成功回调
  }, opts);

  // 获取节点
  const pwd   = form.querySelector(cfg.passwordSel);
  const cpwd  = form.querySelector(cfg.confirmSel);
  if (!pwd || !cpwd) return;

  // 创建/获取提示节点
  let tip = cpwd.parentNode.querySelector(`.${cfg.msgClass}`);
  if (!tip) {
    tip = document.createElement('div');
    tip.className = cfg.msgClass;
    tip.style.display = 'none';
    cpwd.parentNode.appendChild(tip);
  }
  tip.textContent = cfg.mismatchMsg;

  // 校验逻辑
  const validate = () => {
    const ok = pwd.value === cpwd.value;
    if (ok) {
      cpwd.classList.remove(cfg.errorClass);
      tip.style.display = 'none';
      cfg.onSuccess && cfg.onSuccess(pwd, cpwd);
    } else {
      cpwd.classList.add(cfg.errorClass);
      tip.style.display = 'block';
      cfg.onError && cfg.onError(pwd, cpwd);
    }
    return ok;
  };

  // 绑定事件
  if (cfg.liveCheck) {
    [pwd, cpwd].forEach(el => el.addEventListener('input', validate));
  }
  if (cfg.beforeSubmit) {
    form.addEventListener('submit', e => {
      if (!validate()) {
        e.preventDefault();
        cpwd.focus();
      }
    });
  }
}

/* 自动初始化：页面上所有带 data-pwd-confirm 的表单 */
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('form[data-pwd-confirm]').forEach(form => {
    // 通过 data-* 属性传参
    const opts = {};
    if (form.dataset.pwdConfirmMsg)  opts.mismatchMsg = form.dataset.pwdConfirmMsg;
    if (form.dataset.pwdLive === 'false') opts.liveCheck = false;
    PasswordConfirm(form, opts);
  });
});

export function init(){
  PasswordConfirm();
}