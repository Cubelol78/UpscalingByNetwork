#!/usr/bin/env python3
"""
CLI Interface for UpscalingByNetwork Server
Provides a rich terminal interface for headless operation
"""

import asyncio
import signal
import sys
import os
from pathlib import Path
from typing import Optional
import logging

# Rich imports for beautiful CLI
try:
    from rich.console import Console
    from rich.table import Table
    from rich.live import Live
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
    from rich.logging import RichHandler
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Warning: 'rich' library not installed. Install with: pip install rich")

# Add server directory to path
sys.path.insert(0, str(Path(__file__).parent))

from core.server import UpscalingServer
from config.settings import config
from utils.logger import get_logger

class ServerCLI:
    """Command-line interface for the server"""

    def __init__(self, server: UpscalingServer):
        self.server = server
        self.console = Console() if RICH_AVAILABLE else None
        self.logger = get_logger(__name__)
        self.running = True
        self.stats_task = None

    async def start(self, show_stats: bool = True):
        """Start the CLI interface"""
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        if RICH_AVAILABLE and show_stats:
            await self._run_with_rich_ui()
        else:
            await self._run_simple()

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
        asyncio.create_task(self.server.stop())

    async def _run_simple(self):
        """Run with simple text output (no Rich)"""
        print("=" * 60)
        print("UpscalingByNetwork Server - CLI Mode")
        print("=" * 60)
        print(f"Host: {config.HOST}")
        print(f"Port: {config.PORT}")
        print("=" * 60)
        print("\nServer starting...\n")

        # Start server in background
        server_task = asyncio.create_task(self.server.start())

        # Simple stats display
        while self.running and self.server.running:
            await asyncio.sleep(5)
            self._print_simple_stats()

        await server_task

    def _print_simple_stats(self):
        """Print simple statistics"""
        uptime = self.server._get_uptime() if hasattr(self.server, '_get_uptime') else 0
        print(f"\n[{self._get_timestamp()}] Server Status:")
        print(f"  Clients: {len(self.server.clients)}")
        print(f"  Jobs: {len(self.server.jobs)}")
        print(f"  Batches: {len(self.server.batches)}")
        print(f"  Uptime: {uptime}s")

    def _get_timestamp(self):
        """Get current timestamp"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async def _run_with_rich_ui(self):
        """Run with Rich terminal UI"""
        layout = self._create_layout()

        # Start server in background
        server_task = asyncio.create_task(self.server.start())

        # Live display with auto-refresh
        with Live(layout, console=self.console, refresh_per_second=1, screen=False) as live:
            while self.running and self.server.running:
                layout = self._create_layout()
                live.update(layout)
                await asyncio.sleep(1)

        await server_task

    def _create_layout(self) -> Layout:
        """Create the Rich layout"""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )

        layout["main"].split_row(
            Layout(name="stats", ratio=1),
            Layout(name="clients", ratio=2)
        )

        # Header
        layout["header"].update(
            Panel(
                f"[bold cyan]UpscalingByNetwork Server[/bold cyan] - {config.HOST}:{config.PORT}",
                style="bold white on blue"
            )
        )

        # Stats panel
        layout["stats"].update(self._create_stats_panel())

        # Clients panel
        layout["clients"].update(self._create_clients_panel())

        # Footer
        uptime = self._get_uptime_str()
        layout["footer"].update(
            Panel(
                f"Uptime: {uptime} | Press Ctrl+C to stop",
                style="dim"
            )
        )

        return layout

    def _create_stats_panel(self) -> Panel:
        """Create statistics panel"""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Clients", str(len(self.server.clients)))
        table.add_row("Active Jobs", str(len([j for j in self.server.jobs.values() if j.status.value == 'processing'])))
        table.add_row("Total Jobs", str(len(self.server.jobs)))
        table.add_row("Batches", str(len(self.server.batches)))
        table.add_row("Completed", str(sum(1 for b in self.server.batches.values() if b.status.value == 'completed')))

        return Panel(table, title="[bold]Server Statistics[/bold]", border_style="blue")

    def _create_clients_panel(self) -> Panel:
        """Create clients panel"""
        if not self.server.clients:
            return Panel(
                "[dim]No clients connected[/dim]",
                title="[bold]Connected Clients[/bold]",
                border_style="blue"
            )

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("MAC", style="cyan", width=17)
        table.add_column("IP", style="green", width=15)
        table.add_column("Status", style="yellow", width=12)
        table.add_column("Jobs", justify="right", width=6)
        table.add_column("Performance", justify="right", width=11)

        for client in self.server.clients.values():
            status_color = {
                "active": "green",
                "idle": "yellow",
                "processing": "blue",
                "disconnected": "red"
            }.get(client.status.value, "white")

            table.add_row(
                client.mac_address,
                client.ip_address,
                f"[{status_color}]{client.status.value}[/{status_color}]",
                str(client.total_batches_processed),
                f"{client.performance_score}/100"
            )

        return Panel(table, title="[bold]Connected Clients[/bold]", border_style="blue")

    def _get_uptime_str(self) -> str:
        """Get formatted uptime string"""
        import time
        uptime_seconds = int(time.time() - self.server._start_time)
        hours = uptime_seconds // 3600
        minutes = (uptime_seconds % 3600) // 60
        seconds = uptime_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def main():
    """Main entry point for CLI mode"""
    import argparse

    parser = argparse.ArgumentParser(
        description="UpscalingByNetwork Server - Distributed video upscaling",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument(
        '--host',
        default=config.HOST,
        help='Server bind address'
    )

    parser.add_argument(
        '--port',
        type=int,
        default=config.PORT,
        help='Server port'
    )

    parser.add_argument(
        '--no-stats',
        action='store_true',
        help='Disable real-time statistics display'
    )

    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level'
    )

    parser.add_argument(
        '--config',
        type=Path,
        help='Configuration file path'
    )

    parser.add_argument(
        '--daemon',
        action='store_true',
        help='Run as daemon (no interactive output)'
    )

    args = parser.parse_args()

    # Update config from arguments
    config.HOST = args.host
    config.PORT = args.port

    # Setup logging
    log_level = getattr(logging, args.log_level)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            RichHandler(rich_tracebacks=True) if RICH_AVAILABLE else logging.StreamHandler()
        ]
    )

    # Create server
    server = UpscalingServer()

    # Run in daemon mode or CLI mode
    if args.daemon:
        # Daemon mode - just run the server
        asyncio.run(server.start())
    else:
        # CLI mode with rich UI
        cli = ServerCLI(server)
        asyncio.run(cli.start(show_stats=not args.no_stats))


if __name__ == "__main__":
    main()
