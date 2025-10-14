# UpscalingByNetwork

> **Distributed Video Upscaling System powered by Real-ESRGAN**

A high-performance, distributed video upscaling solution that leverages multiple machines across a network to process video files using Real-ESRGAN AI models. Perfect for upscaling anime, videos, and images with GPU acceleration.

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Windows%20%7C%20macOS-lightgrey.svg)](https://github.com/)
[![Docker](https://img.shields.io/badge/Docker-Supported-blue.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [System Requirements](#system-requirements)
- [Performance](#performance)
- [Troubleshooting](#troubleshooting)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

---

## Features

### Core Capabilities
- ✅ **Distributed Processing**: Harness multiple machines across your network for parallel video upscaling
- ✅ **Real-ESRGAN Integration**: Industry-leading AI upscaling with multiple model support
- ✅ **GPU Acceleration**: NVIDIA, AMD, and Intel GPU support via Vulkan
- ✅ **High Performance**: Process large 4K+ videos efficiently with batch processing
- ✅ **Automatic Load Balancing**: Smart batch distribution based on client capabilities
- ✅ **Fault Tolerance**: Automatic retry on failure, batch reassignment, client monitoring

### Interfaces
- ✅ **Dual Interfaces**: Full-featured GUI (PyQt5) and powerful CLI (Click + Rich)
- ✅ **Headless Mode**: Run server/clients as background services
- ✅ **Cross-Platform**: Native support for Linux, Windows, and macOS

### Enterprise Features
- ✅ **Encryption**: End-to-end encryption for secure batch transmission
- ✅ **Authentication**: Client authentication and session management
- ✅ **Resource Management**: CPU, memory, and GPU resource controls
- ✅ **Monitoring**: Real-time statistics, progress tracking, performance metrics
- ✅ **Docker Support**: Production-ready containers with GPU support
- ✅ **Systemd Integration**: Linux service management with security hardening

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Server (Orchestrator)                    │
│  • Job Management    • Batch Distribution                   │
│  • Client Management • Video Processing Pipeline            │
│  • GUI/CLI Interface                                        │
└───────────────┬─────────────────────────────────────────────┘
                │
        WebSocket (Port 8888)
                │
    ┌───────────┼───────────┐
    │           │           │
┌───▼───┐   ┌──▼───┐   ┌──▼───┐
│Client │   │Client│   │Client│
│  #1   │   │  #2  │   │  #3  │
│ GPU   │   │ CPU  │   │ GPU  │
└───────┘   └──────┘   └──────┘
```

### Workflow

1. **Video Submission**: Submit video to server (GUI or command line)
2. **Frame Extraction**: Server extracts frames using FFmpeg
3. **Batch Creation**: Frames divided into batches (default: 50 frames)
4. **Distribution**: Batches assigned to available clients based on performance
5. **Processing**: Clients upscale frames using Real-ESRGAN
6. **Collection**: Server collects processed frames
7. **Assembly**: Final video assembled with FFmpeg, audio preserved

---

## Quick Start

### Using Docker (Recommended)

```bash
# Clone repository
git clone https://github.com/yourusername/UpscalingByNetwork.git
cd UpscalingByNetwork/docker

# Start server with Docker Compose
cp .env.example .env
docker-compose -f docker-compose-optimized.yml up -d

# Server is now running on port 8888
```

### Manual Installation (Linux)

```bash
# Server
cd scripts
sudo ./install.sh --server
upscaling-server  # Start server

# Client (on other machines)
sudo ./install.sh --client
upscaling-client --host SERVER_IP
```

---

## Installation

See detailed installation guides:
- **Server**: [Server Installation Guide](docs/SERVER_INSTALL.md)
- **Client**: [Client Installation Guide](docs/CLIENT_INSTALL.md)
- **Docker**: [Docker Guide](docker/README.md)
- **Systemd**: [Linux Services](scripts/services/systemd/README.md)

---

## Usage

### Server

**GUI Mode** (automatic if display detected):
```bash
python3 server/server_main.py
```

**CLI Mode** (headless):
```bash
python3 server/server_main.py --no-gui --host 0.0.0.0 --port 8888
```

**Systemd Service** (Linux):
```bash
sudo systemctl start upscaling-server
sudo journalctl -u upscaling-server -f
```

### Client

**GUI Mode**:
```bash
python3 client/linux/client_gui.py
```

**CLI Mode**:
```bash
python3 client/linux/client_main.py run --host SERVER_IP --port 8888
```

**Systemd Service** (Linux):
```bash
sudo systemctl start upscaling-client@$USER
```

---

## Configuration

Configuration files are automatically created on first run:

- **Server**: `~/.config/distributed-upscaling/server_config.json`
- **Client**: `~/.config/upscaling-client/config.json`
- **Docker**: `docker/.env`

Example server configuration:

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 8888
  },
  "processing": {
    "batch_size": 50
  },
  "realesrgan": {
    "model": "realesr-animevideov3",
    "scale": 4
  }
}
```

---

## System Requirements

### Server
- CPU: 4+ cores
- RAM: 8 GB minimum, 16 GB recommended
- Storage: 100 GB+ free (SSD recommended)
- Network: 100 Mbps minimum, 1 Gbps recommended

### Client
- **CPU-only**: 4 cores, 4 GB RAM
- **GPU-accelerated**: NVIDIA RTX 2060+ / AMD RX 5700+ / Intel Arc, 6 GB+ VRAM

---

## Performance

**GPU vs CPU** (1080p → 4K upscaling):
- CPU (Ryzen 9): ~10-20 sec/frame
- GPU (RTX 3070): ~1-2 sec/frame
- **10-20x faster with GPU!**

**10 Distributed Clients** (1-minute 1080p video):
- Single client: ~25-50 minutes
- 10 clients: ~2.5-5 minutes
- **10x speedup with distribution!**

---

## Troubleshooting

See [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for common issues.

**Quick fixes**:

**Server won't start**:
```bash
# Check port
sudo lsof -i :8888

# Check logs
tail -f server/logs/server.log
```

**Client can't connect**:
```bash
# Test connection
python3 client_main.py test-connection --host SERVER_IP

# Check firewall
sudo ufw allow 8888/tcp
```

**GPU not detected**:
```bash
# NVIDIA
nvidia-smi

# Vulkan
vulkaninfo | grep deviceName
```

---

## Documentation

- [Server Installation](docs/SERVER_INSTALL.md)
- [Client Installation](docs/CLIENT_INSTALL.md)
- [Docker Guide](docker/README.md)
- [Systemd Services](scripts/services/systemd/README.md)
- [Configuration Reference](docs/CONFIGURATION.md)
- [API Documentation](docs/API.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

---

## Project Structure

```
UpscalingByNetwork/
├── server/                # Server application
│   ├── core/             # Core logic
│   ├── gui/              # PyQt5 GUI
│   ├── server_main.py    # Entry point
│   └── server_cli.py     # CLI interface
├── client/               # Client applications
│   ├── linux/           # Linux/cross-platform client
│   └── windows/         # Windows client
├── docker/               # Docker configurations
│   ├── Dockerfile.server-optimized
│   ├── Dockerfile.server-gpu
│   └── docker-compose-optimized.yml
├── scripts/              # Installation scripts
│   ├── install.sh       # Linux installer
│   ├── install.ps1      # Windows installer
│   └── services/        # Systemd/Windows services
└── docs/                 # Documentation
```

---

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Submit a pull request

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

---

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) for details.

---

## Acknowledgments

- **Real-ESRGAN**: [xinntao/Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN)
- **FFmpeg**: [FFmpeg](https://ffmpeg.org/)
- **PyQt5**: [Riverbank Computing](https://www.riverbankcomputing.com/software/pyqt/)

---

## Support

- Issues: [GitHub Issues](https://github.com/yourusername/UpscalingByNetwork/issues)
- Discussions: [GitHub Discussions](https://github.com/yourusername/UpscalingByNetwork/discussions)

---

**Made with ❤️ by the UpscalingByNetwork Team**
