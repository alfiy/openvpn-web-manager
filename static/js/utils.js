// utils.js

/**
 * 原生选择器简写
 * @param {string} sel
 * @param {Document | HTMLElement} ctx
 * @returns {HTMLElement | null}
 */
export const qs = (sel, ctx = document) => ctx.querySelector(sel);

/**
 * 原生选择器简写（返回数组）
 * @param {string} sel
 * @param {Document | HTMLElement} ctx
 * @returns {HTMLElement[]}
 */
export const qsa = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

/**
 * 动态创建 Bootstrap 模态框的 HTML 结构
 * @param {string} id
 * @param {string} title
 * @param {string} bodyContent
 * @returns {string}
 */
const createModal = (id, title, bodyContent, includeConfirmBtn = false) => `
<div class="modal fade" id="${id}" tabindex="-1" aria-labelledby="${id}Label" aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title" id="${id}Label">${title}</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body">${bodyContent}</div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                ${includeConfirmBtn ? `<button type="button" class="btn btn-primary d-none" id="${id}-confirm-btn">确定</button>` : ''}
            </div>
        </div>
    </div>
</div>`;

// 在页面加载时，动态添加提示和确认模态框
document.addEventListener('DOMContentLoaded', () => {
    if (!qs("#custom-modal-container")) {
        const container = document.createElement('div');
        container.id = 'custom-modal-container';
        // 动态创建消息和确认模态框
        container.innerHTML = createModal('messageModal', '提示', '');
        container.innerHTML += createModal('confirmModal', '请确认', '', true); // 确认模态框需要确定按钮
        document.body.appendChild(container);
    }
});

/**
 * 带有认证功能的 Fetch 请求封装
 * @param {string} url - 请求 URL
 * @param {object} options - Fetch 请求选项
 * @returns {Promise<object>} - 返回一个 Promise，成功时解析 JSON 数据
 */
export async function authFetch(url, options = {}) {
  // 假设你从某个地方获取 CSRF 令牌，例如从 meta 标签
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');

  // 如果请求方法不是 GET，且未包含 CSRF 令牌，则添加
  if (options.method && options.method.toUpperCase() !== 'GET') {
    options.headers = {
      ...options.headers,
      'X-CSRFToken': csrfToken
    };
  }

  const response = await fetch(url, options);

  // 检查响应状态码。如果不是 2xx，则抛出错误。
  if (!response.ok) {
    // 如果响应体是 JSON，则解析并作为错误信息
    const errorData = await response.json();
    const error = new Error(errorData.message || '请求失败');
    error.status = response.status;
    error.data = errorData;
    throw error;
  }

  // 成功响应，解析 JSON
  return response.json();
}

/**
 * 验证 IPv4 地址的合法性
 * @param {string} ip
 * @returns {boolean}
 */
export function isValidIP(ip) {
    const regex = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
    return regex.test(ip);
}

/**
 * 动态切换自定义日期输入框的显示状态
 * @param {string} prefix
 */
export function toggleCustomDate(prefix) {
    const wrapper = qs(`#${prefix}CustomDateWrapper`);
    const customRadio = qs(`#${prefix}Custom`);
    if (wrapper && customRadio) {
        wrapper.classList.toggle('d-none', !customRadio.checked);
    }
}

/**
 * 显示自定义消息模态框
 * @param {string} message
 * @param {string} title
 */
export function showCustomMessage(message, title = '提示') {
    const modalEl = qs('#messageModal');
    // 使用新的 Bootstrap 实例化方法来避免重复创建和 aria-hidden 问题
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    
    qs('#messageModal .modal-title').textContent = title;
    qs('#messageModal .modal-body').textContent = message;
    
    modal.show();
}


/**
 * 显示自定义确认模态框
 * @param {string} message
 * @param {Function} callback
 * @param {string} title
 */
export function showCustomConfirm(message, callback, title = '确认操作') {
    const modalEl = qs('#confirmModal');
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    const body = qs('#confirmModal .modal-body');
    const okBtn = qs('#confirmModal-confirm-btn');

    // **关键改动: 确保确认模态框的 z-index 总是高于其他模态框**
    modalEl.style.zIndex = 1060; 

    // 确保标题和消息正确显示
    qs('#confirmModal .modal-title').textContent = title;
    body.textContent = message;
    okBtn.classList.remove('d-none');

    // 使用 .onclick 来确保每次只有一个回调函数
    okBtn.onclick = () => {
        modal.hide();
        callback(true);
    };

    // 绑定模态框隐藏事件，以处理取消操作和清理
    modalEl.addEventListener('hide.bs.modal', (e) => {
        // **关键改动: 隐藏后重置 z-index**
        modalEl.style.zIndex = ''; 

        // 如果是点击了关闭按钮，则执行取消回调
        if (e.relatedTarget && e.relatedTarget.dataset.bsDismiss) {
            callback(false);
        }
        // 清理按钮事件和显示状态，只执行一次
        okBtn.onclick = null;
        okBtn.classList.add('d-none');
    }, { once: true });
    
    modal.show();
}