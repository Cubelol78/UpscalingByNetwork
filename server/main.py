#!/usr/bin/env python3
"""
UpscalingByNetwork/server/main.py
Main entry point for the distributed upscaling server

Supports:
- GUI mode (PyQt5 with qasync)
- CLI mode (Rich console interface)
- Headless mode (minimal output)
- Daemon mode (systemd/Windows service)
- Auto-detection of display availability
"""

import sys
import os
import asyncio
import logging
import argparse
from pathlib import Path
from typing import Optional

# Path setup
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
server_root = current_dir

# Add necessary paths
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(server_root))


# ============================================================================
# Logging Configuration
# ============================================================================

def setup_logging(log_level: str = "INFO", log_file: Optional[Path] = None):
    """
    Configure logging system with file and console handlers

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional log file path
    """
    log_dir = server_root / "logs"
    log_dir.mkdir(exist_ok=True)

    # Determine log file
    if log_file is None:
        log_file = log_dir / "server.log"

    # Configure logging format
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'

    # Create handlers
    handlers = [
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]

    # Basic configuration
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=log_format,
        datefmt=date_format,
        handlers=handlers
    )

    # Set specific log levels for noisy libraries
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    logging.getLogger('PIL').setLevel(logging.WARNING)


# ============================================================================
# Dependency Checking
# ============================================================================

def check_dependencies(gui_required: bool = False) -> tuple[bool, list[str]]:
    """
    Check for required and optional dependencies

    Args:
        gui_required: Whether GUI dependencies are required

    Returns:
        Tuple of (all_ok, missing_deps)
    """
    missing_deps = []
    optional_missing = []

    # Core dependencies
    core_deps = {
        'cryptography': 'cryptography',
        'PIL': 'Pillow',
        'psutil': 'psutil',
    }

    for module, package in core_deps.items():
        try:
            __import__(module)
        except ImportError:
            missing_deps.append(package)

    # GUI dependencies (optional unless gui_required)
    gui_deps = {
        'PyQt5': 'PyQt5',
        'qasync': 'qasync',
    }

    for module, package in gui_deps.items():
        try:
            __import__(module)
        except ImportError:
            if gui_required:
                missing_deps.append(package)
            else:
                optional_missing.append(package)

    # CLI enhancement (optional)
    try:
        import rich
    except ImportError:
        optional_missing.append('rich')

    # Log results
    logger = logging.getLogger(__name__)

    if missing_deps:
        logger.error("Required dependencies missing:")
        for dep in missing_deps:
            logger.error(f"  - {dep}")
        logger.error("Install with: pip install " + " ".join(missing_deps))

    if optional_missing:
        logger.info("Optional dependencies missing (non-critical):")
        for dep in optional_missing:
            logger.info(f"  - {dep}")

    return len(missing_deps) == 0, missing_deps


# ============================================================================
# Directory Setup
# ============================================================================

def create_directories():
    """Create necessary working directories"""
    directories = [
        server_root / "server_work",
        server_root / "server_work" / "jobs",
        server_root / "server_work" / "temp",
        server_root / "server_work" / "encryption_keys",
        server_root / "logs",
        server_root / "output",
        server_root / "config",
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


# ============================================================================
# Display Detection
# ============================================================================

def detect_display_available() -> bool:
    """
    Detect if a display is available for GUI
    Works on Linux, Windows, and macOS
    """
    # Linux/Unix - check DISPLAY or WAYLAND_DISPLAY
    if sys.platform.startswith('linux') or sys.platform == 'darwin':
        if os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'):
            return True
        return False

    # Windows - usually has display unless running as service
    elif sys.platform == 'win32':
        # Check if running as Windows service
        try:
            import win32api
            import win32con
            try:
                # This will fail if running as a service
                win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
                return True
            except (OSError, AttributeError, Exception):
                # Service mode or API call failed
                return False
        except ImportError:
            # Assume display available if we can't check
            return True

    return False


# ============================================================================
# Server Mode Runners
# ============================================================================

async def run_server_gui(host: str = "0.0.0.0", port: int = 8888):
    """
    Launch server with GUI interface

    Args:
        host: Server bind address
        port: Server port
    """
    logger = logging.getLogger(__name__)

    try:
        # Import GUI modules
        import qasync
        from PyQt5.QtWidgets import QApplication
        from gui.server_window import ServerWindow

        # Create Qt application
        app = QApplication(sys.argv)
        app.setApplicationName("UpscalingByNetwork Server")
        app.setApplicationVersion("1.0.0")
        app.setOrganizationName("UpscalingByNetwork")

        # Create async event loop
        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)

        # Create and show main window
        window = ServerWindow()
        window.set_server_config(host, port)
        window.show()

        logger.info(f"GUI server started on {host}:{port}")

        # Run event loop - use asyncio.Event for proper qasync integration
        # This keeps the event loop running until the window is closed
        shutdown_event = asyncio.Event()

        # Connect window close to shutdown event
        def on_close():
            shutdown_event.set()

        # Override the window's closeEvent to trigger shutdown
        original_close_event = window.closeEvent
        def close_event_wrapper(event):
            original_close_event(event)
            if event.isAccepted():
                on_close()
        window.closeEvent = close_event_wrapper

        # Wait for shutdown event
        with loop:
            await shutdown_event.wait()

    except ImportError as e:
        logger.error(f"GUI dependencies not available: {e}")
        logger.info("Solution: pip install PyQt5 qasync")
        logger.info("Or use --no-gui for headless mode")
        return False
    except Exception as e:
        logger.error(f"GUI error: {e}", exc_info=True)
        return False


