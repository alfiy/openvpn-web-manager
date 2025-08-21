#!/bin/bash
# Ubuntu OpenVPN installer with uninstall functionality

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
    # For NAT environments, use internal IP instead of external IP
    # First try to get the internal IP from hostname -I
    INTERNAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    
    # If hostname -I fails, try ip route method
    if [[ -z "$INTERNAL_IP" ]]; then
        INTERNAL_IP=$(ip route get 8.8.8.8 2>/dev/null | grep -oP 'src \K[^ ]+')
    fi
    
    # If both methods fail, try to get from network interfaces
    if [[ -z "$INTERNAL_IP" ]]; then
        INTERNAL_IP=$(ip addr show | grep 'inet ' | grep -v '127.0.0.1' | head -n1 | awk '{print $2}' | cut -d'/' -f1)
    fi
    
    # Check if we got an internal IP
    if [[ -n "$INTERNAL_IP" ]]; then
        echo "$INTERNAL_IP"
    else
        echo "Failed to resolve internal IP"
        return 1
    fi
}

# Main installation function
function installOpenVPN() {
    echo "🚀 Starting OpenVPN installation..."
    apt-get update
    apt-get install -y openvpn iptables openssl ca-certificates wget curl

    if [[ -d /etc/openvpn/easy-rsa/ ]]; then
        rm -rf /etc/openvpn/easy-rsa/
    fi

    # mkdir /etc/openvpn/client
    if [[ ! -d /etc/openvpn/client ]]; then
        mkdir -p /etc/openvpn/client
        echo "📂 Created /etc/openvpn/client directory"
    else
        echo "ℹ️ /etc/openvpn/client already exists, skipping creation"
    fi

    # Install easy-rsa
    echo "📦 Installing Easy-RSA..."
    wget -O ~/easy-rsa.tgz https://github.com/OpenVPN/easy-rsa/releases/download/v3.1.2/EasyRSA-3.1.2.tgz
    mkdir -p /etc/openvpn/easy-rsa
    tar xzf ~/easy-rsa.tgz --strip-components=1 --directory /etc/openvpn/easy-rsa
    rm -f ~/easy-rsa.tgz

    # Generate certificates
    cd /etc/openvpn/easy-rsa/ || return
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
port 1194
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
verb 3
EOF

    # Create directories
    mkdir -p /etc/openvpn/ccd
    mkdir -p /var/log/openvpn
    
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
iptables -I INPUT 1 -i $NIC -p udp --dport 1194 -j ACCEPT
EOF

    # Create remove rules script
    cat > /etc/iptables/rm-openvpn-rules.sh << EOF
#!/bin/sh
iptables -t nat -D POSTROUTING -s 10.8.0.0/24 -o $NIC -j MASQUERADE
iptables -D INPUT -i tun0 -j ACCEPT
iptables -D FORWARD -i $NIC -o tun0 -j ACCEPT
iptables -D FORWARD -i tun0 -o $NIC -j ACCEPT
iptables -D INPUT -i $NIC -p udp --dport 1194 -j ACCEPT
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
remote $(resolvePublicIP) 1194
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
EOF
    
    echo "🎉 OpenVPN installation completed successfully!"
}



# Script execution starts here
echo "🚀 Ubuntu OpenVPN Installer & Manager"
echo "======================================"

# Check for root, TUN, OS...
initialCheck

# Check if OpenVPN is already installed
if [[ -e /etc/openvpn/server.conf ]]; then
    echo "OpenVPN has installed"
else
    installOpenVPN
    # Generate default "server" client after installation
    echo "📱 Generating default server client configuration..."
    cd /etc/openvpn/easy-rsa/ || exit
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

