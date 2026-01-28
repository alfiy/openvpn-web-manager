#!/bin/bash
set -e

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

APP_USER=$USER
APP_DIR="/opt/vpnwm"
APP_PORT=8080

# TC 限速相关配置
TC_DAEMON_SCRIPT="/usr/local/sbin/vpn-tc-daemon.sh"
TC_SERVICE_FILE="/etc/systemd/system/vpn-tc-daemon.service"
TC_USERS_CONF="/etc/openvpn/tc-users.conf"
TC_ROLES_MAP="/etc/openvpn/tc-roles.map"

echo "=== VPN Web Manager 部署脚本（含 TC 限速功能）==="

echo "=== 1. 创建应用目录 ==="
sudo mkdir -p "$APP_DIR"

echo "=== 2. 同步项目文件到 $APP_DIR ==="
sudo rsync -av \
    --exclude 'venv' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.git' \
    --exclude 'deploy.sh' \
    --exclude 'deploy_with_tc.sh' \
    --exclude '*.md' \
    ./ "$APP_DIR/"
echo "✓ 文件同步完成"

echo "=== 3. 创建数据库目录和文件 ==="
DATA_DIR="$APP_DIR/data"
echo "创建数据目录：$DATA_DIR"
sudo -u "$APP_USER" mkdir -p "$DATA_DIR"

sudo chown -R "$APP_USER":"$APP_USER" "$APP_DIR"
echo "✓ 目录所有权已设置"

echo "=== 3.1 设置 /opt/vpnwm/data 权限 ==="
sudo chmod -R 750 "$DATA_DIR"
echo "✓ data 目录权限设置完成"

echo "=== 3.2 初始化数据库文件（确保属主正确）==="
DB_FILE="$DATA_DIR/vpn_users.db"
if [ ! -f "$DB_FILE" ]; then
    sudo -u "$APP_USER" touch "$DB_FILE"
    echo "✓ 数据库文件已创建：$DB_FILE"
else
    echo "✓ 数据库文件已存在：$DB_FILE"
fi

echo "=== 4. 创建虚拟环境 ==="

# 确认 Python 已安装
if ! command_exists python3; then
    echo "Python is not installed. Installing Python..."
    sudo apt update && sudo apt install -y python3
    if [ $? -ne 0 ]; then
        echo "Failed to install Python. Exiting..."
        exit 1
    fi
else
    echo "Python is already installed."
fi

PYTHON_VERSION=$(python3 --version | cut -d ' ' -f 2 | cut -d '.' -f 1-2)
echo "Detected Python version: $PYTHON_VERSION"

if ! python3 -m venv --help >/dev/null 2>&1; then
    echo "python3-venv not installed. Installing..."
    sudo apt update && sudo apt install -y python3-venv
else
    echo "python3-venv is already installed."
fi

if [ ! -d "$APP_DIR/venv" ]; then
    sudo -u "$APP_USER" python3 -m venv "$APP_DIR/venv"
    echo "✓ 虚拟环境创建完成"
else
    echo "✓ 虚拟环境已存在"
fi

echo "=== 5. 安装 Python 依赖（多镜像源容错）==="

# 定义镜像源列表
PIP_MIRRORS=(
    "https://mirrors.aliyun.com/pypi/simple/"
    "https://pypi.tuna.tsinghua.edu.cn/simple"
    "https://mirrors.ustc.edu.cn/pypi/web/simple"
    "https://pypi.mirrors.ustc.edu.cn/simple/"
    "https://pypi.org/simple"
)

# 配置 pip 信任所有主机（避免 SSL 证书问题）
PIP_CONFIG_DIR="/home/$APP_USER/.config/pip"
sudo -u "$APP_USER" mkdir -p "$PIP_CONFIG_DIR"
sudo -u "$APP_USER" tee "$PIP_CONFIG_DIR/pip.conf" > /dev/null <<EOF
[global]
trusted-host = pypi.tuna.tsinghua.edu.cn
               mirrors.aliyun.com
               mirrors.ustc.edu.cn
               pypi.mirrors.ustc.edu.cn
               pypi.org
               files.pythonhosted.org
EOF
echo "✓ pip 配置已设置"