async def run_server_cli(host: str = "0.0.0.0", port: int = 8888,
                         interactive: bool = True):
    """
    Launch server with CLI interface

    Args:
        host: Server bind address
        port: Server port
        interactive: Enable interactive mode with live updates
    """
    logger = logging.getLogger(__name__)

    try:
        # Import server and CLI
        from core.distributed_server import DistributedServer
        from cli import ServerCLI

        logger.info(f"Starting CLI server on {host}:{port}")

        # Create and start server
        server = DistributedServer()

        # Create CLI interface
        cli = ServerCLI(server, interactive=interactive)
        cli.print_startup_banner()

        # Start server
        await server.start(host, port)

        logger.info("Server started successfully")

        # Run CLI interface
        await cli.run()

    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
    except Exception as e:
        logger.error(f"CLI server error: {e}", exc_info=True)
        return False


async def run_server_headless(host: str = "0.0.0.0", port: int = 8888):
    """
    Launch server in headless mode (minimal output)

    Args:
        host: Server bind address
        port: Server port
    """
    logger = logging.getLogger(__name__)

    try:
        from core.distributed_server import DistributedServer

        logger.info(f"Starting headless server on {host}:{port}")

        # Create and start server
        server = DistributedServer()
        await server.start(host, port)

        logger.info("Server started. Press Ctrl+C to stop.")

        # Keep running
        try:
            while True:
                await asyncio.sleep(10)

                # Log periodic status
                stats = server.get_server_stats()
                logger.debug(
                    f"Status: {stats['clients_connected']} clients, "
                    f"{stats['active_jobs']} jobs"
                )
        except KeyboardInterrupt:
            logger.info("Stopping server...")
            await server.stop()

    except Exception as e:
        logger.error(f"Headless server error: {e}", exc_info=True)
        return False


# ============================================================================
# Daemon Mode
# ============================================================================

async def run_server_daemon(host: str = "0.0.0.0", port: int = 8888,
                           pid_file: Optional[Path] = None):
    """
    Launch server in daemon mode

    Args:
        host: Server bind address
        port: Server port
        pid_file: Optional PID file path
    """
    logger = logging.getLogger(__name__)

    try:
        from daemon import DaemonServer

        logger.info(f"Starting daemon server on {host}:{port}")

        # Create daemon server
        daemon = DaemonServer(host, port, pid_file)
        await daemon.run()

    except ImportError:
        logger.error("Daemon module not available")
        logger.info("Running in headless mode instead")
        await run_server_headless(host, port)
    except Exception as e:
        logger.error(f"Daemon server error: {e}", exc_info=True)
        return False


# ============================================================================
# Configuration File Support
# ============================================================================

def load_config_file(config_path: Path) -> dict:
    """
    Load configuration from file

    Args:
        config_path: Path to configuration file

    Returns:
        Configuration dictionary
    """
    import json
    import yaml

    logger = logging.getLogger(__name__)

    if not config_path.exists():
        logger.error(f"Configuration file not found: {config_path}")
        return {}

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            if config_path.suffix in ['.json']:
                return json.load(f)
            elif config_path.suffix in ['.yaml', '.yml']:
                return yaml.safe_load(f)
            else:
                logger.error(f"Unsupported config format: {config_path.suffix}")
                return {}
    except Exception as e:
        logger.error(f"Error loading config file: {e}")
        return {}


