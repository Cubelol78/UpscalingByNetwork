#!/bin/bash
# Launcher script that automatically activates venv and starts CLI

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if venv exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Launch CLI
python3 client_main.py "$@"
