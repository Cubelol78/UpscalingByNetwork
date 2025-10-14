#!/bin/bash
# Installation script for the Linux client

set -e

echo "==================================="
echo "Upscaling Client - Linux Installer"
echo "==================================="
echo

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "Found Python $PYTHON_VERSION"

# Create virtual environment (optional)
read -p "Create virtual environment? (recommended) [Y/n]: " CREATE_VENV
CREATE_VENV=${CREATE_VENV:-Y}

if [[ $CREATE_VENV =~ ^[Yy]$ ]]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    echo "Virtual environment created and activated"
fi

# Install dependencies
echo
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo
echo "==================================="
echo "Installation complete!"
echo "==================================="
echo
echo "Usage:"
echo "  CLI mode:  ./client_main.py run --host SERVER_IP"
echo "  GUI mode:  ./client_gui.py"
echo
echo "Configuration:"
echo "  Config file: ~/.config/upscaling-client/config.json"
echo "  Log files:   ~/.local/share/upscaling-client/logs/"
echo
echo "See README.md for more information"
