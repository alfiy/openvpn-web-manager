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
pip install --upgrade flask flask-session werkzeug -i https://pypi.tuna.tsinghua.edu.cn/simple

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


# ----------------------------------------------------------
# 为运行 Web 服务的用户配置完整的免密 sudo 权限
# ----------------------------------------------------------
# # 允许手动指定运行用户（默认当前用户）
# WEB_USER=${WEB_USER:-$(whoami)}
# SUDOERS_FILE="/etc/sudoers.d/openvpn-utils"
# # 所有接口会用到的 sudo 命令（去重、按字母排序）
# COMMANDS=(
#     "/bin/bash"
#     "/bin/cat"
#     "/bin/chmod"
#     "/bin/cp"
#     "/bin/find"
#     "/bin/mkdir"
#     "/bin/rm"
#     "/bin/sed"
#     "/bin/systemctl daemon-reload"
#     "/bin/systemctl disable iptables-openvpn"
#     "/bin/systemctl disable openvpn@server"
#     "/bin/systemctl is-active openvpn@server"
#     "/bin/systemctl reload openvpn@server"
#     "/bin/systemctl restart openvpn@server"
#     "/bin/systemctl start openvpn@server"
#     "/bin/systemctl stop iptables-openvpn"
#     "/bin/systemctl stop openvpn@server"
#     "/bin/test -e /etc/openvpn/server.conf"
#     "/etc/openvpn/easy-rsa/easyrsa --batch revoke"
#     "/etc/openvpn/easy-rsa/easyrsa gen-crl"
#     "/usr/bin/apt-get remove --purge -y openvpn"
#     "/usr/bin/hostname -I"
#     "/usr/bin/ip route get 8.8.8.8"
#     "/usr/bin/killall -SIGUSR1 openvpn"
#     "/usr/bin/nc"
#     "/usr/bin/netcat"
#     "/usr/bin/tail"
#     "/usr/bin/head"
# )

# # 生成临时文件
# TMP=$(mktemp)
# for cmd in "${COMMANDS[@]}"; do
#     echo "$WEB_USER ALL=(ALL) NOPASSWD: $cmd" >> "$TMP"
# done

# # 只有内容变化时才替换
# if ! cmp -s "$TMP" "$SUDOERS_FILE"; then
#     echo "授予 $WEB_USER 完整的免密 sudo 权限..."
#     sudo install -m 440 "$TMP" "$SUDOERS_FILE"
#     echo "权限已写入 $SUDOERS_FILE"
# else
#     echo "sudoers 权限已存在，跳过。"
# fi
# rm -f "$TMP"
# ----------------------------------------------------------

# 运行 Flask 应用
echo "Running Flask application..."
python "$SCRIPT_DIR/app.py"

