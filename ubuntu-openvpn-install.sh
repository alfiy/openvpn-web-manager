#!/bin/bash
# Ubuntu OpenVPN installer with uninstall functionality

# 获取脚本的绝对路径，这能避免相对路径带来的问题
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

# Function to check if the user is root
function isRoot() {
    if [ "$EUID" -ne 0 ]; then
        return 1
    fi
    return 0
}

# Function to check if TUN is available
function tunAvailable() {
    if [ ! -e /dev/net/tun ]; then
        return 1
    fi
    return 0
}

# Function to check OS
function checkOS() {
    if [[ ! -e /etc/debian_version ]]; then
        echo "❌ This script only supports Ubuntu systems."
        exit 1
    fi
    
    source /etc/os-release
    if [[ $ID != "ubuntu" ]]; then
        echo "❌ This script only supports Ubuntu systems."
        exit 1
    fi
    
    echo "✅ Ubuntu $VERSION_ID detected"
}

# Initial checks
function initialCheck() {
    if ! isRoot; then
        echo "❌ Sorry, you need to run this script as root."
        exit 1
    fi
    if ! tunAvailable; then
        echo "❌ TUN is not available."
        exit 1
    fi
    checkOS
}

# Function to get internal IP for NAT environment
function resolvePublicIP() {
    INTERNAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    if [[ -z "$INTERNAL_IP" ]]; then
        INTERNAL_IP=$(ip route get 8.8.8.8 2>/dev/null | grep -oP 'src \K[^ ]+')
    fi
    if [[ -z "$INTERNAL_IP" ]]; then
        INTERNAL_IP=$(ip addr show | grep 'inet ' | grep -v '127.0.0.1' | head -n1 | awk '{print $2}' | cut -d'/' -f1)
    fi
    
    if [[ -n "$INTERNAL_IP" ]]; then
        echo "$INTERNAL_IP"
    else
        echo "Failed to resolve internal IP"
        return 1
    fi
}

# 接收端口号参数，默认为1194
OPENVPN_PORT=${1:-1194}
SERVER_IP=$(resolvePublicIP)
if [[ $? -ne 0 ]]; then
    exit 1
fi

# 新增函数：从源码安装OpenVPN
function installOpenVPNFromSource() {
    echo "📦 Starting OpenVPN installation from source..."

    # 安装编译OpenVPN所需的依赖包
    apt-get update
    apt-get install -y openssl ca-certificates wget curl build-essential pkg-config libssl-dev liblzo2-dev libpam0g-dev libnl-3-dev libnl-genl-3-dev libcap-ng-dev liblz4-dev

    # 定义OpenVPN源码包路径和解压目录
    local openvpn_tgz_path="$SCRIPT_DIR/resource/openvpn-2.6.14.tar.gz"
    local openvpn_build_dir="$SCRIPT_DIR/resource/openvpn-2.6.14"

    # 检查本地源码包是否存在
    if [[ ! -f "$openvpn_tgz_path" ]]; then
        echo "❌ 本地文件 "$openvpn_tgz_path" 不存在，请检查路径或放入文件后再运行脚本。"
        exit 1
    fi
    echo "✅ 发现本地 OpenVPN 包：$openvpn_tgz_path"

    # 解压源码包并编译安装
    mkdir -p "$openvpn_build_dir"
    tar xzf "$openvpn_tgz_path" --strip-components=1 --directory "$openvpn_build_dir" || { echo "❌ 解压 OpenVPN 源码失败。"; exit 1; }
    
    cd "$openvpn_build_dir" || { echo "❌ 无法进入 OpenVPN 编译目录。"; exit 1; }
    
    ./configure --prefix=/usr || { echo "❌ OpenVPN configure 失败。"; exit 1; }
    make -j$(nproc) || { echo "❌ OpenVPN make 失败。"; exit 1; }
    make install || { echo "❌ OpenVPN make install 失败。"; exit 1; }

    echo "✅ OpenVPN 从源码编译安装完成。"
}

