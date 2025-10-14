# UpscalingByNetwork Server - CLI/Headless Mode

Complete guide for running the server in CLI and headless modes on Linux, Windows, and Docker.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Running Modes](#running-modes)
- [Linux Systemd Service](#linux-systemd-service)
- [Windows Service](#windows-service)
- [Docker Deployment](#docker-deployment)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

## Features

- **Multiple Run Modes:**
  - GUI mode (with PyQt5)
  - CLI mode (with Rich library for beautiful terminal UI)
  - Headless mode (minimal output)
  - Daemon mode (systemd/Windows service)

- **Auto-Detection:**
  - Automatically detects display availability
  - Falls back to CLI mode when no display is available

- **Full CLI Arguments:**
  - `--host` - Server bind address
  - `--port` - Server port
  - `--no-gui` - Force CLI mode
  - `--non-interactive` - Headless mode
  - `--daemon` - Daemon/service mode
  - `--config` - Configuration file path
  - `--log-level` - Logging level (DEBUG, INFO, WARNING, ERROR)
  - `--log-file` - Custom log file path
  - `--pid-file` - PID file for daemon mode

- **Production Ready:**
  - Graceful shutdown (SIGTERM, SIGINT, Ctrl+C)
  - Signal handling
  - PID file management
  - systemd integration
  - Windows Service support
  - Docker support

## Installation

### Basic Installation

```bash
# Clone repository
cd /DATA-2T/UpscalingByNetwork/server

# Install dependencies
pip install -r requirements.txt
```

### For CLI Mode (Enhanced)

```bash
# Install Rich library for beautiful terminal UI
pip install rich
```

### For Windows Service

```bash
# Install Windows service support
pip install pywin32
```

## Usage

### Basic Usage

```bash
# Start with auto-detection (GUI if available, CLI otherwise)
python main.py

# Start in CLI mode
python main.py --no-gui

# Start in headless mode
python main.py --no-gui --non-interactive

# Custom host and port
python main.py --no-gui --host 0.0.0.0 --port 9000

# Enable debug logging
python main.py --no-gui --log-level DEBUG

# Use configuration file
python main.py --config config/server_config.json
```

### CLI Mode Features

When running in CLI mode (with Rich library installed), you get:

- **Real-time dashboard** with server statistics
- **Connected clients table** with status
- **Live updates** every 2 seconds
- **Beautiful colored output**
- **Resource monitoring** (CPU, memory)

### Headless Mode Features

Headless mode is perfect for:
- Running in SSH sessions
- Docker containers
- Background processes
- Systems without display

```bash
python main.py --no-gui --non-interactive --host 0.0.0.0 --port 8888
```

## Running Modes

### 1. GUI Mode (Default with Display)

```bash
python main.py
```

Requires:
- Display available (X11, Wayland on Linux)
- PyQt5 and qasync installed

### 2. CLI Mode (Interactive)

```bash
python main.py --no-gui
```

Features:
- Live dashboard with Rich library
- Real-time statistics
- Client monitoring
- Graceful shutdown with Ctrl+C

### 3. Headless Mode (Non-Interactive)

```bash
python main.py --no-gui --non-interactive
```

Features:
- Minimal console output
- Logs to file
- Perfect for Docker/systemd
- Low resource usage

### 4. Daemon Mode

```bash
python main.py --daemon --host 0.0.0.0 --port 8888
```

Features:
- Background process
- PID file management
- Signal handling
- Integration with systemd/init.d

## Linux Systemd Service

### Installation

```bash
# Run installation script (as root)
sudo ./install-systemd.sh
```

This will:
1. Copy server files to `/opt/upscaling-server`
2. Create Python virtual environment
3. Install dependencies
4. Configure systemd service
5. Enable auto-start on boot

### Manual Installation

```bash
# Copy service file
sudo cp upscaling-server.service /etc/systemd/system/

# Edit paths if needed
sudo nano /etc/systemd/system/upscaling-server.service

# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable upscaling-server
```

### Service Management

```bash
# Start service
sudo systemctl start upscaling-server

# Stop service
sudo systemctl stop upscaling-server

# Restart service
sudo systemctl restart upscaling-server

# Check status
sudo systemctl status upscaling-server

# View logs
sudo journalctl -u upscaling-server -f

# View last 100 lines
sudo journalctl -u upscaling-server -n 100
```

### Service Configuration

The systemd service runs with:
- User: `nobody`
- Group: `nogroup`
- Working directory: `/opt/upscaling-server`
- Auto-restart on failure
- Resource limits (configurable)

Edit `/etc/systemd/system/upscaling-server.service` to customize.

## Windows Service

### Installation

```powershell
# Run PowerShell as Administrator
.\install-windows-service.ps1 install
```

This will:
1. Check for Python installation
2. Install pywin32 if needed
3. Register Windows service
4. Configure auto-start

### Manual Installation

```powershell
# Install pywin32
pip install pywin32

# Install service
python windows-service-wrapper.py install
```

### Service Management

Using PowerShell (as Administrator):

```powershell
# Start service
.\install-windows-service.ps1 start
# OR
net start UpscalingByNetwork

# Stop service
.\install-windows-service.ps1 stop
# OR
net stop UpscalingByNetwork

# Check status
.\install-windows-service.ps1 status
# OR
sc query UpscalingByNetwork

# Restart service
.\install-windows-service.ps1 restart

# Uninstall service
.\install-windows-service.ps1 uninstall
```

Using Services Manager:
1. Press `Win + R`
2. Type `services.msc`
3. Find "UpscalingByNetwork Distributed Server"
4. Right-click for options

### Service Logs

Windows service logs to:
- File: `logs/service.log`
- Event Viewer: Windows Logs → Application

## Docker Deployment

### Quick Start

```bash
# Build and run with docker-compose
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Manual Docker Commands

```bash
# Build image
docker build -t upscaling-server .

# Run container
docker run -d \
  --name upscaling-server \
  -p 8888:8888 \
  -v $(pwd)/logs:/app/server/logs \
  -v $(pwd)/output:/app/server/output \
  -v $(pwd)/server_work:/app/server/server_work \
  -e SERVER_HOST=0.0.0.0 \
  -e SERVER_PORT=8888 \
  -e SERVER_MODE=headless \
  -e LOG_LEVEL=INFO \
  upscaling-server

# View logs
docker logs -f upscaling-server

# Stop and remove
docker stop upscaling-server
docker rm upscaling-server
```

### Docker Environment Variables

- `SERVER_HOST` - Bind address (default: 0.0.0.0)
- `SERVER_PORT` - Port (default: 8888)
- `SERVER_MODE` - Run mode: headless, cli, daemon (default: headless)
- `LOG_LEVEL` - Logging level: DEBUG, INFO, WARNING, ERROR (default: INFO)

### Docker Volumes

- `/app/server/logs` - Server logs
- `/app/server/output` - Processed videos
- `/app/server/server_work` - Working directory
- `/config` - Configuration files

## Configuration

### Configuration File

Create `config/server_config.json`:

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 8888,
    "max_clients": 10
  },
  "processing": {
    "batch_size": 50,
    "upscale_factor": 4,
    "realesrgan_model": "RealESRGAN_x4plus"
  },
  "storage": {
    "work_directory": "./server_work",
    "output_directory": "./output"
  },
  "monitoring": {
    "log_level": "INFO"
  }
}
```

Use with:

```bash
python main.py --config config/server_config.json
```

### Environment Variables

For Docker or systemd, you can use environment variables:

```bash
export SERVER_HOST=0.0.0.0
export SERVER_PORT=8888
export LOG_LEVEL=INFO
```

## Troubleshooting

### No Display Detected

If you see "No display detected, falling back to CLI mode":

**On Linux:**
```bash
# Check DISPLAY variable
echo $DISPLAY

# Set if missing
export DISPLAY=:0

# Or use CLI mode explicitly
python main.py --no-gui
```

**On Windows:**
- This usually means running as a service
- Use `--no-gui` flag explicitly

### Rich Library Not Available

If you see "Warning: Rich library not available":

```bash
pip install rich
```

The server will still work with basic text output.

### Permission Denied (Linux)

For systemd service:

```bash
# Check file permissions
ls -la /opt/upscaling-server

# Fix if needed
sudo chown -R nobody:nogroup /opt/upscaling-server
sudo chmod -R 755 /opt/upscaling-server
```

### Port Already in Use

```bash
# Check what's using the port
sudo lsof -i :8888
# OR
sudo netstat -tulpn | grep 8888

# Use a different port
python main.py --no-gui --port 9000
```

### Windows Service Won't Start

1. Check logs in `logs/service.log`
2. Verify pywin32 is installed: `pip list | findstr pywin32`
3. Run as Administrator
4. Check Event Viewer for errors

### Docker Container Exits

```bash
# Check logs
docker logs upscaling-server

# Check if port is available
docker run --rm -p 8888:8888 alpine nc -l -p 8888

# Try with different mode
docker run -e SERVER_MODE=cli ...
```

## Examples

### Development Setup

```bash
# Run in CLI mode with debug logging
python main.py --no-gui --log-level DEBUG --port 8888
```

### Production Linux Server

```bash
# Install as systemd service
sudo ./install-systemd.sh

# Enable and start
sudo systemctl enable --now upscaling-server

# Monitor logs
sudo journalctl -u upscaling-server -f
```

### Production Windows Server

```powershell
# Run PowerShell as Administrator
.\install-windows-service.ps1 install
.\install-windows-service.ps1 start

# Check status
.\install-windows-service.ps1 status
```

### Docker Production

```bash
# Edit docker-compose.yml for your needs
docker-compose up -d

# Scale if needed (not applicable for this service, but for reference)
docker-compose up -d --scale upscaling-server=1

# Update and restart
docker-compose pull
docker-compose up -d
```

### Remote SSH Server

```bash
# Connect via SSH (no display)
ssh user@server

# Server auto-detects no display and uses CLI mode
cd /DATA-2T/UpscalingByNetwork/server
python main.py --no-gui --host 0.0.0.0 --port 8888

# Or use tmux/screen for persistence
tmux new -s upscaling
python main.py --no-gui
# Ctrl+B, D to detach
```

## Support

For issues, please check:
1. Log files in `logs/server.log`
2. System logs (journalctl on Linux, Event Viewer on Windows)
3. Docker logs if using containers
4. This README for common solutions

## License

See main project LICENSE file.
