#!/bin/bash
# UpscalingByNetwork/server/start_server.sh
# Script de lancement du serveur Linux

echo ""
echo "====================================="
echo "  UpscalingByNetwork - Serveur v1.0"
echo "====================================="
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

# Fonction pour pause avant fermeture en cas d'erreur
pause_on_error() {
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo -e "${RED}Une erreur est survenue - Lisez le message ci-dessus${NC}"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    read -p "Appuyez sur ENTRÉE pour fermer cette fenêtre..." -r
}

# Fonction de nettoyage à la sortie
cleanup() {
    echo ""
    log_info "Arrêt du serveur..."
    exit 0
}

# Piéger les signaux d'interruption
trap cleanup SIGINT SIGTERM

# Verification de Python
if ! command -v python3 &> /dev/null; then
    log_error "Python3 n'est pas installé"
    echo ""
    echo "Installez Python3 avec:"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-pip python3-venv"
    echo "  CentOS/RHEL:   sudo yum install python3 python3-pip"
    echo "  Fedora:        sudo dnf install python3 python3-pip"
    echo ""
    pause_on_error
    exit 1
fi

log_info "Python3 détecté"
python3 --version

# Changement vers le dossier du script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Verification de l'existence du fichier principal
if [[ ! -f "main.py" ]]; then
    log_error "Fichier main.py non trouvé"
    echo "Vérifiez que vous êtes dans le bon dossier"
    echo "Dossier actuel: $SCRIPT_DIR"
    pause_on_error
    exit 1
fi

log_info "Fichier serveur trouvé"

# Verification/création de l'environnement virtuel (optionnel mais recommandé)
if [[ ! -d "venv" ]] && command -v python3 -m venv &> /dev/null; then
    log_info "Création de l'environnement virtuel..."
    python3 -m venv venv
    if [[ $? -eq 0 ]]; then
        log_success "Environnement virtuel créé"
    else
        log_warning "Impossible de créer l'environnement virtuel"
    fi
fi

# Activation de l'environnement virtuel si présent
if [[ -d "venv" ]] && [[ -f "venv/bin/activate" ]]; then
    log_info "Activation de l'environnement virtuel"
    source venv/bin/activate
fi

# Installation des dépendances si requirements.txt existe
if [[ -f "requirements.txt" ]]; then
    log_info "Installation des dépendances..."
    python3 -m pip install -r requirements.txt
    if [[ $? -ne 0 ]]; then
        log_error "Erreur lors de l'installation des dépendances"
        echo ""
        echo "Le serveur peut ne pas fonctionner correctement"
        echo ""
        read -p "Continuer quand même? (y/N) " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            pause_on_error
            exit 1
        fi
    fi
fi

# Verification des dépendances système
log_info "Vérification des dépendances système..."

# PyQt5 (pour l'interface graphique)
if python3 -c "import PyQt5" 2>/dev/null; then
    log_success "PyQt5 trouvé"
    GUI_AVAILABLE=true
else
    log_warning "PyQt5 non trouvé"
    echo "Interface graphique non disponible"
    echo "Installez PyQt5 avec:"
    echo "  Ubuntu/Debian: sudo apt install python3-pyqt5"
    echo "  CentOS/RHEL:   sudo yum install python3-qt5"
    echo "  Fedora:        sudo dnf install python3-qt5"
    echo "  Ou avec pip:   python3 -m pip install PyQt5"
    GUI_AVAILABLE=false
fi

# Verification des outils
log_info "Vérification des outils..."

# FFmpeg
if [[ -f "ffmpeg/ffmpeg" ]]; then
    log_success "FFmpeg trouvé (local)"
elif command -v ffmpeg &> /dev/null; then
    log_success "FFmpeg trouvé (système)"
else
    log_warning "FFmpeg non trouvé"
    echo "Téléchargez FFmpeg depuis https://ffmpeg.org/"
    echo "Ou installez avec: sudo apt install ffmpeg"
fi

# Real-ESRGAN
if [[ -f "realesrgan-ncnn-vulkan/realesrgan-ncnn-vulkan" ]]; then
    log_success "Real-ESRGAN trouvé"
    
    # Vérifier les permissions d'exécution
    if [[ -x "realesrgan-ncnn-vulkan/realesrgan-ncnn-vulkan" ]]; then
        log_success "Real-ESRGAN exécutable"
    else
        log_info "Attribution des permissions d'exécution à Real-ESRGAN"
        chmod +x realesrgan-ncnn-vulkan/realesrgan-ncnn-vulkan
    fi
else
    log_warning "Real-ESRGAN non trouvé dans realesrgan-ncnn-vulkan/"
    echo "Téléchargez Real-ESRGAN depuis:"
    echo "https://github.com/xinntao/Real-ESRGAN/releases"
fi

# Verification des ports et permissions
log_info "Vérification de la configuration réseau..."

# Vérifier si le port 8888 est libre (par défaut)
if netstat -tuln 2>/dev/null | grep -q ":8888 "; then
    log_warning "Le port 8888 semble déjà utilisé"
    echo "Vous devrez peut-être utiliser un autre port avec --port XXXX"
fi

# Vérifier les permissions firewall (informatif)
if command -v ufw &> /dev/null; then
    UFW_STATUS=$(ufw status 2>/dev/null | head -1)
    if [[ "$UFW_STATUS" == *"active"* ]]; then
        log_info "UFW firewall actif - vous devrez peut-être ouvrir le port"
        echo "Commande: sudo ufw allow 8888/tcp"
    fi
fi

# Création des dossiers nécessaires
log_info "Création des dossiers de travail..."
mkdir -p server_work/{jobs,temp,encryption_keys}
mkdir -p logs
mkdir -p output

echo ""
log_info "Démarrage du serveur..."

# Déterminer les arguments de lancement
LAUNCH_ARGS="$@"

# Forcer le mode console si pas de GUI disponible
if [[ "$GUI_AVAILABLE" == false ]] && [[ "$LAUNCH_ARGS" != *"--no-gui"* ]]; then
    LAUNCH_ARGS="$LAUNCH_ARGS --no-gui"
    log_info "Mode console forcé (pas de GUI disponible)"
fi

# Arguments par défaut
if [[ -z "$LAUNCH_ARGS" ]]; then
    LAUNCH_ARGS="--host 0.0.0.0 --port 8888"
    log_info "Utilisation des paramètres par défaut: $LAUNCH_ARGS"
fi

echo "Appuyez sur Ctrl+C pour arrêter le serveur"
echo ""

# Démarrage du serveur avec gestion des erreurs
python3 main.py $LAUNCH_ARGS

EXIT_CODE=$?

echo ""
if [[ $EXIT_CODE -ne 0 ]]; then
    log_error "Le serveur s'est arrêté avec une erreur (code: $EXIT_CODE)"
    echo ""
    echo "Consultez les logs dans logs/server.log pour plus de détails"
    echo ""
    pause_on_error
else
    log_info "Serveur arrêté normalement"
    echo ""
    read -p "Appuyez sur ENTRÉE pour fermer..." -r
fi

# Désactivation de l'environnement virtuel si activé
if [[ -n "$VIRTUAL_ENV" ]]; then
    deactivate
fi

echo ""