#!/usr/bin/env python3
"""
UpscalingByNetwork Server - CLI Interface
Full-featured command-line interface with Rich library for status display
Supports headless mode, interactive mode, and daemon mode
"""

import asyncio
import signal
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import logging
from utils.system import detect_display_available
from utils.file_utils import format_duration

try:
    from rich.console import Console
    from rich.table import Table
    from rich.live import Live
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
    from rich.text import Text
    from rich.style import Style
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Warning: Rich library not available. Install with: pip install rich")

# Add project root to path
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(current_dir))


class ServerCLI:
    """Command-line interface for the distributed upscaling server"""

    def __init__(self, server, interactive: bool = True, use_rich: bool = True):
        """
        Initialize CLI interface

        Args:
            server: DistributedServer instance
            interactive: Enable interactive mode with live updates
            use_rich: Use Rich library for enhanced display (if available)
        """
        self.server = server
        self.interactive = interactive
        self.use_rich = use_rich and RICH_AVAILABLE
        self.running = False
        self.shutdown_requested = False

        # Console setup
        if self.use_rich:
            self.console = Console()

        # Statistics
        self.start_time = datetime.now()
        self.last_update = datetime.now()
        self.update_interval = 2.0  # seconds

        # Logger
        self.logger = logging.getLogger(__name__)

        # Signal handlers
        self.setup_signal_handlers()

    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}")
            self.shutdown_requested = True
            if self.running:
                asyncio.create_task(self.shutdown())

        # Handle SIGINT (Ctrl+C) and SIGTERM
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Windows-specific signals
        if sys.platform == 'win32':
            try:
                signal.signal(signal.SIGBREAK, signal_handler)
            except AttributeError:
                pass  # SIGBREAK not available

    async def run(self):
        """Run the CLI interface"""
        self.running = True

        try:
            if self.interactive and self.use_rich:
                await self.run_interactive_rich()
            elif self.interactive:
                await self.run_interactive_basic()
            else:
                await self.run_headless()
        except Exception as e:
            self.logger.error(f"CLI error: {e}", exc_info=True)
        finally:
            self.running = False

    async def run_interactive_rich(self):
        """Run interactive mode with Rich library"""
        self.console.print(Panel.fit(
            "[bold cyan]UpscalingByNetwork Distributed Server[/bold cyan]\n"
            "[dim]Press Ctrl+C to stop[/dim]",
            border_style="cyan"
        ))

        with Live(self.generate_rich_display(), refresh_per_second=2, console=self.console) as live:
            while self.running and not self.shutdown_requested:
                await asyncio.sleep(self.update_interval)
                live.update(self.generate_rich_display())

    async def run_interactive_basic(self):
        """Run interactive mode with basic text output"""
        print("\n" + "=" * 70)
        print("UpscalingByNetwork Distributed Server")
        print("=" * 70)
        print("Press Ctrl+C to stop\n")

        while self.running and not self.shutdown_requested:
            await asyncio.sleep(self.update_interval)
            self.print_basic_status()

    async def run_headless(self):
        """Run headless mode with minimal output"""
        self.logger.info("Server running in headless mode")

        # Print initial status
        print(f"Server started on {self.server.host}:{self.server.port}")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Keep running until shutdown
        while self.running and not self.shutdown_requested:
            await asyncio.sleep(10)

            # Log periodic status
            stats = self.server.get_server_stats()
            self.logger.info(
                f"Status: {stats['clients_connected']} clients, "
                f"{stats['active_jobs']} jobs, "
                f"{stats['pending_batches']} pending batches"
            )

    def generate_rich_display(self) -> Layout:
        """Generate Rich layout for display"""
        layout = Layout()

        # Split layout into sections
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )

        # Split main section
        layout["main"].split_row(
            Layout(name="left"),
            Layout(name="right")
        )

        # Header
        layout["header"].update(self.create_header_panel())

        # Server stats
        layout["left"].update(self.create_server_stats_panel())

        # Clients table
        layout["right"].update(self.create_clients_panel())

        # Footer with commands
        layout["footer"].update(self.create_footer_panel())

        return layout

    def create_header_panel(self) -> Panel:
        """Create header panel"""
        stats = self.server.get_server_stats()
        uptime = format_duration(int(stats['uptime']))

        status_text = Text()
        status_text.append("UpscalingByNetwork Server ", style="bold cyan")
        status_text.append(f"[{self.server.host}:{self.server.port}] ", style="dim")

        if stats['running']:
            status_text.append("RUNNING", style="bold green")
        else:
            status_text.append("STOPPED", style="bold red")

        status_text.append(f" | Uptime: {uptime}", style="dim")

        return Panel(status_text, border_style="cyan")

    def create_server_stats_panel(self) -> Panel:
        """Create server statistics panel"""
        stats = self.server.get_server_stats()

        table = Table.grid(padding=(0, 2))
        table.add_column(style="cyan", justify="right")
        table.add_column(style="white")

        # Server info
        table.add_row("Server Status:", "Running" if stats['running'] else "Stopped")
        table.add_row("Connected Clients:", str(stats['clients_connected']))
        table.add_row("Active Jobs:", str(stats['active_jobs']))
        table.add_row("Active Batches:", str(stats['active_batches']))
        table.add_row("Pending Batches:", str(stats['pending_batches']))
        table.add_row("Images Processed:", str(stats['total_images_processed']))
        table.add_row("", "")

        # Memory and performance (if available)
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            cpu_percent = process.cpu_percent(interval=0.1)

            table.add_row("Memory Usage:", f"{memory_mb:.1f} MB")
            table.add_row("CPU Usage:", f"{cpu_percent:.1f}%")
        except ImportError:
            pass

        return Panel(table, title="[bold cyan]Server Statistics[/bold cyan]", border_style="cyan")

    def create_clients_panel(self) -> Panel:
        """Create clients panel"""
        clients = self.server.get_client_stats()

        if not clients:
            return Panel(
                "[dim]No clients connected[/dim]",
                title="[bold cyan]Connected Clients[/bold cyan]",
                border_style="cyan"
            )

        table = Table(show_header=True, header_style="bold cyan", box=None)
        table.add_column("Hostname", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Batches", justify="right")
        table.add_column("Images", justify="right")

        for client in clients[:10]:  # Show max 10 clients
            status_style = "green" if client['status'] == "idle" else "yellow"
            status_text = client['status'].upper()

            table.add_row(
                client['hostname'][:20],
                f"[{status_style}]{status_text}[/{status_style}]",
                str(client['batches_processed']),
                str(client['total_images_processed'])
            )

        title = f"[bold cyan]Connected Clients ({len(clients)})[/bold cyan]"
        return Panel(table, title=title, border_style="cyan")

    def create_footer_panel(self) -> Panel:
        """Create footer panel with commands"""
        footer_text = Text()
        footer_text.append("Commands: ", style="dim")
        footer_text.append("Ctrl+C", style="bold cyan")
        footer_text.append(" = Shutdown ", style="dim")
        footer_text.append("| ", style="dim")
        footer_text.append(f"Updated: {datetime.now().strftime('%H:%M:%S')}", style="dim")

        return Panel(footer_text, border_style="cyan")

    def print_basic_status(self):
        """Print basic status without Rich library"""
        stats = self.server.get_server_stats()
        uptime = format_duration(int(stats['uptime']))

        # Clear screen (simple approach)
        print("\n" + "=" * 70)
        print(f"Server Status - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)
        print(f"Host: {self.server.host}:{self.server.port} | Uptime: {uptime}")
        print(f"Clients: {stats['clients_connected']} | Jobs: {stats['active_jobs']}")
        print(f"Active Batches: {stats['active_batches']} | Pending: {stats['pending_batches']}")
        print(f"Total Images Processed: {stats['total_images_processed']}")
        print("=" * 70)

        # Show clients
        clients = self.server.get_client_stats()
        if clients:
            print("\nConnected Clients:")
            print(f"{'Hostname':<20} {'Status':<12} {'Batches':<10} {'Images':<10}")
            print("-" * 70)
            for client in clients[:10]:
                print(
                    f"{client['hostname'][:20]:<20} "
                    f"{client['status']:<12} "
                    f"{client['batches_processed']:<10} "
                    f"{client['total_images_processed']:<10}"
                )
        else:
            print("\nNo clients connected")

        print("\nPress Ctrl+C to stop the server")

    async def shutdown(self):
        """Gracefully shutdown the server"""
        if not self.running:
            return

        self.running = False

        if self.use_rich:
            self.console.print("\n[yellow]Shutting down server...[/yellow]")
        else:
            print("\nShutting down server...")

        try:
            # Stop the server
            await self.server.stop()

            if self.use_rich:
                self.console.print("[green]Server stopped successfully[/green]")
            else:
                print("Server stopped successfully")
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
            if self.use_rich:
                self.console.print(f"[red]Error during shutdown: {e}[/red]")
            else:
                print(f"Error during shutdown: {e}")

    def print_startup_banner(self):
        """Print startup banner"""
        if self.use_rich:
            self.console.print(Panel.fit(
                "[bold cyan]UpscalingByNetwork Distributed Server[/bold cyan]\n"
                f"[dim]Version 1.0.0[/dim]\n\n"
                f"Server: [cyan]{self.server.host}:{self.server.port}[/cyan]\n"
                f"Mode: [cyan]{'Interactive' if self.interactive else 'Headless'}[/cyan]\n"
                f"Started: [cyan]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/cyan]",
                border_style="cyan",
                title="[bold]Server Starting[/bold]"
            ))
        else:
            print("\n" + "=" * 70)
            print("UpscalingByNetwork Distributed Server v1.0.0")
            print("=" * 70)
            print(f"Server: {self.server.host}:{self.server.port}")
            print(f"Mode: {'Interactive' if self.interactive else 'Headless'}")
            print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 70 + "\n")


class CLICommands:
    """CLI commands for server management"""

    def __init__(self, server):
        self.server = server
        self.console = Console() if RICH_AVAILABLE else None

    def print_status(self):
        """Print current server status"""
        stats = self.server.get_server_stats()

        if self.console:
            table = Table(title="Server Status", show_header=True, header_style="bold cyan")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", justify="right")

            table.add_row("Status", "Running" if stats['running'] else "Stopped")
            table.add_row("Uptime", format_duration(int(stats['uptime'])))
            table.add_row("Connected Clients", str(stats['clients_connected']))
            table.add_row("Active Jobs", str(stats['active_jobs']))
            table.add_row("Active Batches", str(stats['active_batches']))
            table.add_row("Pending Batches", str(stats['pending_batches']))
            table.add_row("Total Images", str(stats['total_images_processed']))

            self.console.print(table)
        else:
            print("\n=== Server Status ===")
            print(f"Status: {'Running' if stats['running'] else 'Stopped'}")
            print(f"Uptime: {format_duration(int(stats['uptime']))}")
            print(f"Connected Clients: {stats['clients_connected']}")
            print(f"Active Jobs: {stats['active_jobs']}")
            print(f"Active Batches: {stats['active_batches']}")
            print(f"Pending Batches: {stats['pending_batches']}")
            print(f"Total Images Processed: {stats['total_images_processed']}")

    def print_clients(self):
        """Print connected clients"""
        clients = self.server.get_client_stats()

        if not clients:
            print("No clients connected")
            return

        if self.console:
            table = Table(title=f"Connected Clients ({len(clients)})",
                         show_header=True, header_style="bold cyan")
            table.add_column("MAC Address", style="cyan")
            table.add_column("Hostname")
            table.add_column("IP Address")
            table.add_column("Status", justify="center")
            table.add_column("Batches", justify="right")
            table.add_column("Images", justify="right")

            for client in clients:
                status_style = "green" if client['status'] == "idle" else "yellow"
                table.add_row(
                    client['mac_address'][:17],
                    client['hostname'],
                    client['ip_address'],
                    f"[{status_style}]{client['status']}[/{status_style}]",
                    str(client['batches_processed']),
                    str(client['total_images_processed'])
                )

            self.console.print(table)
        else:
            print(f"\n=== Connected Clients ({len(clients)}) ===")
            for client in clients:
                print(f"\nMAC: {client['mac_address']}")
                print(f"  Hostname: {client['hostname']}")
                print(f"  IP: {client['ip_address']}")
                print(f"  Status: {client['status']}")
                print(f"  Batches: {client['batches_processed']}")
                print(f"  Images: {client['total_images_processed']}")

    def print_jobs(self):
        """Print active jobs"""
        jobs = self.server.get_job_stats()

        if not jobs:
            print("No active jobs")
            return

        if self.console:
            table = Table(title=f"Active Jobs ({len(jobs)})",
                         show_header=True, header_style="bold cyan")
            table.add_column("Job ID", style="cyan")
            table.add_column("Status", justify="center")
            table.add_column("Progress", justify="right")
            table.add_column("Frames", justify="right")

            for job in jobs:
                progress = (job['completed_batches'] / job['total_batches'] * 100) if job['total_batches'] > 0 else 0
                table.add_row(
                    job['job_id'][:20],
                    job['status'],
                    f"{progress:.1f}%",
                    str(job['total_frames'])
                )

            self.console.print(table)
        else:
            print(f"\n=== Active Jobs ({len(jobs)}) ===")
            for job in jobs:
                progress = (job['completed_batches'] / job['total_batches'] * 100) if job['total_batches'] > 0 else 0
                print(f"\nJob: {job['job_id']}")
                print(f"  Status: {job['status']}")
                print(f"  Progress: {progress:.1f}%")
                print(f"  Frames: {job['total_frames']}")



if __name__ == "__main__":
    print("This module should be imported, not run directly")
    print("Use: python main.py --help")
