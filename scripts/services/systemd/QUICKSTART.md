# UpscalingByNetwork - Systemd Quick Start Guide

A quick reference for getting up and running with systemd services.

## Installation (5 Minutes)

```bash
# 1. Navigate to systemd scripts directory
cd /path/to/UpscalingByNetwork/scripts/services/systemd

# 2. Run installation script
sudo ./install-systemd.sh

# 3. Follow the prompts
# - Install Python dependencies (if needed)
# - Enable server service (recommended: yes)
# - Start server now (recommended: yes)
# - Configure client service (optional)
```

That's it! The server should now be running.

## Quick Commands

### Server

```bash
# Start server
sudo systemctl start upscaling-server

# Stop server
sudo systemctl stop upscaling-server

# Restart server
sudo systemctl restart upscaling-server

# Check status
sudo systemctl status upscaling-server

# View logs (real-time)
sudo journalctl -u upscaling-server -f

# View logs (last 50 lines)
sudo journalctl -u upscaling-server -n 50

# Enable auto-start on boot
sudo systemctl enable upscaling-server

# Disable auto-start
sudo systemctl disable upscaling-server
```

### Client (replace 'john' with username)

```bash
# Start client
sudo systemctl start upscaling-client@john

# Stop client
sudo systemctl stop upscaling-client@john

# Restart client
sudo systemctl restart upscaling-client@john

# Check status
sudo systemctl status upscaling-client@john

# View logs (real-time)
sudo journalctl -u upscaling-client@john -f

# Enable auto-start on boot
sudo systemctl enable upscaling-client@john

# List all active clients
systemctl list-units 'upscaling-client@*'
```

## Configuration

### Server Configuration

Edit `/etc/upscaling/server.env`:

```bash
sudo nano /etc/upscaling/server.env
```

Common settings:

```bash
# Change port
SERVER_PORT=9999

# Enable debug logging
LOG_LEVEL=DEBUG

# Limit clients
MAX_CLIENTS=25
```

After editing, restart the server:

```bash
sudo systemctl restart upscaling-server
```

### Client Configuration

Edit `~/.upscaling/client.env` (as the client user):

```bash
nano ~/.upscaling/client.env
```

Common settings:

```bash
# Set server address
SERVER_HOST=192.168.1.100
SERVER_PORT=8888

# Auto-connect on start
AUTO_CONNECT=true

# Enable debug logging
LOG_LEVEL=DEBUG
```

After editing, restart the client:

```bash
sudo systemctl restart upscaling-client@username
```

## Common Tasks

### Check if Services are Running

```bash
# Check server
systemctl is-active upscaling-server

# Check client
systemctl is-active upscaling-client@john

# Check all services
systemctl list-units 'upscaling-*' --all
```

### View Resource Usage

```bash
# Real-time resource usage
systemd-cgtop

# Server memory usage
systemctl status upscaling-server | grep Memory

# Detailed server status
systemctl show upscaling-server | grep -E "(Memory|CPU|Tasks)"
```

### Search Logs

```bash
# Search for errors
sudo journalctl -u upscaling-server | grep -i error

# Show only errors and critical
sudo journalctl -u upscaling-server -p err

# Show logs from specific time
sudo journalctl -u upscaling-server --since "10:00" --until "11:00"

# Show logs from last hour
sudo journalctl -u upscaling-server --since "1 hour ago"

# Export logs to file
sudo journalctl -u upscaling-server > server_logs.txt
```

### Adding a New Client

```bash
# 1. Create client working directory for user
sudo -u john mkdir -p ~/.upscaling/{logs,work,temp}

# 2. Copy environment file
sudo cp /opt/UpscalingByNetwork/scripts/services/systemd/client.env.example /home/john/.upscaling/client.env

# 3. Set ownership
sudo chown -R john:john /home/john/.upscaling

# 4. Edit configuration
sudo -u john nano /home/john/.upscaling/client.env

# 5. Enable service
sudo systemctl enable upscaling-client@john

# 6. Start service
sudo systemctl start upscaling-client@john

# 7. Check status
sudo systemctl status upscaling-client@john
```

## Troubleshooting

### Server Won't Start

```bash
# 1. Check detailed status
sudo systemctl status upscaling-server -l

# 2. Check full logs
sudo journalctl -xeu upscaling-server

# 3. Test Python dependencies
sudo -u upscaling python3 -c "import PyQt5, qasync, cryptography"

# 4. Check file permissions
ls -la /opt/UpscalingByNetwork/server/

# 5. Check if port is available
sudo netstat -tlnp | grep 8888
```

### Port Already in Use

```bash
# Find what's using the port
sudo lsof -i :8888

# Change port in config
echo "SERVER_PORT=9999" | sudo tee -a /etc/upscaling/server.env

# Restart server
sudo systemctl restart upscaling-server
```

### Permission Errors

```bash
# Fix server permissions
sudo chown -R upscaling:upscaling /opt/UpscalingByNetwork

# Fix client permissions (for user 'john')
sudo chown -R john:john /home/john/.upscaling
```

### Service Keeps Crashing

