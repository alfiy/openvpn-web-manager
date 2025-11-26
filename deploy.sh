#!/bin/bash
set -e

command_exists() {
    command -v "" >/dev/null 2>&1
}

APP_USER="vpnwm"
APP_DIR="/opt/vpnwm"
APP_PORT=8080


echo "=== VPN Web Manager 部署脚本 ==="

echo "=== 1. 检查/创建应用用户 ==="
if id "$APP_USER" >/dev/null 2>&1; then
    echo "✓ 用户 $APP_USER 已存在"
else
    sudo useradd -m -s /bin/bash "$APP_USER"
    echo "✓ 用户 $APP_USER 创建完成"
fi

echo "=== 2. 创建应用目录 ==="
sudo mkdir -p "$APP_DIR"

echo "=== 3. 同步项目文件到 $APP_DIR ==="
sudo rsync -av \
    --exclude 'venv' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.git' \
    --exclude '.env' \
    ./ "$APP_DIR/"
echo "✓ 文件同步完成"

sudo chown -R "$APP_USER":"$APP_USER" "$APP_DIR"
echo "✓ 目录所有权已设置"

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

# 检测 Python 版本
PYTHON_VERSION=$(python3 --version | cut -d ' ' -f 2 | cut -d '.' -f 1-2)
echo "Detected Python version: $PYTHON_VERSION"

# 检查 venv 模块
if ! python3 -m venv --help >/dev/null 2>&1; then
    echo "python3-venv not installed. Installing..."
    sudo apt update && sudo apt install -y $PYTHON_VERSION-venv
else
    echo "python3-venv is already installed."
fi


if [ ! -d "$APP_DIR/venv" ]; then
    sudo -u "$APP_USER" python3 -m venv "$APP_DIR/venv"
    echo "✓ 虚拟环境创建完成"
else
    echo "✓ 虚拟环境已存在"
fi

echo "=== 5. 安装 Python 依赖 ==="
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install --upgrade pip setuptools wheel -i https://pypi.tuna.tsinghua.edu.cn/simple

if [ -f "$APP_DIR/requirements.txt" ]; then
    sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple

    echo "✓ 依赖安装完成"
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
Group=root
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

sudo systemctl daemon-reload
sudo systemctl enable vpnwm
sudo systemctl start vpnwm


echo "=== 7. 检查服务状态 ==="
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
echo "=== 8. 验证端口监听 ==="
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
