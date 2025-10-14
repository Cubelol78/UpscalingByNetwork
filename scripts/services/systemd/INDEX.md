# UpscalingByNetwork - Systemd Services Index

Complete systemd service configuration for Linux systems.

## 📁 Files Overview

### Service Files

| File | Purpose |
|------|---------|
| `upscaling-server.service` | Main server service unit file |
| `upscaling-client@.service` | Client service template (per-user instances) |

### Installation Scripts

| File | Purpose |
|------|---------|
| `install-systemd.sh` | Automated installation script |
| `uninstall-systemd.sh` | Automated removal script |
| `check-systemd.sh` | Health check and validation script |

### Documentation

| File | Purpose |
|------|---------|
| `README.md` | Complete documentation (18KB) |
| `QUICKSTART.md` | Quick reference guide (9KB) |
| `INDEX.md` | This file - directory overview |

### Configuration Examples

| File | Purpose |
|------|---------|
| `server.env.example` | Server environment variables template |
| `client.env.example` | Client environment variables template |

### Other Files

| File | Purpose |
|------|---------|
| `.gitignore` | Git ignore patterns for env files |

## 🚀 Quick Start

### New Users - Start Here

1. **Read QUICKSTART.md** - Get up and running in 5 minutes
2. **Run installation**: `sudo ./install-systemd.sh`
3. **Verify installation**: `./check-systemd.sh`
4. **Start using**: `sudo systemctl start upscaling-server`

### Experienced Users

1. Review `README.md` for detailed configuration options
2. Customize environment files before installation
3. Review security settings in service files
4. Configure resource limits as needed

## 📚 Documentation Hierarchy

```
├── QUICKSTART.md          ← Start here for basic usage
├── README.md              ← Complete reference documentation
├── INDEX.md               ← You are here
├── server.env.example     ← Server configuration reference
└── client.env.example     ← Client configuration reference
```

## 🔧 Common Tasks

### Installation

```bash
sudo ./install-systemd.sh
```

See: `QUICKSTART.md` → Installation section

### Configuration

- Server: `/etc/upscaling/server.env`
- Client: `~/.upscaling/client.env`

See: `README.md` → Configuration section
Example: `server.env.example`, `client.env.example`

### Service Management

```bash
# Server
sudo systemctl start upscaling-server
sudo systemctl status upscaling-server
sudo journalctl -u upscaling-server -f

# Client
sudo systemctl start upscaling-client@username
sudo systemctl status upscaling-client@username
```

See: `QUICKSTART.md` → Quick Commands section

### Troubleshooting

```bash
# Health check
./check-systemd.sh

# View errors
sudo journalctl -u upscaling-server -p err

# Check dependencies
sudo -u upscaling python3 -c "import PyQt5, qasync, cryptography"
```

See: `QUICKSTART.md` → Troubleshooting section
See: `README.md` → Troubleshooting section (detailed)

### Uninstallation

```bash
sudo ./uninstall-systemd.sh
```

See: `README.md` → Uninstallation section

## 📋 Feature Summary

### Server Service (`upscaling-server.service`)

- ✅ Runs as non-root user (`upscaling`)
- ✅ Auto-restart on failure (5 retries in 5 minutes)
- ✅ Resource limits (4GB RAM, 200% CPU by default)
- ✅ Security hardening (sandboxing, syscall filtering)
- ✅ GPU device access (NVIDIA, AMD/Intel)
- ✅ Systemd journal logging
- ✅ Graceful shutdown (30s timeout)
- ✅ Network dependency management
- ✅ Environment file support

### Client Service (`upscaling-client@.service`)

- ✅ Per-user instances (template service)
- ✅ Runs as specified user
- ✅ Auto-restart on failure
- ✅ Resource limits (8GB RAM, 400% CPU by default)
- ✅ Security hardening
- ✅ GPU device access
- ✅ User home directory access
- ✅ Auto-connect to server
- ✅ Per-user logging

### Installation Script (`install-systemd.sh`)

- ✅ Prerequisite checking (systemd, Python)
- ✅ Dependency verification
- ✅ Service user creation
- ✅ Application file deployment
- ✅ Directory structure creation
- ✅ Permission management
- ✅ Service file installation
- ✅ Interactive configuration
- ✅ Service activation
- ✅ Status reporting

### Uninstallation Script (`uninstall-systemd.sh`)

- ✅ Service stopping
- ✅ Service disabling
- ✅ Service file removal
- ✅ Optional application cleanup
- ✅ Optional configuration cleanup
- ✅ Optional user removal
- ✅ Client directory cleanup
- ✅ Safety confirmations

### Health Check Script (`check-systemd.sh`)

- ✅ Systemd availability check
- ✅ Service file validation
- ✅ User/group verification
- ✅ Directory structure check
- ✅ Permission validation
- ✅ Python dependency check
- ✅ Service status check
- ✅ Port availability check
- ✅ GPU access verification
- ✅ Log error scanning
- ✅ Resource limit reporting
- ✅ Summary report

## 🔐 Security Features

All services implement comprehensive security hardening:

- **Sandboxing**: Private tmp, protected system paths
- **Capabilities**: No capabilities granted
- **System Calls**: Filtered to essential syscalls only
- **Namespaces**: Restricted namespace creation
- **Devices**: Minimal device access (GPU only)
- **Privileges**: No privilege escalation
- **SUID/SGID**: Blocked
- **Realtime**: Restricted

Security audit score: Target < 5.0/10 (systemd-analyze security)

See: `README.md` → Security section for details

## 📊 Resource Management

### Default Limits

