#!/bin/bash
#
# UpscalingByNetwork - Systemd Service Uninstallation Script
# Removes systemd services and optionally cleans up application files
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

# Stop and disable services
stop_services() {
    log_info "Stopping and disabling services..."

    # Stop server service
    if systemctl is-active --quiet upscaling-server.service; then
        log_info "Stopping server service..."
        systemctl stop upscaling-server.service
        log_success "Server service stopped"
    fi

    if systemctl is-enabled --quiet upscaling-server.service 2>/dev/null; then
        log_info "Disabling server service..."
        systemctl disable upscaling-server.service
        log_success "Server service disabled"
    fi

    # Find and stop all client services
    log_info "Searching for active client services..."
    CLIENT_SERVICES=$(systemctl list-units 'upscaling-client@*' --all --no-legend | awk '{print $1}' || true)

    if [[ -n "$CLIENT_SERVICES" ]]; then
        for service in $CLIENT_SERVICES; do
            log_info "Processing $service..."

            if systemctl is-active --quiet "$service"; then
                systemctl stop "$service"
                log_success "Stopped $service"
            fi

            if systemctl is-enabled --quiet "$service" 2>/dev/null; then
                systemctl disable "$service"
                log_success "Disabled $service"
            fi
        done
    else
        log_info "No active client services found"
    fi
}

# Remove service files
remove_service_files() {
    log_info "Removing systemd service files..."

    # Remove server service
    if [[ -f "$SYSTEMD_DIR/upscaling-server.service" ]]; then
        rm -f "$SYSTEMD_DIR/upscaling-server.service"
        log_success "Server service file removed"
    fi

    # Remove client service template
    if [[ -f "$SYSTEMD_DIR/upscaling-client@.service" ]]; then
        rm -f "$SYSTEMD_DIR/upscaling-client@.service"
        log_success "Client service template removed"
    fi
}

# Reload systemd
reload_systemd() {
    log_info "Reloading systemd daemon..."
    systemctl daemon-reload
    systemctl reset-failed
    log_success "systemd daemon reloaded"
}

# Remove application files
remove_application() {
    echo
    read -p "Do you want to remove the application files from $INSTALL_DIR? (y/N) " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_warning "This will remove all application files including logs and data!"
        read -p "Are you absolutely sure? (type 'yes' to confirm): " CONFIRM

        if [[ "$CONFIRM" == "yes" ]]; then
            if [[ -d "$INSTALL_DIR" ]]; then
                log_info "Removing application directory..."
                rm -rf "$INSTALL_DIR"
                log_success "Application directory removed"
            else
                log_info "Application directory not found"
            fi
        else
            log_info "Skipping application files removal"
        fi
    else
        log_info "Keeping application files at $INSTALL_DIR"
    fi
}

# Remove configuration files
remove_configuration() {
    echo
    read -p "Do you want to remove configuration files from $CONFIG_DIR? (y/N) " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if [[ -d "$CONFIG_DIR" ]]; then
            log_info "Removing configuration directory..."
            rm -rf "$CONFIG_DIR"
            log_success "Configuration directory removed"
        else
            log_info "Configuration directory not found"
        fi
    else
        log_info "Keeping configuration files at $CONFIG_DIR"
    fi
}

# Remove service user
remove_service_user() {
    echo
    read -p "Do you want to remove the service user '$SERVICE_USER'? (y/N) " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if id "$SERVICE_USER" &>/dev/null; then
            log_info "Removing service user..."
            userdel "$SERVICE_USER" 2>/dev/null || {
                log_warning "Could not remove user '$SERVICE_USER'. May need manual cleanup."
            }
            log_success "Service user removed"
        else
            log_info "Service user '$SERVICE_USER' not found"
        fi
    else
        log_info "Keeping service user '$SERVICE_USER'"
    fi
}

# Clean up client directories
cleanup_client_directories() {
    echo
    read -p "Do you want to clean up client working directories in user home folders? (y/N) " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_warning "This will search for .upscaling directories in /home/*"
        read -p "Continue? (y/N) " -n 1 -r
        echo

        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log_info "Searching for client directories..."

            FOUND=0
            for user_home in /home/*; do
                if [[ -d "$user_home/.upscaling" ]]; then
                    USERNAME=$(basename "$user_home")
                    log_info "Found client directory for user: $USERNAME"

                    read -p "Remove $user_home/.upscaling? (y/N) " -n 1 -r
                    echo
                    if [[ $REPLY =~ ^[Yy]$ ]]; then
                        rm -rf "$user_home/.upscaling"
                        log_success "Removed client directory for $USERNAME"
                        FOUND=$((FOUND + 1))
                    fi
                fi
            done

            if [[ $FOUND -eq 0 ]]; then
                log_info "No client directories found"
            else
                log_success "Cleaned up $FOUND client directories"
            fi
        fi
    fi
}

# Print final status
print_status() {
    echo
    echo "=============================================="
    log_success "Uninstallation Complete!"
    echo "=============================================="
    echo
    echo "Removed:"
    echo "  - systemd service files"
    echo "  - Running services"
    echo

    if [[ -d "$INSTALL_DIR" ]]; then
        echo "Kept:"
        echo "  - Application files: $INSTALL_DIR"
    fi

    if [[ -d "$CONFIG_DIR" ]]; then
        echo "  - Configuration files: $CONFIG_DIR"
    fi

    if id "$SERVICE_USER" &>/dev/null; then
        echo "  - Service user: $SERVICE_USER"
    fi

    echo
    echo "To manually clean up remaining files:"
    echo "  sudo rm -rf $INSTALL_DIR"
    echo "  sudo rm -rf $CONFIG_DIR"
    echo "  sudo userdel $SERVICE_USER"
    echo "=============================================="
}

# Main uninstallation
main() {
    echo "=============================================="
    echo "UpscalingByNetwork - Systemd Uninstallation"
    echo "=============================================="
    echo

    check_root

    log_warning "This will stop and remove UpscalingByNetwork systemd services"
    echo
    read -p "Do you want to continue? (y/N) " -n 1 -r
    echo

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Uninstallation cancelled"
        exit 0
    fi

    echo
    stop_services
    remove_service_files
    reload_systemd
    remove_application
    remove_configuration
    cleanup_client_directories
    remove_service_user
    print_status
}

# Run main function
main
