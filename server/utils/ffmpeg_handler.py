# UpscalingByNetwork/server/utils/ffmpeg_handler.py
"""
Gestionnaire FFmpeg pour l'extraction et l'assemblage de vidéos
Gère l'extraction des frames, la détection audio et le réassemblage final
"""

import asyncio
import logging
import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import subprocess
import shutil

class FFmpegHandler:
    """Gestionnaire des opérations FFmpeg"""
    
    def __init__(self, ffmpeg_path: Path = None, ffprobe_path: Path = None):
        self.logger = logging.getLogger(__name__)
        
        # Détection automatique des exécutables
        self.ffmpeg_path = self._find_ffmpeg_executable(ffmpeg_path)
        self.ffprobe_path = self._find_ffprobe_executable(ffprobe_path)
        
        # Configuration par défaut
        self.default_fps = 30
        self.default_quality = 'high'  # high, medium, low
        self.temp_audio_format = 'aac'
        
        # Vérification de la disponibilité
        if not self._verify_ffmpeg():
            raise RuntimeError("FFmpeg non disponible ou non fonctionnel")
        
        self.logger.info(f"FFmpeg initialisé: {self.ffmpeg_path}")
    
    def _find_ffmpeg_executable(self, custom_path: Path = None) -> Path:
        """Trouve l'exécutable FFmpeg"""
        if custom_path and custom_path.exists():
            return custom_path
        
        # Chercher dans le dossier du projet
        project_paths = [
            Path("ffmpeg/ffmpeg.exe"),  # Windows
            Path("ffmpeg/ffmpeg"),      # Linux
            Path("../ffmpeg/ffmpeg.exe"),
            Path("../ffmpeg/ffmpeg")
        ]
        
        for path in project_paths:
            if path.exists():
                return path.resolve()
        
        # Chercher dans le PATH système
        system_ffmpeg = shutil.which("ffmpeg")
        if system_ffmpeg:
            return Path(system_ffmpeg)
        
        # Fallback - sera vérifié plus tard
        return Path("ffmpeg.exe")
    
    def _find_ffprobe_executable(self, custom_path: Path = None) -> Path:
        """Trouve l'exécutable FFprobe"""
        if custom_path and custom_path.exists():
            return custom_path
        
        # Dériver du chemin FFmpeg
        ffprobe_path = self.ffmpeg_path.parent / "ffprobe.exe"
        if ffprobe_path.exists():
            return ffprobe_path
        
        ffprobe_path = self.ffmpeg_path.parent / "ffprobe"
        if ffprobe_path.exists():
            return ffprobe_path
        
        # Chercher dans le PATH système
        system_ffprobe = shutil.which("ffprobe")
        if system_ffprobe:
            return Path(system_ffprobe)
        
        return Path("ffprobe.exe")
    
    def _verify_ffmpeg(self) -> bool:
        """Vérifie que FFmpeg fonctionne"""
        try:
            result = subprocess.run(
                [str(self.ffmpeg_path), "-version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except Exception as e:
            self.logger.error(f"Erreur vérification FFmpeg: {e}")
            return False
    
    async def get_video_info(self, video_path: Path) -> Dict[str, Any]:
        """Récupère les informations d'une vidéo"""
        try:
            cmd = [
                str(self.ffprobe_path),
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(video_path)
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise RuntimeError(f"Erreur FFprobe: {stderr.decode()}")
            
            info = json.loads(stdout.decode())
            
            # Extraction des informations utiles
            video_info = {
                'duration': 0,
                'fps': self.default_fps,
                'width': 0,
                'height': 0,
                'total_frames': 0,
                'has_audio': False,
                'audio_streams': [],
                'video_streams': [],
                'format': info.get('format', {})
            }
            
            # Analyse des streams
            for stream in info.get('streams', []):
                if stream['codec_type'] == 'video':
                    video_info['video_streams'].append(stream)
                    if video_info['width'] == 0:  # Premier stream vidéo
                        video_info['width'] = stream.get('width', 0)
                        video_info['height'] = stream.get('height', 0)
                        
                        # Calcul du FPS
                        fps_str = stream.get('r_frame_rate', '30/1')
                        if '/' in fps_str:
                            num, den = fps_str.split('/')
                            video_info['fps'] = float(num) / float(den) if float(den) != 0 else self.default_fps
                        else:
                            video_info['fps'] = float(fps_str)
                
                elif stream['codec_type'] == 'audio':
                    video_info['has_audio'] = True
                    video_info['audio_streams'].append(stream)
            
            # Durée et nombre total de frames
            format_info = info.get('format', {})
            if 'duration' in format_info:
                video_info['duration'] = float(format_info['duration'])
                video_info['total_frames'] = int(video_info['duration'] * video_info['fps'])
            
            self.logger.info(f"Infos vidéo {video_path.name}: {video_info['total_frames']} frames, {video_info['fps']:.2f} fps")
            
            return video_info
            
        except Exception as e:
            self.logger.error(f"Erreur analyse vidéo {video_path}: {e}")
            raise
    
    async def extract_frames(self, video_path: Path, output_dir: Path, 
                           start_time: float = 0, duration: float = None) -> int:
        """Extrait les frames d'une vidéo"""
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Construction de la commande
            cmd = [
                str(self.ffmpeg_path),
                "-i", str(video_path),
                "-y",  # Overwrite files
                "-v", "warning",  # Reduce verbosity
            ]
            
            # Gestion du temps de début
            if start_time > 0:
                cmd.extend(["-ss", str(start_time)])
            
            # Gestion de la durée
            if duration:
                cmd.extend(["-t", str(duration)])
            
            # Format de sortie
            cmd.extend([
                "-f", "image2",
                "-vf", "format=rgb24",  # Format pour Real-ESRGAN
                str(output_dir / "frame_%06d.png")
            ])
            
            self.logger.info(f"Extraction frames: {video_path.name} -> {output_dir}")
            
            # Exécution
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Erreur inconnue"
                raise RuntimeError(f"Erreur extraction frames: {error_msg}")
            
            # Comptage des frames extraites
            extracted_frames = len(list(output_dir.glob("frame_*.png")))
            
            self.logger.info(f"Extraction terminée: {extracted_frames} frames")
            
            return extracted_frames
            
        except Exception as e:
            self.logger.error(f"Erreur extraction frames de {video_path}: {e}")
            raise
    
    async def extract_audio(self, video_path: Path, output_path: Path) -> bool:
        """Extrait l'audio d'une vidéo"""
        try:
            # Vérifier s'il y a de l'audio
            video_info = await self.get_video_info(video_path)
            if not video_info['has_audio']:
                self.logger.info(f"Pas d'audio dans {video_path.name}")
                return False
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            cmd = [
                str(self.ffmpeg_path),
                "-i", str(video_path),
                "-y",
                "-v", "warning",
                "-vn",  # No video
                "-acodec", self.temp_audio_format,
                "-q:a", "2",  # High quality
                str(output_path)
            ]
            
            self.logger.info(f"Extraction audio: {video_path.name} -> {output_path.name}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Erreur inconnue"
                self.logger.warning(f"Échec extraction audio: {error_msg}")
                return False
            
            self.logger.info("Extraction audio terminée")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur extraction audio de {video_path}: {e}")
            return False
    
    async def assemble_video(self, frames_dir: Path, original_video_path: Path, 
                           output_path: Path, fps: float = None) -> bool:
        """Assemble les frames en vidéo avec l'audio original"""
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Obtenir les infos de la vidéo originale
            original_info = await self.get_video_info(original_video_path)
            target_fps = fps or original_info['fps']
            
            # Vérifier la présence des frames
            frame_files = sorted(frames_dir.glob("frame_*.png"))
            if not frame_files:
                raise RuntimeError(f"Aucune frame trouvée dans {frames_dir}")
            
            self.logger.info(f"Assemblage vidéo: {len(frame_files)} frames à {target_fps:.2f} fps")
            
            # Extraction de l'audio temporaire
            temp_audio_path = frames_dir.parent / "temp_audio.aac"
            has_audio = await self.extract_audio(original_video_path, temp_audio_path)
            
            # Construction de la commande d'assemblage
            cmd = [
                str(self.ffmpeg_path),
                "-y",
                "-v", "warning",
                "-framerate", str(target_fps),
                "-i", str(frames_dir / "frame_%06d.png"),
            ]
            
            # Ajout de l'audio si disponible
            if has_audio and temp_audio_path.exists():
                cmd.extend(["-i", str(temp_audio_path)])
                cmd.extend(["-c:a", "copy"])  # Copy audio without re-encoding
                cmd.extend(["-shortest"])     # Match shortest stream
            
            # Configuration vidéo selon la qualité
            quality_settings = self._get_quality_settings(self.default_quality)
            cmd.extend(quality_settings)
            
            # Sortie
            cmd.append(str(output_path))
            
            self.logger.info(f"Commande assemblage: {' '.join(cmd[:10])}...")
            
            # Exécution avec monitoring de la progression
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Erreur inconnue"
                raise RuntimeError(f"Erreur assemblage vidéo: {error_msg}")
            
            # Nettoyage
            if temp_audio_path.exists():
                temp_audio_path.unlink()
            
            # Vérification du fichier de sortie
            if not output_path.exists():
                raise RuntimeError("Fichier de sortie non créé")
            
            file_size_mb = output_path.stat().st_size / (1024 * 1024)
            self.logger.info(f"Assemblage terminé: {output_path.name} ({file_size_mb:.1f} MB)")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur assemblage vidéo: {e}")
            return False
    
    def _get_quality_settings(self, quality: str) -> List[str]:
        """Retourne les paramètres de qualité pour l'encodage"""
        settings = {
            'high': [
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "18",
                "-pix_fmt", "yuv420p"
            ],
            'medium': [
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-pix_fmt", "yuv420p"
            ],
            'low': [
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "28",
                "-pix_fmt", "yuv420p"
            ]
        }
        
        return settings.get(quality, settings['medium'])
    
    async def split_video_by_time(self, video_path: Path, output_dir: Path, 
                                segment_duration: float = 60.0) -> List[Path]:
        """Divise une vidéo en segments temporels"""
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Obtenir la durée totale
            video_info = await self.get_video_info(video_path)
            total_duration = video_info['duration']
            
            segments = []
            current_time = 0.0
            segment_num = 0
            
            while current_time < total_duration:
                segment_path = output_dir / f"segment_{segment_num:03d}.mp4"
                remaining_duration = total_duration - current_time
                actual_duration = min(segment_duration, remaining_duration)
                
                cmd = [
                    str(self.ffmpeg_path),
                    "-i", str(video_path),
                    "-y",
                    "-v", "warning",
                    "-ss", str(current_time),
                    "-t", str(actual_duration),
                    "-c", "copy",  # Stream copy for speed
                    str(segment_path)
                ]
                
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await process.communicate()
                
                if process.returncode == 0 and segment_path.exists():
                    segments.append(segment_path)
                    self.logger.debug(f"Segment créé: {segment_path.name}")
                
                current_time += segment_duration
                segment_num += 1
            
            self.logger.info(f"Vidéo divisée en {len(segments)} segments")
            return segments
            
        except Exception as e:
            self.logger.error(f"Erreur division vidéo {video_path}: {e}")
            return []
    
    async def get_frame_at_time(self, video_path: Path, timestamp: float, 
                              output_path: Path) -> bool:
        """Extrait une frame à un timestamp donné"""
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            cmd = [
                str(self.ffmpeg_path),
                "-i", str(video_path),
                "-y",
                "-v", "warning",
                "-ss", str(timestamp),
                "-vframes", "1",
                "-f", "image2",
                str(output_path)
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            return process.returncode == 0 and output_path.exists()
            
        except Exception as e:
            self.logger.error(f"Erreur extraction frame à {timestamp}s: {e}")
            return False
    
    def estimate_processing_time(self, total_frames: int, fps: float) -> Dict[str, float]:
        """Estime les temps de traitement"""
        # Estimations basées sur des benchmarks moyens
        extraction_time_per_frame = 0.05  # 50ms par frame
        assembly_time_base = 30  # 30 secondes de base
        assembly_time_per_frame = 0.02  # 20ms par frame
        
        extraction_time = total_frames * extraction_time_per_frame
        assembly_time = assembly_time_base + (total_frames * assembly_time_per_frame)
        
        return {
            'extraction_seconds': extraction_time,
            'assembly_seconds': assembly_time,
            'total_seconds': extraction_time + assembly_time,
            'total_minutes': (extraction_time + assembly_time) / 60
        }
    
    def get_supported_formats(self) -> Dict[str, List[str]]:
        """Retourne les formats supportés"""
        return {
            'input': ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v'],
            'output': ['.mp4', '.avi', '.mkv', '.mov']
        }
    
    def validate_video_file(self, video_path: Path) -> Tuple[bool, str]:
        """Valide un fichier vidéo"""
        if not video_path.exists():
            return False, "Fichier inexistant"
        
        if video_path.suffix.lower() not in self.get_supported_formats()['input']:
            return False, f"Format non supporté: {video_path.suffix}"
        
        if video_path.stat().st_size == 0:
            return False, "Fichier vide"
        
        return True, "Fichier valide"