# 尝试升级 pip
PIP_UPGRADED=false
for mirror in "${PIP_MIRRORS[@]}"; do
    echo "📦 尝试镜像: $mirror"
    if sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install --upgrade pip setuptools wheel -i "$mirror" --timeout 30; then
        PIP_UPGRADED=true
        echo "✅ pip 升级成功（使用镜像: $mirror）"
        WORKING_MIRROR="$mirror"
        break
    else
        echo "❌ 该镜像失败，尝试下一个..."
    fi
done

if [ "$PIP_UPGRADED" = false ]; then
    echo "⚠️  警告: 所有镜像升级 pip 均失败，使用现有版本继续"
    WORKING_MIRROR="${PIP_MIRRORS[0]}"
fi

# 安装项目依赖
if [ -f "$APP_DIR/requirements.txt" ]; then
    echo "📦 安装项目依赖（使用镜像: $WORKING_MIRROR）"
    
    # 尝试使用成功的镜像安装
    if sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" -i "$WORKING_MIRROR" --timeout 60; then
        echo "✓ 依赖安装完成"
    else
        echo "❌ 使用 $WORKING_MIRROR 安装失败，尝试其他镜像..."
        
        # 如果失败，遍历所有镜像尝试
        DEPS_INSTALLED=false
        for mirror in "${PIP_MIRRORS[@]}"; do
            if [ "$mirror" = "$WORKING_MIRROR" ]; then
                continue
            fi
            
            echo "🔄 尝试镜像: $mirror"
            if sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" -i "$mirror" --timeout 60; then
                DEPS_INSTALLED=true
                echo "✅ 依赖安装成功（使用镜像: $mirror）"
                break
            fi
        done
        
        if [ "$DEPS_INSTALLED" = false ]; then
            echo "❌ 错误: 所有镜像源均安装失败"
            exit 1
        fi
    fi
else
    echo "⚠ 警告: requirements.txt 不存在"
fi

echo ""
echo "==================================================================="
echo "=== 6. 配置 TC 流量控制（限速功能）==="
echo "==================================================================="

echo "=== 6.1 检查必需的系统工具 ==="
REQUIRED_TOOLS=("tc" "ip" "modprobe" "awk")
MISSING_TOOLS=()

for tool in "${REQUIRED_TOOLS[@]}"; do
    if ! command_exists "$tool"; then
        MISSING_TOOLS+=("$tool")
    fi
done

