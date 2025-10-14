#!/usr/bin/env python3
"""
UpscalingByNetwork Server - Daemon/Service Support
Supports running as:
- Linux daemon (systemd)
- Windows service
- Unix daemon (traditional fork)
"""

import sys
import os
import asyncio
import logging
import signal
from pathlib import Path
from typing import Optional

# Path setup
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(current_dir))


class DaemonServer:
    """Daemon server wrapper for the distributed upscaling server"""

    def __init__(self, host: str = "0.0.0.0", port: int = 8888,
                 pid_file: Optional[Path] = None):
        """
        Initialize daemon server

        Args:
            host: Server bind address
            port: Server port
            pid_file: Path to PID file
        """
        self.host = host
        self.port = port
        self.pid_file = pid_file or Path("/var/run/upscaling-server.pid")
        self.logger = logging.getLogger(__name__)
        self.server = None
        self.running = False

        # Setup signal handlers
        self.setup_signal_handlers()

    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}")
            self.running = False  # Set flag instead of creating task
            # The task will be created in the event loop if it's running
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.stop())
            except RuntimeError:
                # No event loop running yet, just set the flag
                pass

        # Handle common signals
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        # Unix-specific signals
        if hasattr(signal, 'SIGHUP'):
            signal.signal(signal.SIGHUP, signal_handler)

    async def run(self):
        """Run the daemon server"""
        try:
            # Write PID file
            self.write_pid_file()

            # Import and start server
            from core.distributed_server import DistributedServer

            self.logger.info(f"Starting daemon server on {self.host}:{self.port}")

            # Create and start server
            self.server = DistributedServer()
            await self.server.start(self.host, self.port)

            self.running = True
            self.logger.info("Daemon server started successfully")

            # Keep running
            while self.running:
                await asyncio.sleep(10)

                # Log periodic status
                stats = self.server.get_server_stats()
                self.logger.info(
                    f"Status: {stats['clients_connected']} clients, "
                    f"{stats['active_jobs']} jobs, "
                    f"{stats['pending_batches']} pending batches"
                )

        except Exception as e:
            self.logger.error(f"Daemon error: {e}", exc_info=True)
        finally:
            await self.cleanup()

    async def stop(self):
        """Stop the daemon server"""
        self.logger.info("Stopping daemon server...")
        self.running = False

        if self.server:
            try:
                await self.server.stop()
            except Exception as e:
                self.logger.error(f"Error stopping server: {e}")

    async def cleanup(self):
        """Cleanup daemon resources"""
        # Remove PID file
        if self.pid_file.exists():
            try:
                self.pid_file.unlink()
                self.logger.info(f"Removed PID file: {self.pid_file}")
            except Exception as e:
                self.logger.error(f"Error removing PID file: {e}")

    def write_pid_file(self):
        """Write process ID to PID file"""
        try:
            # Ensure parent directory exists
            self.pid_file.parent.mkdir(parents=True, exist_ok=True)

            # Write PID
            with open(self.pid_file, 'w') as f:
                f.write(str(os.getpid()))

            self.logger.info(f"PID file written: {self.pid_file}")

        except Exception as e:
            self.logger.error(f"Error writing PID file: {e}")

    @classmethod
    def is_running(cls, pid_file: Path) -> bool:
        """Check if daemon is already running"""
        if not pid_file.exists():
            return False

        try:
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())

            # Check if process exists
            try:
                os.kill(pid, 0)  # Signal 0 doesn't kill, just checks
                return True
            except OSError:
                return False

        except Exception:
            return False


