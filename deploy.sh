#!/bin/bash
set -e

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

APP_USER=$USER
APP_DIR="/opt/vpnwm"
APP_PORT=8080

echo "=== VPN Web Manager 部署脚本 ==="

echo "=== 1. 创建应用目录 ==="
sudo mkdir -p "$APP_DIR"

echo "=== 2. 同步项目文件到 $APP_DIR ==="
sudo rsync -av \
    --exclude 'venv' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.git' \
    --exclude '.env' \
    --exclude 'deploy.sh' \
    --exclude '*.md' \
    ./ "$APP_DIR/"
echo "✓ 文件同步完成"

echo "=== 3.创建数据库目录和文件 ==="
DATA_DIR="$APP_DIR/data"
echo "创建数据目录：$DATA_DIR"
sudo -u "$APP_USER" mkdir -p "$DATA_DIR"

sudo chown -R "$APP_USER":"$APP_USER" "$APP_DIR"
echo "✓ 目录所有权已设置"

echo "=== 3.1 设置 /opt/vpnwm/data 权限（新增） ==="
sudo chmod -R 750 "$DATA_DIR"
echo "✓ data 目录权限设置完成"

echo "=== 3.2 初始化数据库文件（确保属主正确） ==="
DB_FILE="$DATA_DIR/vpn_users.db"
if [ ! -f "$DB_FILE" ]; then
    sudo -u "$APP_USER" touch "$DB_FILE"
    echo "✓ 数据库文件已创建：$DB_FILE"
else
    echo "✓ 数据库文件已存在：$DB_FILE"
fi

echo "✓ OpenVPN 组权限设置完成"

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

echo "=== 5. 安装 Python 依赖（多镜像源容错） ==="

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

echo "=== 6. 配置 Flask 应用服务 ==="
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
ExecStart=$APP_DIR/venv/bin/gunicorn --timeout 600 -w 1 -b 0.0.0.0:$APP_PORT --access-logfile - --error-logfile - "app:app"
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
echo "✓ Flask 服务配置完成"

echo "=== 7. 配置 OpenVPN 客户端同步服务 ==="
sudo tee /etc/systemd/system/sync_openvpn_clients.service > /dev/null <<EOF
[Unit]
Description=Sync OpenVPN Clients to DB after OpenVPN is ready
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
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
echo "✓ OpenVPN 同步服务配置完成"

echo "=== 8. 配置 OpenVPN 客户端同步定时器 ==="
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

sudo systemctl daemon-reload
sudo systemctl enable vpnwm
sudo systemctl enable sync_openvpn_clients.service
sudo systemctl enable sync_openvpn_clients.timer
sudo systemctl start vpnwm
sudo systemctl start sync_openvpn_clients.timer

echo "=== 9. 检查服务状态 ==="
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
echo "=== 10. 验证端口监听 ==="
if sudo lsof -i :$APP_PORT >/dev/null 2>&1; then
    echo "✓ Flask 应用监听端口 $APP_PORT"
else
    echo "✗ Flask 应用未监听端口 $APP_PORT"
fi

echo ""
echo "=== 部署完成！==="
echo "Flask 应用: http://127.0.0.1:$APP_PORT"

echo ""
echo "常用命令:"
echo "  查看 Flask 日志:  sudo journalctl -u vpnwm -f"
echo "  重启 Flask:      sudo systemctl restart vpnwm"
echo "  查看同步服务日志:          sudo journalctl -u sync_openvpn_clients.service -f"
echo "  查看同步定时器状态:        sudo systemctl status sync_openvpn_clients.timer"
echo "  手动运行同步服务:          sudo systemctl start sync_openvpn_clients.service"
echo "  停止同步定时器:            sudo systemctl stop sync_openvpn_clients.timer"
echo "  启动同步定时器:            sudo systemctl start sync_openvpn_clients.timer"