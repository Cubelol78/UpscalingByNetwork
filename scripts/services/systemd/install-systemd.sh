#!/bin/bash
#
# UpscalingByNetwork - Systemd Service Installation Script
# Installs and configures systemd services for server and client
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SYSTEMD_DIR="/etc/systemd/system"
SERVICE_USER="upscaling"
SERVICE_GROUP="upscaling"
INSTALL_DIR="/opt/UpscalingByNetwork"
CONFIG_DIR="/etc/upscaling"

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Check if systemd is available
check_systemd() {
    log_info "Checking for systemd..."

    if ! command -v systemctl &> /dev/null; then
        log_error "systemd not found. This script requires systemd."
        exit 1
    fi

    if ! systemctl --version &> /dev/null; then
        log_error "systemd is not running on this system."
        exit 1
    fi

    log_success "systemd detected: $(systemctl --version | head -n1)"
}

# Check Python and dependencies
check_python() {
    log_info "Checking Python installation..."

    if ! command -v python3 &> /dev/null; then
        log_error "python3 not found. Please install Python 3.8 or later."
        exit 1
    fi

    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    log_success "Python detected: $PYTHON_VERSION"

    # Check if requirements.txt exists
    if [[ -f "$PROJECT_ROOT/requirements.txt" ]]; then
        log_info "Requirements file found at $PROJECT_ROOT/requirements.txt"

        read -p "Do you want to install Python dependencies now? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log_info "Installing Python dependencies..."
            python3 -m pip install -r "$PROJECT_ROOT/requirements.txt" || {
                log_warning "Some dependencies failed to install. Continue anyway? (y/N)"
                read -n 1 -r
                echo
                if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                    exit 1
                fi
            }
            log_success "Python dependencies installed"
        fi
    fi
}

# Create service user
create_service_user() {
    log_info "Creating service user '$SERVICE_USER'..."

    if id "$SERVICE_USER" &>/dev/null; then
        log_warning "User '$SERVICE_USER' already exists"
    else
        useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER" || {
            log_error "Failed to create user '$SERVICE_USER'"
            exit 1
        }
        log_success "User '$SERVICE_USER' created"
    fi
}

# Copy application files
install_application() {
    log_info "Installing application to $INSTALL_DIR..."

    # Create installation directory
    mkdir -p "$INSTALL_DIR"

    # Copy files
    log_info "Copying application files..."
    rsync -av --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
          --exclude='.venv' --exclude='venv' --exclude='build' \
          --exclude='dist' --exclude='*.egg-info' \
          "$PROJECT_ROOT/" "$INSTALL_DIR/" || {
        log_error "Failed to copy application files"
        exit 1
    }

    log_success "Application files installed"
}

# Create working directories
create_directories() {
    log_info "Creating working directories..."

    # Server directories
    mkdir -p "$INSTALL_DIR/server/server_work"/{jobs,temp,encryption_keys}
    mkdir -p "$INSTALL_DIR/server/logs"
    mkdir -p "$INSTALL_DIR/server/output"

    # Configuration directory
    mkdir -p "$CONFIG_DIR"

    # Set ownership
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$CONFIG_DIR"

    # Set permissions
    chmod 750 "$INSTALL_DIR"
    chmod 750 "$CONFIG_DIR"
    chmod 700 "$INSTALL_DIR/server/server_work/encryption_keys"

    log_success "Working directories created"
}

# Install systemd service files
install_service_files() {
    log_info "Installing systemd service files..."

    # Copy server service
    if [[ -f "$SCRIPT_DIR/upscaling-server.service" ]]; then
        cp "$SCRIPT_DIR/upscaling-server.service" "$SYSTEMD_DIR/"
        chmod 644 "$SYSTEMD_DIR/upscaling-server.service"
        log_success "Server service file installed"
    else
        log_error "Server service file not found: $SCRIPT_DIR/upscaling-server.service"
        exit 1
    fi

    # Copy client service template
    if [[ -f "$SCRIPT_DIR/upscaling-client@.service" ]]; then
        cp "$SCRIPT_DIR/upscaling-client@.service" "$SYSTEMD_DIR/"
        chmod 644 "$SYSTEMD_DIR/upscaling-client@.service"
        log_success "Client service template installed"
    else
        log_error "Client service template not found: $SCRIPT_DIR/upscaling-client@.service"
        exit 1
    fi
}

# Create environment file template
create_env_file() {
    log_info "Creating environment file template..."

    cat > "$CONFIG_DIR/server.env" <<EOF
# UpscalingByNetwork Server Environment Configuration
# Edit this file to customize server settings

# Server configuration
#SERVER_HOST=0.0.0.0
#SERVER_PORT=8888

# Python configuration
PYTHONUNBUFFERED=1

# Logging
#LOG_LEVEL=INFO

# Add custom environment variables below
EOF

    chown "$SERVICE_USER:$SERVICE_GROUP" "$CONFIG_DIR/server.env"
    chmod 640 "$CONFIG_DIR/server.env"

    log_success "Environment file created at $CONFIG_DIR/server.env"
}

