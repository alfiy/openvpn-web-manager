#!/bin/bash
# Ubuntu OpenVPN installer with uninstall functionality

# Function definitions must come before they are called.
# This function resolves the public IP address of the server.
function resolvePublicIP() {
    # Using a reliable web service to get the public IP is more robust
    # than trying to infer it from internal network interfaces.
    PUBLIC_IP=$(curl -s ifconfig.me)
    if [[ -z "$PUBLIC_IP" ]]; then
        echo "Failed to resolve public IP." >&2
        return 1
    fi
    echo "$PUBLIC_IP"
}

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
    if [[ "$ID" != "ubuntu" ]]; then
        echo "❌ This script only supports Ubuntu systems."
        exit 1
    fi
    
    echo "✅ Ubuntu $VERSION_ID detected."
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

# Main installation function
function installOpenVPN() {
    echo "🚀 Starting OpenVPN installation..."
    
    # Only install necessary packages, OpenVPN is already being installed by apt.
    apt-get update
    apt-get install -y openvpn iptables openssl ca-certificates curl

    if [[ -d /etc/openvpn/easy-rsa/ ]]; then
        rm -rf /etc/openvpn/easy-rsa/
    fi

    mkdir -p /etc/openvpn/client
    echo "📂 Created /etc/openvpn/client directory."

    # Use an absolute path based on the script's directory to avoid errors.
    EASYRSA_TGZ="$(dirname "$0")/resource/easy-rsa/EasyRSA-3.1.2.tgz"
    if [[ ! -f "$EASYRSA_TGZ" ]]; then
        echo "❌ 本地文件 $EASYRSA_TGZ 不存在，请检查路径或放文件后再运行脚本。"
        exit 1
    fi
    echo "📦 使用本地 Easy-RSA 包：$EASYRSA_TGZ."
    mkdir -p /etc/openvpn/easy-rsa
    tar xzf "$EASYRSA_TGZ" --strip-components=1 --directory /etc/openvpn/easy-rsa

    # Generate certificates
    cd /etc/openvpn/easy-rsa/ || exit 1
    ./easyrsa init-pki
    ./easyrsa --batch --req-cn="OpenVPN-CA" build-ca nopass
    ./easyrsa --batch build-server-full server nopass
    ./easyrsa gen-crl
    openvpn --genkey --secret /etc/openvpn/tls-crypt.key
    
    # Copy certificates
    cp pki/ca.crt pki/private/ca.key "pki/issued/server.crt" "pki/private/server.key" /etc/openvpn/easy-rsa/pki/crl.pem /etc/openvpn
    chmod 644 /etc/openvpn/crl.pem
    
    # Get the "public" interface
    NIC=$(ip -4 route ls | grep default | grep -Po '(?<=dev )(\S+)' | head -1)
    
    # Generate server config
    cat > /etc/openvpn/server.conf << EOF
port $OPENVPN_PORT
proto udp
dev tun
user nobody
group nogroup
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
status /var/log/openvpn/status.log
log /var/log/openvpn/openvpn.log
verb 3
client-connect /etc/openvpn/scripts/client-connect.sh
EOF

    # Create directories
    mkdir -p /etc/openvpn/ccd /var/log/openvpn
    
    # Enable IP forwarding
    echo 'net.ipv4.ip_forward=1' > /etc/sysctl.d/99-openvpn.conf
    sysctl --system
    
    # Setup iptables
    mkdir -p /etc/iptables
    
    # Create add rules script
    cat > /etc/iptables/add-openvpn-rules.sh << EOF
#!/bin/sh
iptables -t nat -I POSTROUTING 1 -s 10.8.0.0/24 -o $NIC -j MASQUERADE
iptables -I INPUT 1 -i tun0 -j ACCEPT
iptables -I FORWARD 1 -i $NIC -o tun0 -j ACCEPT
iptables -I FORWARD 1 -i tun0 -o $NIC -j ACCEPT
iptables -I INPUT 1 -i $NIC -p udp --dport $OPENVPN_PORT -j ACCEPT
EOF

    # Create remove rules script
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
    
    # Create systemd service for iptables
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
    
    # Start and enable the services
    systemctl daemon-reload
    systemctl enable iptables-openvpn
    systemctl start iptables-openvpn
    
    # Setup OpenVPN service
    systemctl enable openvpn@server
    systemctl start openvpn@server
    
    # Create client template
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
setenv opt block-outside-dns
verb 3
log openvpn.log
EOF

    # create disable enable client script
    cat > /etc/openvpn/scripts/client-connect.sh << EOF
#!/bin/bash

# OpenVPN 自动设置了 $common_name 环境变量，直接使用即可。
CLIENT_NAME="${common_name}"

# 检查 $common_name 是否为空
if [ -z "$CLIENT_NAME" ]; then
    logger -t openvpn-client-connect "ERROR: The common_name environment variable is not set. Rejecting connection."
    exit 1
fi

# 现在使用正确的通用名来检查禁用标志文件。
FLAG_FILE="/etc/openvpn/disabled_clients/${CLIENT_NAME}"

if [ -f "$FLAG_FILE" ]; then
  logger -t openvpn-client-connect "Client ${CLIENT_NAME} is disabled. Rejecting connection."
  exit 1
else
  logger -t openvpn-client-connect "Client ${CLIENT_NAME} is allowed to connect."
  exit 0
fi
EOF

    chmod +x /etc/openvpn/scripts/client-connect.sh

    
    echo "🎉 OpenVPN installation completed successfully!"
}

# ---
# Script execution starts here
echo "🚀 Ubuntu OpenVPN Installer & Manager"
echo "======================================"

# Check for root, TUN, OS...
initialCheck

# The function call for SERVER_IP is now placed after the function is defined.
OPENVPN_PORT=${1:-1194}
SERVER_IP=${2:-$(resolvePublicIP)}

# Check if OpenVPN is already installed
if [[ -e /etc/openvpn/server.conf ]]; then
    echo "OpenVPN has installed."
else
    installOpenVPN
    # Generate default "server" client after installation
    echo "📱 Generating default server client configuration..."
    cd /etc/openvpn/easy-rsa/ || exit 1
    EASYRSA_CERT_EXPIRE=3650 ./easyrsa --batch build-client-full "server" nopass
    echo "✅ Client server added."
    
    # Generate client config
    cp /etc/openvpn/client-template.txt "/etc/openvpn/client/server.ovpn"
    {
        echo "<ca>"
        cat "/etc/openvpn/easy-rsa/pki/ca.crt"
        echo "</ca>"
        
        echo "<cert>"
        awk '/BEGIN/,/END CERTIFICATE/' "/etc/openvpn/easy-rsa/pki/issued/server.crt"
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