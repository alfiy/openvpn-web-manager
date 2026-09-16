#!/bin/bash
# 将当前目录的 P0 代码升级到已运行的 /opt/vpnwm
# 不卸载 OpenVPN，不删除 clients / users，不重建 PKI
set -euo pipefail

APP_USER="${APP_USER:-$USER}"
APP_DIR="${APP_DIR:-/opt/vpnwm}"
DATA_DIR="$APP_DIR/data"
DB_FILE="$DATA_DIR/vpn_users.db"
BACKUP_ROOT="${BACKUP_ROOT:-$HOME/vpnwm-upgrade-backup}"
STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="$BACKUP_ROOT/$STAMP"

command_exists() { command -v "$1" >/dev/null 2>&1; }

if [ ! -f ./app.py ] || [ ! -d ./routes ] || [ ! -d ./utils ]; then
    echo "请在 P0 补丁项目根目录执行:  bash ./upgrade.sh"
    exit 1
fi

if [ ! -d "$APP_DIR" ]; then
    echo "未找到 $APP_DIR，这不像是已部署环境。全新安装请用 ./deploy.sh"
    exit 1
fi

echo "=== 1. 备份（升级前必做）==="
mkdir -p "$BACKUP_DIR"
if [ -f "$DB_FILE" ]; then
    sudo cp -a "$DB_FILE" "$BACKUP_DIR/vpn_users.db"
    if command_exists sqlite3; then
        sudo sqlite3 "$DB_FILE" ".backup '$BACKUP_DIR/vpn_users.backup.sqlite'"
    fi
    echo "✓ 数据库已备份: $BACKUP_DIR/vpn_users.db"
else
    echo "⚠️  未找到 $DB_FILE，若这是正在使用的环境请立刻停止升级"
fi
if [ -f "$APP_DIR/.env" ]; then
    sudo cp -a "$APP_DIR/.env" "$BACKUP_DIR/env"
    echo "✓ .env 已备份"
fi
if [ -d "$APP_DIR/data/session" ]; then
    sudo cp -a "$APP_DIR/data/session" "$BACKUP_DIR/session" 2>/dev/null || true
fi
# OpenVPN 证书与客户端配置（只备份，不改）
if [ -d /etc/openvpn ]; then
    sudo tar -C /etc -czf "$BACKUP_DIR/etc-openvpn.tgz" openvpn
    echo "✓ /etc/openvpn 已备份: $BACKUP_DIR/etc-openvpn.tgz"
fi
sudo chown -R "$APP_USER":"$APP_USER" "$BACKUP_DIR" 2>/dev/null || true
echo "备份目录: $BACKUP_DIR"

echo "=== 2. 停止 Web 服务（不停 OpenVPN）==="
sudo systemctl stop vpnwm || true
# 不要 stop openvpn@server，不要跑卸载

echo "=== 3. 同步代码（排除数据与密钥）==="
# 不用 deploy.sh：它会 rsync 覆盖 .env，且会重写一堆服务
sudo rsync -a \
    --exclude 'venv/' \
    --exclude 'data/' \
    --exclude '.env' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.git/' \
    --exclude 'upgrade.sh' \
    --exclude 'deploy.sh' \
    --exclude '*.md' \
    ./ "$APP_DIR/"
echo "✓ 代码已同步到 $APP_DIR（data/ 与 .env 未覆盖）"

echo "=== 4. 补 SECRET_KEY（只追加，不改已有值）==="
ENV_FILE="$APP_DIR/.env"
sudo touch "$ENV_FILE"
if ! sudo grep -q '^SECRET_KEY=' "$ENV_FILE" 2>/dev/null; then
    SK=$(openssl rand -hex 32)
    echo "SECRET_KEY=$SK" | sudo tee -a "$ENV_FILE" >/dev/null
    echo "✓ 已追加 SECRET_KEY（生产环境启动需要）"
else
    echo "✓ 保留原 SECRET_KEY"
fi
sudo chown "$APP_USER":"$APP_USER" "$ENV_FILE"
sudo chmod 600 "$ENV_FILE"

echo "=== 5. 数据目录权限 ==="
sudo mkdir -p "$DATA_DIR"
sudo chown -R "$APP_USER":"$APP_USER" "$APP_DIR"
sudo chmod 750 "$DATA_DIR"
if [ -f "$DB_FILE" ]; then
    sudo chmod 640 "$DB_FILE"
fi

echo "=== 6. 依赖（沿用原 venv）==="
if [ -x "$APP_DIR/venv/bin/pip" ]; then
    sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt" || \
        echo "⚠️  pip 安装未完全成功，可稍后手动执行"
else
    echo "⚠️  未找到 $APP_DIR/venv，请先按原方式创建虚拟环境"
fi

