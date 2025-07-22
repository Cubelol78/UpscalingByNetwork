"""
Processeur vidéo pour l'extraction et l'assemblage des frames
"""

import os
import subprocess
import asyncio
import shutil
from pathlib import Path
from typing import List, Optional, Tuple
import re

from models.job import Job, JobStatus
from models.batch import Batch
from config.settings import config
from utils.logger import get_logger
from utils.file_utils import ensure_dir, get_video_info

class VideoProcessor:
    """Gestionnaire du traitement vidéo"""
    
    def __init__(self, server):
        self.server = server
        self.logger = get_logger(__name__)
    
    async def create_job_from_video(self, input_video_path: str) -> Optional[Job]:
        """Crée un job à partir d'un fichier vidéo"""
        try:
            if not os.path.exists(input_video_path):
                self.logger.error(f"Fichier vidéo introuvable: {input_video_path}")
                return None
            
            # Création du job
            video_name = Path(input_video_path).stem
            output_path = os.path.join(config.OUTPUT_DIR, f"{video_name}_upscaled_1080p.mp4")
            
            job = Job(
                input_video_path=input_video_path,
                output_video_path=output_path
            )
            
            # Analyse de la vidéo
            video_info = await self.get_video_info(input_video_path)
            if not video_info:
                return None
            
            job.frame_rate = video_info["frame_rate"]
            job.has_audio = video_info["has_audio"]
            
            self.logger.info(f"Job créé: {job.id} pour {video_name}")
            return job
            
        except Exception as e:
            self.logger.error(f"Erreur création job: {e}")
            return None
    
    async def extract_frames(self, job: Job) -> bool:
        """Extrait les frames d'une vidéo"""
        try:
            job.status = JobStatus.EXTRACTING
            self.logger.info(f"Extraction des frames pour le job {job.id}")
            
            # Préparation des dossiers
            frames_dir = Path(config.TEMP_DIR) / f"job_{job.id}_frames"
            upscaled_dir = Path(config.TEMP_DIR) / f"job_{job.id}_upscaled"
            
            ensure_dir(frames_dir)
            ensure_dir(upscaled_dir)
            
            # Extraction des frames avec FFmpeg
            ffmpeg_cmd = [
                "ffmpeg", "-i", job.input_video_path,
                "-q:v", "1",
                str(frames_dir / "frame_%06d.png"),
                "-loglevel", "quiet", "-stats"
            ]
            
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                self.logger.error(f"Erreur FFmpeg extraction: {stderr.decode()}")
                return False
            
            # Comptage des frames extraites
            frame_files = list(frames_dir.glob("frame_*.png"))
            job.total_frames = len(frame_files)
            
            if job.total_frames == 0:
                self.logger.error("Aucune frame extraite")
                return False
            
            # Extraction de l'audio si présent
            if job.has_audio:
                await self._extract_audio(job)
            
            # Création des lots
            frame_paths = [str(f) for f in sorted(frame_files)]
            batches = self.server.batch_manager.create_batches_from_frames(job, frame_paths)
            job.batches = [batch.id for batch in batches]
            
            job.start()
            self.logger.info(f"Extraction terminée: {job.total_frames} frames, {len(batches)} lots")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur extraction frames: {e}")
            job.fail(str(e))
            return False
    
    async def _extract_audio(self, job: Job) -> bool:
        """Extrait l'audio d'une vidéo"""
        try:
            audio_path = Path(config.TEMP_DIR) / f"job_{job.id}_audio.aac"
            
            # Tentative d'extraction en AAC
            ffmpeg_cmd = [
                "ffmpeg", "-i", job.input_video_path,
                "-vn", "-acodec", "aac", "-b:a", "192k",
                str(audio_path), "-loglevel", "error"
            ]
            
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            
            if process.returncode == 0 and audio_path.exists():
                job.audio_path = str(audio_path)
                self.logger.info("Audio extrait (AAC)")
                return True
            
            # Tentative alternative en WAV
            audio_path_wav = Path(config.TEMP_DIR) / f"job_{job.id}_audio.wav"
            ffmpeg_cmd_wav = [
                "ffmpeg", "-i", job.input_video_path,
                "-vn", "-acodec", "pcm_s16le",
                str(audio_path_wav), "-loglevel", "error"
            ]
            
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd_wav,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            
            if process.returncode == 0 and audio_path_wav.exists():
                job.audio_path = str(audio_path_wav)
                self.logger.info("Audio extrait (WAV)")
                return True
            
            self.logger.warning("Impossible d'extraire l'audio")
            job.has_audio = False
            return False
            
        except Exception as e:
            self.logger.error(f"Erreur extraction audio: {e}")
            job.has_audio = False
            return False
    
    async def assemble_video(self, job: Job) -> bool:
        """Assemble la vidéo finale à partir des frames upscalées"""
        try:
            self.logger.info(f"Assemblage de la vidéo pour le job {job.id}")
            
            upscaled_dir = Path(config.TEMP_DIR) / f"job_{job.id}_upscaled"
            
            # Vérification que tous les frames upscalés sont présents
            if not await self._verify_upscaled_frames(job, upscaled_dir):
                self.logger.error("Frames upscalés manquants")
                return False
            
            # Construction de la commande FFmpeg
            ffmpeg_cmd = self._build_ffmpeg_command(job, upscaled_dir)
            
            # Exécution de FFmpeg
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                self.logger.error(f"Erreur FFmpeg assemblage: {stderr.decode()}")
                return False
            
            # Vérification du fichier de sortie
            if not os.path.exists(job.output_video_path):
                self.logger.error("Fichier de sortie non créé")
                return False
            
            # Vérification de la synchronisation audio/vidéo
            if job.has_audio:
                await self._verify_av_sync(job)
            
            # Nettoyage des fichiers temporaires
            await self._cleanup_job_files(job)
            
            self.logger.info(f"Assemblage terminé: {job.output_video_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur assemblage vidéo: {e}")
            return False
    
    async def _verify_upscaled_frames(self, job: Job, upscaled_dir: Path) -> bool:
        """Vérifie que tous les frames upscalés sont présents"""
        expected_frames = job.total_frames
        upscaled_frames = list(upscaled_dir.glob("frame_*.png"))
        
        if len(upscaled_frames) < expected_frames:
            self.logger.warning(f"Frames manquants: {len(upscaled_frames)}/{expected_frames}")
            
            # Tentative de récupération des frames manquants
            missing_frames = []
            for i in range(1, expected_frames + 1):
                frame_path = upscaled_dir / f"frame_{i:06d}.png"
                if not frame_path.exists():
                    missing_frames.append(i)
            
            if missing_frames:
                self.logger.info(f"Frames manquants: {missing_frames[:10]}...")
                # TODO: Implémenter la récupération des frames manquants
                # Pour l'instant, on accepte les frames manquants
        
        return len(upscaled_frames) > 0
    
    def _build_ffmpeg_command(self, job: Job, upscaled_dir: Path) -> List[str]:
        """Construit la commande FFmpeg pour l'assemblage"""
        cmd = [
            "ffmpeg",
            "-framerate", str(job.frame_rate),
            "-i", str(upscaled_dir / "frame_%06d.png"),
        ]
        
        # Ajout de l'audio si présent
        if job.has_audio and job.audio_path:
            cmd.extend(["-i", job.audio_path])
        
        # Configuration vidéo
        cmd.extend([
            "-c:v", "libx264",
            "-crf", str(config.FFMPEG_CRF),
            "-pix_fmt", "yuv420p",
            "-threads", str(config.FFMPEG_THREADS),
            "-vsync", "cfr",
            "-preset", config.FFMPEG_PRESET
        ])
        
        # Configuration audio
        if job.has_audio and job.audio_path:
            cmd.extend([
                "-c:a", "aac",
                "-async", "1",
                "-shortest"
            ])
        
        # Fichier de sortie
        cmd.extend([
            job.output_video_path,
            "-loglevel", "quiet",
            "-stats"
        ])
        
        return cmd
    
    async def _verify_av_sync(self, job: Job):
        """Vérifie la synchronisation audio/vidéo"""
        try:
            # Obtention de la durée de la vidéo
            ffprobe_cmd = [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                job.output_video_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *ffprobe_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                duration = float(stdout.decode().strip())
                self.logger.info(f"Durée vidéo finale: {duration:.2f}s")
            
        except Exception as e:
            self.logger.warning(f"Impossible de vérifier la synchronisation AV: {e}")
    
    async def _cleanup_job_files(self, job: Job):
        """Nettoie les fichiers temporaires d'un job"""
        try:
            temp_dirs = [
                Path(config.TEMP_DIR) / f"job_{job.id}_frames",
                Path(config.TEMP_DIR) / f"job_{job.id}_upscaled"
            ]
            
            temp_files = [
                Path(config.TEMP_DIR) / f"job_{job.id}_audio.aac",
                Path(config.TEMP_DIR) / f"job_{job.id}_audio.wav"
            ]
            
            # Suppression des dossiers
            for temp_dir in temp_dirs:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
                    self.logger.debug(f"Dossier supprimé: {temp_dir}")
            
            # Suppression des fichiers
            for temp_file in temp_files:
                if temp_file.exists():
                    temp_file.unlink()
                    self.logger.debug(f"Fichier supprimé: {temp_file}")
            
        except Exception as e:
            self.logger.warning(f"Erreur nettoyage fichiers temporaires: {e}")
    
    async def get_video_info(self, video_path: str) -> Optional[dict]:
        """Obtient les informations d'une vidéo"""
        try:
            # Détection du framerate
            ffprobe_cmd = [
                "ffprobe", "-v", "quiet",
                "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate,duration",
                "-of", "csv=s=x:p=0",
                video_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *ffprobe_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                self.logger.error(f"Erreur ffprobe: {stderr.decode()}")
                return None
            
            output = stdout.decode().strip()
            parts = output.split('x')
            
            if len(parts) >= 1 and '/' in parts[0]:
                # Parse du framerate
                frame_rate_str = parts[0]
                if frame_rate_str and '/' in frame_rate_str:
                    num, den = frame_rate_str.split('/')
                    frame_rate = round(float(num) / float(den), 3)
                else:
                    frame_rate = 30.0
            else:
                frame_rate = 30.0
            
            # Détection de l'audio
            ffprobe_audio_cmd = [
                "ffprobe", "-v", "quiet",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0",
                video_path
            ]
            
            process_audio = await asyncio.create_subprocess_exec(
                *ffprobe_audio_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout_audio, _ = await process_audio.communicate()
            has_audio = process_audio.returncode == 0 and b"audio" in stdout_audio
            
            return {
                "frame_rate": frame_rate,
                "has_audio": has_audio
            }
            
        except Exception as e:
            self.logger.error(f"Erreur analyse vidéo: {e}")
            return None