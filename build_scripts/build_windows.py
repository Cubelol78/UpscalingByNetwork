"""
Script de build pour créer les exécutables Windows autonomes
UpscalingByNetwork/build_scripts/build_windows.py
"""

import os
import sys
import shutil
import subprocess
import zipfile
from pathlib import Path
import requests
import json

class WindowsBuilder:
    """Constructeur pour les exécutables Windows"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.build_dir = self.project_root / "build"
        self.dist_dir = self.project_root / "dist"
        self.downloads_dir = self.project_root / "downloads"
        
        # URLs de téléchargement des dépendances
        self.dependency_urls = {
            'ffmpeg': 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip',
            'realesrgan': 'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.3.0/realesrgan-ncnn-vulkan-20220424-windows.zip'
        }
        
        print("🏗️  Constructeur Windows initialisé")
        print(f"📁 Dossier projet: {self.project_root}")
    
    def clean_build(self):
        """Nettoie les dossiers de build"""
        print("🧹 Nettoyage des dossiers de build...")
        
        for directory in [self.build_dir, self.dist_dir]:
            if directory.exists():
                shutil.rmtree(directory)
                print(f"   Supprimé: {directory}")
        
        # Création des dossiers
        for directory in [self.build_dir, self.dist_dir, self.downloads_dir]:
            directory.mkdir(parents=True, exist_ok=True)
    
    def check_dependencies(self):
        """Vérifie les dépendances de build"""
        print("🔍 Vérification des dépendances de build...")
        
        # Vérification de PyInstaller
        try:
            import PyInstaller
            print(f"   ✅ PyInstaller: {PyInstaller.__version__}")
        except ImportError:
            print("   ❌ PyInstaller non trouvé")
            print("   📦 Installation: pip install pyinstaller")
            return False
        
        # Vérification des modules requis
        required_modules = [
            'websockets', 'cryptography', 'psutil', 'PyQt5', 'qasync'
        ]
        
        missing_modules = []
        for module in required_modules:
            try:
                __import__(module)
                print(f"   ✅ {module}")
            except ImportError:
                missing_modules.append(module)
                print(f"   ❌ {module}")
        
        if missing_modules:
            print(f"   📦 Modules manquants: {', '.join(missing_modules)}")
            print(f"   📦 Installation: pip install {' '.join(missing_modules)}")
            return False
        
        return True
    
    def download_dependencies(self):
        """Télécharge les dépendances externes"""
        print("📥 Téléchargement des dépendances externes...")
        
        for name, url in self.dependency_urls.items():
            zip_path = self.downloads_dir / f"{name}.zip"
            
            if zip_path.exists():
                print(f"   ⏭️  {name} déjà téléchargé")
                continue
            
            print(f"   📥 Téléchargement de {name}...")
            try:
                response = requests.get(url, stream=True)
                response.raise_for_status()
                
                with open(zip_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                print(f"   ✅ {name} téléchargé ({zip_path.stat().st_size // 1024 // 1024} MB)")
                
            except Exception as e:
                print(f"   ❌ Erreur téléchargement {name}: {e}")
                return False
        
        return True
    
    def extract_dependencies(self):
        """Extrait les dépendances téléchargées"""
        print("📦 Extraction des dépendances...")
        
        # FFmpeg
        ffmpeg_zip = self.downloads_dir / "ffmpeg.zip"
        if ffmpeg_zip.exists():
            print("   📦 Extraction de FFmpeg...")
            
            server_ffmpeg_dir = self.project_root / "server" / "ffmpeg"
            client_ffmpeg_dir = self.project_root / "client" / "windows" / "ffmpeg"
            
            with zipfile.ZipFile(ffmpeg_zip, 'r') as zf:
                # Extraction pour le serveur
                self._extract_ffmpeg(zf, server_ffmpeg_dir)
                # Extraction pour le client (optionnel)
                self._extract_ffmpeg(zf, client_ffmpeg_dir)
        
        # Real-ESRGAN
        realesrgan_zip = self.downloads_dir / "realesrgan.zip"
        if realesrgan_zip.exists():
            print("   📦 Extraction de Real-ESRGAN...")
            
            server_realesrgan_dir = self.project_root / "server" / "realesrgan-ncnn-vulkan"
            client_realesrgan_dir = self.project_root / "client" / "windows" / "realesrgan-ncnn-vulkan"
            
            with zipfile.ZipFile(realesrgan_zip, 'r') as zf:
                # Extraction pour le serveur
                self._extract_realesrgan(zf, server_realesrgan_dir)
                # Extraction pour le client
                self._extract_realesrgan(zf, client_realesrgan_dir)
        
        return True
    
    def _extract_ffmpeg(self, zip_file, target_dir):
        """Extrait FFmpeg vers un dossier cible"""
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Recherche des exécutables FFmpeg dans le ZIP
        for file_info in zip_file.filelist:
            if file_info.filename.endswith(('ffmpeg.exe', 'ffprobe.exe')):
                # Extraction avec nom simplifié
                exe_name = Path(file_info.filename).name
                target_path = target_dir / exe_name
                
                with zip_file.open(file_info) as source, open(target_path, 'wb') as target:
                    shutil.copyfileobj(source, target)
                
                print(f"     ✅ {exe_name} extrait")
    
    def _extract_realesrgan(self, zip_file, target_dir):
        """Extrait Real-ESRGAN vers un dossier cible"""
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Extraction complète du contenu
        zip_file.extractall(target_dir)
        
        # Recherche du fichier principal
        main_exe = None
        for file_path in target_dir.rglob("realesrgan-ncnn-vulkan.exe"):
            main_exe = file_path
            break
        
        if main_exe:
            print(f"     ✅ Real-ESRGAN extrait vers {target_dir}")
        else:
            print(f"     ⚠️  Exécutable Real-ESRGAN non trouvé dans {target_dir}")
    
    def build_server(self):
        """Build l'exécutable serveur"""
        print("🏗️  Build du serveur...")
        
        server_main = self.project_root / "server" / "server_main.py"
        server_output = self.dist_dir / "UpscalingByNetwork_Server"
        
        # Commande PyInstaller
        cmd = [
            'pyinstaller',
            '--onedir',  # Un dossier (pour inclure les dépendances)
            '--windowed',  # Pas de console (sauf en mode debug)
            '--noconfirm',
            '--clean',
            f'--distpath={self.dist_dir}',
            f'--workpath={self.build_dir}',
            f'--specpath={self.build_dir}',
            '--name=UpscalingByNetwork_Server',
            '--add-data=server/ffmpeg;ffmpeg/',
            '--add-data=server/realesrgan-ncnn-vulkan;realesrgan-ncnn-vulkan/',
            '--hidden-import=PyQt5.QtCore',
            '--hidden-import=PyQt5.QtWidgets',
            '--hidden-import=PyQt5.QtGui',
            '--hidden-import=qasync',
            '--hidden-import=websockets',
            '--hidden-import=cryptography',
            '--collect-all=cryptography',
            str(server_main)
        ]
        
        print(f"   🔨 Commande: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, cwd=self.project_root, capture_output=True, text=True)
            
            if result.returncode == 0:
                print("   ✅ Serveur buildé avec succès")
                return True
            else:
                print(f"   ❌ Erreur build serveur:")
                print(f"      {result.stderr}")
                return False
                
        except Exception as e:
            print(f"   ❌ Exception build serveur: {e}")
            return False
    
    def build_client(self):
        """Build l'exécutable client"""
        print("🏗️  Build du client Windows...")
        
        client_main = self.project_root / "client" / "windows" / "client_main.py"
        client_output = self.dist_dir / "UpscalingByNetwork_Client"
        
        # Commande PyInstaller
        cmd = [
            'pyinstaller',
            '--onedir',  # Un dossier
            '--windowed',  # Pas de console
            '--noconfirm',
            '--clean',
            f'--distpath={self.dist_dir}',
            f'--workpath={self.build_dir}',
            f'--specpath={self.build_dir}',
            '--name=UpscalingByNetwork_Client',
            '--add-data=client/windows/realesrgan-ncnn-vulkan;realesrgan-ncnn-vulkan/',
            '--hidden-import=PyQt5.QtCore',
            '--hidden-import=PyQt5.QtWidgets',
            '--hidden-import=PyQt5.QtGui',
            '--hidden-import=qasync',
            '--hidden-import=websockets',
            '--hidden-import=cryptography',
            '--collect-all=cryptography',
            str(client_main)
        ]
        
        print(f"   🔨 Commande: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, cwd=self.project_root, capture_output=True, text=True)
            
            if result.returncode == 0:
                print("   ✅ Client buildé avec succès")
                return True
            else:
                print(f"   ❌ Erreur build client:")
                print(f"      {result.stderr}")
                return False
                
        except Exception as e:
            print(f"   ❌ Exception build client: {e}")
            return False
    
    def create_installer_package(self):
        """Crée un package d'installation"""
        print("📦 Création du package d'installation...")
        
        package_dir = self.dist_dir / "UpscalingByNetwork_Package"
        package_dir.mkdir(exist_ok=True)
        
        # Copie des exécutables
        server_dist = self.dist_dir / "UpscalingByNetwork_Server"
        client_dist = self.dist_dir / "UpscalingByNetwork_Client"
        
        if server_dist.exists():
            shutil.copytree(server_dist, package_dir / "Server", dirs_exist_ok=True)
            print("   ✅ Serveur copié dans le package")
        
        if client_dist.exists():
            shutil.copytree(client_dist, package_dir / "Client", dirs_exist_ok=True)
            print("   ✅ Client copié dans le package")
        
        # Création des scripts de lancement
        self._create_launch_scripts(package_dir)
        
        # Création du README
        self._create_readme(package_dir)
        
        # Création du ZIP final
        zip_path = self.dist_dir / "UpscalingByNetwork_Windows.zip"
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file_path in package_dir.rglob('*'):
                if file_path.is_file():
                    arcname = file_path.relative_to(package_dir)
                    zf.write(file_path, arcname)
        
        print(f"   📦 Package créé: {zip_path}")
        print(f"   📏 Taille: {zip_path.stat().st_size // 1024 // 1024} MB")
        
        return True
    
    def _create_launch_scripts(self, package_dir):
        """Crée les scripts de lancement"""
        
        # Script serveur
        server_script = package_dir / "Start_Server.bat"
        with open(server_script, 'w') as f:
            f.write("""@echo off
title UpscalingByNetwork - Serveur
echo Demarrage du serveur UpscalingByNetwork...
cd /d "%~dp0Server"
UpscalingByNetwork_Server.exe
pause
""")
        
        # Script client
        client_script = package_dir / "Start_Client.bat"
        with open(client_script, 'w') as f:
            f.write("""@echo off
title UpscalingByNetwork - Client
echo Demarrage du client UpscalingByNetwork...
cd /d "%~dp0Client"
UpscalingByNetwork_Client.exe
pause
""")
        
        print("   ✅ Scripts de lancement créés")
    
    def _create_readme(self, package_dir):
        """Crée le fichier README"""
        readme_path = package_dir / "README.txt"
        
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write("""UpscalingByNetwork - Système d'Upscaling Distribué
====================================================

Ce package contient le serveur et le client pour le système d'upscaling distribué.

INSTALLATION:
1. Extrayez tous les fichiers dans un dossier
2. Le serveur et le client sont prêts à l'emploi (aucune installation requise)

UTILISATION:

Serveur:
- Double-cliquez sur "Start_Server.bat" pour démarrer le serveur
- L'interface graphique s'ouvrira automatiquement
- Configurez l'adresse IP et le port (par défaut: 0.0.0.0:8888)
- Cliquez sur "Démarrer le serveur"

Client:
- Double-cliquez sur "Start_Client.bat" pour démarrer le client
- L'interface graphique s'ouvrira automatiquement
- Configurez l'adresse du serveur dans l'onglet "Connexion"
- Cliquez sur "Se connecter"

CONFIGURATION RÉSEAU:
- Le serveur doit être accessible depuis les clients
- Par défaut, le port 8888 est utilisé
- Vérifiez les paramètres de pare-feu si nécessaire

MODE CONSOLE:
- Serveur console: Server/UpscalingByNetwork_Server.exe --no-gui
- Client console: Client/UpscalingByNetwork_Client.exe --no-gui --host <IP_SERVEUR>

SUPPORT:
- Documentation complète: https://github.com/votre-repo/UpscalingByNetwork
- Issues: https://github.com/votre-repo/UpscalingByNetwork/issues

Version: 1.0.0
Plateforme: Windows 10/11 64-bit
""")
        
        print("   ✅ README créé")
    
    def verify_build(self):
        """Vérifie les builds créés"""
        print("🔍 Vérification des builds...")
        
        server_exe = self.dist_dir / "UpscalingByNetwork_Server" / "UpscalingByNetwork_Server.exe"
        client_exe = self.dist_dir / "UpscalingByNetwork_Client" / "UpscalingByNetwork_Client.exe"
        
        success = True
        
        if server_exe.exists():
            size_mb = server_exe.stat().st_size // 1024 // 1024
            print(f"   ✅ Serveur: {server_exe} ({size_mb} MB)")
        else:
            print(f"   ❌ Serveur non trouvé: {server_exe}")
            success = False
        
        if client_exe.exists():
            size_mb = client_exe.stat().st_size // 1024 // 1024
            print(f"   ✅ Client: {client_exe} ({size_mb} MB)")
        else:
            print(f"   ❌ Client non trouvé: {client_exe}")
            success = False
        
        return success
    
    def build_all(self):
        """Build complet"""
        print("🚀 Début du build complet Windows")
        print("=" * 50)
        
        steps = [
            ("Nettoyage", self.clean_build),
            ("Vérification dépendances", self.check_dependencies),
            ("Téléchargement dépendances", self.download_dependencies),
            ("Extraction dépendances", self.extract_dependencies),
            ("Build serveur", self.build_server),
            ("Build client", self.build_client),
            ("Vérification builds", self.verify_build),
            ("Création package", self.create_installer_package)
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
        
        print("\n" + "=" * 50)
        print("🎉 Build Windows terminé avec succès!")
        print(f"📦 Package disponible dans: {self.dist_dir}")
        
        return True

def main():
    """Point d'entrée du script de build"""
    if len(sys.argv) > 1:
        if sys.argv[1] == "--server-only":
            builder = WindowsBuilder()
            builder.clean_build()
            builder.check_dependencies()
            builder.download_dependencies()
            builder.extract_dependencies()
            builder.build_server()
            builder.verify_build()
        elif sys.argv[1] == "--client-only":
            builder = WindowsBuilder()
            builder.clean_build()
            builder.check_dependencies()
            builder.download_dependencies()
            builder.extract_dependencies()
            builder.build_client()
            builder.verify_build()
        else:
            print("Usage: python build_windows.py [--server-only|--client-only]")
    else:
        # Build complet
        builder = WindowsBuilder()
        success = builder.build_all()
        sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()