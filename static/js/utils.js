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
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    const method = options.method ? options.method.toUpperCase() : 'GET';
    
    // 如果没有 CSRF 令牌，直接抛出错误
    if (!csrfToken) {
        console.error('❌ CSRF 令牌缺失!');
        throw new Error("缺少 CSRF 令牌");
    }
    
    // 创建一个新的 Headers 对象，以避免直接修改原始 options
    const headers = new Headers(options.headers || {});
    
    // 确保设置正确的 Content-Type（如果存在请求体）
    if (method !== 'GET' && !headers.has('Content-Type') && options.body) {
        headers.set('Content-Type', 'application/json');
    }
    
    // 无论请求方法是什么，都添加 CSRF 令牌
    if (!headers.has('X-CSRFToken')) {
        headers.set('X-CSRFToken', csrfToken);
    }
    
    // 使用新的 Headers 对象进行 fetch 请求
    const fetchOptions = {
        ...options,
        headers: headers,
    };
    
    try {
        const response = await fetch(url, fetchOptions);
        
        // ⭐ 关键修改：先尝试解析 JSON，再判断错误
        let data;
        try {
            data = await response.json();
        } catch (jsonError) {
            // 如果 JSON 解析失败，说明不是标准的 API 响应
            if (!response.ok) {
                const error = new Error(`HTTP错误: ${response.status} ${response.statusText}`);
                error.status = response.status;
                throw error;
            }
            throw jsonError;
        }
        
        // ⭐ 检查后端返回的 code 字段或 HTTP 状态码
        // 优先使用 data.code，因为后端可能返回 HTTP 400 但在 JSON 中有详细错误信息
        if (!response.ok || (data.code !== undefined && data.code !== 0)) {
            console.error('❌ 请求失败:', data);
            // ⭐ 从 data.data.error 或其他字段提取错误消息
            const errorMessage = data?.data?.error || 
                                data?.error || 
                                data?.message || 
                                data?.msg || 
                                `HTTP错误: ${response.status}`;
            const error = new Error(errorMessage);
            error.status = response.status;
            error.data = data; // ⭐ 保留完整的响应数据
            throw error;
        }
        
        if (options.returnRawResponse) {
            return response;
        }
        
        return data;
    } catch (error) {
        console.error('❌ authFetch 异常:', error);
        throw error;
    }
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
    let wrapperId, customId;

    if (prefix === 'expiry') {
        wrapperId = '#expiryDateWrapper';
        customId = '#expiryCustom';
    } else if (prefix === 'modify-expiry') {
        wrapperId = '#modifyCustomDateWrapper';
        customId = '#modify-expiryCustom';
    }

    const wrapper = qs(wrapperId);
    const customRadio = qs(customId);

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
    
    // ✅ 添加标志追踪用户是否已经做出选择
    let userResponded = false;
    
    modalEl.style.zIndex = 1060; 
    
    qs('#confirmModal .modal-title').textContent = title;
    body.textContent = message;
    okBtn.classList.remove('d-none');
    
    okBtn.onclick = () => {
        userResponded = true; // ✅ 标记用户已响应
        modal.hide();
        callback(true);
    };
    
    modalEl.addEventListener('hide.bs.modal', (e) => {
        modalEl.style.zIndex = ''; 
        
        // ✅ 只有在用户未响应时才调用 callback(false)
        if (!userResponded) {
            callback(false);
        }
        
        okBtn.onclick = null;
        okBtn.classList.add('d-none');
    }, { once: true });
    
    modal.show();
}