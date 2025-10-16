"""
Utilitaires pour FFmpeg avec chemins intégrés
"""

import os
import subprocess
import json
from pathlib import Path
from typing import Optional, List, Dict, Any

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

    async def get_all_streams(self, video_path: str) -> Optional[Dict[str, Any]]:
        """
        Get complete stream information from a video file using ffprobe.
        Returns a dictionary with all streams categorized by type.

        Returns:
            {
                'audio': [list of audio stream dicts],
                'subtitle': [list of subtitle stream dicts],
                'video': [list of video stream dicts],
                'format': format metadata dict
            }
        """
        try:
            ffprobe_args = [
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                video_path
            ]

            result = await self.run_ffprobe_async(ffprobe_args)

            if result.returncode != 0:
                self.logger.error(f"FFprobe error: {result.stderr.decode()}")
                return None

            data = json.loads(result.stdout.decode())

            # Categorize streams by type
            categorized = {
                'audio': [],
                'subtitle': [],
                'video': [],
                'format': data.get('format', {})
            }

            for stream in data.get('streams', []):
                codec_type = stream.get('codec_type', '')
                if codec_type in categorized:
                    categorized[codec_type].append(stream)

            return categorized

        except Exception as e:
            self.logger.error(f"Error getting stream info: {e}")
            return None

    async def detect_audio_tracks(self, video_path: str) -> List[Dict[str, Any]]:
        """
        Detect all audio tracks in a video file.

        Returns:
            List of dicts containing audio track metadata:
            [
                {
                    'index': stream index,
                    'codec': codec name,
                    'language': language code,
                    'title': track title,
                    'channels': number of channels,
                    'sample_rate': sample rate in Hz,
                    'bitrate': bitrate in bits/s,
                    'is_default': default flag
                }
            ]
        """
        streams = await self.get_all_streams(video_path)
        if not streams:
            return []

        audio_tracks = []
        for stream in streams['audio']:
            track = {
                'index': stream.get('index', 0),
                'codec': stream.get('codec_name', 'unknown'),
                'language': stream.get('tags', {}).get('language', 'und'),
                'title': stream.get('tags', {}).get('title', ''),
                'channels': stream.get('channels', 2),
                'sample_rate': int(stream.get('sample_rate', 48000)),
                'bitrate': int(stream.get('bit_rate', 192000)) if stream.get('bit_rate') else 192000,
                'is_default': stream.get('disposition', {}).get('default', 0) == 1
            }
            audio_tracks.append(track)

        return audio_tracks

    async def detect_subtitle_tracks(self, video_path: str) -> List[Dict[str, Any]]:
        """
        Detect all subtitle tracks in a video file.

        Returns:
            List of dicts containing subtitle track metadata:
            [
                {
                    'index': stream index,
                    'codec': codec name,
                    'language': language code,
                    'title': track title,
                    'is_default': default flag,
                    'is_forced': forced flag
                }
            ]
        """
        streams = await self.get_all_streams(video_path)
        if not streams:
            return []

        subtitle_tracks = []
        for stream in streams['subtitle']:
            track = {
                'index': stream.get('index', 0),
                'codec': stream.get('codec_name', 'unknown'),
                'language': stream.get('tags', {}).get('language', 'und'),
                'title': stream.get('tags', {}).get('title', ''),
                'is_default': stream.get('disposition', {}).get('default', 0) == 1,
                'is_forced': stream.get('disposition', {}).get('forced', 0) == 1
            }
            subtitle_tracks.append(track)

        return subtitle_tracks

# Instance globale
ffmpeg_utils = FFmpegUtils()