# 主要安装函数，包含了配置和启动逻辑
function installOpenVPN() {
    # 1. 从源码安装OpenVPN
    installOpenVPNFromSource

    # 2. 清理旧的 Easy-RSA 目录
    if [[ -d /etc/openvpn/easy-rsa/ ]]; then
        rm -rf /etc/openvpn/easy-rsa/
    fi

    # 3. 创建客户端配置目录
    if [[ ! -d /etc/openvpn/client ]]; then
        mkdir -p /etc/openvpn/client
        echo "📂 Created /etc/openvpn/client directory"
    else
        echo "ℹ️ /etc/openvpn/client already exists, skipping creation"
    fi

    # 4. 安装 easy-rsa
    easyrsa_tgz_path="$SCRIPT_DIR/resource/easy-rsa/EasyRSA-3.1.2.tgz"
    if [[ ! -f "$easyrsa_tgz_path" ]]; then
        echo "❌ 本地文件 $easyrsa_tgz_path 不存在，请检查路径或放入文件后再运行脚本。"
        exit 1
    fi
    echo "📦 使用本地 Easy-RSA 包：$easyrsa_tgz_path"
    mkdir -p /etc/openvpn/easy-rsa
    tar xzf "$easyrsa_tgz_path" --strip-components=1 --directory /etc/openvpn/easy-rsa

    # 5. 生成证书
    cd /etc/openvpn/easy-rsa/ || exit
    ./easyrsa init-pki
    ./easyrsa --batch --req-cn="OpenVPN-CA" build-ca nopass
    ./easyrsa --batch build-server-full server nopass
    ./easyrsa gen-crl
    openvpn --genkey --secret /etc/openvpn/tls-crypt.key

    # 确保密钥文件只有 owner 能够读写，这是 OpenVPN 的安全要求
    # 将权限设置为600，只允许 owner (nobody) 读写
    chmod 600 /etc/openvpn/tls-crypt.key

    # 6. 复制证书到 OpenVPN 配置目录
    cp pki/ca.crt pki/private/ca.key "pki/issued/server.crt" "pki/private/server.key" pki/crl.pem /etc/openvpn/
    chmod 644 /etc/openvpn/crl.pem
    
    
    # 7. 获取公共接口
    NIC=$(ip -4 route ls | grep default | grep -Po '(?<=dev )(\S+)' | head -1)
    
    # 8. 生成服务器配置文件 /etc/openvpn/server.conf
    cat > /etc/openvpn/server.conf << EOF
port $OPENVPN_PORT
proto udp
dev tun
persist-key
persist-tun
keepalive 10 120
topology subnet
server 10.8.0.0 255.255.255.0
ifconfig-pool-persist ipp.txt
push "dhcp-option DNS 1.1.1.1"
push "dhcp-option DNS 1.0.0.1"
push "redirect-gateway def1 bypass-dhcp"
dh none
ecdh-curve prime256v1
tls-crypt tls-crypt.key
crl-verify crl.pem
ca ca.crt
cert server.crt
key server.key
auth SHA256
cipher AES-128-GCM
ncp-ciphers AES-128-GCM
tls-server
tls-version-min 1.2
tls-cipher TLS-ECDHE-ECDSA-WITH-AES-128-GCM-SHA256
client-config-dir /etc/openvpn/ccd
management 127.0.0.1 7505
status /var/log/openvpn/status.log
verb 3
log /var/log/openvpn/openvpn.log
EOF

    # 9. 创建必要的目录
    mkdir -p /etc/openvpn/ccd
    mkdir -p /var/log/openvpn
    
    # 10. 启用IP转发
    echo 'net.ipv4.ip_forward=1' > /etc/sysctl.d/99-openvpn.conf
    sysctl --system
    
    # 11. 设置iptables规则
    mkdir -p /etc/iptables
    cat > /etc/iptables/add-openvpn-rules.sh << EOF
#!/bin/sh
iptables -t nat -I POSTROUTING 1 -s 10.8.0.0/24 -o $NIC -j MASQUERADE
iptables -I INPUT 1 -i tun0 -j ACCEPT
iptables -I FORWARD 1 -i $NIC -o tun0 -j ACCEPT
iptables -I FORWARD 1 -i tun0 -o $NIC -j ACCEPT
iptables -I INPUT 1 -i $NIC -p udp --dport $OPENVPN_PORT -j ACCEPT
EOF

    cat > /etc/iptables/rm-openvpn-rules.sh << EOF
#!/bin/sh
iptables -t nat -D POSTROUTING -s 10.8.0.0/24 -o $NIC -j MASQUERADE
iptables -D INPUT -i tun0 -j ACCEPT
iptables -D FORWARD -i $NIC -o tun0 -j ACCEPT
iptables -D FORWARD -i tun0 -o $NIC -j ACCEPT
iptables -D INPUT -i $NIC -p udp --dport $OPENVPN_PORT -j ACCEPT
EOF

    chmod +x /etc/iptables/add-openvpn-rules.sh
    chmod +x /etc/iptables/rm-openvpn-rules.sh
    
    # 12. 创建iptables服务
    cat > /etc/systemd/system/iptables-openvpn.service << EOF
[Unit]
Description=iptables rules for OpenVPN
Before=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/etc/iptables/add-openvpn-rules.sh
ExecStop=/etc/iptables/rm-openvpn-rules.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

    # --- 新增的代码块开始 ---
    # 13. 创建 openvpn@.service 服务单元
    # OpenVPN 在编译安装后不会自动创建这个服务文件
    echo "📁 创建 openvpn@.service 服务文件..."

if [[ ! -d /run/openvpn ]]; then
    mkdir -p /run/openvpn
    chmod 755 /run/openvpn
    echo " Create /run/openvpn directory"
fi
    cat > /etc/systemd/system/openvpn@.service << EOF
[Unit]
Description=OpenVPN connection to %i
PartOf=openvpn.service
Before=systemd-user-sessions.service
After=network-online.target
Wants=network-online.target
Documentation=man:openvpn(8)
Documentation=https://community.openvpn.net/openvpn/wiki/Openvpn24ManPage
Documentation=https://community.openvpn.net/openvpn/wiki/HOWTO

[Service]
Type=forking
PrivateTmp=true
WorkingDirectory=/etc/openvpn
ExecStart=/usr/sbin/openvpn --daemon ovpn-%i \
    --status /run/openvpn/%i.status 10 \
    --cd /etc/openvpn \
    --script-security 2 \
    --config /etc/openvpn/%i.conf \
    --writepid /run/openvpn/%i.pid
PIDFile=/run/openvpn/%i.pid
KillMode=process
CapabilityBoundingSet=CAP_IPC_LOCK CAP_NET_ADMIN CAP_NET_BIND_SERVICE CAP_NET_RAW CAP_SETGID CAP_SETUID CAP_SYS_CHROOT CAP_DAC_OVERRIDE CAP_AUDIT_WRITE
LimitNPROC=100
DeviceAllow=/dev/null rw
DeviceAllow=/dev/net/tun rw
ProtectSystem=true
ProtectHome=true
RestartSec=5s
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
    # --- 新增的代码块结束 ---
    
    # 14. 启动和启用服务
    systemctl daemon-reload
    systemctl enable iptables-openvpn
    systemctl start iptables-openvpn
    systemctl enable openvpn@server
    systemctl start openvpn@server
    
    # 15. 创建客户端模板
    cat > /etc/openvpn/client-template.txt << EOF
client
proto udp
explicit-exit-notify
remote $SERVER_IP $OPENVPN_PORT
dev tun
resolv-retry infinite
nobind
persist-key
persist-tun
remote-cert-tls server
auth SHA256
auth-nocache
cipher AES-128-GCM
tls-client
tls-version-min 1.2
tls-cipher TLS-ECDHE-ECDSA-WITH-AES-128-GCM-SHA256
ignore-unknown-option block-outside-dns
verb 3
EOF
    
#     # create disable enable client script
#     mkdir -p /etc/openvpn/scripts /etc/openvpn/disabled_clients

#     cat > /etc/openvpn/scripts/client-connect.sh << 'EOF'
# #!/bin/bash

# # OpenVPN 自动设置了 $common_name 环境变量，直接使用即可。
# CLIENT_NAME="${common_name}"

# # 检查 ${common_name} 是否为空。如果为空，则说明 OpenVPN 没有正确传递该变量，拒绝连接。
# if [ -z "$CLIENT_NAME" ]; then
#     logger -t openvpn-client-connect "错误：未设置 common_name 环境变量。连接请求被拒绝。"
#     exit 1
# fi

# # 使用客户端的通用名来检查禁用标志文件。
# FLAG_FILE="/etc/openvpn/disabled_clients/${CLIENT_NAME}"

# # 如果标志文件存在，则拒绝连接。
# if [ -f "$FLAG_FILE" ]; then
#     logger -t openvpn-client-connect "客户端 ${CLIENT_NAME} 已被禁用，连接请求被拒绝。"
#     exit 1
# else
#     # 如果标志文件不存在，则允许连接。
#     logger -t openvpn-client-connect "客户端 ${CLIENT_NAME} 已被允许连接。"
#     exit 0
# fi

# EOF

#     chmod +x /etc/openvpn/scripts/client-connect.sh

    
    echo "🎉 OpenVPN installation completed successfully!"
}


