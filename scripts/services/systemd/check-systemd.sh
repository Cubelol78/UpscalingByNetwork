#!/bin/bash
#
# UpscalingByNetwork - Systemd Service Health Check
# Validates systemd installation and service configuration
#

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SYSTEMD_DIR="/etc/systemd/system"
SERVICE_USER="upscaling"
INSTALL_DIR="/opt/UpscalingByNetwork"
CONFIG_DIR="/etc/upscaling"

# Counters
CHECKS_PASSED=0
CHECKS_FAILED=0
CHECKS_WARNING=0

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    CHECKS_WARNING=$((CHECKS_WARNING + 1))
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
    CHECKS_FAILED=$((CHECKS_FAILED + 1))
}

# Check functions
check_systemd() {
    log_info "Checking systemd..."

    if ! command -v systemctl &> /dev/null; then
        log_error "systemd not found (systemctl command missing)"
        return 1
    fi

    if ! systemctl --version &> /dev/null; then
        log_error "systemd not running"
        return 1
    fi

    VERSION=$(systemctl --version | head -n1 | awk '{print $2}')
    log_success "systemd found (version $VERSION)"
}

check_service_files() {
    log_info "Checking service files..."

    # Check server service
    if [[ -f "$SYSTEMD_DIR/upscaling-server.service" ]]; then
        log_success "Server service file exists"

        # Validate syntax
        if systemd-analyze verify "$SYSTEMD_DIR/upscaling-server.service" 2>/dev/null; then
            log_success "Server service file syntax valid"
        else
            log_error "Server service file has syntax errors"
        fi
    else
        log_error "Server service file not found"
    fi

    # Check client service template
    if [[ -f "$SYSTEMD_DIR/upscaling-client@.service" ]]; then
        log_success "Client service template exists"

        # Validate syntax
        if systemd-analyze verify "$SYSTEMD_DIR/upscaling-client@.service" 2>/dev/null; then
            log_success "Client service template syntax valid"
        else
            log_error "Client service template has syntax errors"
        fi
    else
        log_error "Client service template not found"
    fi
}

check_service_user() {
    log_info "Checking service user..."

    if id "$SERVICE_USER" &>/dev/null; then
        log_success "Service user '$SERVICE_USER' exists"

        # Check if it's a system user
        USER_ID=$(id -u "$SERVICE_USER")
        if [[ $USER_ID -lt 1000 ]]; then
            log_success "Service user is a system account (UID: $USER_ID)"
        else
            log_warning "Service user has regular user UID: $USER_ID"
        fi
    else
        log_error "Service user '$SERVICE_USER' not found"
    fi
}

check_directories() {
    log_info "Checking directories..."

    # Application directory
    if [[ -d "$INSTALL_DIR" ]]; then
        log_success "Installation directory exists: $INSTALL_DIR"

        # Check ownership
        OWNER=$(stat -c '%U' "$INSTALL_DIR" 2>/dev/null || stat -f '%Su' "$INSTALL_DIR" 2>/dev/null)
        if [[ "$OWNER" == "$SERVICE_USER" ]]; then
            log_success "Installation directory owned by $SERVICE_USER"
        else
            log_error "Installation directory owned by $OWNER (expected $SERVICE_USER)"
        fi

        # Check permissions
        PERMS=$(stat -c '%a' "$INSTALL_DIR" 2>/dev/null || stat -f '%A' "$INSTALL_DIR" 2>/dev/null)
        if [[ "$PERMS" == "750" ]] || [[ "$PERMS" == "755" ]]; then
            log_success "Installation directory permissions OK: $PERMS"
        else
            log_warning "Installation directory permissions: $PERMS (recommended: 750)"
        fi
    else
        log_error "Installation directory not found: $INSTALL_DIR"
    fi

    # Server working directories
    WORK_DIRS=(
        "$INSTALL_DIR/server/server_work"
        "$INSTALL_DIR/server/server_work/jobs"
        "$INSTALL_DIR/server/server_work/temp"
        "$INSTALL_DIR/server/server_work/encryption_keys"
        "$INSTALL_DIR/server/logs"
        "$INSTALL_DIR/server/output"
    )

    for dir in "${WORK_DIRS[@]}"; do
        if [[ -d "$dir" ]]; then
            log_success "Working directory exists: $(basename $dir)"
        else
            log_warning "Working directory missing: $dir"
        fi
    done

    # Configuration directory
    if [[ -d "$CONFIG_DIR" ]]; then
        log_success "Configuration directory exists: $CONFIG_DIR"
    else
        log_warning "Configuration directory not found: $CONFIG_DIR"
    fi
}

