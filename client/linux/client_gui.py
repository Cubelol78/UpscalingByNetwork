#!/usr/bin/env python3
"""
GUI entry point for the Linux client
Requires PyQt5 for graphical interface
"""

import sys
import os
import asyncio
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))


def main():
    """Main GUI entry point"""
    try:
        from PyQt5.QtWidgets import QApplication, QMessageBox
        from PyQt5.QtCore import QTimer

    except ImportError:
        print("PyQt5 not available. Install with: pip install PyQt5")
        print("Or run in CLI mode: python client_main.py")
        sys.exit(1)

    try:
        from gui.main_window import ClientMainWindow
        from core.client import DistributedUpscalingClient
        from utils.logger import setup_logging
        from utils.config import config

    except ImportError as e:
        print(f"Error importing modules: {e}")
        sys.exit(1)

    # Setup logging
    log_level = config.get("client.log_level", "INFO")
    setup_logging(log_level=log_level)

    logger = logging.getLogger(__name__)
    logger.info("Starting GUI client")

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("Distributed Upscaling Client")
    app.setApplicationVersion("1.0.0")
    app.setQuitOnLastWindowClosed(True)

    # Create event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Create client
    try:
        client = DistributedUpscalingClient()
    except Exception as e:
        QMessageBox.critical(
            None, "Initialization Error", f"Failed to initialize client:\n{e}"
        )
        return 1

    # Create main window
    window = ClientMainWindow(client)
    window.show()

    # Timer to process async events
    timer = QTimer()
    timer.timeout.connect(lambda: loop.run_until_complete(asyncio.sleep(0.01)))
    timer.start(10)

    # Run application
    try:
        result = app.exec_()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        result = 0
    finally:
        # Cleanup
        loop.run_until_complete(client.cleanup())
        loop.close()

    return result


if __name__ == "__main__":
    sys.exit(main())
