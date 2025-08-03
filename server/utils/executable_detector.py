# server/utils/executable_detector.py
"""
Détecteur d'exécutables pour le serveur d'upscaling distribué
Recherche FFmpeg et Real-ESRGAN dans les dossiers locaux du projet
Version corrigée pour respecter la structure UpscalingByNetwork
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Dict, List
import logging

class ExecutableDetector:
    """Détecteur d'exécutables avec chemins spécifiques au projet"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Dossier racine du projet (UpscalingByNetwork)
        self.project_root = self._find_project_root()
        self.server_root = self.project_root / "server"
        
        # Cache des chemins détectés
        self._realesrgan_path = None
        self._ffmpeg_path = None
        self._ffprobe_path = None
        
        self.logger.info(f"Détecteur initialisé - Racine projet: {self.project_root}")
        self.logger.info(f"Racine serveur: {self.server_root}")
    
    def _find_project_root(self) -> Path:
        """Trouve la racine du projet UpscalingByNetwork"""
        current = Path(__file__).resolve()
        
        # Remonte jusqu'à trouver le dossier UpscalingByNetwork
        while current.parent != current:
            if current.name == "UpscalingByNetwork":
                return current
            if (current / "UpscalingByNetwork").exists():
                return current / "UpscalingByNetwork"
            current = current.parent
        
        # Si pas trouvé via la structure, utilise l'emplacement du fichier actuel
        # Ce fichier est dans server/utils/, donc la racine est 2 niveaux au-dessus
        current_file = Path(__file__).resolve()
        if "server" in current_file.parts and "utils" in current_file.parts:
            # Remonte de utils -> server -> UpscalingByNetwork
            return current_file.parent.parent
        
        # Fallback : utilise le dossier courant
        return Path.cwd()
    
    def find_realesrgan(self) -> Optional[str]:
        """Trouve l'exécutable Real-ESRGAN selon la structure du projet"""
        if self._realesrgan_path:
            return self._realesrgan_path
        
        # Noms possibles selon la plateforme
        if sys.platform == "win32":
            executable_name = "realesrgan-ncnn-vulkan.exe"
        else:
            executable_name = "realesrgan-ncnn-vulkan"
        
        # Chemins de recherche selon la structure du projet mentionnée
        search_paths = [
            # Structure principale du projet
            self.server_root / "realesrgan-ncnn-vulkan" / executable_name,
            self.server_root / "realesrgan-ncnn-vulkan" / "Windows" / executable_name,
            self.server_root / "realesrgan-ncnn-vulkan" / "bin" / executable_name,
            
            # Structure alternative avec dossier dependencies
            self.server_root / "dependencies" / "realesrgan-ncnn-vulkan" / executable_name,
            self.server_root / "dependencies" / executable_name,
            
            # Dossier racine du serveur
            self.server_root / executable_name,
            
            # Fallbacks dans le dossier courant
            Path.cwd() / "realesrgan-ncnn-vulkan" / executable_name,
            Path.cwd() / executable_name,
        ]
        
        self.logger.info(f"🔍 Recherche Real-ESRGAN ({executable_name})...")
        
        for path in search_paths:
            self.logger.debug(f"  Vérification: {path}")
            if path.exists() and path.is_file():
                # Test de l'exécutable
                if self._test_executable(path, ["-h"]):
                    self._realesrgan_path = str(path)
                    self.logger.info(f"✅ Real-ESRGAN trouvé et testé: {path}")
                    return self._realesrgan_path
                else:
                    self.logger.warning(f"⚠️ Fichier trouvé mais non fonctionnel: {path}")
        
        # Recherche dans le PATH système
        system_path = shutil.which(executable_name)
        if system_path:
            if self._test_executable(system_path, ["-h"]):
                self._realesrgan_path = system_path
                self.logger.info(f"✅ Real-ESRGAN trouvé dans PATH: {system_path}")
                return self._realesrgan_path
        
        self.logger.error(f"❌ Real-ESRGAN non trouvé")
        self.logger.error("📥 Téléchargez depuis: https://github.com/xinntao/Real-ESRGAN/releases")
        self.logger.error(f"📁 Placez dans: {self.server_root / 'realesrgan-ncnn-vulkan'}")
        
        return None
    
    def find_ffmpeg(self) -> Optional[str]:
        """Trouve l'exécutable FFmpeg selon la structure du projet"""
        if self._ffmpeg_path:
            return self._ffmpeg_path
        
        # Noms possibles selon la plateforme
        if sys.platform == "win32":
            executable_name = "ffmpeg.exe"
        else:
            executable_name = "ffmpeg"
        
        # Chemins de recherche selon la structure du projet
        search_paths = [
            # Structure principale du serveur
            self.server_root / "ffmpeg" / executable_name,
            self.server_root / "ffmpeg" / "bin" / executable_name,
            self.server_root / "ffmpeg" / "Windows" / executable_name,
            
            # Structure alternative avec dependencies
            self.server_root / "dependencies" / "ffmpeg" / executable_name,
            self.server_root / "dependencies" / "ffmpeg" / "bin" / executable_name,
            self.server_root / "dependencies" / executable_name,
            
            # Dossier racine du serveur
            self.server_root / executable_name,
            
            # Fallbacks
            Path.cwd() / "ffmpeg" / executable_name,
            Path.cwd() / executable_name,
        ]
        
        self.logger.info(f"🔍 Recherche FFmpeg ({executable_name})...")
        
        for path in search_paths:
            self.logger.debug(f"  Vérification: {path}")
            if path.exists() and path.is_file():
                if self._test_executable(path, ["-version"]):
                    self._ffmpeg_path = str(path)
                    self.logger.info(f"✅ FFmpeg trouvé et testé: {path}")
                    return self._ffmpeg_path
                else:
                    self.logger.warning(f"⚠️ Fichier trouvé mais non fonctionnel: {path}")
        
        # Recherche dans le PATH système
        system_path = shutil.which(executable_name)
        if system_path:
            if self._test_executable(system_path, ["-version"]):
                self._ffmpeg_path = system_path
                self.logger.info(f"✅ FFmpeg trouvé dans PATH: {system_path}")
                return self._ffmpeg_path
        
        self.logger.warning(f"⚠️ FFmpeg non trouvé")
        self.logger.warning("📥 Téléchargez depuis: https://ffmpeg.org/download.html")
        self.logger.warning(f"📁 Placez dans: {self.server_root / 'ffmpeg'}")
        
        return None
    
    def find_ffprobe(self) -> Optional[str]:
        """Trouve l'exécutable FFprobe (généralement avec FFmpeg)"""
        if self._ffprobe_path:
            return self._ffprobe_path
        
        # FFprobe est généralement dans le même dossier que FFmpeg
        ffmpeg_path = self.find_ffmpeg()
        if ffmpeg_path:
            ffmpeg_dir = Path(ffmpeg_path).parent
            if sys.platform == "win32":
                probe_name = "ffprobe.exe"
            else:
                probe_name = "ffprobe"
            
            probe_path = ffmpeg_dir / probe_name
            if probe_path.exists() and self._test_executable(probe_path, ["-version"]):
                self._ffprobe_path = str(probe_path)
                self.logger.info(f"✅ FFprobe trouvé: {probe_path}")
                return self._ffprobe_path
        
        # Recherche indépendante
        system_path = shutil.which("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
        if system_path and self._test_executable(system_path, ["-version"]):
            self._ffprobe_path = system_path
            self.logger.info(f"✅ FFprobe trouvé dans PATH: {system_path}")
            return self._ffprobe_path
        
        self.logger.warning(f"⚠️ FFprobe non trouvé")
        return None
    
    def _test_executable(self, executable_path: str, test_args: List[str]) -> bool:
        """Teste si un exécutable fonctionne correctement"""
        try:
            result = subprocess.run(
                [str(executable_path)] + test_args,
                capture_output=True,
                timeout=10,
                text=True
            )
            return result.returncode == 0 or result.returncode == 1  # Certains programmes retournent 1 pour -h
        except Exception as e:
            self.logger.debug(f"Test exécutable échoué pour {executable_path}: {e}")
            return False
    
    def get_all_executables_status(self) -> Dict[str, any]:
        """Retourne le statut de tous les exécutables"""
        status = {
            'realesrgan': {
                'path': self.find_realesrgan(),
                'required': True,
                'description': 'Real-ESRGAN pour l\'upscaling d\'images'
            },
            'ffmpeg': {
                'path': self.find_ffmpeg(),
                'required': True,
                'description': 'FFmpeg pour le traitement vidéo'
            },
            'ffprobe': {
                'path': self.find_ffprobe(),
                'required': False,
                'description': 'FFprobe pour l\'analyse vidéo'
            }
        }
        
        # Résumé
        missing_required = [name for name, info in status.items() 
                          if info['required'] and not info['path']]
        
        status['summary'] = {
            'all_found': len(missing_required) == 0,
            'missing_required': missing_required,
            'project_root': str(self.project_root),
            'server_root': str(self.server_root)
        }
        
        return status
    
    def is_server_ready(self) -> bool:
        """Vérifie si le serveur a tous les exécutables requis"""
        status = self.get_all_executables_status()
        return status['summary']['all_found']
    
    def print_status_report(self):
        """Affiche un rapport de statut complet"""
        status = self.get_all_executables_status()
        
        print("\n" + "="*60)
        print("📋 RAPPORT DE STATUT DES EXÉCUTABLES SERVEUR")
        print("="*60)
        print(f"📁 Racine du projet: {status['summary']['project_root']}")
        print(f"🖥️  Racine du serveur: {status['summary']['server_root']}")
        print()
        
        for name, info in status.items():
            if name == 'summary':
                continue
                
            required_str = "REQUIS" if info['required'] else "OPTIONNEL"
            if info['path']:
                print(f"✅ {name.upper()}: {info['path']} ({required_str})")
            else:
                print(f"❌ {name.upper()}: NON TROUVÉ ({required_str})")
            print(f"   └─ {info['description']}")
        
        print()
        if status['summary']['all_found']:
            print("🎉 Tous les exécutables requis sont disponibles!")
        else:
            print("⚠️  Exécutables manquants:")
            for missing in status['summary']['missing_required']:
                print(f"   - {missing}")
        print("="*60)

# Instance globale
executable_detector = ExecutableDetector()

# Test au démarrage si exécuté directement
if __name__ == "__main__":
    executable_detector.print_status_report()