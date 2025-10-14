#!/bin/bash
# Docker entrypoint script for UpscalingByNetwork server
# Supports various run modes and configurations

set -e

# Default values
HOST="${SERVER_HOST:-0.0.0.0}"
PORT="${SERVER_PORT:-8888}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
MODE="${SERVER_MODE:-headless}"

echo "=== UpscalingByNetwork Server (Docker) ==="
echo "Host: $HOST"
echo "Port: $PORT"
echo "Log Level: $LOG_LEVEL"
echo "Mode: $MODE"
echo ""

# Change to server directory
cd /app/server

# Check if config file exists
if [ -f "/config/server_config.json" ]; then
    echo "Using configuration file: /config/server_config.json"
    cp /config/server_config.json ./config/server_config.json
fi

# Create necessary directories
mkdir -p logs output server_work config

# Determine run mode
case "$MODE" in
    "headless")
        echo "Starting in headless mode..."
        exec python3 main.py \
            --no-gui \
            --non-interactive \
            --host "$HOST" \
            --port "$PORT" \
            --log-level "$LOG_LEVEL"
        ;;

    "cli")
        echo "Starting in CLI mode..."
        exec python3 main.py \
            --no-gui \
            --host "$HOST" \
            --port "$PORT" \
            --log-level "$LOG_LEVEL"
        ;;

    "daemon")
        echo "Starting in daemon mode..."
        exec python3 main.py \
            --daemon \
            --host "$HOST" \
            --port "$PORT" \
            --log-level "$LOG_LEVEL"
        ;;

    *)
        echo "Unknown mode: $MODE"
        echo "Valid modes: headless, cli, daemon"
        exit 1
        ;;
esac
