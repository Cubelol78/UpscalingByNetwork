# UpscalingByNetwork/scripts/install.sh

#!/bin/bash

# Script d'installation automatique pour UpscalingByNetwork
# UpscalingByNetwork/scripts/install.sh

set -e  # Arrêt en cas d'erreur

# Couleurs pour l'affichage
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
REPO_URL="https://github.com/votre-repo/UpscalingByNetwork"
INSTALL_DIR="$HOME/UpscalingByNetwork"
PYTHON_MIN_VERSION="3.8"

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════╗"
echo "║        UpscalingByNetwork Installer          ║"
echo "║             Version 1.0.0                    ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${NC}"

# Fonction d'affichage
print_step() {
    echo -e "${BLUE}[ÉTAPE]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[ATTENTION]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERREUR]${NC} $1"
}

# Détection de l'OS
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if [ -f /etc/os-release ]; then
            . /etc/os-release
            OS=$NAME
            DISTRO=$ID
        else
            OS="Linux"
            DISTRO="unknown"
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macOS"
        DISTRO="macos"
    else
        print_error "Système d'exploitation non supporté: $OSTYPE"
        exit 1
    fi
    
    print_success "OS détecté: $OS"
}

# Vérification de Python
check_python() {
    print_step "Vérification de Python..."
    
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        print_error "Python non trouvé. Veuillez installer Python $PYTHON_MIN_VERSION ou supérieur."
        exit 1
    fi
    
    # Vérification de la version
    PYTHON_VERSION=$($PYTHON_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    
    if ! $PYTHON_CMD -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)"; then
        print_error "Python $PYTHON_VERSION détecté. Version $PYTHON_MIN_VERSION ou supérieure requise."
        exit 1
    fi
    
    print_success "Python $PYTHON_VERSION détecté"
}

# Installation des dépendances système
install_system_deps() {
    print_step "Installation des dépendances système..."
    
    case $DISTRO in
        ubuntu|debian)
            sudo apt update
            sudo apt install -y \
                python3-pip \
                python3-venv \
                python3-pyqt5 \
                git \
                wget \
                unzip \
                build-essential \
                libgl1-mesa-glx \
                libxrender1 \
                libfontconfig1 \
                libxss1
            ;;
        fedora|centos|rhel)
            sudo dnf install -y \
                python3-pip \
                python3-virtualenv \
                python3-qt5 \
                git \
                wget \
                unzip \
                gcc \
                gcc-c++ \
                mesa-libGL \
                libXrender \
                fontconfig \
                libXScrnSaver
            ;;
        arch|manjaro)
            sudo pacman -S --noconfirm \
                python-pip \
                python-virtualenv \
                python-pyqt5 \
                git \
                wget \
                unzip \
                base-devel \
                mesa \
                libxrender \
                fontconfig \
                libxss
            ;;
        macos)
            if ! command -v brew &> /dev/null; then
                print_error "Homebrew requis sur macOS. Installez-le depuis https://brew.sh"
                exit 1
            fi
            
            brew install python3 pyqt5 git wget
            ;;
        *)
            print_warning "Distribution non reconnue. Installation manuelle des dépendances requise."
            ;;
    esac
    
    print_success "Dépendances système installées"
}

# Téléchargement du code source
download_source() {
    print_step "Téléchargement du code source..."
    
    if [ -d "$INSTALL_DIR" ]; then
        print_warning "Le dossier $INSTALL_DIR existe déjà"
        read -p "Voulez-vous le supprimer et réinstaller ? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$INSTALL_DIR"
        else
            print_error "Installation annulée"
            exit 1
        fi
    fi
    
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    
    print_success "Code source téléchargé dans $INSTALL_DIR"
}

# Création de l'environnement virtuel
create_venv() {
    print_step "Création de l'environnement virtuel Python..."
    
    $PYTHON_CMD -m venv venv
    source venv/bin/activate
    
    # Mise à jour de pip
    pip install --upgrade pip
    
    print_success "Environnement virtuel créé"
}

# Installation des dépendances Python
install_python_deps() {
    print_step "Installation des dépendances Python..."
    
    source venv/bin/activate
    pip install -r requirements.txt
    
    print_success "Dépendances Python installées"
}