# 脚本执行开始
echo "🚀 Ubuntu OpenVPN Installer & Manager"
echo "======================================"

initialCheck

if [[ -e /etc/openvpn/server.conf ]]; then
    echo "OpenVPN has installed"
else
    # 调用完整的安装函数
    installOpenVPN
    echo "📱 Generating default server client configuration..."
    cd /etc/openvpn/easy-rsa/ || exit
    EASYRSA_CERT_EXPIRE=3650 ./easyrsa --batch build-client-full "server" nopass
    echo "✅ Client server added."

    cp /etc/openvpn/client-template.txt "/etc/openvpn/client/server.ovpn"
    {
        echo "<ca>"
        cat "/etc/openvpn/easy-rsa/pki/ca.crt"
        echo "</ca>"
        echo "<cert>"
        cat "/etc/openvpn/easy-rsa/pki/issued/server.crt"
        echo "</cert>"
        echo "<key>"
        cat "/etc/openvpn/easy-rsa/pki/private/server.key"
        echo "</key>"
        echo "<tls-crypt>"
        cat /etc/openvpn/tls-crypt.key
        echo "</tls-crypt>"
    } >>"/etc/openvpn/client/server.ovpn"

    echo ""
    echo "📄 Default client configuration written to /etc/openvpn/client/server.ovpn"
fi