```bash
# View crash logs
sudo journalctl -u upscaling-server | tail -100

# Increase memory limit
sudo systemctl edit upscaling-server
# Add:
# [Service]
# MemoryMax=8G

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart upscaling-server
```

### GPU Not Detected

```bash
# Check GPU devices
ls -la /dev/dri/
ls -la /dev/nvidia*

# Add user to video group (AMD/Intel)
sudo usermod -aG video upscaling

# Add user to render group
sudo usermod -aG render upscaling

# Check NVIDIA drivers
nvidia-smi

# Restart service
sudo systemctl restart upscaling-server
```

## Advanced Usage

### Custom Service Modifications

```bash
# Create override file (recommended method)
sudo systemctl edit upscaling-server

# This opens an editor where you can add overrides
# Changes are preserved during updates

# Example: Increase memory and CPU limits
[Service]
MemoryMax=16G
CPUQuota=400%

# Save and exit, then reload
sudo systemctl daemon-reload
sudo systemctl restart upscaling-server
```

### Multiple Server Instances

```bash
# Copy server service to instance template
sudo cp /etc/systemd/system/upscaling-server.service \
       /etc/systemd/system/upscaling-server@.service

# Edit template to use instance parameter
sudo nano /etc/systemd/system/upscaling-server@.service
# Change port to use %i: --port %i

# Start instances on different ports
sudo systemctl start upscaling-server@8888
sudo systemctl start upscaling-server@8889

# Enable both
sudo systemctl enable upscaling-server@8888
sudo systemctl enable upscaling-server@8889
```

### Monitoring with Journalctl

```bash
# Follow logs with filtering
sudo journalctl -u upscaling-server -f | grep -i "error\|warning\|client"

# Show logs with timestamps
sudo journalctl -u upscaling-server -o short-precise

# Show logs in JSON format
sudo journalctl -u upscaling-server -o json-pretty

# Show kernel messages + service logs
sudo journalctl -b -u upscaling-server
```

## Performance Tuning

### For High-Performance Systems

Edit service override:

```bash
sudo systemctl edit upscaling-server
```

Add:

```ini
[Service]
# Use more CPU
CPUQuota=800%

# Use more memory
MemoryMax=16G

# Higher priority
Nice=-10

# More file descriptors
LimitNOFILE=131072

# More processes
LimitNPROC=16384
TasksMax=16384
```

### For Low-Resource Systems

```bash
sudo systemctl edit upscaling-server
```

Add:

```ini
[Service]
# Limit CPU
CPUQuota=100%

# Limit memory
MemoryMax=2G

# Lower priority
Nice=10

# Reduce batch size via environment
Environment="BATCH_SIZE=25"
Environment="MAX_CLIENTS=10"
```

Apply changes:

```bash
sudo systemctl daemon-reload
sudo systemctl restart upscaling-server
```

## Uninstallation

```bash
# Run uninstall script
cd /path/to/UpscalingByNetwork/scripts/services/systemd
sudo ./uninstall-systemd.sh

# Follow prompts to remove:
# - Services (required)
# - Application files (optional)
# - Configuration files (optional)
# - Service user (optional)
# - Client directories (optional)
```

## Getting Help

### Check Service Health

```bash
# Server health
sudo systemctl status upscaling-server
sudo journalctl -u upscaling-server -n 50

# Client health
sudo systemctl status upscaling-client@username
sudo journalctl -u upscaling-client@username -n 50

# System health
systemctl --failed
journalctl -p err -b
```

### Collect Debug Information

```bash
# Create debug report
{
  echo "=== System Info ==="
  uname -a
  systemctl --version
  python3 --version

  echo -e "\n=== Server Status ==="
  systemctl status upscaling-server

  echo -e "\n=== Server Logs ==="
  journalctl -u upscaling-server -n 100 --no-pager

  echo -e "\n=== Environment ==="
  sudo cat /etc/upscaling/server.env

  echo -e "\n=== Permissions ==="
  ls -la /opt/UpscalingByNetwork/server/
} > debug_report.txt

# Share debug_report.txt when asking for help
```

## Additional Resources

- Full documentation: `README.md` in this directory
- Example configs: `server.env.example`, `client.env.example`
- Project repository: [GitHub URL]
- Issue tracker: [GitHub Issues URL]

---

**Quick Reference Card**

| Task | Command |
|------|---------|
| Start server | `sudo systemctl start upscaling-server` |
| Stop server | `sudo systemctl stop upscaling-server` |
| Server status | `sudo systemctl status upscaling-server` |
| Server logs | `sudo journalctl -u upscaling-server -f` |
| Start client | `sudo systemctl start upscaling-client@USER` |
| Client logs | `sudo journalctl -u upscaling-client@USER -f` |
| Enable on boot | `sudo systemctl enable SERVICE` |
| Disable on boot | `sudo systemctl disable SERVICE` |
| Edit config | `sudo nano /etc/upscaling/server.env` |
| Reload after edit | `sudo systemctl restart upscaling-server` |

---

*For detailed information, see the full README.md in this directory.*
