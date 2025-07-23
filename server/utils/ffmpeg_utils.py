"""
Utilitaires pour FFmpeg avec chemins intégrés
"""

import os
import subprocess
from pathlib import Path
from typing import Optional, List

from utils.logger import get_logger

class FFmpegUtils:
    """Classe utilitaire pour FFmpeg"""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        self.ffmpeg_dir = Path(__file__).parent.parent / "ffmpeg"
        
        # Chemins vers les exécutables
        self.ffmpeg_path = self.ffmpeg_dir / "ffmpeg.exe"
        self.ffprobe_path = self.ffmpeg_dir / "ffprobe.exe"
        self.ffplay_path = self.ffmpeg_dir / "ffplay.exe"
        
        # Vérifier la disponibilité
        self.available = self._check_availability()
    
    def _check_availability(self) -> bool:
        """Vérifie si FFmpeg est disponible"""
        try:
            if not self.ffmpeg_path.exists():
                self.logger.warning(f"FFmpeg non trouvé: {self.ffmpeg_path}")
                return False
            
            if not self.ffprobe_path.exists():
                self.logger.warning(f"FFprobe non trouvé: {self.ffprobe_path}")
                return False
            
            # Test rapide de FFmpeg
            result = subprocess.run(
                [str(self.ffmpeg_path), "-version"],
                capture_output=True,
                timeout=5
            )
            
            if result.returncode == 0:
                self.logger.info(f"FFmpeg détecté: {self.ffmpeg_path}")
                return True
            else:
                self.logger.warning("FFmpeg non fonctionnel")
                return False
                
        except Exception as e:
            self.logger.warning(f"Erreur vérification FFmpeg: {e}")
            return False
    
    def get_ffmpeg_cmd(self, args: List[str]) -> List[str]:
        """Retourne une commande FFmpeg complète"""
        if not self.available:
            raise RuntimeError("FFmpeg non disponible")
        return [str(self.ffmpeg_path)] + args
    
    def get_ffprobe_cmd(self, args: List[str]) -> List[str]:
        """Retourne une commande FFprobe complète"""
        if not self.available:
            raise RuntimeError("FFprobe non disponible")
        return [str(self.ffprobe_path)] + args
    
    async def run_ffmpeg_async(self, args: List[str]) -> subprocess.CompletedProcess:
        """Exécute FFmpeg de manière asynchrone"""
        import asyncio
        
        cmd = self.get_ffmpeg_cmd(args)
        self.logger.debug(f"Exécution FFmpeg: {' '.join(cmd)}")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr
        )
    
    async def run_ffprobe_async(self, args: List[str]) -> subprocess.CompletedProcess:
        """Exécute FFprobe de manière asynchrone"""
        import asyncio
        
        cmd = self.get_ffprobe_cmd(args)
        self.logger.debug(f"Exécution FFprobe: {' '.join(cmd)}")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr
        )

# Instance globale
ffmpeg_utils = FFmpegUtils()