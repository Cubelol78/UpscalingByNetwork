# Distributed Upscaling Client - Linux Edition

Cross-platform distributed image upscaling client with CLI and GUI support.

## Features

- **Cross-Platform**: Works on Linux, Windows, and macOS
- **GPU Acceleration**: NVIDIA GPU support with pynvml
- **Dual Mode**: Both CLI and GUI interfaces
- **Secure Communication**: Encrypted client-server communication
- **Auto-Reconnection**: Automatic reconnection on connection loss
- **XDG Compliant**: Follows XDG Base Directory Specification on Linux
- **Rich CLI**: Beautiful terminal UI with progress bars and colors
- **Real-ESRGAN**: State-of-the-art image upscaling

## Installation

### Prerequisites

- Python 3.8 or higher
- Real-ESRGAN executable (`realesrgan-ncnn-vulkan`)

### Dependencies

Install required Python packages:

```bash
pip install websockets cryptography psutil pynvml click rich PyQt5
```

Or install from requirements file:

```bash
pip install -r requirements.txt
```

### Real-ESRGAN Setup

1. Download Real-ESRGAN from: https://github.com/xinntao/Real-ESRGAN
2. Place the executable in one of these locations:
   - `~/.local/bin/realesrgan-ncnn-vulkan`
   - `/usr/local/bin/realesrgan-ncnn-vulkan`
   - Project `dependencies/` directory
   - Or specify path in config

3. Place models in:
   - `~/.local/share/upscaling-client/models/`
   - Or next to the executable in `models/` directory

## Usage

### CLI Mode

Run the client in CLI mode:

```bash
# Basic usage
python client_main.py run --host SERVER_IP --port 8765

# Show help
python client_main.py --help

# Test connection
python client_main.py test-connection --host SERVER_IP --port 8765

# Show system info
python client_main.py info

# Test Real-ESRGAN
python client_main.py test-realesrgan

# Configuration management
python client_main.py config-show
python client_main.py config-set --key server.host --value 192.168.1.100
python client_main.py config-reset
```

### GUI Mode

Run the client with graphical interface:

```bash
python client_gui.py
```

## Configuration

Configuration is stored in:
- Linux: `~/.config/upscaling-client/config.json`
- Windows: `%APPDATA%\upscaling-client\config.json`

### Configuration Options

```json
{
  "server": {
    "host": "localhost",
    "port": 8765,
    "use_ssl": false
  },
  "processing": {
    "use_gpu": true,
    "gpu_id": 0,
    "tile_size": 256,
    "realesrgan_model": "RealESRGAN_x4plus",
    "scale": 4
  }
}
```

## Directory Structure

```
client/linux/
├── __init__.py
├── client_main.py          # CLI entry point
├── client_gui.py           # GUI entry point
├── core/                   # Core functionality
│   ├── client.py           # Main client
│   ├── processor.py        # Image processor
│   ├── connection.py       # Connection manager
│   ├── batch_processor.py  # Batch handling
│   └── security.py         # Security/encryption
├── gui/                    # GUI components
│   ├── main_window.py
│   ├── connection_panel.py
│   ├── processing_panel.py
│   └── settings_panel.py
├── cli/                    # CLI components
│   ├── commands.py         # Click commands
│   └── ui.py               # Rich UI
├── utils/                  # Utilities
│   ├── config.py           # Configuration
│   ├── system_info.py      # System detection
│   ├── realesrgan_handler.py
│   └── logger.py           # Logging
└── config/
    └── default_config.json
```

## Platform Support

### Linux
- ✅ Full support
- ✅ NVIDIA GPU detection via pynvml
- ✅ AMD/Intel GPU detection via lspci
- ✅ XDG Base Directory compliance
- ✅ Signal handling (SIGTERM, SIGINT)

### Windows
- ✅ Compatible with Windows client structure
- ✅ NVIDIA GPU detection
- ✅ Standard paths

### macOS
- ✅ Should work (untested)
- ✅ Standard paths

## Signal Handling

The client handles these signals gracefully:
- `SIGINT` (Ctrl+C): Graceful shutdown
- `SIGTERM`: Graceful shutdown

## Logging

Logs are stored in:
- Linux: `~/.local/share/upscaling-client/logs/`
- Windows: `%LOCALAPPDATA%\upscaling-client\logs\`

Log files:
- `client.log`: General logs
- `errors.log`: Errors and critical issues only

## GPU Support

### NVIDIA GPUs
Install pynvml:
```bash
pip install pynvml
```

### AMD/Intel GPUs
Automatic detection on Linux via lspci.

## Troubleshooting

### Real-ESRGAN not found
```bash
# Test Real-ESRGAN installation
python client_main.py test-realesrgan

# Specify path in config
python client_main.py config-set --key paths.realesrgan_executable --value /path/to/realesrgan-ncnn-vulkan
```

### Connection issues
```bash
# Test connection
python client_main.py test-connection --host SERVER_IP --port 8765

# Check firewall settings
sudo ufw status
```

### GPU not detected
```bash
# Install pynvml for NVIDIA GPUs
pip install pynvml

# Test GPU detection
python client_main.py info
```

## Development

### Running Tests
```bash
pytest tests/
```

### Code Style
```bash
black client/linux/
flake8 client/linux/
```

## License

See main project LICENSE file.

## Contributing

Contributions welcome! Please follow the project's coding standards and submit pull requests.

## Support

For issues and questions:
1. Check this README
2. Check the main project documentation
3. Open an issue on GitHub
