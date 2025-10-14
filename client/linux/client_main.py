#!/usr/bin/env python3
"""
Main entry point for the Linux client (CLI mode)
Cross-platform distributed upscaling client
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Run CLI
if __name__ == "__main__":
    try:
        from cli.commands import cli

        cli(obj={})

    except ImportError as e:
        print(f"Error: Missing dependencies - {e}")
        print("\nInstall dependencies with:")
        print("  pip install click rich websockets cryptography psutil pynvml")
        sys.exit(1)

    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
