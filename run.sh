#!/bin/bash

# Check if python3-venv is available
if ! python3 -m venv --help >/dev/null 2>&1; then
    echo "python3-venv is not installed. Installing it..."
    apt update && apt install -y python3-venv python3-pip
    if [ $? -ne 0 ]; then
        echo "Failed to install python3-venv. Trying alternative approach..."
        echo "Installing dependencies directly with --break-system-packages flag..."
        pip3 install -r requirements.txt --break-system-packages
        echo "Dependencies installed. Continuing with script execution..."
    else
        echo "python3-venv installed successfully. Creating virtual environment..."
        python3 -m venv venv
        if [ -f "venv/bin/activate" ]; then
            source venv/bin/activate
            pip install -r requirements.txt
        else
            echo "Virtual environment creation failed. Using fallback approach..."
            pip3 install -r requirements.txt --break-system-packages
        fi
    fi
else
    # Create virtual environment if it doesn't exist
    if [ ! -d "venv" ]; then
        echo "Creating virtual environment..."
        python3 -m venv venv
    fi
    
    # Activate virtual environment
    echo "Activating virtual environment..."
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
        # Install Python dependencies in virtual environment
        echo "Installing dependencies..."
        pip install -r requirements.txt
    else
        echo "Virtual environment activation failed. Using fallback approach..."
        pip3 install -r requirements.txt --break-system-packages
    fi
fi

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

