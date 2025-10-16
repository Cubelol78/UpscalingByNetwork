#!/bin/bash
# Launcher script that automatically activates venv and starts GUI

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if venv exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Launch GUI
echo "Starting Upscaling Client GUI..."
python3 -m client_gui "$@"