# ============================================================================
# Main Entry Point
# ============================================================================

def parse_arguments():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description="UpscalingByNetwork Distributed Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start with GUI (auto-detect display)
  python main.py

  # Start in CLI mode with custom port
  python main.py --no-gui --port 9000

  # Start in headless mode
  python main.py --no-gui --non-interactive

  # Start as daemon (Linux/systemd)
  python main.py --daemon --host 0.0.0.0 --port 8888

  # Use custom configuration file
  python main.py --config server_config.json

  # Enable debug logging
  python main.py --log-level DEBUG
        """
    )

    # Server options
    parser.add_argument('--host', default='0.0.0.0',
                       help='Server bind address (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=8888,
                       help='Server port (default: 8888)')

    # Mode options
    mode_group = parser.add_argument_group('mode options')
    mode_group.add_argument('--no-gui', action='store_true',
                           help='Disable GUI, use CLI mode')
    mode_group.add_argument('--non-interactive', action='store_true',
                           help='Non-interactive mode (headless)')
    mode_group.add_argument('--daemon', action='store_true',
                           help='Run as daemon/service')

    # Configuration
    parser.add_argument('--config', type=Path,
                       help='Path to configuration file (JSON or YAML)')

    # Logging
    parser.add_argument('--log-level',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       default='INFO',
                       help='Logging level (default: INFO)')
    parser.add_argument('--log-file', type=Path,
                       help='Log file path (default: logs/server.log)')

    # Daemon options
    daemon_group = parser.add_argument_group('daemon options')
    daemon_group.add_argument('--pid-file', type=Path,
                             help='PID file path for daemon mode')

    return parser.parse_args()


def main():
    """Main entry point"""
    args = parse_arguments()

    # Load configuration file if provided
    config = {}
    if args.config:
        config = load_config_file(args.config)

    # Apply config file values (command-line args take precedence)
    host = args.host or config.get('host', '0.0.0.0')
    port = args.port or config.get('port', 8888)
    log_level = args.log_level or config.get('log_level', 'INFO')

    # Setup logging
    setup_logging(log_level, args.log_file)
    logger = logging.getLogger(__name__)

    logger.info("=" * 70)
    logger.info("UpscalingByNetwork Distributed Server v1.0.0")
    logger.info("=" * 70)
    logger.info(f"Project root: {project_root}")
    logger.info(f"Server root: {server_root}")
    logger.info(f"Python: {sys.version}")
    logger.info(f"Platform: {sys.platform}")

    # Create directories
    create_directories()

    # Determine mode
    if args.daemon:
        mode = 'daemon'
        gui_required = False
    elif args.non_interactive:
        mode = 'headless'
        gui_required = False
    elif args.no_gui:
        mode = 'cli'
        gui_required = False
    else:
        # Auto-detect: try GUI if display available
        display_available = detect_display_available()
        logger.info(f"Display available: {display_available}")

        if display_available:
            mode = 'gui'
            gui_required = True
        else:
            logger.info("No display detected, falling back to CLI mode")
            mode = 'cli'
            gui_required = False

    logger.info(f"Mode: {mode}")

    # Check dependencies
    deps_ok, missing = check_dependencies(gui_required)
    if not deps_ok:
        logger.error("Cannot start server due to missing dependencies")
        logger.error(f"Install with: pip install {' '.join(missing)}")
        return 1

    # Run server in selected mode
    try:
        if mode == 'gui':
            logger.info(f"Starting GUI mode on {host}:{port}")
            asyncio.run(run_server_gui(host, port))

        elif mode == 'cli':
            logger.info(f"Starting CLI mode on {host}:{port}")
            asyncio.run(run_server_cli(host, port, interactive=True))

        elif mode == 'headless':
            logger.info(f"Starting headless mode on {host}:{port}")
            asyncio.run(run_server_headless(host, port))

        elif mode == 'daemon':
            logger.info(f"Starting daemon mode on {host}:{port}")
            asyncio.run(run_server_daemon(host, port, args.pid_file))

    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1

    logger.info("Server stopped successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
