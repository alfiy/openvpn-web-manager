// 网络接口设置相关
import { qs, showCustomMessage, authFetch } from './utils.js';

const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
let networkInterfaceModal = null;

// 初始化网络接口设置模态框
export function initNetworkInterfaceSettings() {
    const modalEl = qs('#networkInterfaceModal');
    if (modalEl) {
        networkInterfaceModal = new bootstrap.Modal(modalEl);
    }
    
    // 绑定设置按钮点击事件
    const settingsBtn = qs('#networkInterfaceSettingsBtn');
    if (settingsBtn) {
        settingsBtn.addEventListener('click', openNetworkInterfaceModal);
    }
    
    // 绑定保存按钮
    const saveBtn = qs('#saveInterfaceBtn');
    if (saveBtn) {
        saveBtn.addEventListener('click', saveNetworkInterface);
    }
}

// 打开网络接口设置模态框
async function openNetworkInterfaceModal() {
    try {
        // 加载可用接口列表
        const response = await authFetch('/api/dashboard/network-interfaces');
        
        if (response.code === 0) {
            const interfaces = response.data.interfaces;
            const currentInterface = response.data.current;
            
            const select = qs('#interfaceSelect');
            select.innerHTML = '<option value="">-- 请选择接口 --</option>';
            
            interfaces.forEach(iface => {
                const option = document.createElement('option');
                option.value = iface.name;
                
                let displayText = iface.name;
                if (iface.ipv4) {
                    displayText += ` (${iface.ipv4})`;
                }
                if (iface.is_up) {
                    displayText += ' [运行中]';
                } else {
                    displayText += ' [已停止]';
                }
                
                option.textContent = displayText;
                
                if (iface.is_current) {
                    option.selected = true;
                }
                
                select.appendChild(option);
            });
            
            // 清空手动输入框和消息
            const input = qs('#interfaceInput');
            const messageDiv = qs('#interfaceMessage');
            if (input) input.value = '';
            if (messageDiv) messageDiv.innerHTML = '';
            
            if (networkInterfaceModal) {
                networkInterfaceModal.show();
            }
        } else {
            showCustomMessage('加载接口列表失败: ' + response.msg, 'error');
        }
    } catch (error) {
        showCustomMessage('加载接口列表失败: ' + error.message, 'error');
    }
}

// 保存网络接口设置
async function saveNetworkInterface() {
    const select = qs('#interfaceSelect');
    const input = qs('#interfaceInput');
    const messageDiv = qs('#interfaceMessage');
    
    // 优先使用手动输入，否则使用选择框
    const interfaceName = input.value.trim() || select.value;
    
    if (!interfaceName) {
        if (messageDiv) {
            messageDiv.innerHTML = '<div class="alert alert-danger">请选择或输入网络接口名称</div>';
        }
        return;
    }
    
    try {
        const response = await authFetch('/api/dashboard/network-interface', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({ interface: interfaceName })
        });
        
        if (response.code === 0) {
            if (messageDiv) {
                messageDiv.innerHTML = '<div class="alert alert-success"><i class="fa-solid fa-check-circle me-2"></i>' + response.msg + '</div>';
            }
            
            // 更新显示
            updateCurrentInterface(interfaceName);

            // ⭐ 3 秒后自动消失 success 提示
            setTimeout(() => {
                const alertEl = qs('#interfaceSuccessAlert');
                if (alertEl) {
                    alertEl.classList.add('fade');
                    alertEl.classList.remove('show');
                    alertEl.remove();
                }
            }, 3000);
            
            setTimeout(() => {
                if (networkInterfaceModal) {
                    networkInterfaceModal.hide();
                }
                
                // 刷新监控数据
                showCustomMessage('网络接口已更新，正在刷新数据...', 'success');
            }, 1500);
        } else {
            if (messageDiv) {
                messageDiv.innerHTML = '<div class="alert alert-danger"><i class="fa-solid fa-exclamation-circle me-2"></i>' + response.msg + '</div>';
            }
        }
    } catch (error) {
        if (messageDiv) {
            messageDiv.innerHTML = '<div class="alert alert-danger">保存失败: ' + error.message + '</div>';
        }
    }
}

// 更新当前接口显示
export function updateCurrentInterface(interfaceName) {
    const badge = qs('#current-interface');
    if (badge) {
        badge.textContent = interfaceName;
    }
}

// 在监控数据更新时同步更新接口显示
export function updateNetworkDisplay(networkData) {
    if (networkData.interface) {
        updateCurrentInterface(networkData.interface);
    }
}