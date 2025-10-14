# Linux Client Architecture

## Overview

The Linux client is a complete rewrite of the Windows client with cross-platform compatibility, improved architecture, and both CLI and GUI interfaces.

## Key Improvements Over Windows Client

### 1. Cross-Platform Compatibility

- **No Windows-specific code**: Removed all WMI and Windows-only dependencies
- **Platform detection**: Automatic platform detection for Windows, Linux, macOS
- **Path handling**: Uses `pathlib` for cross-platform path operations
- **Executable detection**: Finds Real-ESRGAN executable on any platform

### 2. Linux-Specific Features

- **XDG Base Directory**: Follows XDG specification for config/data directories
  - Config: `~/.config/upscaling-client/`
  - Data: `~/.local/share/upscaling-client/`
  - Runtime: `$XDG_RUNTIME_DIR/upscaling-client/` or `/tmp/upscaling-client/`

- **Signal Handling**: Proper SIGTERM and SIGINT handling for graceful shutdown

- **GPU Detection**:
  - NVIDIA: Uses `pynvml` (Linux-compatible)
  - AMD/Intel: Uses `lspci` on Linux
  - No WMI or GPUtil dependencies

- **Systemd Integration**: Includes systemd service file for daemon mode

### 3. Dual Interface

#### CLI Mode (Click + Rich)
- Beautiful terminal UI with colors and progress bars
- Command-line interface with subcommands
- Can run headless on servers
- Signal handling for clean shutdown

#### GUI Mode (PyQt5)
- Optional graphical interface
- Same codebase as Windows client
- Can be disabled if not needed

### 4. Improved Architecture

#### Modular Design
```
core/
├── client.py           # Main client orchestration
├── connection.py       # WebSocket connection manager
├── processor.py        # Image processing
├── batch_processor.py  # Batch queue management
└── security.py         # Encryption/decryption
```

#### Separation of Concerns
- **Connection**: Handles WebSocket, reconnection, message routing
- **Processor**: Handles image processing, Real-ESRGAN execution
- **Security**: Handles encryption, key exchange
- **Client**: Orchestrates everything

### 5. Enhanced Configuration

- JSON-based configuration
- Environment variable support
- Command-line overrides
- XDG-compliant paths
- Validation and defaults

### 6. Better Logging

- Colored console output
- File rotation (10MB, 5 backups)
- Separate error log
- Structured logging with context
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL

## Module Documentation

### Core Modules

#### `core/client.py`
Main client class that orchestrates all components.

**Key Features**:
- Async/await throughout
- Event-driven architecture
- Automatic reconnection
- Message routing
- Status reporting

**Public API**:
```python
client = DistributedUpscalingClient()
await client.connect(host, port)
await client.disconnect()
status = client.get_status()
await client.cleanup()
```

#### `core/connection.py`
WebSocket connection manager with reconnection logic.

**Key Features**:
- Connection state machine
- Automatic reconnection with backoff
- Message handlers registration
- Event callbacks
- Heartbeat support

**States**:
- DISCONNECTED
- CONNECTING
- CONNECTED
- AUTHENTICATING
- READY
- ERROR
- RECONNECTING

#### `core/processor.py`
Image batch processor using Real-ESRGAN.

**Key Features**:
- Batch extraction from ZIP
- Real-ESRGAN execution
- Result packaging
- Automatic cleanup
- Statistics tracking

#### `core/security.py`
Security layer for encryption/decryption.

**Key Features**:
- RSA key pair generation
- Session key exchange
- Fernet encryption
- Graceful degradation if crypto unavailable

### Utility Modules

#### `utils/config.py`
Configuration management with XDG support.

**Features**:
- Dot notation for nested keys
- Default values
- Validation
- Import/export
- Platform-specific paths

#### `utils/system_info.py`
Cross-platform system information collector.

**Features**:
- CPU info (psutil)
- Memory info
- GPU detection (pynvml, lspci)
- Vulkan detection
- Performance scoring

#### `utils/realesrgan_handler.py`
Real-ESRGAN executable wrapper.

