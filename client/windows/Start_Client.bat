@echo off
REM UpscalingByNetwork/client/windows/Start_Client.bat
REM Script de lancement du client Windows

title UpscalingByNetwork - Client Distribue

echo.
echo ====================================
echo   UpscalingByNetwork - Client v1.0
echo ====================================
echo.

REM Verification de Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python n'est pas installe ou pas dans le PATH
    echo.
    echo Veuillez installer Python 3.8+ depuis https://python.org
    echo.
    pause
    exit /b 1
)

echo [INFO] Python detecte
python --version

REM Changement vers le dossier du script
cd /d "%~dp0"

REM Verification de l'existence du fichier principal
if not exist "client_main.py" (
    echo [ERREUR] Fichier client_main.py non trouve
    echo Verifiez que vous etes dans le bon dossier
    pause
    exit /b 1
)

echo [INFO] Fichier client trouve

REM Installation des dependances si requirements.txt existe
if exist "requirements.txt" (
    echo [INFO] Installation des dependances...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ATTENTION] Erreur installation dependances
        echo Le client peut ne pas fonctionner correctement
        pause
    )
)

REM Verification de Real-ESRGAN
echo [INFO] Verification de Real-ESRGAN...
if exist "realesrgan-ncnn-vulkan\realesrgan-ncnn-vulkan.exe" (
    echo [OK] Real-ESRGAN trouve
) else (
    echo [ERREUR] Real-ESRGAN non trouve dans realesrgan-ncnn-vulkan\
    echo.
    echo Telechargez Real-ESRGAN depuis:
    echo https://github.com/xinntao/Real-ESRGAN/releases
    echo.
    echo Extrayez le contenu dans le dossier realesrgan-ncnn-vulkan\
    echo.
    pause
    exit /b 1
)

REM Test Vulkan
echo [INFO] Test de compatibilite Vulkan...
realesrgan-ncnn-vulkan\realesrgan-ncnn-vulkan.exe >nul 2>&1
if errorlevel 1 (
    echo [ATTENTION] Probleme potentiel avec Vulkan
    echo Assurez-vous que vos pilotes GPU sont a jour
    pause
)

echo.
echo [INFO] Demarrage du client...
echo Appuyez sur Ctrl+C pour arreter le client
echo.

REM Arguments par defaut si non fournis
set ARGS=%*
if "%ARGS%"=="" (
    set ARGS=--host localhost --port 8888
    echo [INFO] Utilisation des parametres par defaut: %ARGS%
)

REM Demarrage du client avec gestion des erreurs
python client_main.py %ARGS%

if errorlevel 1 (
    echo.
    echo [ERREUR] Le client s'est arrete avec une erreur
    echo Consultez les logs dans client_work\logs\
) else (
    echo.
    echo [INFO] Client arrete normalement
)

echo.
pause

---

#!/bin/bash
# UpscalingByNetwork/client/linux/start_client.sh
# Script de lancement du client Linux

echo ""
echo "===================================="
echo "  UpscalingByNetwork - Client v1.0"
echo "===================================="
echo ""

# Couleurs pour l'affichage
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Fonction d'affichage avec couleurs
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[ATTENTION]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERREUR]${NC} $1"
}

# Verification de Python
if ! command -v python3 &> /dev/null; then
    log_error "Python3 n'est pas installé"
    echo ""
    echo "Installez Python3 avec:"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-pip"
    echo "  CentOS/RHEL:   sudo yum install python3 python3-pip"
    echo "  Fedora:        sudo dnf install python3 python3-pip"
    echo ""
    exit 1
fi

log_info "Python3 détecté"
python3 --version

# Changement vers le dossier du script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Verification de l'existence du fichier principal
if [[ ! -f "client_main.py" ]]; then
    log_error "Fichier client_main.py non trouvé"
    echo "Vérifiez que vous êtes dans le bon dossier"
    exit 1
fi

log_info "Fichier client trouvé"

# Installation des dépendances si requirements.txt existe
if [[ -f "requirements.txt" ]]; then
    log_info "Installation des dépendances..."
    python3 -m pip install -r requirements.txt --user
    if [[ $? -ne 0 ]]; then
        log_warning "Erreur installation dépendances"
        echo "Le client peut ne pas fonctionner correctement"
        read -p "Continuer quand même? (y/N) " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
fi

# Verification des dépendances système
log_info "Vérification des dépendances système..."

# PyQt5
if python3 -c "import PyQt5" 2>/dev/null; then
    log_success "PyQt5 trouvé"
else
    log_error "PyQt5 non trouvé"
    echo ""
    echo "Installez PyQt5 avec:"
    echo "  Ubuntu/Debian: sudo apt install python3-pyqt5"
    echo "  CentOS/RHEL:   sudo yum install python3-qt5"
    echo "  Fedora:        sudo dnf install python3-qt5"
    echo "  Ou avec pip:   python3 -m pip install PyQt5 --user"
    echo ""
    exit 1
fi

# Verification de Real-ESRGAN
log_info "Vérification de Real-ESRGAN..."
if [[ -f "realesrgan-ncnn-vulkan/realesrgan-ncnn-vulkan" ]]; then
    log_success "Real-ESRGAN trouvé"
    
    # Test d'exécution
    if ./realesrgan-ncnn-vulkan/realesrgan-ncnn-vulkan >/dev/null 2>&1; then
        log_success "Real-ESRGAN exécutable"
    else
        log_warning "Problème d'exécution de Real-ESRGAN"
        echo "Vérifiez les permissions et les dépendances Vulkan"
    fi
else
    log_error "Real-ESRGAN non trouvé dans realesrgan-ncnn-vulkan/"
    echo ""
    echo "Téléchargez Real-ESRGAN depuis:"
    echo "https://github.com/xinntao/Real-ESRGAN/releases"
    echo ""
    echo "Extrayez le contenu dans le dossier realesrgan-ncnn-vulkan/"
    echo "Et rendez l'exécutable exécutable:"
    echo "chmod +x realesrgan-ncnn-vulkan/realesrgan-ncnn-vulkan"
    echo ""
    exit 1
fi

# Verification Vulkan (optionnel)
if command -v vulkaninfo &> /dev/null; then
    if vulkaninfo >/dev/null 2>&1; then
        log_success "Vulkan supporté"
    else
        log_warning "Problème avec Vulkan"
        echo "Le traitement sera peut-être plus lent"
    fi
else
    log_info "vulkaninfo non trouvé (optionnel)"
    echo "Installez vulkan-tools pour plus d'informations sur le support GPU"
fi

echo ""
log_info "Démarrage du client..."
echo "Appuyez sur Ctrl+C pour arrêter le client"
echo ""

# Arguments par défaut si non fournis
if [[ $# -eq 0 ]]; then
    ARGS="--host localhost --port 8888"
    log_info "Utilisation des paramètres par défaut: $ARGS"
else
    ARGS="$@"
fi

# Création du dossier de travail si nécessaire
mkdir -p client_work/logs

# Démarrage du client avec gestion des erreurs
python3 client_main.py $ARGS

EXIT_CODE=$?

if [[ $EXIT_CODE -ne 0 ]]; then
    echo ""
    log_error "Le client s'est arrêté avec une erreur (code: $EXIT_CODE)"
    echo "Consultez les logs dans client_work/logs/"
else
    echo ""
    log_info "Client arrêté normalement"
fi

echo ""
read -p "Appuyez sur Entrée pour continuer..."