if [ ${#MISSING_TOOLS[@]} -gt 0 ]; then
    echo "⚠️  缺少以下工具: ${MISSING_TOOLS[*]}"
    echo "正在安装 iproute2 工具包..."
    sudo apt update && sudo apt install -y iproute2 kmod gawk
    echo "✓ 系统工具安装完成"
else
    echo "✓ 所有必需工具已安装"
fi

echo "=== 6.2 检查并加载 ifb 内核模块 ==="
if ! lsmod | grep -q "^ifb\b"; then
    echo "正在加载 ifb 模块..."
    sudo modprobe ifb numifbs=1 2>/dev/null || {
        echo "⚠️  警告: ifb 模块加载失败，可能需要重新编译内核"
        echo "尝试继续..."
    }
else
    echo "✓ ifb 模块已加载"
fi

# 确保 ifb 模块开机自动加载
if [ ! -f /etc/modules-load.d/ifb.conf ]; then
    echo "设置 ifb 模块开机自动加载..."
    echo "ifb" | sudo tee /etc/modules-load.d/ifb.conf > /dev/null
    echo "✓ ifb 模块已配置为开机自动加载"
fi

echo "=== 6.3 复制 TC 限速守护脚本 ==="
if [ -f "$APP_DIR/vpn-tc-daemon.sh" ]; then
    sudo cp "$APP_DIR/vpn-tc-daemon.sh" "$TC_DAEMON_SCRIPT"
    sudo chmod +x "$TC_DAEMON_SCRIPT"
    echo "✓ TC 守护脚本已复制到 $TC_DAEMON_SCRIPT"
else
    echo "⚠️  警告: vpn-tc-daemon.sh 不存在，跳过限速功能配置"
    echo "如需启用限速功能，请确保 vpn-tc-daemon.sh 在项目根目录"
fi

echo "=== 6.4 创建 TC 配置文件目录 ==="
sudo mkdir -p /etc/openvpn
sudo mkdir -p /var/log/openvpn

# 初始化 TC 配置文件（如果不存在）
if [ ! -f "$TC_USERS_CONF" ]; then
    echo "创建初始 TC 用户配置文件..."
    sudo tee "$TC_USERS_CONF" > /dev/null <<'EOF'
# 自动生成的 TC 用户限速配置
# 生成时间: 由 openvpn-web-manager 自动导出
# 格式: 用户/用户组=上行速率 下行速率

# ========== 默认配置 ==========
# 未分组客户端使用默认速率（2Mbit上行 / 5Mbit下行）

# ========== 角色定义（用户组）==========
# 示例：
# @vip=20Mbit 50Mbit
# @normal=5Mbit 10Mbit
EOF
    echo "✓ 已创建默认 TC 配置文件: $TC_USERS_CONF"
fi

if [ ! -f "$TC_ROLES_MAP" ]; then
    echo "创建初始 TC 角色映射文件..."
    sudo tee "$TC_ROLES_MAP" > /dev/null <<'EOF'
# 自动生成的客户端角色映射
# 生成时间: 由 openvpn-web-manager 自动导出
# 格式: 客户端名=@用户组名

# ========== 客户端到用户组的映射 ==========
# 示例：
# alice=@vip
# bob=@normal
EOF
    echo "✓ 已创建默认 TC 角色映射文件: $TC_ROLES_MAP"
fi

echo "=== 6.5 配置 TC 守护进程 systemd 服务 ==="
sudo tee "$TC_SERVICE_FILE" > /dev/null <<'EOF'
[Unit]
Description=OpenVPN TC Traffic Control Daemon
Documentation=man:tc(8)
After=network.target openvpn@server.service
Wants=openvpn@server.service
# 如果 OpenVPN 停止，这个服务也应该停止
BindsTo=openvpn@server.service

[Service]
Type=simple
ExecStart=/usr/local/sbin/vpn-tc-daemon.sh
ExecReload=/bin/kill -HUP $MAINPID

# 重启策略
Restart=always
RestartSec=10
StartLimitInterval=300
StartLimitBurst=5

# Watchdog 配置
WatchdogSec=30
# 脚本需要定期发送心跳，否则 systemd 会重启服务

# 资源限制
LimitNOFILE=65535
LimitNPROC=4096

# 安全加固（如需更严格可取消注释）
# ProtectSystem=strict
# ProtectHome=yes
# NoNewPrivileges=true
# PrivateTmp=yes

# 日志配置
StandardOutput=journal
StandardError=journal
SyslogIdentifier=vpn-tc-daemon

# 工作目录
WorkingDirectory=/var/log/openvpn

# 运行用户（必须是 root 才能操作 tc）
User=root
Group=root

# 环境变量
Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# KillMode
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF
echo "✓ TC 守护进程服务配置完成"

echo "=== 6.6 设置 TC 配置文件权限 ==="
sudo chmod 644 "$TC_USERS_CONF"
sudo chmod 644 "$TC_ROLES_MAP"
echo "✓ TC 配置文件权限已设置"

echo ""
echo "=== 7. 配置 Flask 应用服务 ==="
sudo tee /etc/systemd/system/vpnwm.service > /dev/null <<EOF
[Unit]
Description=VPN Web Manager
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
Environment="FLASK_ENV=production"
Environment="PYTHONUNBUFFERED=1"
ExecStart=$APP_DIR/venv/bin/gunicorn --timeout 600 -w 1 -b 0.0.0.0:$APP_PORT --access-logfile /dev/null --error-logfile - "app:app"
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
echo "✓ Flask 服务配置完成"

echo "=== 8. 配置 OpenVPN 客户端同步服务 ==="
sudo tee /etc/systemd/system/sync_openvpn_clients.service > /dev/null <<EOF
[Unit]
# Description=Sync OpenVPN Clients to DB after OpenVPN is ready
Requires=openvpn@server.service
After=openvpn@server.service
PartOf=openvpn@server.service

[Service]
Type=oneshot
User=root
WorkingDirectory=$APP_DIR

Environment="VPNWM_APP_DIR=$APP_DIR"
Environment="VPNWM_DATA_DIR=$APP_DIR/data"
Environment="OPENVPN_STATUS_FILE=/var/log/openvpn/status.log"
Environment="OPENVPN_CCD_DIR=/etc/openvpn/ccd"
Environment="OPENVPN_INDEX_TXT=/etc/openvpn/easy-rsa/pki/index.txt"

ExecStart=$APP_DIR/venv/bin/python3 sync_clients.py

LogLevelMax=notice          # 只记录 notice/warning/err/crit

#  调试时将null 改为journal
StandardOutput=null
StandardError=null

[Install]
WantedBy=multi-user.target
EOF
echo "✓ OpenVPN 同步服务配置完成"

echo "=== 9. 配置 OpenVPN 客户端同步定时器 ==="
sudo tee /etc/systemd/system/sync_openvpn_clients.timer > /dev/null <<EOF
[Unit]
Description=Run sync_openvpn_clients.service every 10 seconds

[Timer]
OnBootSec=10
OnUnitActiveSec=10
AccuracySec=1s
Unit=sync_openvpn_clients.service

[Install]
WantedBy=timers.target
EOF
echo "✓ OpenVPN 同步定时器配置完成"

echo ""
echo "=== 10. 重新加载 systemd 并启用所有服务 ==="
sudo systemctl daemon-reload

# 启用基础服务
sudo systemctl enable vpnwm
sudo systemctl enable sync_openvpn_clients.service
sudo systemctl enable sync_openvpn_clients.timer

# 启用 TC 限速服务（如果脚本存在）
if [ -f "$TC_DAEMON_SCRIPT" ]; then
    sudo systemctl enable vpn-tc-daemon.service
    echo "✓ TC 限速服务已启用"
else
    echo "⚠️  TC 守护脚本不存在，跳过服务启用"
fi

echo ""
echo "=== 11. 启动所有服务 ==="
sudo systemctl start vpnwm
sudo systemctl start sync_openvpn_clients.timer

# 启动 TC 限速服务（如果脚本存在且 OpenVPN 正在运行）
if [ -f "$TC_DAEMON_SCRIPT" ]; then
    if sudo systemctl is-active --quiet openvpn@server.service; then
        echo "正在启动 TC 限速守护进程..."
        sudo systemctl start vpn-tc-daemon.service
        sleep 2
        if sudo systemctl is-active --quiet vpn-tc-daemon.service; then
            echo "✓ TC 限速守护进程已启动"
        else
            echo "⚠️  TC 限速守护进程启动失败，请检查日志"
            echo "    查看日志: sudo journalctl -u vpn-tc-daemon.service -n 50"
        fi
    else
        echo "⚠️  OpenVPN 服务未运行，跳过 TC 限速服务启动"
        echo "    OpenVPN 启动后，TC 服务会自动启动"
    fi
fi

echo ""
echo "=== 12. 检查服务状态 ==="
echo ""
echo "--- Flask 应用 ---"
if sudo systemctl is-active --quiet vpnwm; then
    echo "✓ vpnwm 服务运行正常"
    sudo systemctl status vpnwm --no-pager -l | head -20
else
    echo "✗ vpnwm 服务启动失败"
    sudo journalctl -u vpnwm -n 30 --no-pager
fi

echo ""
echo "--- OpenVPN 同步服务 ---"
if sudo systemctl is-active --quiet sync_openvpn_clients.timer; then
    echo "✓ sync_openvpn_clients.timer 定时器运行正常"
    sudo systemctl status sync_openvpn_clients.timer --no-pager -l | head -10
else
    echo "✗ sync_openvpn_clients.timer 定时器启动失败"
    sudo journalctl -u sync_openvpn_clients.timer -n 10 --no-pager
fi

echo ""
echo "--- TC 限速服务 ---"
if [ -f "$TC_DAEMON_SCRIPT" ]; then
    if sudo systemctl is-active --quiet vpn-tc-daemon.service; then
        echo "✓ vpn-tc-daemon.service 运行正常"
        sudo systemctl status vpn-tc-daemon.service --no-pager -l | head -15
    else
        echo "⚠️  vpn-tc-daemon.service 未运行（可能是因为 OpenVPN 未启动）"
        echo "    服务状态:"
        sudo systemctl status vpn-tc-daemon.service --no-pager -l | head -10
    fi
else
    echo "⚠️  TC 守护脚本不存在，限速功能未配置"
fi

echo ""
echo "=== 13. 验证端口监听 ==="
if sudo lsof -i :$APP_PORT >/dev/null 2>&1; then
    echo "✓ Flask 应用监听端口 $APP_PORT"
else
    echo "✗ Flask 应用未监听端口 $APP_PORT"
fi

echo ""
echo "=== 14. 检查 TC 配置状态 ==="
if [ -f "$TC_DAEMON_SCRIPT" ] && sudo systemctl is-active --quiet vpn-tc-daemon.service; then
    echo "--- TC 队列规则 (tun0) ---"
    if sudo tc qdisc show dev tun0 2>/dev/null | grep -q "htb"; then
        echo "✓ tun0 TC 规则已配置"
        sudo tc qdisc show dev tun0 | head -5
    else
        echo "⚠️  tun0 TC 规则未配置（可能 tun0 设备不存在）"
    fi
    
    echo ""
    echo "--- TC 队列规则 (ifb0) ---"
    if sudo tc qdisc show dev ifb0 2>/dev/null | grep -q "htb"; then
        echo "✓ ifb0 TC 规则已配置"
        sudo tc qdisc show dev ifb0 | head -5
    else
        echo "⚠️  ifb0 TC 规则未配置（守护进程可能正在初始化）"
    fi
fi

echo ""
echo "==================================================================="
echo "=== 部署完成！==="
echo "==================================================================="
echo ""
echo "📌 访问地址:"
echo "   Flask 应用: http://127.0.0.1:$APP_PORT"
echo ""
echo "📌 TC 限速配置文件:"
echo "   用户配置: $TC_USERS_CONF"
echo "   角色映射: $TC_ROLES_MAP"
echo "   本地备份: $APP_DIR/data/tc-*.conf"
echo ""
echo "📌 常用管理命令:"
echo ""
echo "   --- Flask 应用 ---"
echo "   查看日志:    sudo journalctl -u vpnwm -f"
echo "   重启服务:    sudo systemctl restart vpnwm"
echo "   查看状态:    sudo systemctl status vpnwm"
echo ""
echo "   --- OpenVPN 同步 ---"
echo "   查看日志:    sudo journalctl -u sync_openvpn_clients.service -f"
echo "   查看定时器:  sudo systemctl status sync_openvpn_clients.timer"
echo "   手动同步:    sudo systemctl start sync_openvpn_clients.service"
echo ""
echo "   --- TC 限速服务 ---"
echo "   查看日志:    sudo journalctl -u vpn-tc-daemon.service -f"
echo "   重启服务:    sudo systemctl restart vpn-tc-daemon.service"
echo "   查看状态:    sudo systemctl status vpn-tc-daemon.service"
echo "   停止服务:    sudo systemctl stop vpn-tc-daemon.service"
echo "   启动服务:    sudo systemctl start vpn-tc-daemon.service"
echo ""
echo "   --- TC 配置查看 ---"
echo "   查看 tun0:   sudo tc qdisc show dev tun0"
echo "   查看 ifb0:   sudo tc qdisc show dev ifb0"
echo "   查看 class:  sudo tc class show dev tun0"
echo "   查看 filter: sudo tc filter show dev tun0"
echo ""
echo "   --- TC 配置清理（调试用）---"
echo "   清理所有规则: sudo tc qdisc del dev tun0 root 2>/dev/null || true"
echo "                 sudo tc qdisc del dev tun0 ingress 2>/dev/null || true"
echo "                 sudo tc qdisc del dev ifb0 root 2>/dev/null || true"
echo ""
echo "📌 重要提示:"
echo "   1. TC 限速服务会在 OpenVPN 启动后自动启动"
echo "   2. 通过 Web 界面管理用户组时，TC 配置会自动更新"
echo "   3. 如需手动编辑 TC 配置，修改后需重启 vpn-tc-daemon 服务"
echo "   4. 确保 /var/log/openvpn/status.log 文件存在且可读"
echo ""
echo "==================================================================="