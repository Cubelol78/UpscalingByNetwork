"""
Click-based CLI commands for the Linux client
"""

import asyncio
import sys
import signal
from pathlib import Path

try:
    import click

    CLICK_AVAILABLE = True
except ImportError:
    CLICK_AVAILABLE = False

from core.client import DistributedUpscalingClient
from utils.config import config
from utils.logger import setup_logging
from cli.ui import CLIInterface


if not CLICK_AVAILABLE:
    print("Click library not available. Install with: pip install click")
    sys.exit(1)


@click.group()
@click.option("--log-level", default="INFO", help="Logging level")
@click.option("--config", type=click.Path(), help="Config file path")
@click.pass_context
def cli(ctx, log_level, config_path):
    """Distributed Upscaling Client CLI"""
    # Setup logging
    setup_logging(log_level=log_level)

    # Load config
    if config_path:
        config.import_config(Path(config_path))

    ctx.ensure_object(dict)
    ctx.obj["config"] = config


@cli.command()
@click.option("--host", default="localhost", help="Server host")
@click.option("--port", default=8765, type=int, help="Server port")
@click.option("--no-colors", is_flag=True, help="Disable colored output")
@click.pass_context
def run(ctx, host, port, no_colors):
    """Run client in interactive mode"""
    use_colors = not no_colors

    try:
        ui = CLIInterface(use_colors=use_colors)
    except RuntimeError:
        click.echo("Rich library not available. Install with: pip install rich")
        return

    ui.print_banner()

    # Create client
    try:
        client = DistributedUpscalingClient()
        ui.print_success("Client initialized")
    except Exception as e:
        ui.print_error(f"Failed to initialize client: {e}")
        return

    # Signal handling
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def signal_handler(sig, frame):
        ui.print_info("Shutting down...")
        loop.create_task(client.disconnect())
        loop.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Connect
    async def connect_and_run():
        ui.print_info(f"Connecting to {host}:{port}")

        if await client.connect(host, port):
            ui.print_success("Connected to server")
            ui.print_status(client)

            # Keep running
            try:
                while client.is_connected:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                pass
        else:
            ui.print_error("Failed to connect to server")

        await client.cleanup()

    try:
        loop.run_until_complete(connect_and_run())
    except KeyboardInterrupt:
        ui.print_info("Interrupted by user")
    finally:
        loop.close()


@cli.command()
@click.pass_context
def status(ctx):
    """Show client status"""
    try:
        ui = CLIInterface()
        ui.print_info("Status check not implemented in standalone mode")
    except RuntimeError:
        click.echo("Rich library not available")


@cli.command()
@click.pass_context
def info(ctx):
    """Show system information"""
    try:
        ui = CLIInterface()
        from utils.system_info import SystemInfo

        system_info = SystemInfo()
        sys_info = system_info.get_system_info()

        ui.print_system_info(sys_info)

    except RuntimeError:
        click.echo("Rich library not available")
    except Exception as e:
        click.echo(f"Error: {e}")


@cli.command()
@click.option("--host", required=True, help="Server host")
@click.option("--port", default=8765, type=int, help="Server port")
@click.pass_context
def test_connection(ctx, host, port):
    """Test connection to server"""
    click.echo(f"Testing connection to {host}:{port}...")

    try:
        client = DistributedUpscalingClient()

        async def test():
            result = await client.connect(host, port)
            if result:
                click.echo("Connection successful!")
                await client.disconnect()
            else:
                click.echo("Connection failed!")

        asyncio.run(test())

    except Exception as e:
        click.echo(f"Error: {e}")


@cli.command()
@click.pass_context
def config_show(ctx):
    """Show current configuration"""
    import json

    config_dict = config.config
    click.echo(json.dumps(config_dict, indent=2))


@cli.command()
@click.option("--key", required=True, help="Config key (dot notation)")
@click.option("--value", required=True, help="Config value")
@click.pass_context
def config_set(ctx, key, value):
    """Set configuration value"""
    try:
        # Try to parse as JSON for complex types
        try:
            import json

            parsed_value = json.loads(value)
        except:
            parsed_value = value

        config.set(key, parsed_value)
        click.echo(f"Set {key} = {parsed_value}")

    except Exception as e:
        click.echo(f"Error: {e}")


@cli.command()
@click.pass_context
def config_reset(ctx):
    """Reset configuration to defaults"""
    if click.confirm("Reset configuration to defaults?"):
        config.reset_to_defaults()
        click.echo("Configuration reset")


@cli.command()
@click.pass_context
def test_realesrgan(ctx):
    """Test Real-ESRGAN installation"""
    try:
        from utils.realesrgan_handler import RealESRGANHandler

        handler = RealESRGANHandler()
        test_result = handler.test_installation()

        click.echo("\nReal-ESRGAN Test Results:")
        click.echo(f"  Executable Found: {test_result['executable_found']}")
        click.echo(f"  Path: {test_result['executable_path']}")
        click.echo(f"  Functional: {test_result['functional']}")
        click.echo(f"  Models Found: {len(test_result['models_found'])}")

        if test_result['models_found']:
            for model in test_result['models_found']:
                click.echo(f"    - {model}")

        if test_result['error']:
            click.echo(f"  Error: {test_result['error']}")

    except Exception as e:
        click.echo(f"Error: {e}")


@cli.command()
@click.pass_context
def version(ctx):
    """Show version information"""
    click.echo("Distributed Upscaling Client")
    click.echo("Version: 1.0.0")
    click.echo("Platform: Linux")
    click.echo("Python: " + sys.version.split()[0])


if __name__ == "__main__":
    cli(obj={})
