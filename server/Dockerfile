# UpscalingByNetwork Server - Docker Image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SERVER_HOST=0.0.0.0 \
    SERVER_PORT=8888 \
    SERVER_MODE=headless \
    LOG_LEVEL=INFO

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements first (for layer caching)
COPY server/requirements.txt /app/server/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/server/requirements.txt

# Copy server files
COPY . /app/server/

# Create necessary directories
RUN mkdir -p /app/server/logs \
             /app/server/output \
             /app/server/server_work \
             /app/server/config && \
    chmod +x /app/server/docker-entrypoint.sh

# Create volumes
VOLUME ["/app/server/logs", "/app/server/output", "/app/server/server_work", "/config"]

# Expose server port
EXPOSE 8888

# Set working directory
WORKDIR /app/server

# Use entrypoint script
ENTRYPOINT ["/app/server/docker-entrypoint.sh"]
