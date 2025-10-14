# UpscalingByNetwork Windows Service Installation Script
# Run as Administrator

param(
    [Parameter(Mandatory=$false)]
    [string]$Action = "install",

    [Parameter(Mandatory=$false)]
    [string]$Host = "0.0.0.0",

    [Parameter(Mandatory=$false)]
    [int]$Port = 8888
)

# Check if running as administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "Error: This script must be run as Administrator" -ForegroundColor Red
    Write-Host "Right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
    exit 1
}

Write-Host "=== UpscalingByNetwork Windows Service Management ===" -ForegroundColor Cyan
Write-Host ""

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ServiceScript = Join-Path $ScriptDir "windows-service-wrapper.py"

# Check if service script exists
if (-not (Test-Path $ServiceScript)) {
    Write-Host "Error: Service wrapper not found: $ServiceScript" -ForegroundColor Red
    exit 1
}

# Check if Python is installed
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "Error: Python not found in PATH" -ForegroundColor Red
    Write-Host "Please install Python 3.8+ from https://www.python.org/" -ForegroundColor Yellow
    exit 1
}

# Get Python version
$pythonVersion = & python --version 2>&1
Write-Host "Python: $pythonVersion" -ForegroundColor Green

# Check if pywin32 is installed
$pywin32Check = & python -c "import win32serviceutil" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing pywin32..." -ForegroundColor Yellow
    & python -m pip install pywin32

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to install pywin32" -ForegroundColor Red
        exit 1
    }

    Write-Host "pywin32 installed successfully" -ForegroundColor Green
}

# Perform action
switch ($Action.ToLower()) {
    "install" {
        Write-Host "Installing Windows service..." -ForegroundColor Yellow
        & python $ServiceScript install

        if ($LASTEXITCODE -eq 0) {
            Write-Host "Service installed successfully" -ForegroundColor Green
            Write-Host ""
            Write-Host "Service commands:" -ForegroundColor Cyan
            Write-Host "  Start:   net start UpscalingByNetwork" -ForegroundColor White
            Write-Host "  Stop:    net stop UpscalingByNetwork" -ForegroundColor White
            Write-Host "  Status:  sc query UpscalingByNetwork" -ForegroundColor White
            Write-Host ""
            Write-Host "Or use PowerShell:" -ForegroundColor Cyan
            Write-Host "  .\install-windows-service.ps1 start" -ForegroundColor White
            Write-Host "  .\install-windows-service.ps1 stop" -ForegroundColor White
            Write-Host "  .\install-windows-service.ps1 uninstall" -ForegroundColor White
        } else {
            Write-Host "Error: Service installation failed" -ForegroundColor Red
            exit 1
        }
    }

    "uninstall" {
        Write-Host "Uninstalling Windows service..." -ForegroundColor Yellow
        & python $ServiceScript remove

        if ($LASTEXITCODE -eq 0) {
            Write-Host "Service uninstalled successfully" -ForegroundColor Green
        } else {
            Write-Host "Error: Service uninstallation failed" -ForegroundColor Red
            exit 1
        }
    }

    "start" {
        Write-Host "Starting service..." -ForegroundColor Yellow
        & python $ServiceScript start

        if ($LASTEXITCODE -eq 0) {
            Write-Host "Service started successfully" -ForegroundColor Green
        } else {
            Write-Host "Error: Failed to start service" -ForegroundColor Red
            exit 1
        }
    }

    "stop" {
        Write-Host "Stopping service..." -ForegroundColor Yellow
        & python $ServiceScript stop

        if ($LASTEXITCODE -eq 0) {
            Write-Host "Service stopped successfully" -ForegroundColor Green
        } else {
            Write-Host "Error: Failed to stop service" -ForegroundColor Red
            exit 1
        }
    }

    "restart" {
        Write-Host "Restarting service..." -ForegroundColor Yellow
        & python $ServiceScript stop
        Start-Sleep -Seconds 2
        & python $ServiceScript start

        if ($LASTEXITCODE -eq 0) {
            Write-Host "Service restarted successfully" -ForegroundColor Green
        } else {
            Write-Host "Error: Failed to restart service" -ForegroundColor Red
            exit 1
        }
    }

    "status" {
        Write-Host "Checking service status..." -ForegroundColor Yellow
        $service = Get-Service -Name "UpscalingByNetwork" -ErrorAction SilentlyContinue

        if ($service) {
            Write-Host "Service Status: $($service.Status)" -ForegroundColor Green
            Write-Host "Display Name: $($service.DisplayName)" -ForegroundColor White
            Write-Host "Start Type: $($service.StartType)" -ForegroundColor White
        } else {
            Write-Host "Service not installed" -ForegroundColor Yellow
        }
    }

    default {
        Write-Host "Unknown action: $Action" -ForegroundColor Red
        Write-Host ""
        Write-Host "Valid actions:" -ForegroundColor Yellow
        Write-Host "  install   - Install the Windows service" -ForegroundColor White
        Write-Host "  uninstall - Uninstall the Windows service" -ForegroundColor White
        Write-Host "  start     - Start the service" -ForegroundColor White
        Write-Host "  stop      - Stop the service" -ForegroundColor White
        Write-Host "  restart   - Restart the service" -ForegroundColor White
        Write-Host "  status    - Check service status" -ForegroundColor White
        Write-Host ""
        Write-Host "Example: .\install-windows-service.ps1 install" -ForegroundColor Cyan
        exit 1
    }
}

exit 0