class WindowsService:
    """Windows service wrapper"""

    def __init__(self, host: str = "0.0.0.0", port: int = 8888):
        """
        Initialize Windows service

        Args:
            host: Server bind address
            port: Server port
        """
        self.host = host
        self.port = port
        self.logger = logging.getLogger(__name__)

        # Check if running on Windows
        if sys.platform != 'win32':
            raise RuntimeError("WindowsService only works on Windows")

        # Import Windows-specific modules
        try:
            import win32serviceutil
            import win32service
            import win32event
            import servicemanager

            self.win32serviceutil = win32serviceutil
            self.win32service = win32service
            self.win32event = win32event
            self.servicemanager = servicemanager

        except ImportError:
            raise ImportError(
                "Windows service support requires pywin32. "
                "Install with: pip install pywin32"
            )

    def create_service_class(self):
        """Create Windows service class"""
        # This needs to be done dynamically because it requires win32 modules
        import win32serviceutil
        import win32service
        import win32event
        import servicemanager

        host = self.host
        port = self.port

        class UpscalingNetworkService(win32serviceutil.ServiceFramework):
            """Windows service for UpscalingByNetwork server"""

            _svc_name_ = "UpscalingByNetwork"
            _svc_display_name_ = "UpscalingByNetwork Distributed Server"
            _svc_description_ = "Distributed video upscaling server"

            def __init__(self, args):
                win32serviceutil.ServiceFramework.__init__(self, args)
                self.stop_event = win32event.CreateEvent(None, 0, 0, None)
                self.logger = logging.getLogger(__name__)
                self.server = None

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

                    self.logger.info(f"Starting server on {host}:{port}")
                    self.server = DistributedServer()
                    await self.server.start(host, port)

                    self.logger.info("Server started successfully")

                    # Wait for stop event
                    while True:
                        # Check stop event
                        if win32event.WaitForSingleObject(
                            self.stop_event, 1000
                        ) == win32event.WAIT_OBJECT_0:
                            break

                        await asyncio.sleep(1)

                    # Cleanup
                    self.logger.info("Stopping server")
                    if self.server:
                        await self.server.stop()

                except Exception as e:
                    self.logger.error(f"Server error: {e}", exc_info=True)

        return UpscalingNetworkService

    def install(self):
        """Install Windows service"""
        try:
            service_class = self.create_service_class()
            self.win32serviceutil.HandleCommandLine(service_class, argv=['', 'install'])
            print("Service installed successfully")
            print("Start with: net start UpscalingByNetwork")
        except Exception as e:
            print(f"Error installing service: {e}")

    def uninstall(self):
        """Uninstall Windows service"""
        try:
            service_class = self.create_service_class()
            self.win32serviceutil.HandleCommandLine(service_class, argv=['', 'remove'])
            print("Service uninstalled successfully")
        except Exception as e:
            print(f"Error uninstalling service: {e}")

    def start(self):
        """Start Windows service"""
        try:
            service_class = self.create_service_class()
            self.win32serviceutil.HandleCommandLine(service_class, argv=['', 'start'])
            print("Service started successfully")
        except Exception as e:
            print(f"Error starting service: {e}")

    def stop(self):
        """Stop Windows service"""
        try:
            service_class = self.create_service_class()
            self.win32serviceutil.HandleCommandLine(service_class, argv=['', 'stop'])
            print("Service stopped successfully")
        except Exception as e:
            print(f"Error stopping service: {e}")


def daemonize():
    """
    Traditional Unix daemonization using double fork
    This is for systems without systemd
    """
    try:
        # First fork
        pid = os.fork()
        if pid > 0:
            # Exit parent
            sys.exit(0)
    except OSError as e:
        sys.stderr.write(f"Fork #1 failed: {e}\n")
        sys.exit(1)

    # Decouple from parent environment
    os.chdir('/')
    os.setsid()
    os.umask(0)

    # Second fork
    try:
        pid = os.fork()
        if pid > 0:
            # Exit second parent
            sys.exit(0)
    except OSError as e:
        sys.stderr.write(f"Fork #2 failed: {e}\n")
        sys.exit(1)

    # Redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()

    with open('/dev/null', 'r') as f:
        os.dup2(f.fileno(), sys.stdin.fileno())

    with open('/dev/null', 'a+') as f:
        os.dup2(f.fileno(), sys.stdout.fileno())

    with open('/dev/null', 'a+') as f:
        os.dup2(f.fileno(), sys.stderr.fileno())


def cli_daemon_control(action: str, host: str = "0.0.0.0", port: int = 8888,
                       pid_file: Optional[Path] = None):
    """
    CLI interface for daemon control

    Args:
        action: Action to perform (start, stop, restart, status)
        host: Server bind address
        port: Server port
        pid_file: Path to PID file
    """
    if pid_file is None:
        pid_file = Path("/var/run/upscaling-server.pid")

    if action == 'start':
        # Check if already running
        if DaemonServer.is_running(pid_file):
            print("Server is already running")
            return 1

        print("Starting server daemon...")

        # Daemonize on Unix systems
        if sys.platform != 'win32':
            daemonize()

        # Start daemon
        daemon = DaemonServer(host, port, pid_file)
        asyncio.run(daemon.run())

    elif action == 'stop':
        # Check if running
        if not DaemonServer.is_running(pid_file):
            print("Server is not running")
            return 1

        # Read PID
        with open(pid_file, 'r') as f:
            pid = int(f.read().strip())

        print(f"Stopping server daemon (PID {pid})...")

        # Send SIGTERM
        try:
            os.kill(pid, signal.SIGTERM)
            print("Server stopped")
        except OSError as e:
            print(f"Error stopping server: {e}")
            return 1

    elif action == 'restart':
        # Stop then start
        cli_daemon_control('stop', host, port, pid_file)
        import time
        time.sleep(2)
        cli_daemon_control('start', host, port, pid_file)

    elif action == 'status':
        # Check status
        if DaemonServer.is_running(pid_file):
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            print(f"Server is running (PID {pid})")
        else:
            print("Server is not running")

    else:
        print(f"Unknown action: {action}")
        print("Valid actions: start, stop, restart, status")
        return 1

    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="UpscalingByNetwork Daemon Control")
    parser.add_argument('action', choices=['start', 'stop', 'restart', 'status'],
                       help='Action to perform')
    parser.add_argument('--host', default='0.0.0.0', help='Server bind address')
    parser.add_argument('--port', type=int, default=8888, help='Server port')
    parser.add_argument('--pid-file', type=Path, help='PID file path')

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Run daemon control
    sys.exit(cli_daemon_control(args.action, args.host, args.port, args.pid_file))
