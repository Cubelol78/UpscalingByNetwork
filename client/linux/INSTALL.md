# Installation Guide - Linux Client

## Quick Install

```bash
# Make install script executable
chmod +x install.sh

# Run installer
./install.sh
```

## Manual Installation

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Install Real-ESRGAN

Download Real-ESRGAN from: https://github.com/xinntao/Real-ESRGAN/releases

```bash
# Download and extract
wget https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-ubuntu.zip
unzip realesrgan-ncnn-vulkan-20220424-ubuntu.zip

# Install executable
sudo cp realesrgan-ncnn-vulkan /usr/local/bin/
sudo chmod +x /usr/local/bin/realesrgan-ncnn-vulkan

# Install models
mkdir -p ~/.local/share/upscaling-client/models
cp models/* ~/.local/share/upscaling-client/models/
```

### 3. Configure Client

Edit configuration:

```bash
# Copy default config
mkdir -p ~/.config/upscaling-client
cp config/default_config.json ~/.config/upscaling-client/config.json

# Edit config
nano ~/.config/upscaling-client/config.json
```

## Running as System Service

### 1. Install Service

```bash
# Edit service file with your paths
sudo nano upscaling-client.service

# Copy to systemd
sudo cp upscaling-client.service /etc/systemd/system/upscaling-client@.service

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable upscaling-client@$USER
sudo systemctl start upscaling-client@$USER
```

### 2. Service Management

```bash
# Check status
sudo systemctl status upscaling-client@$USER

# View logs
sudo journalctl -u upscaling-client@$USER -f

# Restart service
sudo systemctl restart upscaling-client@$USER

# Stop service
sudo systemctl stop upscaling-client@$USER
```

## Docker Installation

```bash
# Build Docker image
docker build -t upscaling-client .

# Run container
docker run -d \
  --name upscaling-client \
  --network host \
  -v $HOME/.config/upscaling-client:/config \
  -v $HOME/.local/share/upscaling-client:/data \
  upscaling-client
```

## Uninstallation

```bash
# Stop service
sudo systemctl stop upscaling-client@$USER
sudo systemctl disable upscaling-client@$USER

# Remove service
sudo rm /etc/systemd/system/upscaling-client@.service
sudo systemctl daemon-reload

# Remove files
rm -rf ~/.config/upscaling-client
rm -rf ~/.local/share/upscaling-client

# Uninstall Python packages
pip uninstall -r requirements.txt
```

## Troubleshooting

### Permission Issues

```bash
# Ensure correct permissions
chmod +x client_main.py client_gui.py
chmod -R 755 ~/.config/upscaling-client
chmod -R 755 ~/.local/share/upscaling-client
```

### Missing Dependencies

```bash
# Install system dependencies (Ubuntu/Debian)
sudo apt install python3-pip python3-venv

# Install system dependencies (Fedora/RHEL)
sudo dnf install python3-pip python3-virtualenv

# Install system dependencies (Arch)
sudo pacman -S python-pip
```

### GPU Issues

```bash
# Install NVIDIA drivers (Ubuntu)
sudo ubuntu-drivers autoinstall

# Install Vulkan
sudo apt install vulkan-tools mesa-vulkan-drivers

# Test Vulkan
vulkaninfo
```

## Platform-Specific Notes

### Ubuntu/Debian

```bash
sudo apt update
sudo apt install python3-pip python3-venv vulkan-tools
```

### Fedora/RHEL

```bash
sudo dnf install python3-pip vulkan-tools
```

### Arch Linux

```bash
sudo pacman -S python-pip vulkan-tools
```

## Next Steps

1. Test installation: `python client_main.py test-realesrgan`
2. Configure server: `python client_main.py config-set --key server.host --value YOUR_SERVER`
3. Test connection: `python client_main.py test-connection --host YOUR_SERVER`
4. Run client: `python client_main.py run`

For more information, see README.md
