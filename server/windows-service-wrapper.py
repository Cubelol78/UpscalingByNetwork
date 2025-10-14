#!/usr/bin/env python3
"""
UpscalingByNetwork Windows Service Wrapper
Provides Windows service functionality for the server
"""

import sys
import os
import logging
from pathlib import Path

# Path setup
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(current_dir))

# Check if running on Windows
if sys.platform != 'win32':
    print("Error: This script only works on Windows")
    sys.exit(1)

# Import Windows-specific modules
try:
    import win32serviceutil
    import win32service
    import win32event
    import servicemanager
except ImportError:
    print("Error: pywin32 not installed")
    print("Install with: pip install pywin32")
    sys.exit(1)

import asyncio


class UpscalingNetworkService(win32serviceutil.ServiceFramework):
    """Windows service for UpscalingByNetwork server"""

    _svc_name_ = "UpscalingByNetwork"
    _svc_display_name_ = "UpscalingByNetwork Distributed Server"
    _svc_description_ = "Distributed video upscaling server for network processing"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.server = None

        # Setup logging
        log_dir = current_dir / "logs"
        log_dir.mkdir(exist_ok=True)

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_dir / "service.log"),
            ]
        )
        self.logger = logging.getLogger(__name__)

    def SvcStop(self):
        """Called when the service is being stopped"""
        self.logger.info("Service stop requested")
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        """Called when the service is started"""
        self.logger.info("Service starting")
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )

        try:
            # Run the server
            asyncio.run(self.run_server())
        except Exception as e:
            self.logger.error(f"Service error: {e}", exc_info=True)
            servicemanager.LogErrorMsg(f"Service error: {e}")

    async def run_server(self):
        """Run the server in async context"""
        try:
            from core.distributed_server import DistributedServer

            # Default configuration
            host = "0.0.0.0"
            port = 8888

            # Try to load config file
            config_file = current_dir / "config" / "server_config.json"
            if config_file.exists():
                import json
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    host = config.get('server', {}).get('host', host)
                    port = config.get('server', {}).get('port', port)

            self.logger.info(f"Starting server on {host}:{port}")
            self.server = DistributedServer()
            await self.server.start(host, port)

            self.logger.info("Server started successfully")

            # Wait for stop event
            while True:
                # Check stop event (non-blocking with timeout)
                result = win32event.WaitForSingleObject(self.stop_event, 1000)
                if result == win32event.WAIT_OBJECT_0:
                    break

                await asyncio.sleep(1)

            # Cleanup
            self.logger.info("Stopping server")
            if self.server:
                await self.server.stop()

            self.logger.info("Server stopped")

        except Exception as e:
            self.logger.error(f"Server error: {e}", exc_info=True)
            raise


def main():
    """Main entry point for service control"""
    if len(sys.argv) == 1:
        # No arguments - try to start service
        try:
            servicemanager.Initialize()
            servicemanager.PrepareToHostSingle(UpscalingNetworkService)
            servicemanager.StartServiceCtrlDispatcher()
        except Exception as e:
            print(f"Error starting service: {e}")
            print("\nUsage:")
            print("  Install:   python windows-service-wrapper.py install")
            print("  Remove:    python windows-service-wrapper.py remove")
            print("  Start:     python windows-service-wrapper.py start")
            print("  Stop:      python windows-service-wrapper.py stop")
            print("  Restart:   python windows-service-wrapper.py restart")
            sys.exit(1)
    else:
        # Handle command-line arguments
        win32serviceutil.HandleCommandLine(UpscalingNetworkService)


if __name__ == '__main__':
    main()
