# UpscalingByNetwork/build_scripts/build_linux.py

"""
Script de build pour la version Linux du client
UpscalingByNetwork/build_scripts/build_linux.py
"""

import os
import sys
import shutil
import subprocess
import tarfile
from pathlib import Path
import requests
import stat

class LinuxBuilder:
    """Constructeur pour le client Linux"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.build_dir = self.project_root / "build_linux"
        self.dist_dir = self.project_root / "dist_linux"
        self.downloads_dir = self.project_root / "downloads_linux"
        
        # URL Real-ESRGAN pour Linux
        self.realesrgan_url = 'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.3.0/realesrgan-ncnn-vulkan-20220424-ubuntu.zip'
        
        print("🐧 Constructeur Linux initialisé")
        print(f"📁 Dossier projet: {self.project_root}")
    
    def clean_build(self):
        """Nettoie les dossiers de build"""
        print("🧹 Nettoyage des dossiers de build...")
        
        for directory in [self.build_dir, self.dist_dir]:
            if directory.exists():
                shutil.rmtree(directory)
                print(f"   Supprimé: {directory}")
        
        for directory in [self.build_dir, self.dist_dir, self.downloads_dir]:
            directory.mkdir(parents=True, exist_ok=True)
    
    def create_linux_client(self):
        """Crée la version Linux du client"""
        print("🐧 Création du client Linux...")
        
        # Structure du client Linux
        linux_client_dir = self.project_root / "client" / "linux"
        linux_client_dir.mkdir(parents=True, exist_ok=True)
        
        # Copie de la structure Windows et adaptation
        windows_client_dir = self.project_root / "client" / "windows"
        
        # Copie des modules core et utils
        for module_dir in ['core', 'utils']:
            src_dir = windows_client_dir / module_dir
            dst_dir = linux_client_dir / module_dir
            
            if src_dir.exists():
                shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)
                print(f"   ✅ Module {module_dir} copié")
        
        # Création de l'interface GUI adaptée pour Linux
        self._create_linux_gui(linux_client_dir)
        
        # Création du point d'entrée Linux
        self._create_linux_main(linux_client_dir)
        
        # Script de lancement
        self._create_linux_launcher(linux_client_dir)
        
        return True
    
    def _create_linux_gui(self, client_dir):
        """Crée l'interface GUI adaptée pour Linux"""
        gui_dir = client_dir / "gui"
        gui_dir.mkdir(exist_ok=True)
        
        # Copie des fichiers GUI Windows et adaptation
        windows_gui = self.project_root / "client" / "windows" / "gui"
        
        if windows_gui.exists():
            for gui_file in windows_gui.glob("*.py"):
                shutil.copy2(gui_file, gui_dir)
        
        # Adaptation spécifique Linux (modifications mineures)
        client_window = gui_dir / "client_window.py"
        if client_window.exists():
            # Lecture et modification pour Linux
            content = client_window.read_text()
            
            # Adaptations spécifiques Linux
            content = content.replace(
                'self.setWindowIcon(icon)',
                'self.setWindowIcon(icon)\n        # Optimisations Linux\n        self.setAttribute(Qt.WA_DeleteOnClose)'
            )
            
            client_window.write_text(content)
        
        print("   ✅ Interface GUI Linux créée")
    
    def _create_linux_main(self, client_dir):
        """Crée le point d'entrée Linux"""
        main_file = client_dir / "client_main.py"
        
        # Copie et adaptation du main Windows
        windows_main = self.project_root / "client" / "windows" / "client_main.py"
        
        if windows_main.exists():
            content = windows_main.read_text()
            
            # Adaptations pour Linux
            content = content.replace(
                'UpscalingByNetwork Client Windows',
                'UpscalingByNetwork Client Linux'
            )
            
            content = content.replace(
                '"realesrgan-ncnn-vulkan.exe"',
                '"realesrgan-ncnn-vulkan"'
            )
            
            main_file.write_text(content)
            print("   ✅ Point d'entrée Linux créé")
    
    def _create_linux_launcher(self, client_dir):
        """Crée le script de lancement Linux"""
        launcher_script = client_dir / "start_client.sh"
        
        script_content = """#!/bin/bash

# UpscalingByNetwork Client Linux Launcher

echo "🐧 UpscalingByNetwork Client Linux"
echo "=================================="

# Détection de l'environnement
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "❌ Python non trouvé. Veuillez installer Python 3.8+"
    exit 1
fi

echo "🐍 Python détecté: $PYTHON_CMD"

# Vérification des dépendances
echo "🔍 Vérification des dépendances..."

# Fonction pour vérifier un module Python
check_module() {
    if $PYTHON_CMD -c "import $1" &> /dev/null; then
        echo "   ✅ $1"
        return 0
    else
        echo "   ❌ $1"
        return 1
    fi
}

# Modules requis
MISSING_MODULES=()

if ! check_module "PyQt5"; then
    MISSING_MODULES+=("python3-pyqt5")
fi

if ! check_module "websockets"; then
    MISSING_MODULES+=("websockets")
fi

if ! check_module "cryptography"; then
    MISSING_MODULES+=("cryptography")
fi

if ! check_module "psutil"; then
    MISSING_MODULES+=("psutil")
fi

if ! check_module "qasync"; then
    MISSING_MODULES+=("qasync")
fi

# Installation des modules manquants
if [ ${#MISSING_MODULES[@]} -gt 0 ]; then
    echo "📦 Modules manquants détectés"
    echo "Tentative d'installation automatique..."
    
    for module in "${MISSING_MODULES[@]}"; do
        echo "   📦 Installation de $module..."
        if [[ $module == "python3-pyqt5" ]]; then
            # PyQt5 nécessite installation système
            if command -v apt &> /dev/null; then
                sudo apt update && sudo apt install -y python3-pyqt5 python3-pyqt5.qtwidgets
            elif command -v dnf &> /dev/null; then
                sudo dnf install -y python3-qt5
            elif command -v pacman &> /dev/null; then
                sudo pacman -S python-pyqt5
            else
                echo "   ⚠️  Gestionnaire de paquets non reconnu"
                echo "   📝 Installez manuellement: PyQt5"
            fi
        else
            # Modules pip
            $PYTHON_CMD -m pip install --user $module
        fi
    done
fi

# Vérification de Real-ESRGAN
echo "🔍 Vérification de Real-ESRGAN..."
if [ -f "./realesrgan-ncnn-vulkan/realesrgan-ncnn-vulkan" ]; then
    echo "   ✅ Real-ESRGAN trouvé"
    # Rendre exécutable
    chmod +x ./realesrgan-ncnn-vulkan/realesrgan-ncnn-vulkan
else
    echo "   ❌ Real-ESRGAN non trouvé"
    echo "   📝 Téléchargez Real-ESRGAN pour Linux depuis:"
    echo "   🔗 https://github.com/xinntao/Real-ESRGAN/releases"
    echo "   📁 Extrayez dans: ./realesrgan-ncnn-vulkan/"
fi

# Démarrage du client
echo "🚀 Démarrage du client..."
cd "$(dirname "$0")"
$PYTHON_CMD client_main.py "$@"
"""
        
        launcher_script.write_text(script_content)
        
        # Rendre exécutable
        launcher_script.chmod(launcher_script.stat().st_mode | stat.S_IEXEC)
        
        print("   ✅ Script de lancement Linux créé")
    
    def download_realesrgan_linux(self):
        """Télécharge Real-ESRGAN pour Linux"""
        print("📥 Téléchargement de Real-ESRGAN Linux...")
        
        zip_path = self.downloads_dir / "realesrgan_linux.zip"
        
        if zip_path.exists():
            print("   ⏭️  Real-ESRGAN déjà téléchargé")
            return True
        
        try:
            response = requests.get(self.realesrgan_url, stream=True)
            response.raise_for_status()
            
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"   ✅ Real-ESRGAN téléchargé ({zip_path.stat().st_size // 1024 // 1024} MB)")
            return True
            
        except Exception as e:
            print(f"   ❌ Erreur téléchargement: {e}")
            return False
    
    def extract_realesrgan_linux(self):
        """Extrait Real-ESRGAN pour Linux"""
        print("📦 Extraction de Real-ESRGAN Linux...")
        
        zip_path = self.downloads_dir / "realesrgan_linux.zip"
        client_dir = self.project_root / "client" / "linux"
        target_dir = client_dir / "realesrgan-ncnn-vulkan"
        
        if not zip_path.exists():
            print("   ❌ Archive Real-ESRGAN non trouvée")
            return False
        
        try:
            import zipfile
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(target_dir)
            
            # Recherche de l'exécutable et rendu exécutable
            for exe_file in target_dir.rglob("realesrgan-ncnn-vulkan"):
                if exe_file.is_file():
                    exe_file.chmod(exe_file.stat().st_mode | stat.S_IEXEC)
                    print(f"     ✅ {exe_file} rendu exécutable")
            
            print("   ✅ Real-ESRGAN Linux extrait")
            return True
            
        except Exception as e:
            print(f"   ❌ Erreur extraction: {e}")
            return False
    
    def create_linux_package(self):
        """Crée le package Linux"""
        print("📦 Création du package Linux...")
        
        client_dir = self.project_root / "client" / "linux"
        package_dir = self.dist_dir / "UpscalingByNetwork_Linux"
        
        # Copie du client
        shutil.copytree(client_dir, package_dir, dirs_exist_ok=True)
        
        # Création du README Linux
        readme_path = package_dir / "README.txt"
        readme_content = """UpscalingByNetwork Client Linux
===============================

PRÉREQUIS:
- Python 3.8 ou supérieur
- PyQt5 (python3-pyqt5)
- Modules Python: websockets, cryptography, psutil, qasync

INSTALLATION RAPIDE (Ubuntu/Debian):
sudo apt update
sudo apt install python3 python3-pip python3-pyqt5
pip3 install --user websockets cryptography psutil qasync

UTILISATION:
1. Rendez le script exécutable:
   chmod +x start_client.sh

2. Lancez le client:
   ./start_client.sh

3. Ou directement avec Python:
   python3 client_main.py

MODE CONSOLE:
./start_client.sh --no-gui --host <IP_SERVEUR>

DÉPANNAGE:
- Vérifiez que Real-ESRGAN est présent dans ./realesrgan-ncnn-vulkan/
- Installez les dépendances manquantes avec pip3
- Vérifiez les permissions du script de lancement

Version: 1.0.0
Plateforme: Linux x64
"""
        
        readme_path.write_text(readme_content)
        
        # Création de l'archive
        tar_path = self.dist_dir / "UpscalingByNetwork_Linux.tar.gz"
        
        with tarfile.open(tar_path, 'w:gz') as tar:
            tar.add(package_dir, arcname="UpscalingByNetwork_Linux")
        
        print(f"   📦 Package Linux créé: {tar_path}")
        print(f"   📏 Taille: {tar_path.stat().st_size // 1024 // 1024} MB")
        
        return True
    
    def build_linux_client(self):
        """Build complet du client Linux"""
        print("🐧 Build du client Linux")
        print("=" * 40)
        
        steps = [
            ("Nettoyage", self.clean_build),
            ("Création client Linux", self.create_linux_client),
            ("Téléchargement Real-ESRGAN", self.download_realesrgan_linux),
            ("Extraction Real-ESRGAN", self.extract_realesrgan_linux),
            ("Création package", self.create_linux_package)
        ]
        
        for step_name, step_func in steps:
            print(f"\n📋 Étape: {step_name}")
            try:
                success = step_func()
                if not success:
                    print(f"❌ Échec à l'étape: {step_name}")
                    return False
            except Exception as e:
                print(f"❌ Exception à l'étape {step_name}: {e}")
                return False
        
        print("\n" + "=" * 40)
        print("🎉 Build Linux terminé avec succès!")
        print(f"📦 Package disponible dans: {self.dist_dir}")
        
        return True

def main():
    """Point d'entrée du script de build Linux"""
    builder = LinuxBuilder()
    success = builder.build_linux_client()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()