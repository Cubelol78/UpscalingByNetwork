# UpscalingByNetwork/scripts/install.ps1

# Script d'installation Windows PowerShell
# UpscalingByNetwork/scripts/install.ps1

param(
    [switch]$SkipDeps,
    [string]$InstallPath = "$env:USERPROFILE\UpscalingByNetwork"
)

# Configuration
$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/votre-repo/UpscalingByNetwork"

# Fonctions d'affichage
function Write-Step($Message) {
    Write-Host "[ÉTAPE] $Message" -ForegroundColor Blue
}

function Write-Success($Message) {
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Warning($Message) {
    Write-Host "[ATTENTION] $Message" -ForegroundColor Yellow
}

function Write-Error($Message) {
    Write-Host "[ERREUR] $Message" -ForegroundColor Red
}

# En-tête
Write-Host @"
╔══════════════════════════════════════════════╗
║        UpscalingByNetwork Installer          ║
║             Version 1.0.0                    ║
╚══════════════════════════════════════════════╝
"@ -ForegroundColor Blue

# Vérification des prérequis
function Test-Prerequisites {
    Write-Step "Vérification des prérequis..."
    
    # Test PowerShell version
    if ($PSVersionTable.PSVersion.Major -lt 5) {
        Write-Error "PowerShell 5.0 ou supérieur requis"
        exit 1
    }
    
    # Test Python
    try {
        $pythonVersion = python --version 2>&1
        if ($pythonVersion -match "Python (\d+)\.(\d+)") {
            $major = [int]$matches[1]
            $minor = [int]$matches[2]
            if ($major -eq 3 -and $minor -ge 8) {
                Write-Success "Python $($matches[0]) détecté"
            } else {
                Write-Error "Python 3.8+ requis. Version détectée: $($matches[0])"
                exit 1
            }
        }
    } catch {
        Write-Error "Python non trouvé. Installez Python 3.8+ depuis python.org"
        exit 1
    }
    
    # Test Git
    try {
        git --version | Out-Null
        Write-Success "Git détecté"
    } catch {
        Write-Error "Git non trouvé. Installez Git depuis git-scm.com"
        exit 1
    }
}

# Installation des dépendances Python
function Install-PythonDeps {
    if ($SkipDeps) {
        Write-Warning "Installation des dépendances ignorée (--SkipDeps)"
        return
    }
    
    Write-Step "Installation des dépendances Python..."
    
    # Mise à jour de pip
    python -m pip install --upgrade pip
    
    # Installation des packages
    $packages = @(
        "websockets>=11.0.0",
        "PyQt5>=5.15.0",
        "qasync>=0.24.0",
        "cryptography>=41.0.0",
        "psutil>=5.9.0",
        "requests>=2.31.0",
        "pyinstaller>=5.13.0"
    )
    
    foreach ($package in $packages) {
        Write-Host "   Installation de $package..."
        python -m pip install $package
    }
    
    Write-Success "Dépendances Python installées"
}

# Téléchargement du code source
function Download-Source {
    Write-Step "Téléchargement du code source..."
    
    if (Test-Path $InstallPath) {
        Write-Warning "Le dossier $InstallPath existe déjà"
        $response = Read-Host "Voulez-vous le supprimer et réinstaller ? (y/N)"
        if ($response -eq "y" -or $response -eq "Y") {
            Remove-Item -Recurse -Force $InstallPath
        } else {
            Write-Error "Installation annulée"
            exit 1
        }
    }
    
    git clone $RepoUrl $InstallPath
    Set-Location $InstallPath
    
    Write-Success "Code source téléchargé dans $InstallPath"
}

# Téléchargement des binaires
function Download-Binaries {
    Write-Step "Téléchargement des binaires..."
    
    $downloadDir = Join-Path $InstallPath "downloads"
    New-Item -ItemType Directory -Path $downloadDir -Force | Out-Null
    
    # URLs de téléchargement
    $ffmpegUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    $realesrganUrl = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.3.0/realesrgan-ncnn-vulkan-20220424-windows.zip"
    
    # Téléchargement FFmpeg
    Write-Host "   Téléchargement de FFmpeg..."
    $ffmpegZip = Join-Path $downloadDir "ffmpeg.zip"
    Invoke-WebRequest -Uri $ffmpegUrl -OutFile $ffmpegZip -UseBasicParsing
    
    # Téléchargement Real-ESRGAN
    Write-Host "   Téléchargement de Real-ESRGAN..."
    $realesrganZip = Join-Path $downloadDir "realesrgan.zip"
    Invoke-WebRequest -Uri $realesrganUrl -OutFile $realesrganZip -UseBasicParsing
    
    Write-Success "Binaires téléchargés"
}

# Extraction des binaires
function Extract-Binaries {
    Write-Step "Extraction des binaires..."
    
    $downloadDir = Join-Path $InstallPath "downloads"
    
    # Extraction FFmpeg
    Write-Host "   Extraction de FFmpeg..."
    $ffmpegZip = Join-Path $downloadDir "ffmpeg.zip"
    $serverFFmpegDir = Join-Path $InstallPath "server\ffmpeg"
    $clientFFmpegDir = Join-Path $InstallPath "client\windows\ffmpeg"
    
    Expand-Archive -Path $ffmpegZip -DestinationPath $downloadDir -Force
    
    # Recherche et copie des exécutables FFmpeg
    $ffmpegExtracted = Get-ChildItem -Path $downloadDir -Filter "ffmpeg-*" -Directory | Select-Object -First 1
    if ($ffmpegExtracted) {
        $ffmpegBin = Join-Path $ffmpegExtracted.FullName "bin"
        
        New-Item -ItemType Directory -Path $serverFFmpegDir -Force | Out-Null
        New-Item -ItemType Directory -Path $clientFFmpegDir -Force | Out-Null
        
        Copy-Item -Path (Join-Path $ffmpegBin "ffmpeg.exe") -Destination $serverFFmpegDir
        Copy-Item -Path (Join-Path $ffmpegBin "ffprobe.exe") -Destination $serverFFmpegDir
        Copy-Item -Path (Join-Path $ffmpegBin "ffmpeg.exe") -Destination $clientFFmpegDir
        Copy-Item -Path (Join-Path $ffmpegBin "ffprobe.exe") -Destination $clientFFmpegDir
    }
    
    # Extraction Real-ESRGAN
    Write-Host "   Extraction de Real-ESRGAN..."
    $realesrganZip = Join-Path $downloadDir "realesrgan.zip"
    $serverRealesrganDir = Join-Path $InstallPath "server\realesrgan-ncnn-vulkan"
    $clientRealesrganDir = Join-Path $InstallPath "client\windows\realesrgan-ncnn-vulkan"
    
    New-Item -ItemType Directory -Path $serverRealesrganDir -Force | Out-Null
    New-Item -ItemType Directory -Path $clientRealesrganDir -Force | Out-Null
    
    Expand-Archive -Path $realesrganZip -DestinationPath $serverRealesrganDir -Force
    Expand-Archive -Path $realesrganZip -DestinationPath $clientRealesrganDir -Force
    
    Write-Success "Binaires extraits"
}

# Création des raccourcis
function Create-Shortcuts {
    Write-Step "Création des raccourcis..."
    
    # Script de lancement serveur
    $serverScript = @"
@echo off
title UpscalingByNetwork - Serveur
echo Demarrage du serveur UpscalingByNetwork...
cd /d "$InstallPath\server"
python server_main.py
pause
"@
    
    $serverScript | Out-File -FilePath (Join-Path $InstallPath "Start_Server.bat") -Encoding ascii
    
    # Script de lancement client
    $clientScript = @"
@echo off
title UpscalingByNetwork - Client
echo Demarrage du client UpscalingByNetwork...
cd /d "$InstallPath\client\windows"
python client_main.py
pause
"@
    
    $clientScript | Out-File -FilePath (Join-Path $InstallPath "Start_Client.bat") -Encoding ascii
    
    Write-Success "Raccourcis créés"
}

# Test de l'installation
function Test-Installation {
    Write-Step "Test de l'installation..."
    
    Set-Location $InstallPath
    
    # Test des imports Python
    $testScript = @"
import sys
try:
    import websockets
    import PyQt5
    import cryptography
    import psutil
    print('✅ Modules Python OK')
    
    import os
    if os.path.exists('server/ffmpeg/ffmpeg.exe'):
        print('✅ FFmpeg OK')
    else:
        print('❌ FFmpeg manquant')
        sys.exit(1)
        
    if os.path.exists('server/realesrgan-ncnn-vulkan'):
        print('✅ Real-ESRGAN OK')
    else:
        print('❌ Real-ESRGAN manquant')
        sys.exit(1)
        
    print('🎉 Installation vérifiée avec succès!')
except ImportError as e:
    print(f'❌ Module manquant: {e}')
    sys.exit(1)
"@
    
    $testScript | python
    
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Tests d'installation réussis"
    } else {
        Write-Error "Échec des tests d'installation"
        exit 1
    }
}

# Affichage des informations finales
function Show-FinalInfo {
    Write-Host @"

╔══════════════════════════════════════════════╗
║           Installation terminée !            ║
╚══════════════════════════════════════════════╝

📁 Dossier d'installation: $InstallPath

🚀 Pour démarrer:
   - Serveur: Double-cliquez sur Start_Server.bat
   - Client:  Double-cliquez sur Start_Client.bat

🔧 Mode console:
   - Serveur: cd "$InstallPath\server" && python server_main.py --no-gui
   - Client:  cd "$InstallPath\client\windows" && python client_main.py --no-gui

📖 Documentation: $InstallPath\README.md

"@ -ForegroundColor Green
}

# Script principal
function Main {
    try {
        Test-Prerequisites
        Download-Source
        Install-PythonDeps
        Download-Binaries
        Extract-Binaries
        Create-Shortcuts
        Test-Installation
        Show-FinalInfo
    } catch {
        Write-Error "Erreur durant l'installation: $_"
        exit 1
    }
}

# Vérification des privilèges administrateur
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")
if ($isAdmin) {
    Write-Warning "Il est recommandé de ne pas exécuter ce script en tant qu'administrateur"
}

# Exécution
Main