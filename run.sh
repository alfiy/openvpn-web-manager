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
    echo "python-venv not installed. Installing..."
    sudo apt update && sudo apt install -y python3-venv
else
    echo "python-venv is already installed."
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

# 检查 pip 版本是否足够，否则升级
REQUIRED_PIP_VERSION=23.0
CURRENT_PIP_VERSION=$(pip --version | awk '{print $2}')
if [ "$(printf '%s\n' "$REQUIRED_PIP_VERSION" "$CURRENT_PIP_VERSION" | sort -V | head -n1)" = "$REQUIRED_PIP_VERSION" ]; then
    echo "pip version ($CURRENT_PIP_VERSION) is sufficient, skipping upgrade."
else
    echo "Upgrading pip, setuptools, and wheel..."
    python -m pip install --upgrade --ignore-installed pip setuptools wheel --break-system-packages
fi
pip --version

# 安装依赖（仅安装缺失的）
echo "Checking and installing dependencies..."
pip install --upgrade --no-cache-dir -r "$SCRIPT_DIR/requirements.txt" --break-system-packages
echo "Dependencies installed successfully."

# 检查 OpenVPN 安装脚本
SCRIPT_TARGET="$SCRIPT_DIR/ubuntu-openvpn-install.sh"
if [ ! -f "$SCRIPT_TARGET" ]; then
    echo "Error: ubuntu-openvpn-install.sh not found!"
    exit 1
else
    chmod +x "$SCRIPT_TARGET"
    echo "ubuntu-openvpn-install.sh exists."
fi

# 运行 Flask 应用
echo "Running Flask application..."
python "$SCRIPT_DIR/app.py"

