"""
Rich-based terminal UI for the CLI client
"""

import asyncio
import logging
from typing import Optional, Dict, Any

try:
    from rich.console import Console
    from rich.table import Table
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich.layout import Layout
    from rich import box

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


class CLIInterface:
    """Terminal UI with Rich"""

    def __init__(self, use_colors: bool = True):
        if not RICH_AVAILABLE:
            raise RuntimeError("Rich library not available")

        self.console = Console(color_system="auto" if use_colors else None)
        self.logger = logging.getLogger(__name__)

    def print_banner(self):
        """Print application banner"""
        banner = """
╔══════════════════════════════════════════════════════════╗
║       Distributed Upscaling Client - Linux Edition       ║
║              Cross-Platform Image Upscaling              ║
╚══════════════════════════════════════════════════════════╝
        """
        self.console.print(banner, style="bold cyan")

    def print_status(self, client) -> None:
        """Print client status"""
        status_table = Table(title="Client Status", box=box.ROUNDED)
        status_table.add_column("Property", style="cyan")
        status_table.add_column("Value", style="green")

        status = client.get_status()

        status_table.add_row("Client ID", status["client_id"][:16] + "...")
        status_table.add_row("Connection", status["connection_state"])
        status_table.add_row("Processing", "Yes" if status["is_processing"] else "No")
        status_table.add_row(
            "Performance Score", f"{status['performance_score']:.1f}/100"
        )
        status_table.add_row(
            "CPU Usage", f"{status['system_load']['cpu_percent']:.1f}%"
        )
        status_table.add_row(
            "Memory Usage", f"{status['system_load']['memory_percent']:.1f}%"
        )

        self.console.print(status_table)

    def print_system_info(self, system_info: Dict[str, Any]):
        """Print system information"""
        table = Table(title="System Information", box=box.ROUNDED)
        table.add_column("Component", style="cyan")
        table.add_column("Details", style="green")

        # Basic info
        basic = system_info.get("basic", {})
        table.add_row("Platform", basic.get("platform", "Unknown"))
        table.add_row("Hostname", basic.get("hostname", "Unknown"))

        # Hardware
        hw = system_info.get("hardware", {})
        cpu = hw.get("cpu", {})
        memory = hw.get("memory", {})
        gpus = hw.get("gpu", [])

        table.add_row("CPU Cores", str(cpu.get("logical_cores", "?")))
        table.add_row("RAM", f"{memory.get('total_ram_gb', 0):.1f} GB")

        if gpus:
            gpu_names = ", ".join([g.get("name", "Unknown") for g in gpus])
            table.add_row("GPU(s)", gpu_names)
        else:
            table.add_row("GPU(s)", "None detected")

        self.console.print(table)

    def print_error(self, message: str):
        """Print error message"""
        self.console.print(f"[bold red]Error:[/bold red] {message}")

    def print_success(self, message: str):
        """Print success message"""
        self.console.print(f"[bold green]Success:[/bold green] {message}")

    def print_info(self, message: str):
        """Print info message"""
        self.console.print(f"[cyan]Info:[/cyan] {message}")

    def print_warning(self, message: str):
        """Print warning message"""
        self.console.print(f"[yellow]Warning:[/yellow] {message}")

    def create_progress(self, description: str = "Processing"):
        """Create progress bar"""
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=self.console,
        )

    def print_processor_stats(self, stats: Dict[str, Any]):
        """Print processor statistics"""
        perf_stats = stats.get("performance_stats", {})

        table = Table(title="Processing Statistics", box=box.ROUNDED)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row(
            "Batches Processed", str(perf_stats.get("batches_processed", 0))
        )
        table.add_row(
            "Total Frames", str(perf_stats.get("total_frames_processed", 0))
        )
        table.add_row(
            "Avg Time/Frame",
            f"{perf_stats.get('average_time_per_frame', 0):.2f}s",
        )
        table.add_row("Errors", str(perf_stats.get("errors_count", 0)))
        table.add_row(
            "Data Received", f"{perf_stats.get('data_received_mb', 0):.1f} MB"
        )
        table.add_row(
            "Data Sent", f"{perf_stats.get('data_sent_mb', 0):.1f} MB"
        )

        self.console.print(table)

    def confirm(self, message: str) -> bool:
        """Ask for confirmation"""
        response = self.console.input(f"{message} [y/N]: ")
        return response.lower() in ["y", "yes"]
