#!/bin/bash

# Function to check if a command exists
command_exists() {
    type "$1" &> /dev/null
}

# Get the absolute path of the script directory
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
echo "Script directory: $SCRIPT_DIR"

# Check if Python is installed
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

# Get the current Python version
PYTHON_VERSION=$(python3 --version | cut -d ' ' -f 2 | cut -d '.' -f 1-2)
echo "Detected Python version: $PYTHON_VERSION"

# Check if python-venv is installed for the current Python version
if ! python3 -m venv --help >/dev/null 2>&1; then
    echo "python-venv is not installed for Python $PYTHON_VERSION. Installing it..."
    sudo apt update && sudo apt install -y python3-venv
    if [ $? -ne 0 ]; then
        echo "Failed to install python-venv for Python $PYTHON_VERSION. Exiting..."
        exit 1
    fi
else
    echo "python-venv is already installed for Python $PYTHON_VERSION."
fi

# Check if the virtual environment directory exists
VENV_DIR="$SCRIPT_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Virtual environment directory does not exist. Creating virtual environment in $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo "Failed to create virtual environment. Exiting..."
        exit 1
    fi
    echo "Virtual environment created successfully."
else
    echo "Virtual environment directory already exists. Skipping creation."
fi

# Check if the virtual environment activation script exists
ACTIVATE_SCRIPT="$VENV_DIR/bin/activate"
if [ ! -f "$ACTIVATE_SCRIPT" ]; then
    echo "Virtual environment activation script not found at $ACTIVATE_SCRIPT. Exiting..."
    exit 1
fi

# Activate virtual environment
echo "Activating virtual environment..."
source "$ACTIVATE_SCRIPT"
if [ $? -ne 0 ]; then
    echo "Failed to activate virtual environment. Exiting..."
    exit 1
fi
echo "Virtual environment activated successfully."

# Install Python dependencies in virtual environment
echo "Installing dependencies..."
pip install -r "$SCRIPT_DIR/requirements.txt"
if [ $? -ne 0 ]; then
    echo "Failed to install dependencies. Exiting..."
    exit 1
fi
echo "Dependencies installed successfully."

# Check if ubuntu-openvpn-install.sh exists in the current directory
SCRIPT_TARGET="$SCRIPT_DIR/ubuntu-openvpn-install.sh"
if [ ! -f "$SCRIPT_TARGET" ]; then
    echo "Error: ubuntu-openvpn-install.sh does not exist in the current directory."
    echo "Please ensure ubuntu-openvpn-install.sh exists in the current directory and try again."
    exit 1
else
    echo "ubuntu-openvpn-install.sh exists in the current directory."
fi

# Make sure the script is executable
chmod +x "$SCRIPT_TARGET"

# Run the Flask application
echo "Running the Flask application..."
python "$SCRIPT_DIR/app.py"
