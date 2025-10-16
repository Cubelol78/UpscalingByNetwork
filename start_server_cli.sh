#!/bin/bash
# UpscalingByNetwork Server Launcher (CLI Mode)
# This script starts the server in CLI mode (no GUI required)

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found!"
    echo "Creating virtual environment..."
    python3 -m venv venv

    echo "Installing dependencies..."
    ./venv/bin/pip install -r server/requirements.txt

    echo "✅ Setup complete!"
fi

# Activate virtual environment and start server in CLI mode
echo "🚀 Starting UpscalingByNetwork Server (CLI Mode)..."
echo ""

# Start the server without GUI
./venv/bin/python server/main.py --no-gui "$@"
