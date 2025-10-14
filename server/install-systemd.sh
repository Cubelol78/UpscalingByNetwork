#!/bin/bash
# Install UpscalingByNetwork server as systemd service
# Must be run as root

set -e

echo "=== UpscalingByNetwork Systemd Service Installation ==="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root"
    echo "Usage: sudo ./install-systemd.sh"
    exit 1
fi

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SERVICE_FILE="$SCRIPT_DIR/upscaling-server.service"

# Check if service file exists
if [ ! -f "$SERVICE_FILE" ]; then
    echo "Error: Service file not found: $SERVICE_FILE"
    exit 1
fi

# Install location
INSTALL_DIR="/opt/upscaling-server"

echo "1. Creating installation directory: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

echo "2. Copying server files..."
cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR/"

echo "3. Setting up Python virtual environment..."
cd "$INSTALL_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "4. Creating necessary directories..."
mkdir -p "$INSTALL_DIR"/{logs,output,server_work,config}

echo "5. Setting permissions..."
chown -R nobody:nogroup "$INSTALL_DIR"
chmod -R 755 "$INSTALL_DIR"

echo "6. Installing systemd service..."
cp "$SERVICE_FILE" /etc/systemd/system/upscaling-server.service

# Update service file to use venv python
sed -i "s|/usr/bin/python3|$INSTALL_DIR/venv/bin/python3|g" /etc/systemd/system/upscaling-server.service
sed -i "s|/opt/upscaling-server|$INSTALL_DIR|g" /etc/systemd/system/upscaling-server.service

echo "7. Reloading systemd..."
systemctl daemon-reload

echo "8. Enabling service..."
systemctl enable upscaling-server.service

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Service commands:"
echo "  Start:   sudo systemctl start upscaling-server"
echo "  Stop:    sudo systemctl stop upscaling-server"
echo "  Restart: sudo systemctl restart upscaling-server"
echo "  Status:  sudo systemctl status upscaling-server"
echo "  Logs:    sudo journalctl -u upscaling-server -f"
echo ""
echo "Service is enabled and will start on boot."
echo "To start now, run: sudo systemctl start upscaling-server"
