#!/bin/bash
# UpscalingByNetwork Server Launcher
# This script activates the virtual environment and starts the server

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

# Activate virtual environment and start server
echo "🚀 Starting UpscalingByNetwork Server..."
echo ""

# Start the server with GUI (auto-detect display)
./venv/bin/python server/main.py "$@"