# Téléchargement des binaires
download_binaries() {
    print_step "Téléchargement des binaires..."
    
    mkdir -p downloads
    cd downloads
    
    # Real-ESRGAN pour Linux
    if [[ "$OS" == "Linux" ]]; then
        print_step "Téléchargement de Real-ESRGAN pour Linux..."
        wget -q "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.3.0/realesrgan-ncnn-vulkan-20220424-ubuntu.zip"
        unzip -q realesrgan-ncnn-vulkan-20220424-ubuntu.zip
        
        # Installation dans client/linux
        mkdir -p ../client/linux/realesrgan-ncnn-vulkan
        cp realesrgan-ncnn-vulkan ../client/linux/realesrgan-ncnn-vulkan/
        chmod +x ../client/linux/realesrgan-ncnn-vulkan/realesrgan-ncnn-vulkan
        
        print_success "Real-ESRGAN installé"
    fi
    
    cd ..
}

# Création des scripts de lancement
create_launchers() {
    print_step "Création des scripts de lancement..."
    
    # Script client Linux
    cat > start_client.sh << 'EOF'
#!/bin/bash

cd "$(dirname "$0")"

echo "🐧 UpscalingByNetwork Client Linux"
echo "=================================="

# Activation de l'environnement virtuel
source venv/bin/activate

# Démarrage du client
cd client/linux
python client_main.py "$@"
EOF
    
    chmod +x start_client.sh
    
    # Script serveur (mode console)
    cat > start_server_console.sh << 'EOF'
#!/bin/bash

cd "$(dirname "$0")"

echo "🖥️  UpscalingByNetwork Serveur Console"
echo "====================================="

# Activation de l'environnement virtuel
source venv/bin/activate

# Démarrage du serveur en mode console
cd server
python server_main.py --no-gui --host 0.0.0.0 --port 8888 "$@"
EOF
    
    chmod +x start_server_console.sh
    
    print_success "Scripts de lancement créés"
}

# Création du fichier de désinstallation
create_uninstaller() {
    cat > uninstall.sh << EOF
#!/bin/bash

echo "Désinstallation d'UpscalingByNetwork..."

# Suppression du dossier d'installation
read -p "Supprimer le dossier $INSTALL_DIR ? (y/N): " -n 1 -r
echo
if [[ \$REPLY =~ ^[Yy]$ ]]; then
    rm -rf "$INSTALL_DIR"
    echo "Dossier supprimé"
fi

# Suppression des liens symboliques (si créés)
if [ -L "/usr/local/bin/upscaling-client" ]; then
    sudo rm /usr/local/bin/upscaling-client
    echo "Lien upscaling-client supprimé"
fi

if [ -L "/usr/local/bin/upscaling-server" ]; then
    sudo rm /usr/local/bin/upscaling-server
    echo "Lien upscaling-server supprimé"
fi

echo "Désinstallation terminée"
EOF
    
    chmod +x uninstall.sh
}

# Test de l'installation
test_installation() {
    print_step "Test de l'installation..."
    
    source venv/bin/activate
    
    # Test d'import des modules principaux
    $PYTHON_CMD -c "
import sys
import websockets
import cryptography
import psutil
print('✅ Modules Python OK')

# Test Real-ESRGAN
import os
if os.path.exists('client/linux/realesrgan-ncnn-vulkan/realesrgan-ncnn-vulkan'):
    print('✅ Real-ESRGAN OK')
else:
    print('❌ Real-ESRGAN manquant')
    sys.exit(1)
    
print('🎉 Installation vérifiée avec succès!')
"
    
    print_success "Tests d'installation réussis"
}

# Affichage des informations finales
show_final_info() {
    echo
    echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║           Installation terminée !            ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
    echo
    echo -e "${BLUE}📁 Dossier d'installation:${NC} $INSTALL_DIR"
    echo
    echo -e "${BLUE}🚀 Pour démarrer le client:${NC}"
    echo "   cd $INSTALL_DIR"
    echo "   ./start_client.sh"
    echo
    echo -e "${BLUE}🖥️  Pour démarrer le serveur (mode console):${NC}"
    echo "   cd $INSTALL_DIR"
    echo "   ./start_server_console.sh"
    echo
    echo -e "${BLUE}📖 Documentation:${NC} $INSTALL_DIR/README.md"
    echo -e "${BLUE}🗑️  Désinstallation:${NC} $INSTALL_DIR/uninstall.sh"
    echo
    print_warning "Pour le serveur avec interface graphique, utilisez la version Windows."
}

# Script principal
main() {
    detect_os
    check_python
    
    if [[ "$DISTRO" != "macos" ]]; then
        print_step "Installation des dépendances système (sudo requis)..."
        install_system_deps
    fi
    
    download_source
    create_venv
    install_python_deps
    download_binaries
    create_launchers
    create_uninstaller
    test_installation
    show_final_info
}

# Point d'entrée
if [ "$EUID" -eq 0 ]; then
    print_error "Ne pas exécuter ce script en tant que root"
    exit 1
fi

main "$@"