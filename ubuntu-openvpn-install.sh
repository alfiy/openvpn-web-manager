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

# Install Unbound DNS resolver
function installUnbound() {
    echo "📦 Installing Unbound DNS resolver..."
    apt-get install -y unbound
    
    echo 'interface: 10.8.0.1
access-control: 10.8.0.1/24 allow
hide-identity: yes
hide-version: yes
use-caps-for-id: yes
prefetch: yes' >>/etc/unbound/unbound.conf

    # DNS Rebinding fix
    echo "private-address: 10.0.0.0/8
private-address: 172.16.0.0/12
private-address: 192.168.0.0/16
private-address: 169.254.0.0/16
private-address: 127.0.0.0/8" >>/etc/unbound/unbound.conf

    systemctl enable unbound
    systemctl restart unbound
    echo "✅ Unbound installed and configured"
}

# Function to get public IP
function resolvePublicIP() {
    PUBLIC_IP=$(curl -4 -s https://api.ipify.org)
    if [[ -z $PUBLIC_IP ]]; then
        PUBLIC_IP=$(curl -s https://api.seeip.org)
    fi
    echo "$PUBLIC_IP"
}

# Main installation function
function installOpenVPN() {
    echo "🚀 Starting OpenVPN installation..."
    apt-get update
    apt-get install -y openvpn iptables openssl ca-certificates wget curl

    if [[ -d /etc/openvpn/easy-rsa/ ]]; then
        rm -rf /etc/openvpn/easy-rsa/
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

# Function to create a new client
function newClient() {
    echo ""
    echo "👤 Creating client certificate..."
    echo "The name must consist of alphanumeric characters, underscore or dash."

    read -rp "Client name: " -e CLIENT
    cd /etc/openvpn/easy-rsa/ || return
    
    EASYRSA_CERT_EXPIRE=3650 ./easyrsa --batch build-client-full "$CLIENT" nopass
    echo "✅ Client $CLIENT added."

    # Generate client config
    cp /etc/openvpn/client-template.txt "/root/$CLIENT.ovpn"
    {
        echo "<ca>"
        cat "/etc/openvpn/easy-rsa/pki/ca.crt"
        echo "</ca>"

        echo "<cert>"
        awk '/BEGIN/,/END CERTIFICATE/' "/etc/openvpn/easy-rsa/pki/issued/$CLIENT.crt"
        echo "</cert>"

        echo "<key>"
        cat "/etc/openvpn/easy-rsa/pki/private/$CLIENT.key"
        echo "</key>"

        echo "<tls-crypt>"
        cat /etc/openvpn/tls-crypt.key
        echo "</tls-crypt>"
    } >>"/root/$CLIENT.ovpn"

    echo ""
    echo "📄 Configuration file written to /root/$CLIENT.ovpn"
}

# Function to revoke a client
function revokeClient() {
    NUMBEROFCLIENTS=$(tail -n +2 /etc/openvpn/easy-rsa/pki/index.txt | grep -c "^V")
    if [[ $NUMBEROFCLIENTS == '0' ]]; then
        echo "❌ You have no existing clients!"
        exit 1
    fi

    echo "🔐 Select the client certificate to revoke:"
    tail -n +2 /etc/openvpn/easy-rsa/pki/index.txt | grep "^V" | cut -d '=' -f 2 | nl -s ') '
    read -rp "Select one client: " CLIENTNUMBER
    
    CLIENT=$(tail -n +2 /etc/openvpn/easy-rsa/pki/index.txt | grep "^V" | cut -d '=' -f 2 | sed -n "$CLIENTNUMBER"p)
    cd /etc/openvpn/easy-rsa/ || return
    ./easyrsa --batch revoke "$CLIENT"
    ./easyrsa gen-crl
    rm -f /etc/openvpn/crl.pem
    cp /etc/openvpn/easy-rsa/pki/crl.pem /etc/openvpn/crl.pem
    chmod 644 /etc/openvpn/crl.pem
    rm -f "/root/$CLIENT.ovpn"
    sed -i "/^$CLIENT,.*/d" /etc/openvpn/ipp.txt

    echo "✅ Certificate for client $CLIENT revoked."
}

# Function to remove OpenVPN
function removeOpenVPN() {
    echo ""
    echo "🗑️ COMPLETE OPENVPN UNINSTALLATION"
    echo "⚠️ This will completely remove OpenVPN and all related configurations!"
    echo ""
    read -rp "Do you really want to remove OpenVPN? [y/n]: " -e -i n REMOVE
    if [[ $REMOVE == 'y' ]]; then
        # Stop services
        echo "📦 Stopping OpenVPN services..."
        systemctl disable openvpn@server
        systemctl stop openvpn@server
        
        # Remove firewall rules
        echo "🔥 Removing firewall rules..."
        systemctl stop iptables-openvpn
        systemctl disable iptables-openvpn
        rm -f /etc/systemd/system/iptables-openvpn.service
        systemctl daemon-reload
        rm -f /etc/iptables/add-openvpn-rules.sh
        rm -f /etc/iptables/rm-openvpn-rules.sh
        
        # Remove OpenVPN
        echo "📦 Removing OpenVPN package..."
        apt-get remove --purge -y openvpn
        
        # Clean up files
        echo "🗑️ Cleaning up configuration files..."
        find /root/ -maxdepth 1 -name "*.ovpn" -delete
        rm -rf /etc/openvpn
        rm -f /etc/sysctl.d/99-openvpn.conf
        rm -rf /var/log/openvpn
        
        # Restore system settings
        echo "🌐 Restoring system settings..."
        sysctl -w net.ipv4.ip_forward=0
        
        # Clean remaining firewall rules
        echo "🔧 Cleaning remaining firewall rules..."
        iptables -t nat -D POSTROUTING -s 10.8.0.0/24 -j MASQUERADE 2>/dev/null || true
        iptables -D INPUT -i tun0 -j ACCEPT 2>/dev/null || true
        iptables -D FORWARD -i tun0 -j ACCEPT 2>/dev/null || true
        
        echo ""
        echo "🎉 OpenVPN has been completely removed!"
    else
        echo "❌ Removal aborted!"
    fi
}

# Main menu function
function manageMenu() {
    echo "🎉 Welcome to Ubuntu OpenVPN Manager!"
    echo ""
    echo "What do you want to do?"
    echo "   1) Add a new user"
    echo "   2) Revoke existing user"
    echo "   3) Complete OpenVPN removal"
    echo "   4) Exit"
    
    read -rp "Select an option [1-4]: " -e -i 1 MENU_OPTION
    
    case $MENU_OPTION in
    1)
        newClient
        ;;
    2)
        revokeClient
        ;;
    3)
        removeOpenVPN
        ;;
    4)
        echo "👋 Goodbye!"
        exit 0
        ;;
    esac
}

# Script execution starts here
echo "🚀 Ubuntu OpenVPN Installer & Manager"
echo "======================================"

# Check for root, TUN, OS...
initialCheck

# Check if OpenVPN is already installed
if [[ -e /etc/openvpn/server.conf ]]; then
    manageMenu
else
    installOpenVPN
    newClient
fi