check_python() {
    log_info "Checking Python installation..."

    if ! command -v python3 &> /dev/null; then
        log_error "python3 not found"
        return 1
    fi

    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    log_success "Python3 found: $PYTHON_VERSION"

    # Check if pip is available
    if python3 -m pip --version &> /dev/null; then
        log_success "pip is available"
    else
        log_warning "pip not found (optional)"
    fi
}

check_dependencies() {
    log_info "Checking Python dependencies..."

    DEPS=("cryptography" "psutil")
    OPTIONAL_DEPS=("PyQt5" "qasync" "rich")

    for dep in "${DEPS[@]}"; do
        if python3 -c "import $dep" 2>/dev/null; then
            log_success "Required dependency: $dep"
        else
            log_error "Missing required dependency: $dep"
        fi
    done

    for dep in "${OPTIONAL_DEPS[@]}"; do
        if python3 -c "import $dep" 2>/dev/null; then
            log_success "Optional dependency: $dep"
        else
            log_warning "Missing optional dependency: $dep"
        fi
    done
}

check_server_service() {
    log_info "Checking server service..."

    # Check if service exists
    if ! systemctl list-unit-files upscaling-server.service &>/dev/null; then
        log_error "Server service not found in systemd"
        return 1
    fi

    # Check if enabled
    if systemctl is-enabled upscaling-server.service &>/dev/null; then
        log_success "Server service is enabled (auto-start on boot)"
    else
        log_warning "Server service is not enabled (won't auto-start)"
    fi

    # Check if active
    if systemctl is-active upscaling-server.service &>/dev/null; then
        log_success "Server service is running"

        # Get PID
        PID=$(systemctl show -p MainPID upscaling-server.service | cut -d= -f2)
        if [[ "$PID" != "0" ]]; then
            log_success "Server process running (PID: $PID)"
        fi

        # Check uptime
        ACTIVE_SINCE=$(systemctl show -p ActiveEnterTimestamp upscaling-server.service | cut -d= -f2)
        log_info "Running since: $ACTIVE_SINCE"

    else
        STATUS=$(systemctl is-active upscaling-server.service)
        log_warning "Server service is not running (status: $STATUS)"
    fi

    # Check if failed
    if systemctl is-failed upscaling-server.service &>/dev/null; then
        log_error "Server service is in failed state"
        log_info "Check logs with: journalctl -xeu upscaling-server.service"
    fi
}

check_client_services() {
    log_info "Checking client services..."

    # Find all client instances
    CLIENT_SERVICES=$(systemctl list-units 'upscaling-client@*' --all --no-legend | awk '{print $1}' || true)

    if [[ -z "$CLIENT_SERVICES" ]]; then
        log_info "No client services configured"
    else
        CLIENT_COUNT=$(echo "$CLIENT_SERVICES" | wc -l)
        log_info "Found $CLIENT_COUNT client service(s)"

        for service in $CLIENT_SERVICES; do
            USERNAME=$(echo "$service" | sed 's/upscaling-client@\(.*\)\.service/\1/')

            if systemctl is-active --quiet "$service"; then
                log_success "Client service running for user: $USERNAME"
            else
                log_warning "Client service not running for user: $USERNAME"
            fi
        done
    fi
}

check_ports() {
    log_info "Checking network ports..."

    # Check if netstat or ss is available
    if command -v ss &> /dev/null; then
        PORT_CMD="ss -tlnp"
    elif command -v netstat &> /dev/null; then
        PORT_CMD="netstat -tlnp"
    else
        log_warning "Cannot check ports (ss/netstat not available)"
        return
    fi

    # Check if port 8888 is listening
    if $PORT_CMD 2>/dev/null | grep -q ":8888"; then
        log_success "Server listening on port 8888"
    else
        if systemctl is-active upscaling-server.service &>/dev/null; then
            log_warning "Server running but not listening on port 8888"
        else
            log_info "Server not running (port 8888 not in use)"
        fi
    fi
}

