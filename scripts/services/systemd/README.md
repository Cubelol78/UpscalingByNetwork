# UpscalingByNetwork - Systemd Services

Complete systemd service configuration for running UpscalingByNetwork server and clients as system services on Linux.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Service Files](#service-files)
- [Configuration](#configuration)
- [Usage](#usage)
- [Troubleshooting](#troubleshooting)
- [Security](#security)
- [Performance Tuning](#performance-tuning)
- [Uninstallation](#uninstallation)

## Overview

This directory contains systemd service files and installation scripts for:

- **Server Service** (`upscaling-server.service`): Runs the upscaling server as a system service
- **Client Service Template** (`upscaling-client@.service`): Runs client instances per-user

### Features

- Non-root user execution
- Automatic restart on failure
- Resource limits (memory, CPU, file descriptors)
- Security hardening (sandboxing, capability restrictions)
- GPU device access (NVIDIA, AMD/Intel)
- Systemd journal logging
- Graceful shutdown handling
- Environment variable support

## Prerequisites

### System Requirements

- Linux distribution with systemd (Ubuntu 16.04+, Debian 8+, CentOS 7+, Fedora, etc.)
- Python 3.8 or later
- systemd version 232 or later (for full security features)
- Root/sudo access for installation

### Software Requirements

```bash
# Check systemd version
systemctl --version

# Check Python version
python3 --version

# Install Python dependencies
pip3 install -r requirements.txt
```

### Required Packages

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install python3 python3-pip rsync

# CentOS/RHEL/Fedora
sudo dnf install python3 python3-pip rsync

# Arch Linux
sudo pacman -S python python-pip rsync
```

## Installation

### Quick Install

```bash
# Navigate to the systemd scripts directory
cd /path/to/UpscalingByNetwork/scripts/services/systemd

# Make the installation script executable
chmod +x install-systemd.sh

# Run the installation script as root
sudo ./install-systemd.sh
```

### What the Installer Does

1. **Verifies Prerequisites**: Checks for systemd and Python
2. **Creates Service User**: Creates `upscaling` system user (no login)
3. **Installs Application**: Copies files to `/opt/UpscalingByNetwork`
4. **Creates Directories**: Sets up working directories with proper permissions
5. **Installs Services**: Copies service files to `/etc/systemd/system/`
6. **Creates Configuration**: Generates environment files
7. **Enables Services**: Optionally enables and starts services

### Manual Installation

If you prefer manual installation:

```bash
# 1. Create service user
sudo useradd --system --no-create-home --shell /usr/sbin/nologin upscaling

# 2. Copy application files
sudo mkdir -p /opt/UpscalingByNetwork
sudo rsync -av /path/to/UpscalingByNetwork/ /opt/UpscalingByNetwork/

# 3. Create working directories
sudo mkdir -p /opt/UpscalingByNetwork/server/{server_work/{jobs,temp,encryption_keys},logs,output}
sudo mkdir -p /etc/upscaling

# 4. Set ownership
sudo chown -R upscaling:upscaling /opt/UpscalingByNetwork
sudo chown -R upscaling:upscaling /etc/upscaling

# 5. Copy service files
sudo cp upscaling-server.service /etc/systemd/system/
sudo cp upscaling-client@.service /etc/systemd/system/

# 6. Set permissions
sudo chmod 644 /etc/systemd/system/upscaling-*.service

# 7. Reload systemd
sudo systemctl daemon-reload
```

## Service Files

### upscaling-server.service

System-wide server service that:
- Runs as `upscaling` user
- Listens on `0.0.0.0:8888` by default
- Runs in console mode (no GUI)
- Auto-restarts on failure
- Limited to 4GB RAM and 200% CPU

**Location**: `/etc/systemd/system/upscaling-server.service`

### upscaling-client@.service

Template service for running multiple client instances:
- One instance per user (e.g., `upscaling-client@john.service`)
- Runs as the specified user
- Auto-connects to server
- Limited to 8GB RAM and 400% CPU
- Stores data in user's home directory (`~/.upscaling/`)

**Location**: `/etc/systemd/system/upscaling-client@.service`

## Configuration

### Environment Files

#### Server Configuration

Edit `/etc/upscaling/server.env`:

```bash
# Server binding
SERVER_HOST=0.0.0.0
SERVER_PORT=8888

# Logging
LOG_LEVEL=INFO

# Python settings
PYTHONUNBUFFERED=1

# Custom settings
MAX_CLIENTS=50
BATCH_SIZE=50
```

#### Client Configuration

For each client, edit `~/.upscaling/client.env`:

```bash
# Server connection
SERVER_HOST=192.168.1.100
SERVER_PORT=8888

# Logging
LOG_LEVEL=INFO

# Python settings
PYTHONUNBUFFERED=1

# Auto-connect on start
AUTO_CONNECT=true
```

### Service Customization

To customize service parameters, edit the service files directly or use systemd drop-ins:

```bash
# Create override directory
sudo mkdir -p /etc/systemd/system/upscaling-server.service.d

# Create override file
sudo nano /etc/systemd/system/upscaling-server.service.d/override.conf
```

Example override:

```ini
[Service]
# Increase memory limit
MemoryMax=8G

# Change port
Environment="SERVER_PORT=9999"

# Enable debug logging
ExecStart=
ExecStart=/usr/bin/python3 /opt/UpscalingByNetwork/server/main.py --no-gui --host 0.0.0.0 --port 9999 --log-level DEBUG
```

Reload after changes:

```bash
sudo systemctl daemon-reload
sudo systemctl restart upscaling-server
```

## Usage

### Server Service

#### Start/Stop/Restart

```bash
# Start the server
sudo systemctl start upscaling-server

# Stop the server
sudo systemctl stop upscaling-server

# Restart the server
sudo systemctl restart upscaling-server

# Reload configuration (graceful)
sudo systemctl reload upscaling-server
```

#### Enable/Disable Auto-start

```bash
# Enable auto-start on boot
sudo systemctl enable upscaling-server

# Disable auto-start
sudo systemctl disable upscaling-server

# Check if enabled
systemctl is-enabled upscaling-server
```

#### Check Status

```bash
# View status
sudo systemctl status upscaling-server

# Check if running
systemctl is-active upscaling-server

# View recent logs
sudo journalctl -u upscaling-server -n 50

# Follow logs in real-time
sudo journalctl -u upscaling-server -f

# View logs since last boot
sudo journalctl -u upscaling-server -b

# View logs with priority (errors only)
sudo journalctl -u upscaling-server -p err
```

### Client Service

Client services use the template pattern with username:

#### Start/Stop/Restart

```bash
# Replace 'john' with actual username
# Start client for user 'john'
sudo systemctl start upscaling-client@john

# Stop client
sudo systemctl stop upscaling-client@john

# Restart client
sudo systemctl restart upscaling-client@john
```

#### Enable/Disable

```bash
# Enable auto-start for user 'john'
sudo systemctl enable upscaling-client@john

# Disable auto-start
sudo systemctl disable upscaling-client@john
```

#### Check Status

```bash
# View status
sudo systemctl status upscaling-client@john

# View logs
sudo journalctl -u upscaling-client@john -f

# View all client instances
systemctl list-units 'upscaling-client@*'
```

#### Multiple Clients

Run multiple client instances for different users:

```bash
# Enable clients for multiple users
sudo systemctl enable upscaling-client@john
sudo systemctl enable upscaling-client@jane
sudo systemctl enable upscaling-client@admin

# Start all enabled clients
sudo systemctl start upscaling-client@john
sudo systemctl start upscaling-client@jane
sudo systemctl start upscaling-client@admin

# View all clients
systemctl list-units 'upscaling-client@*' --all
```

### Log Management

#### View Logs

```bash
# Server logs
sudo journalctl -u upscaling-server

# Client logs (for user 'john')
sudo journalctl -u upscaling-client@john

# Combined logs (server + all clients)
sudo journalctl -u 'upscaling-*'

# Follow logs
sudo journalctl -u upscaling-server -f

# Show last 100 lines
sudo journalctl -u upscaling-server -n 100

# Show logs from specific time
sudo journalctl -u upscaling-server --since "2025-10-14 10:00:00"
sudo journalctl -u upscaling-server --since "1 hour ago"
sudo journalctl -u upscaling-server --since today

# Show logs with context
sudo journalctl -u upscaling-server -o verbose
```

#### Log Rotation

Systemd automatically manages log rotation. Configure limits in `/etc/systemd/journald.conf`:

```ini
[Journal]
# Maximum size of persistent journal
SystemMaxUse=1G

# Maximum size of runtime journal
RuntimeMaxUse=100M

# Retention period
MaxRetentionSec=1month
```

Apply changes:

```bash
sudo systemctl restart systemd-journald
```

### Service Management Examples

#### Check Resource Usage

```bash
# Show CPU and memory usage
systemd-cgtop

# Show detailed status
systemctl show upscaling-server

# Check memory usage
systemctl status upscaling-server | grep Memory

# Check all running services
systemctl list-units --type=service --state=running
```

#### Restart All Services

```bash
# Restart server and all clients
sudo systemctl restart upscaling-server
sudo systemctl restart 'upscaling-client@*'
```

## Troubleshooting

### Service Won't Start

#### Check Status and Logs

```bash
# Check service status
sudo systemctl status upscaling-server

# Check journal for errors
sudo journalctl -xeu upscaling-server

# Check full log
sudo journalctl -u upscaling-server --no-pager
```

#### Common Issues

**Permission Denied**

```bash
# Check file ownership
ls -la /opt/UpscalingByNetwork/server/

# Fix ownership
sudo chown -R upscaling:upscaling /opt/UpscalingByNetwork
```

**Missing Dependencies**

```bash
# Test Python imports as service user
sudo -u upscaling python3 -c "import PyQt5, qasync, cryptography"

# Install missing packages
sudo pip3 install PyQt5 qasync cryptography
```

**Port Already in Use**

```bash
# Check what's using port 8888
sudo netstat -tlnp | grep 8888
sudo lsof -i :8888

# Change port in environment file
echo "SERVER_PORT=9999" | sudo tee -a /etc/upscaling/server.env

# Restart service
sudo systemctl restart upscaling-server
```

**GPU Access Issues**

```bash
# Check GPU devices
ls -la /dev/dri/
ls -la /dev/nvidia*

# Add user to video group (for AMD/Intel GPU)
sudo usermod -aG video upscaling

# Add user to render group
sudo usermod -aG render upscaling

# For NVIDIA, check nvidia-docker
nvidia-smi
```

### Service Crashes Frequently

#### Check Resource Limits

```bash
# View current limits
systemctl show upscaling-server | grep -E "(Memory|CPU|Tasks)"

# Increase limits in service file or override
sudo systemctl edit upscaling-server
```

Add:

```ini
[Service]
MemoryMax=8G
CPUQuota=400%
```

#### Check System Resources

```bash
# Check overall system resources
free -h
df -h
top

# Check OOM killer logs
sudo journalctl -k | grep -i "out of memory"
```

### Service Fails After Update

```bash
# Reload systemd after updating service files
sudo systemctl daemon-reload

# Restart service
sudo systemctl restart upscaling-server

# Check for failed services
systemctl --failed
```

### Reset Failed State

```bash
# Reset failed state
sudo systemctl reset-failed upscaling-server

# Restart
sudo systemctl start upscaling-server
```

## Security

### Security Features

The service files implement multiple security hardening measures:

#### Sandboxing

- **PrivateTmp**: Isolated `/tmp` directory
- **ProtectSystem**: Read-only system directories
- **ProtectHome**: Limited home directory access
- **ProtectKernelTunables**: Protected `/proc` and `/sys`
- **ProtectKernelModules**: Prevents kernel module loading
- **ProtectControlGroups**: Protected cgroup filesystem

#### System Call Filtering

- **SystemCallFilter**: Only allows specific syscalls
- Blocks privileged, resource, and obsolete syscalls
- Returns EPERM on blocked calls

#### Capabilities

- **NoNewPrivileges**: Prevents privilege escalation
- **CapabilityBoundingSet**: No capabilities granted
- **AmbientCapabilities**: No ambient capabilities

#### Namespace Restrictions

- **RestrictNamespaces**: Limits namespace creation
- **RestrictRealtime**: Blocks realtime scheduling
- **RestrictSUIDSGID**: Prevents SUID/SGID execution
- **LockPersonality**: Prevents personality changes

#### Device Access

- **PrivateDevices**: Minimal device access
- **DevicePolicy**: Closed by default
- **DeviceAllow**: Only GPU devices (DRI, NVIDIA)

### File Permissions

```bash
# Service files: read-only, owned by root
-rw-r--r-- root:root /etc/systemd/system/upscaling-*.service

# Application files: owned by service user
drwxr-x--- upscaling:upscaling /opt/UpscalingByNetwork

# Sensitive directories: restricted access
drwx------ upscaling:upscaling /opt/UpscalingByNetwork/server/server_work/encryption_keys

# Configuration files: restricted
-rw-r----- upscaling:upscaling /etc/upscaling/server.env
```

### Network Security

```bash
# Restrict server to localhost only
sudo systemctl edit upscaling-server
```

Add:

```ini
[Service]
Environment="SERVER_HOST=127.0.0.1"
```

### Audit Security Settings

```bash
# Check security settings
systemctl show upscaling-server | grep -E "(NoNewPrivileges|PrivateTmp|Protect|Device)"

# Analyze security with systemd-analyze
systemd-analyze security upscaling-server

# Score lower is better (0-10 scale)
```

## Performance Tuning

### CPU Limits

```bash
# Edit service
sudo systemctl edit upscaling-server
```

```ini
[Service]
# Allow more CPU (300% = 3 cores)
CPUQuota=300%

# CPU affinity (specific cores)
CPUAffinity=0 1 2 3
```

### Memory Limits

```ini
[Service]
# Increase memory limits
MemoryMax=16G
MemoryHigh=12G

# Swap limits
MemorySwapMax=0
```

### I/O Limits

```ini
[Service]
# I/O weight (100-10000, default 100)
IOWeight=500

# I/O read bandwidth limit
IOReadBandwidthMax=/dev/sda 100M

# I/O write bandwidth limit
IOWriteBandwidthMax=/dev/sda 50M
```

### File Descriptor Limits

```ini
[Service]
# Increase file descriptor limit
LimitNOFILE=131072
```

### Process Limits

```ini
[Service]
# Increase process/thread limit
LimitNPROC=8192
TasksMax=8192
```

### Nice Priority

```ini
[Service]
# Lower nice value = higher priority (-20 to 19)
Nice=-5

# I/O scheduling class
IOSchedulingClass=realtime
IOSchedulingPriority=0
```

### Apply Changes

```bash
sudo systemctl daemon-reload
sudo systemctl restart upscaling-server
```

## Uninstallation

### Quick Uninstall

```bash
cd /path/to/UpscalingByNetwork/scripts/services/systemd
chmod +x uninstall-systemd.sh
sudo ./uninstall-systemd.sh
```

The uninstall script will:
1. Stop all running services
2. Disable all enabled services
3. Remove systemd service files
4. Optionally remove application files
5. Optionally remove configuration files
6. Optionally remove service user
7. Optionally clean up client directories

### Manual Uninstallation

```bash
# Stop and disable services
sudo systemctl stop upscaling-server
sudo systemctl disable upscaling-server
sudo systemctl stop 'upscaling-client@*'
sudo systemctl disable 'upscaling-client@*'

# Remove service files
sudo rm /etc/systemd/system/upscaling-server.service
sudo rm /etc/systemd/system/upscaling-client@.service

# Reload systemd
sudo systemctl daemon-reload
sudo systemctl reset-failed

# Remove application (optional)
sudo rm -rf /opt/UpscalingByNetwork

# Remove configuration (optional)
sudo rm -rf /etc/upscaling

# Remove service user (optional)
sudo userdel upscaling

# Remove client directories (optional)
rm -rf ~/.upscaling
```

## Advanced Topics

### Running Behind a Reverse Proxy

Use nginx or Apache to proxy requests:

```nginx
# nginx configuration
server {
    listen 80;
    server_name upscaling.example.com;

    location / {
        proxy_pass http://127.0.0.1:8888;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Bind server to localhost:

```ini
[Service]
Environment="SERVER_HOST=127.0.0.1"
```

### Using with Docker

You can run the systemd services alongside Docker:

```bash
# Start Docker containers managed by systemd
sudo systemctl start docker

# Run complementary services
sudo systemctl start upscaling-server
```

### Monitoring with Prometheus

Export metrics to Prometheus:

```bash
# Install node_exporter for system metrics
sudo apt-get install prometheus-node-exporter

# Configure scraping in prometheus.yml
scrape_configs:
  - job_name: 'upscaling'
    static_configs:
      - targets: ['localhost:9100']
```

### High Availability Setup

Run multiple server instances with load balancing:

```bash
# Create multiple server instances
sudo cp upscaling-server.service upscaling-server@.service

# Edit to use different ports
sudo systemctl edit upscaling-server@8888
sudo systemctl edit upscaling-server@8889

# Start instances
sudo systemctl start upscaling-server@8888
sudo systemctl start upscaling-server@8889
```

## Support

### Getting Help

- Check logs: `sudo journalctl -xeu upscaling-server`
- Review service status: `systemctl status upscaling-server`
- Test Python environment: `sudo -u upscaling python3 /opt/UpscalingByNetwork/server/main.py --help`

### Reporting Issues

When reporting issues, include:

```bash
# System information
uname -a
systemctl --version
python3 --version

# Service status
systemctl status upscaling-server

# Recent logs
journalctl -u upscaling-server -n 100 --no-pager

# Configuration
cat /etc/upscaling/server.env
```

## License

Same license as UpscalingByNetwork project.

## Contributing

Contributions welcome! Please test changes thoroughly before submitting.
