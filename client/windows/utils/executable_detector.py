# client/windows/utils/executable_detector.py
"""
Détecteur d'exécutables pour le client Windows d'upscaling distribué
Recherche FFmpeg et Real-ESRGAN dans les dossiers locaux du projet
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import Optional, Dict, List
import logging

class ClientExecutableDetector:
    """Détecteur d'exécutables pour le client Windows"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Dossier racine du projet et du client
        self.project_root = self._find_project_root()
        self.client_root = self.project_root / "client" / "windows"
        
        # Cache des chemins détectés
        self._realesrgan_path = None
        self._ffmpeg_path = None
        self._ffprobe_path = None
        
        self.logger.info(f"Détecteur client initialisé - Racine: {self.client_root}")
    
    def _find_project_root(self) -> Path:
        """Trouve la racine du projet UpscalingByNetwork"""
        current = Path(__file__).parent
        
        # Remonte jusqu'à trouver le dossier UpscalingByNetwork
        while current.parent != current:
            if current.name == "UpscalingByNetwork":
                return current
            if "UpscalingByNetwork" in current.parts:
                # Trouve l'index de UpscalingByNetwork dans le chemin
                parts = current.parts
                try:
                    idx = parts.index("UpscalingByNetwork")
                    return Path(*parts[:idx+1])
                except ValueError:
                    pass
            current = current.parent
        
        # Si pas trouvé, utilise une approche alternative
        client_file = Path(__file__)
        if "client" in client_file.parts and "windows" in client_file.parts:
            # Remonte jusqu'au niveau UpscalingByNetwork
            parts = client_file.parts
            try:
                idx = parts.index("windows")
                return Path(*parts[:idx-1])  # client/windows -> UpscalingByNetwork
            except ValueError:
                pass
        
        # Fallback
        return Path.cwd()
    
    def find_realesrgan(self) -> Optional[str]:
        """Trouve l'exécutable Real-ESRGAN pour le client"""
        if self._realesrgan_path:
            return self._realesrgan_path
        
        executable_name = "realesrgan-ncnn-vulkan.exe"
        
        # Chemins de recherche spécifiques au client Windows
        search_paths = [
            # Structure client Windows
            self.client_root / "realesrgan-ncnn-vulkan" / executable_name,
            self.client_root / "realesrgan-ncnn-vulkan" / "Windows" / executable_name,
            self.client_root / "dependencies" / executable_name,
            
            # Structure racine projet (fallback)
            self.project_root / "client" / "windows" / "realesrgan-ncnn-vulkan" / executable_name,
            
            # Dossier courant
            Path.cwd() / "realesrgan-ncnn-vulkan" / executable_name,
            Path.cwd() / executable_name,
        ]
        
        self.logger.info(f"🔍 Recherche Real-ESRGAN client ({executable_name})...")
        
        for path in search_paths:
            self.logger.debug(f"  Vérification: {path}")
            if path.exists() and path.is_file():
                self._realesrgan_path = str(path)
                self.logger.info(f"✅ Real-ESRGAN trouvé: {path}")
                return self._realesrgan_path
        
        # Recherche dans le PATH système
        system_path = self._find_in_system_path(executable_name)
        if system_path:
            self._realesrgan_path = system_path
            self.logger.info(f"✅ Real-ESRGAN trouvé dans PATH: {system_path}")
            return self._realesrgan_path
        
        self.logger.warning(f"❌ Real-ESRGAN non trouvé pour le client")
        self.logger.warning("📥 Téléchargez depuis: https://github.com/xinntao/Real-ESRGAN/releases")
        self.logger.warning(f"📁 Placez dans: {self.client_root / 'realesrgan-ncnn-vulkan'}")
        
        return None
    
    def find_ffmpeg(self) -> Optional[str]:
        """Trouve l'exécutable FFmpeg pour le client"""
        if self._ffmpeg_path:
            return self._ffmpeg_path
        
        executable_name = "ffmpeg.exe"
        
        # Chemins de recherche spécifiques au client Windows
        search_paths = [
            # Structure client Windows
            self.client_root / "ffmpeg" / executable_name,
            self.client_root / "ffmpeg" / "bin" / executable_name,
            self.client_root / "dependencies" / executable_name,
            
            # Structure racine projet
            self.project_root / "client" / "windows" / "ffmpeg" / executable_name,
            self.project_root / "client" / "windows" / "ffmpeg" / "bin" / executable_name,
            
            # Dossier courant
            Path.cwd() / "ffmpeg" / executable_name,
            Path.cwd() / executable_name,
        ]
        
        self.logger.info(f"🔍 Recherche FFmpeg client ({executable_name})...")
        
        for path in search_paths:
            self.logger.debug(f"  Vérification: {path}")
            if path.exists() and path.is_file():
                self._ffmpeg_path = str(path)
                self.logger.info(f"✅ FFmpeg trouvé: {path}")
                return self._ffmpeg_path
        
        # Recherche dans le PATH système
        system_path = self._find_in_system_path(executable_name)
        if system_path:
            self._ffmpeg_path = system_path
            self.logger.info(f"✅ FFmpeg trouvé dans PATH: {system_path}")
            return self._ffmpeg_path
        
        self.logger.warning(f"❌ FFmpeg non trouvé pour le client")
        self.logger.warning("📥 Téléchargez depuis: https://ffmpeg.org/download.html")
        self.logger.warning(f"📁 Placez dans: {self.client_root / 'ffmpeg'}")
        
        return None
    
    def find_ffprobe(self) -> Optional[str]:
        """Trouve l'exécutable FFprobe pour le client"""
        if self._ffprobe_path:
            return self._ffprobe_path
        
        executable_name = "ffprobe.exe"
        
        # Cherche dans le même dossier que FFmpeg
        ffmpeg_path = self.find_ffmpeg()
        if ffmpeg_path:
            ffmpeg_dir = Path(ffmpeg_path).parent
            ffprobe_path = ffmpeg_dir / executable_name
            if ffprobe_path.exists():
                self._ffprobe_path = str(ffprobe_path)
                self.logger.info(f"✅ FFprobe trouvé: {ffprobe_path}")
                return self._ffprobe_path
        
        # Recherche indépendante
        search_paths = [
            self.client_root / "ffmpeg" / executable_name,
            self.client_root / "ffmpeg" / "bin" / executable_name,
            self.project_root / "client" / "windows" / "ffmpeg" / executable_name,
        ]
        
        for path in search_paths:
            if path.exists() and path.is_file():
                self._ffprobe_path = str(path)
                self.logger.info(f"✅ FFprobe trouvé: {path}")
                return self._ffprobe_path
        
        # Recherche dans le PATH système
        system_path = self._find_in_system_path(executable_name)
        if system_path:
            self._ffprobe_path = system_path
            self.logger.info(f"✅ FFprobe trouvé dans PATH: {system_path}")
            return self._ffprobe_path
        
        self.logger.warning(f"❌ FFprobe non trouvé pour le client")
        return None
    
    def _find_in_system_path(self, executable_name: str) -> Optional[str]:
        """Recherche un exécutable dans le PATH système"""
        try:
            import shutil
            return shutil.which(executable_name)
        except:
            return None
    
    def test_executable(self, executable_path: str, test_args: List[str] = None) -> bool:
        """Teste si un exécutable fonctionne"""
        if not executable_path or not Path(executable_path).exists():
            return False
        
        try:
            test_args = test_args or ["-version"]
            result = subprocess.run(
                [executable_path] + test_args,
                capture_output=True,
                timeout=10,
                text=True
            )
            return result.returncode == 0
        except Exception as e:
            self.logger.debug(f"Test exécutable échoué pour {executable_path}: {e}")
            return False
    
    def get_executable_info(self, executable_path: str) -> Dict[str, str]:
        """Récupère les informations d'un exécutable"""
        info = {
            'path': executable_path,
            'exists': False,
            'version': 'Inconnue',
            'working': False
        }
        
        if not executable_path:
            return info
        
        path_obj = Path(executable_path)
        info['exists'] = path_obj.exists()
        
        if info['exists']:
            try:
                result = subprocess.run(
                    [executable_path, "-version"],
                    capture_output=True,
                    timeout=10,
                    text=True
                )
                
                if result.returncode == 0:
                    info['working'] = True
                    # Extraction de la version depuis la sortie
                    output = result.stdout + result.stderr
                    lines = output.split('\n')
                    if lines:
                        info['version'] = lines[0].strip()
                        
            except Exception as e:
                self.logger.debug(f"Erreur récupération info {executable_path}: {e}")
        
        return info
    
    def get_all_executables_status(self) -> Dict[str, Dict]:
        """Retourne le statut de tous les exécutables pour le client"""
        status = {
            'realesrgan': self.get_executable_info(self.find_realesrgan()),
            'ffmpeg': self.get_executable_info(self.find_ffmpeg()),
            'ffprobe': self.get_executable_info(self.find_ffprobe())
        }
        
        # Statistiques globales
        status['summary'] = {
            'total_found': sum(1 for exe in status.values() if isinstance(exe, dict) and exe.get('exists', False)),
            'total_working': sum(1 for exe in status.values() if isinstance(exe, dict) and exe.get('working', False)),
            'all_ready': all(exe.get('working', False) for exe in status.values() if isinstance(exe, dict)),
            'client_ready': status['realesrgan'].get('working', False)  # Real-ESRGAN est le minimum pour le client
        }
        
        return status
    
    def setup_instructions(self) -> List[str]:
        """Retourne les instructions de configuration pour le client Windows"""
        instructions = [
            "📋 Instructions de configuration des exécutables (Client Windows):",
            "",
            "1. Real-ESRGAN (REQUIS):",
            f"   📁 Dossier cible: {self.client_root / 'realesrgan-ncnn-vulkan'}",
            "   📥 Télécharger: https://github.com/xinntao/Real-ESRGAN/releases",
            "   📦 Fichier: realesrgan-ncnn-vulkan-YYYYMMDD-windows.zip",
            "   ⚠️  Requis pour le traitement d'upscaling",
            "",
            "2. FFmpeg (OPTIONNEL):",
            f"   📁 Dossier cible: {self.client_root / 'ffmpeg'}",
            "   📥 Télécharger: https://ffmpeg.org/download.html",
            "   📦 Fichier: ffmpeg-master-latest-win64-gpl.zip",
            "   💡 Utilisé pour des traitements vidéo locaux",
            "",
            "3. Structure finale attendue:",
            f"   {self.client_root / 'realesrgan-ncnn-vulkan' / 'realesrgan-ncnn-vulkan.exe'}",
            f"   {self.client_root / 'ffmpeg' / 'ffmpeg.exe'} (optionnel)",
            f"   {self.client_root / 'ffmpeg' / 'ffprobe.exe'} (optionnel)",
            "",
            "4. Vérification:",
            "   Utilisez l'onglet 'Configuration' du client pour tester les exécutables",
        ]
        
        return instructions
    
    def is_client_ready(self) -> bool:
        """Vérifie si le client est prêt (Real-ESRGAN au minimum)"""
        realesrgan = self.find_realesrgan()
        return realesrgan is not None and self.test_executable(realesrgan)

# Instance globale pour le client
client_executable_detector = ClientExecutableDetector()