echo "=== 7. 更新 vpnwm.service（不重建 OpenVPN）==="
sudo tee /etc/systemd/system/vpnwm.service > /dev/null <<EOF
[Unit]
Description=VPN Web Manager
After=network.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment="FLASK_ENV=production"
Environment="PYTHONUNBUFFERED=1"
EnvironmentFile=-$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/gunicorn --timeout 600 -w 1 -b 127.0.0.1:8080 --access-logfile /dev/null --error-logfile - "app:app"
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 受限 sudo（安装/签发证书需要）
SUDOERS_FILE="/etc/sudoers.d/vpnwm"
sudo tee "$SUDOERS_FILE" > /dev/null <<SUDOEOF
Defaults:$APP_USER !requiretty
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl start openvpn@server.service
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl stop openvpn@server.service
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl restart openvpn@server.service
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl reload openvpn@server.service
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl is-active openvpn@server.service
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl status openvpn@server.service
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl disable openvpn@server.service
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl enable openvpn@server.service
$APP_USER ALL=(root) NOPASSWD: /usr/bin/systemctl start openvpn@server.service
$APP_USER ALL=(root) NOPASSWD: /usr/bin/systemctl stop openvpn@server.service
$APP_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart openvpn@server.service
$APP_USER ALL=(root) NOPASSWD: /usr/bin/systemctl reload openvpn@server.service
$APP_USER ALL=(root) NOPASSWD: /usr/bin/systemctl is-active openvpn@server.service
$APP_USER ALL=(root) NOPASSWD: /usr/bin/systemctl status openvpn@server.service
$APP_USER ALL=(root) NOPASSWD: /usr/bin/systemctl disable openvpn@server.service
$APP_USER ALL=(root) NOPASSWD: /usr/bin/systemctl enable openvpn@server.service
$APP_USER ALL=(root) NOPASSWD: /usr/bin/systemctl daemon-reload
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl daemon-reload
$APP_USER ALL=(root) NOPASSWD: /etc/openvpn/easy-rsa/easyrsa
$APP_USER ALL=(root) NOPASSWD: /usr/share/easy-rsa/easyrsa
$APP_USER ALL=(root) NOPASSWD: /bin/cp
$APP_USER ALL=(root) NOPASSWD: /usr/bin/cp
$APP_USER ALL=(root) NOPASSWD: /bin/rm
$APP_USER ALL=(root) NOPASSWD: /usr/bin/rm
$APP_USER ALL=(root) NOPASSWD: /bin/mv
$APP_USER ALL=(root) NOPASSWD: /usr/bin/mv
$APP_USER ALL=(root) NOPASSWD: /bin/chmod
$APP_USER ALL=(root) NOPASSWD: /usr/bin/chmod
$APP_USER ALL=(root) NOPASSWD: /bin/chown
$APP_USER ALL=(root) NOPASSWD: /usr/bin/chown
$APP_USER ALL=(root) NOPASSWD: /bin/mkdir
$APP_USER ALL=(root) NOPASSWD: /usr/bin/mkdir
$APP_USER ALL=(root) NOPASSWD: /bin/cat
$APP_USER ALL=(root) NOPASSWD: /usr/bin/cat
$APP_USER ALL=(root) NOPASSWD: /usr/bin/test
$APP_USER ALL=(root) NOPASSWD: /usr/bin/tee
$APP_USER ALL=(root) NOPASSWD: /usr/bin/sed
$APP_USER ALL=(root) NOPASSWD: /bin/sed
$APP_USER ALL=(root) NOPASSWD: /usr/sbin/sysctl
$APP_USER ALL=(root) NOPASSWD: /usr/bin/apt-get
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl stop iptables-openvpn
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl disable iptables-openvpn
$APP_USER ALL=(root) NOPASSWD: /usr/bin/systemctl stop iptables-openvpn
$APP_USER ALL=(root) NOPASSWD: /usr/bin/systemctl disable iptables-openvpn
$APP_USER ALL=(root) NOPASSWD: /bin/bash $APP_DIR/ubuntu-openvpn-install.sh *
SUDOEOF
sudo chmod 440 "$SUDOERS_FILE"
if ! sudo visudo -cf "$SUDOERS_FILE"; then
    echo "✗ sudoers 语法错误，已删除"
    sudo rm -f "$SUDOERS_FILE"
    exit 1
fi

sudo systemctl daemon-reload
sudo systemctl start vpnwm
sleep 2

echo "=== 8. 检查 ===="
if sudo systemctl is-active --quiet vpnwm; then
    echo "✓ vpnwm 已启动"
else
    echo "✗ vpnwm 启动失败，看日志: sudo journalctl -u vpnwm -n 80 --no-pager"
    echo "  数据备份在: $BACKUP_DIR"
    exit 1
fi

if [ -f "$DB_FILE" ] && command_exists sqlite3; then
    echo "--- 库表行数（确认客户端还在）---"
    sudo sqlite3 "$DB_FILE" "SELECT 'users=' || COUNT(*) FROM users;"
    sudo sqlite3 "$DB_FILE" "SELECT 'clients=' || COUNT(*) FROM clients;"
    sudo sqlite3 "$DB_FILE" "PRAGMA table_info(users);" | awk -F'|' '{print $2}' | grep -q must_change_password \
        && echo "✓ users.must_change_password 列已存在" \
        || echo "⚠️  列尚未出现，重启后 app 会自动 ALTER；也可看 journalctl"
fi

echo ""
echo "升级完成。OpenVPN 服务与证书目录未被改动。"
echo "备份: $BACKUP_DIR"
echo "注意:"
echo "  1. 若 admin/super_admin 仍是 admin123，登录后必须先改密"
echo "  2. 若这次新写了 SECRET_KEY，旧 Session 会失效，重新登录即可，库数据不受影响"
echo "  3. 回滚: sudo systemctl stop vpnwm && sudo cp $BACKUP_DIR/vpn_users.db $DB_FILE && 用旧代码覆盖 $APP_DIR 后 start"
echo "  4. 不要执行 Web 上的「卸载 OpenVPN」，那会删 /etc/openvpn"