check_gpu() {
    log_info "Checking GPU access..."

    # Check for GPU devices
    GPU_FOUND=false

    # NVIDIA
    if [[ -c /dev/nvidia0 ]]; then
        log_success "NVIDIA GPU device found: /dev/nvidia0"
        GPU_FOUND=true

        if command -v nvidia-smi &> /dev/null; then
            log_success "nvidia-smi available"
        else
            log_warning "nvidia-smi not found (NVIDIA drivers may not be installed)"
        fi
    fi

    # AMD/Intel DRI
    if [[ -d /dev/dri ]]; then
        DRI_DEVICES=$(ls /dev/dri/render* 2>/dev/null | wc -l)
        if [[ $DRI_DEVICES -gt 0 ]]; then
            log_success "DRI render devices found: $DRI_DEVICES"
            GPU_FOUND=true
        fi
    fi

    if [[ "$GPU_FOUND" == "false" ]]; then
        log_warning "No GPU devices found (will use CPU)"
    fi

    # Check if service user can access GPU
    if [[ "$GPU_FOUND" == "true" ]]; then
        if groups "$SERVICE_USER" 2>/dev/null | grep -q -E "video|render"; then
            log_success "Service user has GPU access (video/render group)"
        else
            log_warning "Service user not in video/render group (GPU access may be limited)"
        fi
    fi
}

check_logs() {
    log_info "Checking logs..."

    # Check if journalctl is available
    if ! command -v journalctl &> /dev/null; then
        log_warning "journalctl not available"
        return
    fi

    # Check for recent errors in server logs
    if systemctl list-unit-files upscaling-server.service &>/dev/null; then
        ERROR_COUNT=$(journalctl -u upscaling-server.service -p err -n 100 --no-pager 2>/dev/null | grep -c "." || echo "0")

        if [[ $ERROR_COUNT -eq 0 ]]; then
            log_success "No errors in recent server logs"
        else
            log_warning "Found $ERROR_COUNT errors in recent server logs"
            log_info "View with: journalctl -u upscaling-server.service -p err"
        fi
    fi
}

check_resources() {
    log_info "Checking resource limits..."

    if systemctl show upscaling-server.service &>/dev/null; then
        # Memory limit
        MEM_MAX=$(systemctl show -p MemoryMax upscaling-server.service | cut -d= -f2)
        if [[ "$MEM_MAX" != "infinity" ]]; then
            log_info "Memory limit: $MEM_MAX"
        fi

        # CPU quota
        CPU_QUOTA=$(systemctl show -p CPUQuotaPerSecUSec upscaling-server.service | cut -d= -f2)
        if [[ "$CPU_QUOTA" != "infinity" ]]; then
            log_info "CPU quota: $CPU_QUOTA"
        fi

        # Tasks limit
        TASKS_MAX=$(systemctl show -p TasksMax upscaling-server.service | cut -d= -f2)
        if [[ "$TASKS_MAX" != "infinity" ]]; then
            log_info "Tasks limit: $TASKS_MAX"
        fi
    fi
}

# Print summary
print_summary() {
    echo
    echo "=============================================="
    echo "Health Check Summary"
    echo "=============================================="
    echo -e "${GREEN}Passed:${NC}  $CHECKS_PASSED"
    echo -e "${YELLOW}Warnings:${NC} $CHECKS_WARNING"
    echo -e "${RED}Failed:${NC}  $CHECKS_FAILED"
    echo "=============================================="

    if [[ $CHECKS_FAILED -eq 0 ]]; then
        echo -e "${GREEN}✓ All critical checks passed!${NC}"
        return 0
    else
        echo -e "${RED}✗ Some checks failed. Please review the issues above.${NC}"
        return 1
    fi
}

# Main execution
main() {
    echo "=============================================="
    echo "UpscalingByNetwork - Systemd Health Check"
    echo "=============================================="
    echo

    check_systemd
    check_service_files
    check_service_user
    check_directories
    check_python
    check_dependencies
    check_server_service
    check_client_services
    check_ports
    check_gpu
    check_logs
    check_resources

    print_summary
}

# Run main function
main
