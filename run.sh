#!/bin/bash

# 判断命令是否存在
command_exists() {
    type "$1" &> /dev/null
}

# 脚本目录
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
echo "Script directory: $SCRIPT_DIR"


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
    sudo apt update && sudo apt install -y python3-venv
else
    echo "python3-venv is already installed."
fi

# 创建虚拟环境
VENV_DIR="$SCRIPT_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "Virtual environment created successfully."
else
    echo "Virtual environment already exists. Skipping creation."
fi

# 激活虚拟环境
ACTIVATE_SCRIPT="$VENV_DIR/bin/activate"
if [ ! -f "$ACTIVATE_SCRIPT" ]; then
    echo "Error: cannot find $ACTIVATE_SCRIPT"
    exit 1
fi
echo "Activating virtual environment..."
source "$ACTIVATE_SCRIPT"
echo "Virtual environment activated successfully."

# 升级 pip
echo "Upgrading pip, setuptools, and wheel (using Tsinghua mirror)..."
python -m pip install --upgrade pip setuptools wheel -i https://pypi.tuna.tsinghua.edu.cn/simple
pip --version

# 安装 Flask 及依赖
echo "Installing Flask and dependencies (using Tsinghua mirror)..."
pip install --upgrade flask flask-session werkzeug gunicorn -i https://pypi.tuna.tsinghua.edu.cn/simple

# 安装 requirements.txt 里的依赖（如果有）
REQ_FILE="$SCRIPT_DIR/requirements.txt"
if [ -f "$REQ_FILE" ]; then
    echo "Installing additional dependencies from requirements.txt (using Tsinghua mirror)..."
    pip install --upgrade --no-cache-dir -r "$REQ_FILE" -i https://pypi.tuna.tsinghua.edu.cn/simple
else
    echo "requirements.txt not found, skipping."
fi

# 检查 OpenVPN 安装脚本
SCRIPT_TARGET="$SCRIPT_DIR/ubuntu-openvpn-install.sh"
if [ ! -f "$SCRIPT_TARGET" ]; then
    echo "Error: ubuntu-openvpn-install.sh not found!"
    exit 1
else
    chmod +x "$SCRIPT_TARGET"
    echo "ubuntu-openvpn-install.sh exists."
fi

# ---------- 自动生成并启用 systemd service ----------
# 设置 PATH 环境变量，确保能找到 python 和 gunicorn
# 1. 使用 venv 中的 gunicorn 绝对路径
# 2. -w 1 表示开启1个 worker 进程 (轻量级)
# 3. -b 0.0.0.0:8080 绑定端口
# 4. "app:create_app()" 调用 app.py 中的 create_app 函数
SERVICE_NAME="vpnwm.service"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"

# 用当前目录（脚本所在位置）作为项目根
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Generating Systemd Service file at ${SERVICE_PATH}..."

# 生成 service 文件
sudo tee "$SERVICE_PATH" >/dev/null <<EOF
[Unit]
Description=OpenVPN Web Manager
After=network.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=${PROJECT_DIR}
Environment="PATH=${PROJECT_DIR}/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=${PROJECT_DIR}/venv/bin/gunicorn -w 1 -b 0.0.0.0:8080 "app:create_app()"
ExecStop=/bin/kill -INT \$MAINPID
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# 重新加载 systemd 并启动
echo "Reloading systemd daemon..."
sudo systemctl daemon-reload

echo "Enabling and starting ${SERVICE_NAME}..."
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo "✅ 服务已启动！"
echo "查看状态命令: sudo systemctl status ${SERVICE_NAME}"
echo "查看日志命令: sudo journalctl -u ${SERVICE_NAME} -f"

# 打印当前服务状态
sudo systemctl status "${SERVICE_NAME}" --no-pager

# 运行 Flask 应用(开发模式)
# echo "Running Flask application..."
# python "$SCRIPT_DIR/app.py"