# Reload systemd
reload_systemd() {
    log_info "Reloading systemd daemon..."
    systemctl daemon-reload
    log_success "systemd daemon reloaded"
}

# Enable services
enable_services() {
    echo
    log_info "Service installation complete!"
    echo
    echo "Available services:"
    echo "  - upscaling-server.service       (Server service)"
    echo "  - upscaling-client@USERNAME.service  (Client service for USERNAME)"
    echo

    read -p "Do you want to enable the server service to start on boot? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        systemctl enable upscaling-server.service
        log_success "Server service enabled"

        read -p "Do you want to start the server service now? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            systemctl start upscaling-server.service
            sleep 2
            if systemctl is-active --quiet upscaling-server.service; then
                log_success "Server service started successfully"
                systemctl status upscaling-server.service --no-pager -l
            else
                log_error "Server service failed to start. Check logs with: journalctl -xeu upscaling-server.service"
            fi
        fi
    fi

    echo
    read -p "Do you want to configure a client service for a user? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        read -p "Enter username for client service: " CLIENT_USER

        if id "$CLIENT_USER" &>/dev/null; then
            # Create client working directory
            CLIENT_HOME=$(eval echo "~$CLIENT_USER")
            CLIENT_WORK_DIR="$CLIENT_HOME/.upscaling"

            log_info "Creating client working directory for $CLIENT_USER..."
            mkdir -p "$CLIENT_WORK_DIR"/{logs,work,temp}

            # Create client config
            cat > "$CLIENT_WORK_DIR/client.env" <<EOF
# UpscalingByNetwork Client Environment Configuration
# Edit this file to customize client settings

# Server connection (optional, can be configured in app)
#SERVER_HOST=localhost
#SERVER_PORT=8888

# Python configuration
PYTHONUNBUFFERED=1

# Logging
#LOG_LEVEL=INFO

# Add custom environment variables below
EOF

            chown -R "$CLIENT_USER:$CLIENT_USER" "$CLIENT_WORK_DIR"
            chmod 750 "$CLIENT_WORK_DIR"
            chmod 640 "$CLIENT_WORK_DIR/client.env"

            log_success "Client working directory created"

            read -p "Enable client service for $CLIENT_USER to start on boot? (y/N) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                systemctl enable "upscaling-client@$CLIENT_USER.service"
                log_success "Client service enabled for $CLIENT_USER"

                read -p "Start client service for $CLIENT_USER now? (y/N) " -n 1 -r
                echo
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    systemctl start "upscaling-client@$CLIENT_USER.service"
                    sleep 2
                    if systemctl is-active --quiet "upscaling-client@$CLIENT_USER.service"; then
                        log_success "Client service started successfully for $CLIENT_USER"
                        systemctl status "upscaling-client@$CLIENT_USER.service" --no-pager -l
                    else
                        log_error "Client service failed to start. Check logs with: journalctl -xeu upscaling-client@$CLIENT_USER.service"
                    fi
                fi
            fi
        else
            log_error "User '$CLIENT_USER' does not exist"
        fi
    fi
}

# Print final instructions
print_instructions() {
    echo
    echo "=============================================="
    log_success "Installation Complete!"
    echo "=============================================="
    echo
    echo "Service Management Commands:"
    echo
    echo "Server Service:"
    echo "  Start:   sudo systemctl start upscaling-server"
    echo "  Stop:    sudo systemctl stop upscaling-server"
    echo "  Restart: sudo systemctl restart upscaling-server"
    echo "  Status:  sudo systemctl status upscaling-server"
    echo "  Logs:    sudo journalctl -u upscaling-server -f"
    echo
    echo "Client Service (replace USERNAME with actual username):"
    echo "  Start:   sudo systemctl start upscaling-client@USERNAME"
    echo "  Stop:    sudo systemctl stop upscaling-client@USERNAME"
    echo "  Restart: sudo systemctl restart upscaling-client@USERNAME"
    echo "  Status:  sudo systemctl status upscaling-client@USERNAME"
    echo "  Logs:    sudo journalctl -u upscaling-client@USERNAME -f"
    echo
    echo "Configuration Files:"
    echo "  Server:  $CONFIG_DIR/server.env"
    echo "  Client:  ~/.upscaling/client.env"
    echo
    echo "Installation Directory: $INSTALL_DIR"
    echo
    echo "For more information, see README.md in $SCRIPT_DIR"
    echo "=============================================="
}

# Main installation
main() {
    echo "=============================================="
    echo "UpscalingByNetwork - Systemd Installation"
    echo "=============================================="
    echo

    check_root
    check_systemd
    check_python

    echo
    log_info "Installation will:"
    echo "  1. Create system user '$SERVICE_USER'"
    echo "  2. Install application to $INSTALL_DIR"
    echo "  3. Create working directories"
    echo "  4. Install systemd service files"
    echo "  5. Configure environment files"
    echo

    read -p "Do you want to continue? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Installation cancelled"
        exit 0
    fi

    echo
    create_service_user
    install_application
    create_directories
    install_service_files
    create_env_file
    reload_systemd
    enable_services
    print_instructions
}

# Run main function
main