**Server:**
- Memory: 4GB max, 3GB high
- CPU: 200% (2 cores)
- File Descriptors: 65536
- Processes: 4096

**Client:**
- Memory: 8GB max, 6GB high
- CPU: 400% (4 cores)
- File Descriptors: 65536
- Processes: 4096

### Customization

Resource limits can be adjusted via systemd overrides:

```bash
sudo systemctl edit upscaling-server
```

See: `README.md` → Performance Tuning section

## 🔌 Network Configuration

### Default Settings

- **Server**: Binds to `0.0.0.0:8888` (all interfaces)
- **Client**: Connects to `localhost:8888`

### Customization

Configure via environment files:

```bash
# Server: /etc/upscaling/server.env
SERVER_HOST=0.0.0.0
SERVER_PORT=8888

# Client: ~/.upscaling/client.env
SERVER_HOST=192.168.1.100
SERVER_PORT=8888
```

See: `server.env.example` and `client.env.example`

## 🖥️ GPU Support

Services are configured to access GPU devices:

- **NVIDIA**: `/dev/nvidia*` devices
- **AMD/Intel**: `/dev/dri/*` devices

Ensure service user is in `video` and `render` groups.

See: `README.md` → Troubleshooting → GPU Access Issues

## 📝 Logging

### View Logs

```bash
# Real-time server logs
sudo journalctl -u upscaling-server -f

# Real-time client logs
sudo journalctl -u upscaling-client@username -f

# Last 100 lines
sudo journalctl -u upscaling-server -n 100

# Since specific time
sudo journalctl -u upscaling-server --since "10:00"

# Errors only
sudo journalctl -u upscaling-server -p err
```

See: `QUICKSTART.md` → Usage → Log Management

## 🔄 Maintenance

### Regular Tasks

```bash
# Check service health
./check-systemd.sh

# View service status
sudo systemctl status upscaling-server

# Check for errors
sudo journalctl -u upscaling-server -p err --since today

# Monitor resources
systemd-cgtop
```

### Updates

After updating application code:

```bash
# Reinstall files
sudo rsync -av /path/to/source/ /opt/UpscalingByNetwork/

# Reload systemd (if service files changed)
sudo systemctl daemon-reload

# Restart services
sudo systemctl restart upscaling-server
```

## 📦 Directory Structure

After installation:

```
/opt/UpscalingByNetwork/          ← Application root
├── server/
│   ├── main.py                   ← Server entry point
│   ├── server_work/              ← Working directory
│   │   ├── jobs/
│   │   ├── temp/
│   │   └── encryption_keys/
│   ├── logs/                     ← Log files
│   └── output/                   ← Output files
└── client/
    └── windows/
        └── main.py               ← Client entry point

/etc/upscaling/                   ← Configuration
└── server.env                    ← Server environment

/etc/systemd/system/              ← Service files
├── upscaling-server.service
└── upscaling-client@.service

/home/USERNAME/.upscaling/        ← Client working dir
├── client.env                    ← Client environment
├── logs/
├── work/
└── temp/
```

## 🆘 Getting Help

### Self-Service

1. **Run health check**: `./check-systemd.sh`
2. **Check logs**: `sudo journalctl -u upscaling-server -n 100`
3. **Read documentation**: `README.md` and `QUICKSTART.md`
4. **Review examples**: `server.env.example`, `client.env.example`

### Documentation Sections

| Issue | Documentation |
|-------|---------------|
| Installation problems | `QUICKSTART.md` → Troubleshooting |
| Service won't start | `README.md` → Troubleshooting |
| Configuration help | `README.md` → Configuration |
| Performance tuning | `README.md` → Performance Tuning |
| Security questions | `README.md` → Security |
| GPU issues | `README.md` → Troubleshooting → GPU |

### Debug Information

Collect debug info for support:

```bash
{
  echo "=== System ==="
  uname -a
  systemctl --version
  python3 --version

  echo -e "\n=== Status ==="
  systemctl status upscaling-server

  echo -e "\n=== Logs ==="
  journalctl -u upscaling-server -n 100 --no-pager

  echo -e "\n=== Health Check ==="
  ./check-systemd.sh
} > debug_report.txt
```

## 🔗 Related Documentation

### In This Repository

- Main README: `/DATA-2T/UpscalingByNetwork/README.md`
- Docker services: `/DATA-2T/UpscalingByNetwork/docker/`
- Build scripts: `/DATA-2T/UpscalingByNetwork/build_scripts/`

### External Resources

- systemd documentation: https://www.freedesktop.org/wiki/Software/systemd/
- systemd service manual: `man systemd.service`
- systemd exec manual: `man systemd.exec`

## 📈 Version History

- **v1.0** (2025-10-14): Initial release
  - Server and client service files
  - Installation and uninstallation scripts
  - Health check script
  - Comprehensive documentation
  - Example configuration files

## 🤝 Contributing

Contributions welcome! When modifying:

1. Test on multiple Linux distributions
2. Verify security settings (`systemd-analyze security`)
3. Update documentation
4. Test installation/uninstallation
5. Run health check script

## 📄 License

Same as UpscalingByNetwork project.

---

**Quick Links:**
- [Installation Guide](QUICKSTART.md#installation-5-minutes)
- [Quick Commands](QUICKSTART.md#quick-commands)
- [Troubleshooting](QUICKSTART.md#troubleshooting)
- [Configuration](README.md#configuration)
- [Security](README.md#security)
- [Performance Tuning](README.md#performance-tuning)

---

*For questions or issues, run `./check-systemd.sh` and review the logs.*
