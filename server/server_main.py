#!/usr/bin/env python3
"""
Unified entry point for UpscalingByNetwork Server
Supports both GUI and CLI modes with auto-detection
"""

import sys
import os
import argparse
from pathlib import Path

# Add server directory to path
sys.path.insert(0, str(Path(__file__).parent))


def detect_display() -> bool:
    """Detect if a display is available"""
    if sys.platform == 'win32':
        # On Windows, assume GUI is available
        return True
    else:
        # On Linux/macOS, check DISPLAY environment variable
        return bool(os.environ.get('DISPLAY'))


def main():
    """Main entry point with mode detection"""
    parser = argparse.ArgumentParser(
        description='UpscalingByNetwork Server',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument(
        '--gui',
        action='store_true',
        help='Force GUI mode (requires display)'
    )

    parser.add_argument(
        '--no-gui',
        action='store_true',
        help='Force CLI/headless mode'
    )

    parser.add_argument(
        '--host',
        default=None,
        help='Server bind address (CLI mode)'
    )

    parser.add_argument(
        '--port',
        type=int,
        default=None,
        help='Server port (CLI mode)'
    )

    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level'
    )

    parser.add_argument(
        '--daemon',
        action='store_true',
        help='Run as daemon (implies --no-gui)'
    )

    args = parser.parse_args()

    # Determine mode
    if args.daemon:
        mode = 'daemon'
    elif args.gui:
        mode = 'gui'
    elif args.no_gui:
        mode = 'cli'
    else:
        # Auto-detect
        if detect_display():
            mode = 'gui'
        else:
            mode = 'cli'

    # Run in appropriate mode
    if mode == 'gui':
        try:
            from PyQt5.QtWidgets import QApplication
            from PyQt5.QtCore import Qt
            import qdarkstyle

            from gui.main_window import MainWindow
            from core.server import UpscalingServer
            from utils.logger import setup_logger

            # Setup logger
            logger = setup_logger()
            logger.info("Starting server in GUI mode")

            # Create Qt application
            app = QApplication(sys.argv)
            app.setApplicationName("Distributed Upscaling Server")
            app.setApplicationVersion("1.0.0")
            app.setOrganizationName("DistributedUpscaling")

            # Apply dark theme
            app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())

            # Create server and GUI
            server = UpscalingServer()
            main_window = MainWindow(server)
            main_window.show()

            logger.info("GUI started")

            # Run event loop
            exit_code = app.exec_()

            # Cleanup
            logger.info("Shutting down server")
            server.stop()

            sys.exit(exit_code)

        except ImportError as e:
            print(f"Error: GUI mode requires PyQt5 and qdarkstyle")
            print(f"Install with: pip install PyQt5 qdarkstyle")
            print(f"Error details: {e}")
            sys.exit(1)

    else:
        # CLI or daemon mode
        import server_cli

        # Run CLI
        sys.argv = [sys.argv[0]]  # Reset argv for server_cli

        if args.host:
            sys.argv.extend(['--host', args.host])
        if args.port:
            sys.argv.extend(['--port', str(args.port)])
        if args.log_level:
            sys.argv.extend(['--log-level', args.log_level])
        if args.daemon or mode == 'daemon':
            sys.argv.append('--daemon')

        server_cli.main()


if __name__ == "__main__":
    main()
