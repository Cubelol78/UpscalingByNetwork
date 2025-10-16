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

from models.job import Job, JobStatus, AudioTrack, SubtitleTrack
from models.batch import Batch
from config.settings import config
from utils.logger import get_logger
from utils.ffmpeg_utils import ffmpeg_utils
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
            job.has_audio = video_info["has_audio"]  # Legacy compatibility

            # Populate audio tracks
            for audio_info in video_info.get("audio_tracks", []):
                audio_track = AudioTrack(
                    index=audio_info["index"],
                    codec=audio_info["codec"],
                    language=audio_info["language"],
                    title=audio_info["title"],
                    channels=audio_info["channels"],
                    sample_rate=audio_info["sample_rate"],
                    bitrate=audio_info["bitrate"],
                    is_default=audio_info["is_default"]
                )
                job.audio_tracks.append(audio_track)

            # Populate subtitle tracks
            for subtitle_info in video_info.get("subtitle_tracks", []):
                subtitle_track = SubtitleTrack(
                    index=subtitle_info["index"],
                    codec=subtitle_info["codec"],
                    language=subtitle_info["language"],
                    title=subtitle_info["title"],
                    is_default=subtitle_info["is_default"],
                    is_forced=subtitle_info["is_forced"]
                )
                job.subtitle_tracks.append(subtitle_track)

            # Ajouter le job au serveur
            self.server.jobs[job.id] = job
            self.server.current_job = job.id

            self.logger.info(
                f"Job créé: {job.id} pour {video_name} - "
                f"{len(job.audio_tracks)} pistes audio, "
                f"{len(job.subtitle_tracks)} pistes sous-titres"
            )
            return job
            
        except Exception as e:
            self.logger.error(f"Erreur création job: {e}")
            return None
    
    async def extract_frames(self, job: Job) -> bool:
        """Extrait les frames d'une vidéo"""
        try:
            if not ffmpeg_utils.available:
                self.logger.error("FFmpeg non disponible pour l'extraction")
                return False
            
            job.status = JobStatus.EXTRACTING
            self.logger.info(f"Extraction des frames pour le job {job.id}")
            
            # Préparation des dossiers
            frames_dir = Path(config.TEMP_DIR) / f"job_{job.id}_frames"
            upscaled_dir = Path(config.TEMP_DIR) / f"job_{job.id}_upscaled"
            
            ensure_dir(frames_dir)
            ensure_dir(upscaled_dir)
            
            # Extraction des frames avec FFmpeg intégré
            ffmpeg_args = [
                "-i", job.input_video_path,
                "-q:v", "1",
                str(frames_dir / "frame_%06d.png"),
                "-loglevel", "quiet", "-stats"
            ]
            
            result = await ffmpeg_utils.run_ffmpeg_async(ffmpeg_args)
            
            if result.returncode != 0:
                self.logger.error(f"Erreur FFmpeg extraction: {result.stderr.decode()}")
                return False
            
            # Comptage des frames extraites
            frame_files = list(frames_dir.glob("frame_*.png"))
            job.total_frames = len(frame_files)
            
            if job.total_frames == 0:
                self.logger.error("Aucune frame extraite")
                return False
            
            # Extract all audio tracks
            if job.audio_tracks:
                await self._extract_all_audio_tracks(job)
            elif job.has_audio:
                # Legacy fallback for backward compatibility
                await self._extract_audio(job)

            # Extract all subtitle tracks
            if job.subtitle_tracks:
                await self._extract_all_subtitle_tracks(job)

            # Création des lots
            frame_paths = [str(f) for f in sorted(frame_files)]
            batches = self.server.batch_manager.create_batches_from_frames(job, frame_paths)
            job.batches = [batch.id for batch in batches]

            job.start()
            self.logger.info(
                f"Extraction terminée: {job.total_frames} frames, {len(batches)} lots, "
                f"{len(job.audio_tracks)} audio, {len(job.subtitle_tracks)} subtitles"
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur extraction frames: {e}")
            job.fail(str(e))
            return False
    
    async def _extract_audio(self, job: Job) -> bool:
        """Extrait l'audio d'une vidéo (legacy method for backward compatibility)"""
        try:
            audio_path = Path(config.TEMP_DIR) / f"job_{job.id}_audio.aac"

            # Tentative d'extraction en AAC avec FFmpeg intégré
            ffmpeg_args = [
                "-i", job.input_video_path,
                "-vn", "-acodec", "aac", "-b:a", "192k",
                str(audio_path), "-loglevel", "error"
            ]

            result = await ffmpeg_utils.run_ffmpeg_async(ffmpeg_args)

            if result.returncode == 0 and audio_path.exists():
                job.audio_path = str(audio_path)
                self.logger.info("Audio extrait (AAC)")
                return True

            # Tentative alternative en WAV
            audio_path_wav = Path(config.TEMP_DIR) / f"job_{job.id}_audio.wav"
            ffmpeg_args_wav = [
                "-i", job.input_video_path,
                "-vn", "-acodec", "pcm_s16le",
                str(audio_path_wav), "-loglevel", "error"
            ]

            result = await ffmpeg_utils.run_ffmpeg_async(ffmpeg_args_wav)

            if result.returncode == 0 and audio_path_wav.exists():
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

    async def _extract_all_audio_tracks(self, job: Job) -> bool:
        """
        Extract all audio tracks from the video with metadata preservation.

        For each audio track, extract to a separate file maintaining codec,
        language, and other metadata.
        """
        try:
            if not job.audio_tracks:
                self.logger.info("No audio tracks to extract")
                return True

            success_count = 0
            for i, track in enumerate(job.audio_tracks):
                try:
                    # Determine output format based on codec
                    # Use AAC for most codecs, copy for already compatible codecs
                    if track.codec in ['aac', 'mp3', 'opus']:
                        codec_arg = "copy"
                        ext = track.codec
                    else:
                        codec_arg = "aac"
                        ext = "aac"

                    audio_path = Path(config.TEMP_DIR) / f"job_{job.id}_audio_{i}_{track.language}.{ext}"

                    # Extract specific audio stream by index
                    # -map 0:a:{i} selects the i-th audio stream
                    ffmpeg_args = [
                        "-i", job.input_video_path,
                        "-map", f"0:{track.index}",  # Map specific stream by absolute index
                        "-vn",  # No video
                        "-acodec", codec_arg,
                    ]

                    # Add bitrate if not copying
                    if codec_arg != "copy":
                        ffmpeg_args.extend(["-b:a", f"{track.bitrate // 1000}k"])

                    ffmpeg_args.extend([
                        str(audio_path),
                        "-loglevel", "error"
                    ])

                    result = await ffmpeg_utils.run_ffmpeg_async(ffmpeg_args)

                    if result.returncode == 0 and audio_path.exists():
                        track.file_path = str(audio_path)
                        success_count += 1
                        self.logger.info(
                            f"Audio track {i} extracted: {track.language} "
                            f"({track.codec}) -> {audio_path.name}"
                        )
                    else:
                        self.logger.warning(
                            f"Failed to extract audio track {i}: {result.stderr.decode()}"
                        )

                except Exception as e:
                    self.logger.error(f"Error extracting audio track {i}: {e}")
                    continue

            # Set legacy audio_path to first track for backward compatibility
            if job.audio_tracks and job.audio_tracks[0].file_path:
                job.audio_path = job.audio_tracks[0].file_path

            self.logger.info(f"Extracted {success_count}/{len(job.audio_tracks)} audio tracks")
            return success_count > 0

        except Exception as e:
            self.logger.error(f"Error extracting audio tracks: {e}")
            return False

    async def _extract_all_subtitle_tracks(self, job: Job) -> bool:
        """
        Extract all subtitle tracks from the video with metadata preservation.

        For each subtitle track, extract to a separate file maintaining language
        and format information.
        """
        try:
            if not job.subtitle_tracks:
                self.logger.info("No subtitle tracks to extract")
                return True

            success_count = 0
            for i, track in enumerate(job.subtitle_tracks):
                try:
                    # Determine output format based on codec
                    # Convert to SRT for better compatibility
                    if track.codec in ['subrip', 'srt']:
                        codec_arg = "copy"
                        ext = "srt"
                    elif track.codec in ['ass', 'ssa']:
                        codec_arg = "copy"
                        ext = track.codec
                    elif track.codec == 'mov_text':
                        codec_arg = "srt"
                        ext = "srt"
                    else:
                        # Default to SRT conversion for unknown formats
                        codec_arg = "srt"
                        ext = "srt"

                    subtitle_path = Path(config.TEMP_DIR) / f"job_{job.id}_subtitle_{i}_{track.language}.{ext}"

                    # Extract specific subtitle stream by index
                    ffmpeg_args = [
                        "-i", job.input_video_path,
                        "-map", f"0:{track.index}",  # Map specific stream by absolute index
                        "-c:s", codec_arg,
                        str(subtitle_path),
                        "-loglevel", "error"
                    ]

                    result = await ffmpeg_utils.run_ffmpeg_async(ffmpeg_args)

                    if result.returncode == 0 and subtitle_path.exists():
                        track.file_path = str(subtitle_path)
                        success_count += 1
                        self.logger.info(
                            f"Subtitle track {i} extracted: {track.language} "
                            f"({track.codec}) -> {subtitle_path.name}"
                        )
                    else:
                        self.logger.warning(
                            f"Failed to extract subtitle track {i}: {result.stderr.decode()}"
                        )

                except Exception as e:
                    self.logger.error(f"Error extracting subtitle track {i}: {e}")
                    continue

            self.logger.info(f"Extracted {success_count}/{len(job.subtitle_tracks)} subtitle tracks")
            return success_count > 0

        except Exception as e:
            self.logger.error(f"Error extracting subtitle tracks: {e}")
            return False
    
    async def assemble_video(self, job: Job) -> bool:
        """Assemble la vidéo finale à partir des frames upscalées"""
        try:
            if not ffmpeg_utils.available:
                self.logger.error("FFmpeg non disponible pour l'assemblage")
                return False
            
            self.logger.info(f"Assemblage de la vidéo pour le job {job.id}")
            
            upscaled_dir = Path(config.TEMP_DIR) / f"job_{job.id}_upscaled"
            
            # Vérification que tous les frames upscalés sont présents
            if not await self._verify_upscaled_frames(job, upscaled_dir):
                self.logger.error("Frames upscalés manquants")
                return False
            
            # Construction de la commande FFmpeg
            ffmpeg_args = self._build_ffmpeg_args(job, upscaled_dir)
            
            # Exécution de FFmpeg
            result = await ffmpeg_utils.run_ffmpeg_async(ffmpeg_args)
            
            if result.returncode != 0:
                self.logger.error(f"Erreur FFmpeg assemblage: {result.stderr.decode()}")
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
    
    def _build_ffmpeg_args(self, job: Job, upscaled_dir: Path) -> List[str]:
        """
        Construit les arguments FFmpeg pour l'assemblage avec support multi-pistes.

        Builds FFmpeg command to:
        1. Add upscaled video frames as input
        2. Add all extracted audio tracks as separate inputs
        3. Add all extracted subtitle tracks as separate inputs
        4. Map all streams correctly with metadata preservation
        """
        args = [
            "-framerate", str(job.frame_rate),
            "-i", str(upscaled_dir / "frame_%06d.png"),
        ]

        # Track input indices for mapping
        input_index = 1  # 0 is video frames

        # Add all audio track files as inputs
        audio_input_indices = []
        if job.audio_tracks:
            for track in job.audio_tracks:
                if track.file_path and Path(track.file_path).exists():
                    args.extend(["-i", track.file_path])
                    audio_input_indices.append((input_index, track))
                    input_index += 1
        elif job.has_audio and job.audio_path:
            # Legacy fallback
            args.extend(["-i", job.audio_path])
            audio_input_indices.append((input_index, None))
            input_index += 1

        # Add all subtitle track files as inputs
        subtitle_input_indices = []
        if job.subtitle_tracks:
            for track in job.subtitle_tracks:
                if track.file_path and Path(track.file_path).exists():
                    args.extend(["-i", track.file_path])
                    subtitle_input_indices.append((input_index, track))
                    input_index += 1

        # Map video stream
        args.extend(["-map", "0:v:0"])

        # Map all audio streams
        for idx, track in audio_input_indices:
            args.extend(["-map", f"{idx}:a:0"])

        # Map all subtitle streams
        for idx, track in subtitle_input_indices:
            args.extend(["-map", f"{idx}:s:0"])

        # Configuration vidéo
        args.extend([
            "-c:v", "libx264",
            "-crf", str(config.FFMPEG_CRF),
            "-pix_fmt", "yuv420p",
            "-threads", str(config.FFMPEG_THREADS),
            "-vsync", "cfr",
            "-preset", config.FFMPEG_PRESET
        ])

        # Configuration audio - encode all audio tracks
        if audio_input_indices:
            args.extend([
                "-c:a", "aac",
                "-b:a", "192k",
                "-async", "1"
            ])

            # Set metadata for each audio track
            for output_idx, (input_idx, track) in enumerate(audio_input_indices):
                if track:  # New multi-track format
                    args.extend([
                        f"-metadata:s:a:{output_idx}", f"language={track.language}",
                    ])
                    if track.title:
                        args.extend([
                            f"-metadata:s:a:{output_idx}", f"title={track.title}"
                        ])
                    if track.is_default:
                        args.extend([
                            f"-disposition:a:{output_idx}", "default"
                        ])
                    else:
                        args.extend([
                            f"-disposition:a:{output_idx}", "0"
                        ])

        # Configuration subtitle - copy all subtitle tracks
        if subtitle_input_indices:
            args.extend(["-c:s", "mov_text"])  # Use mov_text for MP4 compatibility

            # Set metadata for each subtitle track
            for output_idx, (input_idx, track) in enumerate(subtitle_input_indices):
                args.extend([
                    f"-metadata:s:s:{output_idx}", f"language={track.language}",
                ])
                if track.title:
                    args.extend([
                        f"-metadata:s:s:{output_idx}", f"title={track.title}"
                    ])
                if track.is_default:
                    args.extend([
                        f"-disposition:s:{output_idx}", "default"
                    ])
                else:
                    args.extend([
                        f"-disposition:s:{output_idx}", "0"
                    ])
                if track.is_forced:
                    args.extend([
                        f"-disposition:s:{output_idx}", "forced"
                    ])

        # Use shortest stream to avoid issues with mismatched durations
        if audio_input_indices or subtitle_input_indices:
            args.append("-shortest")

        # Fichier de sortie
        args.extend([
            job.output_video_path,
            "-loglevel", "quiet",
            "-stats"
        ])

        return args
    
    async def _verify_av_sync(self, job: Job):
        """Vérifie la synchronisation audio/vidéo"""
        try:
            if not ffmpeg_utils.available:
                return
            
            # Obtention de la durée de la vidéo
            ffprobe_args = [
                "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                job.output_video_path
            ]
            
            result = await ffmpeg_utils.run_ffprobe_async(ffprobe_args)
            
            if result.returncode == 0:
                duration = float(result.stdout.decode().strip())
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

            # Add all audio track files to cleanup list
            for track in job.audio_tracks:
                if track.file_path:
                    temp_files.append(Path(track.file_path))

            # Add all subtitle track files to cleanup list
            for track in job.subtitle_tracks:
                if track.file_path:
                    temp_files.append(Path(track.file_path))

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
        """Obtient les informations d'une vidéo incluant tous les flux audio et sous-titres"""
        try:
            if not ffmpeg_utils.available:
                self.logger.error("FFprobe non disponible pour l'analyse vidéo")
                return None

            # Get all streams using the new comprehensive method
            streams = await ffmpeg_utils.get_all_streams(video_path)
            if not streams:
                self.logger.error("Impossible d'obtenir les informations de flux")
                return None

            # Parse frame rate from video stream
            frame_rate = 30.0
            if streams['video']:
                video_stream = streams['video'][0]
                r_frame_rate = video_stream.get('r_frame_rate', '30/1')
                if r_frame_rate and '/' in r_frame_rate:
                    num, den = r_frame_rate.split('/')
                    if float(den) != 0:
                        frame_rate = round(float(num) / float(den), 3)

            # Detect all audio tracks
            audio_tracks_info = await ffmpeg_utils.detect_audio_tracks(video_path)

            # Detect all subtitle tracks
            subtitle_tracks_info = await ffmpeg_utils.detect_subtitle_tracks(video_path)

            # Legacy compatibility
            has_audio = len(audio_tracks_info) > 0

            self.logger.info(f"Video info: {frame_rate} fps, {len(audio_tracks_info)} audio tracks, {len(subtitle_tracks_info)} subtitle tracks")

            return {
                "frame_rate": frame_rate,
                "has_audio": has_audio,  # Legacy field
                "audio_tracks": audio_tracks_info,
                "subtitle_tracks": subtitle_tracks_info
            }

        except Exception as e:
            self.logger.error(f"Erreur analyse vidéo: {e}")
            return None