**Features**:
- Automatic executable detection
- Model management
- Async execution
- Progress callbacks
- Statistics

#### `utils/logger.py`
Logging configuration and utilities.

**Features**:
- Colored console output
- File rotation
- Multiple log levels
- Context managers
- Decorators

### CLI Modules

#### `cli/commands.py`
Click-based command-line interface.

**Commands**:
- `run`: Run client in interactive mode
- `status`: Show client status
- `info`: Show system information
- `test-connection`: Test server connection
- `test-realesrgan`: Test Real-ESRGAN
- `config-*`: Configuration management
- `version`: Show version

#### `cli/ui.py`
Rich-based terminal UI components.

**Features**:
- Status tables
- Progress bars
- Colored output
- System info display
- Error/success messages

### GUI Modules

#### `gui/main_window.py`
Main PyQt5 window.

**Features**:
- Tab-based interface
- Auto-refresh status
- Connection/processing/settings tabs

#### `gui/connection_panel.py`
Connection controls.

**Features**:
- Server configuration
- Connect/disconnect
- Status log

#### `gui/processing_panel.py`
Processing status display.

**Features**:
- Current batch info
- Progress bar
- Statistics display

#### `gui/settings_panel.py`
Settings editor.

**Features**:
- Processing configuration
- Model selection
- GPU settings

## Protocol Compatibility

The Linux client is 100% compatible with the existing server protocol:

### Message Types Handled
- `server_hello`: Authentication response
- `batch_assignment`: Receive batch to process
- `batch_request`: Server requests availability
- `configuration_update`: Server updates config
- `ping`: Heartbeat
- `disconnect`: Graceful disconnect
- `error`: Error messages

### Message Types Sent
- `client_hello`: Initial authentication
- `batch_result`: Processing results
- `batch_availability`: Availability response
- `heartbeat`: Keep-alive
- `pong`: Heartbeat response

## Security

### Encryption
- RSA 2048-bit key pairs
- Fernet symmetric encryption for data
- Session key exchange
- Secure message signing

### Authentication
- Client ID (UUID)
- MAC address
- Public key exchange
- Session establishment

### Data Protection
- All batch data encrypted
- Session timeout
- Automatic key rotation

## Performance

### Optimization Strategies
- Async/await throughout
- Concurrent batch processing
- Efficient file I/O
- Memory-mapped files for large batches
- Automatic cleanup of old files

### Resource Management
- Configurable memory limits
- Disk space monitoring
- CPU/GPU load balancing
- Automatic tile size adjustment

## Testing

### Unit Tests
```bash
pytest tests/test_client.py
pytest tests/test_processor.py
pytest tests/test_security.py
```

### Integration Tests
```bash
pytest tests/test_integration.py
```

### Manual Testing
```bash
# Test Real-ESRGAN
python client_main.py test-realesrgan

# Test connection
python client_main.py test-connection --host localhost

# Test processing (requires server)
python client_main.py run --host localhost
```

## Deployment

### Development
```bash
python client_main.py run --host localhost
```

### Production (Systemd)
```bash
sudo systemctl enable upscaling-client@$USER
sudo systemctl start upscaling-client@$USER
```

### Docker
```bash
docker build -t upscaling-client .
docker run -d upscaling-client
```

## Future Enhancements

### Planned Features
1. Multi-server support (failover)
2. Local caching
3. Batch prioritization
4. Load balancing
5. Metrics export (Prometheus)
6. Web dashboard
7. REST API
8. Plugin system

### Known Limitations
1. Single concurrent batch (by design)
2. No batch queuing (processed immediately)
3. Limited error recovery
4. No persistent state across restarts

## Contributing

When contributing to the Linux client:

1. **Follow the architecture**: Maintain separation of concerns
2. **Type hints**: All functions should have type hints
3. **Docstrings**: All public APIs need docstrings
4. **Error handling**: Always handle exceptions gracefully
5. **Logging**: Use appropriate log levels
6. **Testing**: Write tests for new features
7. **Documentation**: Update this file for major changes

## License

See main project LICENSE file.
