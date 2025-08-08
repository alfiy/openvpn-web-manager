#!/bin/bash

# Install Python dependencies
pip install -r requirements.txt

# Ensure the OpenVPN script exists in the workspace directory
SCRIPT_SOURCE="../ubuntu-openvpn-install.sh"
SCRIPT_TARGET="./ubuntu-openvpn-install.sh"

# Check if script exists in workspace, if not, try to copy from parent directory
if [ ! -f "$SCRIPT_TARGET" ]; then
    if [ -f "$SCRIPT_SOURCE" ]; then
        cp "$SCRIPT_SOURCE" "$SCRIPT_TARGET"
        chmod +x "$SCRIPT_TARGET"
        echo "Copied ubuntu-openvpn-install.sh to workspace directory"
    else
        echo "Error: ubuntu-openvpn-install.sh not found in parent directory"
        echo "Please ensure ubuntu-openvpn-install.sh exists in the parent directory"
        exit 1
    fi
else
    echo "ubuntu-openvpn-install.sh already exists in workspace"
fi

# Make sure the script is executable
chmod +x "$SCRIPT_TARGET"

# Run the Flask application
python app.py
