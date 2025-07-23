"""
Processeur vidéo optimisé avec support complet des sous-titres
Fichier: server/core/video_processor.py
"""

import os
import subprocess
import asyncio
import shutil
import json
import re
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
import time

from models.job import Job, JobStatus, SubtitleTrack, MediaInfo, create_job_from_video_info
from models.batch import Batch
from config.settings import config
from utils.logger import get_logger
from utils.file_utils import ensure_dir, get_video_info
from core.optimized_real_esrgan import optimized_realesrgan
from utils.hardware_detector import hardware_detector

class VideoProcessor:
    """Gestionnaire du traitement vidéo avec support avancé des sous-titres"""
    
    def __init__(self, server):
        self.server = server
        self.logger = get_logger(__name__)
        
        # Cache des informations de codecs supportés
        self.supported_subtitle_codecs = None
        
        # Initialisation des optimisations matérielles
        self._initialize_hardware_optimizations()
    
    def _initialize_hardware_optimizations(self):
        """Initialise les optimisations basées sur le matériel détecté"""
        try:
            # Récupération du statut système
            system_status = optimized_realesrgan.get_system_status()
            
            if system_status['system_detected']:
                self.logger.info("Optimisations matérielles activées pour le traitement vidéo")
                
                # Ajustement de la taille des lots selon le matériel
                optimal_batch_size = optimized_realesrgan.get_optimal_batch_size()
                if optimal_batch_size != config.BATCH_SIZE:
                    config.BATCH_SIZE = optimal_batch_size
                    self.logger.info(f"Taille de lot ajustée à {optimal_batch_size} selon le matériel")
                
                # Configuration des threads FFmpeg selon le CPU
                if system_status.get('cpu_cores', 0) > 0:
                    config.FFMPEG_THREADS = min(system_status['cpu_cores'], 16)
                    self.logger.info(f"Threads FFmpeg ajustés à {config.FFMPEG_THREADS}")
                
                # Ajustement CRF pour laptops (économie batterie)
                if system_status.get('is_laptop', False):
                    config.FFMPEG_CRF = min(config.FFMPEG_CRF + 2, 28)
                    config.FFMPEG_PRESET = "fast"
                    self.logger.info("Ajustements laptop appliqués (CRF +2, preset fast)")
                
            else:
                self.logger.warning("Détection matérielle échouée, utilisation des paramètres par défaut")
                
        except Exception as e:
            self.logger.error(f"Erreur initialisation optimisations: {e}")
    
    async def create_job_from_video(self, input_video_path: str) -> Optional[Job]:
        """Crée un job à partir d'un fichier vidéo avec analyse complète"""
        try:
            if not os.path.exists(input_video_path):
                self.logger.error(f"Fichier vidéo introuvable: {input_video_path}")
                return None
            
            # Analyse préliminaire du fichier
            self.logger.info(f"Analyse complète du fichier: {Path(input_video_path).name}")
            
            # Estimation de l'espace requis
            space_analysis = self._analyze_video_requirements(input_video_path)
            if not space_analysis['sufficient_space']:
                self.logger.error(f"Espace disque insuffisant: {space_analysis['required_gb']:.1f}GB requis, "
                                f"{space_analysis['available_gb']:.1f}GB disponible")
                return None
            
            # Analyse vidéo détaillée avec sous-titres
            video_info = await self.get_video_info_complete(input_video_path)
            if not video_info:
                self.logger.error("Impossible d'analyser le fichier vidéo")
                return None
            
            # Création du job avec toutes les informations
            job = create_job_from_video_info(input_video_path, video_info)
            
            # Configuration du fichier de sortie
            video_name = Path(input_video_path).stem
            output_path = os.path.join(config.OUTPUT_DIR, f"{video_name}_upscaled_1080p.mp4")
            job.output_video_path = output_path
            
            # Ajout des informations d'estimation
            requirements = self._estimate_processing_requirements(job)
            job.add_log_entry(f"Espace requis estimé: {requirements['disk_space_gb']:.1f}GB")
            job.add_log_entry(f"Temps estimé: {requirements['estimated_time_display']}")
            
            # Vérifications de compatibilité des sous-titres
            if job.has_subtitles:
                compat_report = job.get_subtitle_compatibility_report()
                if compat_report['problematic_tracks']:
                    for issue in compat_report['problematic_tracks']:
                        job.add_warning(f"Sous-titres {issue['track'].get_display_name()}: {issue['recommendation']}")
            
            subtitle_count = len(job.subtitle_tracks)
            self.logger.info(f"Job créé: {job.id[:8]} pour {video_name} "
                           f"({video_info['frame_rate']}fps, "
                           f"audio: {'oui' if job.has_audio else 'non'}, "
                           f"sous-titres: {subtitle_count})")
            return job
            
        except Exception as e:
            self.logger.error(f"Erreur création job: {e}")
            return None
    
    def _analyze_video_requirements(self, video_path: str) -> dict:
        """Analyse les exigences en ressources pour une vidéo"""
        try:
            from utils.file_utils import estimate_video_processing_space
            
            # Utilisation de la fonction d'estimation améliorée
            space_analysis = estimate_video_processing_space(video_path)
            
            if 'error' in space_analysis:
                self.logger.warning(f"Analyse d'espace échouée: {space_analysis['error']}")
                return {
                    'sufficient_space': True,  # Assumé OK si pas d'analyse
                    'required_gb': 0,
                    'available_gb': 0
                }
            
            breakdown = space_analysis.get('space_breakdown', {})
            total_required = breakdown.get('total_required_gb', 0)
            
            # Vérification de l'espace disponible
            import shutil
            free_bytes = shutil.disk_usage(config.WORK_DRIVE).free
            available_gb = free_bytes / (1024**3)
            
            sufficient = available_gb >= (total_required + config.MIN_FREE_SPACE_GB)
            
            return {
                'sufficient_space': sufficient,
                'required_gb': total_required,
                'available_gb': available_gb,
                'breakdown': breakdown,
                'video_info': space_analysis.get('video_info', {})
            }
            
        except Exception as e:
            self.logger.error(f"Erreur analyse exigences: {e}")
            return {'sufficient_space': True, 'required_gb': 0, 'available_gb': 0}
    
    def _estimate_processing_requirements(self, job: Job) -> dict:
        """Estime les ressources nécessaires pour un job"""
        from models.job import estimate_job_requirements
        return estimate_job_requirements(job)
    
    async def get_video_info_complete(self, video_path: str) -> Optional[Dict[str, Any]]:
        """Obtient les informations complètes d'une vidéo incluant les sous-titres avancés"""
        try:
            # Commande ffprobe pour obtenir toutes les informations détaillées
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', '-show_chapters',
                video_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                info = json.loads(result.stdout)
                
                video_stream = None
                audio_streams = []
                subtitle_streams = []
                
                # Analyse de tous les streams avec informations détaillées
                for i, stream in enumerate(info.get('streams', [])):
                    if stream['codec_type'] == 'video' and not video_stream:
                        video_stream = stream
                        
                    elif stream['codec_type'] == 'audio':
                        audio_streams.append({
                            'index': i,
                            'codec': stream.get('codec_name', 'unknown'),
                            'language': stream.get('tags', {}).get('language', 'und'),
                            'title': stream.get('tags', {}).get('title', ''),
                            'channels': stream.get('channels', 0),
                            'sample_rate': stream.get('sample_rate', 0),
                            'bitrate': int(stream.get('bit_rate', 0)) if stream.get('bit_rate') else 0,
                            'duration': float(stream.get('duration', 0)) if stream.get('duration') else 0
                        })
                        
                    elif stream['codec_type'] == 'subtitle':
                        subtitle_data = self._parse_subtitle_stream(stream, i)
                        subtitle_streams.append(subtitle_data)
                
                if video_stream:
                    # Calcul du framerate avec gestion des fractions
                    r_frame_rate = video_stream.get('r_frame_rate', '30/1')
                    if '/' in r_frame_rate:
                        num, den = r_frame_rate.split('/')
                        frame_rate = float(num) / float(den) if float(den) != 0 else 30.0
                    else:
                        frame_rate = float(r_frame_rate)
                    
                    # Informations de format
                    format_info = info.get('format', {})
                    
                    return {
                        'width': int(video_stream.get('width', 0)),
                        'height': int(video_stream.get('height', 0)),
                        'frame_rate': round(frame_rate, 3),
                        'duration': float(format_info.get('duration', 0)),
                        'bitrate': int(format_info.get('bit_rate', 0)) if format_info.get('bit_rate') else 0,
                        'size_bytes': int(format_info.get('size', 0)) if format_info.get('size') else 0,
                        'video_codec': video_stream.get('codec_name', ''),
                        'pixel_format': video_stream.get('pix_fmt', ''),
                        'has_audio': len(audio_streams) > 0,
                        'audio_streams': audio_streams,
                        'subtitles': {
                            'count': len(subtitle_streams),
                            'streams': subtitle_streams
                        },
                        'chapters': info.get('chapters', []),
                        'format_name': format_info.get('format_name', ''),
                        'format_long_name': format_info.get('format_long_name', '')
                    }
            
            return None
            
        except subprocess.TimeoutExpired:
            self.logger.error("Timeout lors de l'analyse vidéo")
            return None
        except Exception as e:
            self.logger.error(f"Erreur analyse vidéo complète: {e}")
            return None
    
    def _parse_subtitle_stream(self, stream: dict, index: int) -> dict:
        """Parse les informations d'un stream de sous-titres"""
        tags = stream.get('tags', {})
        disposition = stream.get('disposition', {})
        
        # Détection améliorée du type de sous-titres
        codec = stream.get('codec_name', 'unknown')
        title = tags.get('title', '')
        language = tags.get('language', 'und')
        
        # Détection des sous-titres pour malentendants
        hearing_impaired = (
            'sdh' in title.lower() or 
            'hearing impaired' in title.lower() or
            'cc' in title.lower() or
            'closed caption' in title.lower()
        )
        
        # Obtention du nom de langue complet si possible
        language_name = self._get_language_name(language)
        
        return {
            'index': index,
            'codec': codec,
            'language': language,
            'language_name': language_name,
            'title': title,
            'forced': disposition.get('forced', 0) == 1,
            'default': disposition.get('default', 0) == 1,
            'hearing_impaired': hearing_impaired,
            'duration': float(stream.get('duration', 0)) if stream.get('duration') else 0
        }
    
    def _get_language_name(self, language_code: str) -> str:
        """Convertit un code langue en nom complet"""
        language_map = {
            'fr': 'Français',
            'en': 'English', 
            'es': 'Español',
            'de': 'Deutsch',
            'it': 'Italiano',
            'pt': 'Português',
            'ru': 'Русский',
            'ja': '日本語',
            'ko': '한국어',
            'zh': '中文',
            'ar': 'العربية',
            'und': 'Indéterminé'
        }
        return language_map.get(language_code.lower(), language_code.upper())
    
    def _estimate_subtitle_events(self, video_path: str, stream_index: int, duration: float) -> int:
        """Estime le nombre d'événements de sous-titres"""
        # Estimation basique basée sur la durée
        # En moyenne 2-3 événements par minute pour des dialogues normaux
        if duration > 0:
            return int(duration / 60 * 2.5)
        return 0
    
    async def extract_frames(self, job: Job) -> bool:
        """Extrait les frames d'une vidéo avec optimisations et extraction des sous-titres"""
        try:
            job.status = JobStatus.EXTRACTING
            self.logger.info(f"Extraction des frames pour le job {job.id}")
            
            # Préparation des dossiers
            frames_dir = Path(config.TEMP_DIR) / f"job_{job.id}_frames"
            upscaled_dir = Path(config.TEMP_DIR) / f"job_{job.id}_upscaled"
            
            ensure_dir(frames_dir)
            ensure_dir(upscaled_dir)
            
            # Construction de la commande FFmpeg optimisée
            ffmpeg_cmd = self._build_optimized_ffmpeg_extract_command(
                job.input_video_path, 
                frames_dir
            )
            
            self.logger.debug(f"Commande FFmpeg: {' '.join(ffmpeg_cmd)}")
            
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
                await self._extract_audio_optimized(job)
            
            # Extraction des sous-titres si présents
            if job.has_subtitles:
                await self._extract_all_subtitles(job)
            
            # Création des lots avec taille optimisée
            frame_paths = [str(f) for f in sorted(frame_files)]
            optimal_batch_size = optimized_realesrgan.get_optimal_batch_size()
            
            # Utilisation de la taille optimale pour ce job spécifique
            batches = self.server.batch_manager.create_batches_from_frames(
                job, frame_paths, batch_size=optimal_batch_size
            )
            job.batches = [batch.id for batch in batches]
            
            job.start()
            subtitle_count = len(job.subtitle_tracks)
            self.logger.info(f"Extraction terminée: {job.total_frames} frames, {len(batches)} lots "
                           f"(taille optimale: {optimal_batch_size}), {subtitle_count} sous-titres")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur extraction frames: {e}")
            job.fail(str(e))
            return False
    
    def _build_optimized_ffmpeg_extract_command(self, input_path: str, output_dir: Path) -> List[str]:
        """Construit une commande FFmpeg optimisée pour l'extraction"""
        cmd = ["ffmpeg", "-i", input_path]
        
        # Optimisations selon le matériel
        system_status = optimized_realesrgan.get_system_status()
        
        # Utilisation de threads optimaux
        threads = config.FFMPEG_THREADS
        if system_status.get('is_laptop', False):
            threads = min(threads, 8)  # Limitation laptop
        cmd.extend(["-threads", str(threads)])
        
        # Qualité d'extraction optimisée
        cmd.extend(["-q:v", "1"])  # Qualité maximale
        
        # Format de sortie
        cmd.extend([str(output_dir / "frame_%06d.png")])
        
        # Options de performance
        cmd.extend(["-loglevel", "error"])  # Moins de logs pour performance
        
        return cmd
    
    async def _extract_audio_optimized(self, job: Job) -> bool:
        """Extrait l'audio avec optimisations"""
        try:
            audio_path = Path(config.TEMP_DIR) / f"job_{job.id}_audio.aac"
            
            # Tentative d'extraction en AAC avec optimisations
            ffmpeg_cmd = [
                "ffmpeg", "-i", job.input_video_path,
                "-vn", "-acodec", "aac", "-b:a", "192k",
                "-threads", str(min(config.FFMPEG_THREADS, 4)),
                str(audio_path), "-loglevel", "error"
            ]
            
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            
            if process.returncode == 0 and audio_path.exists():
                job.media_info.audio_extraction_path = str(audio_path)
                job.add_log_entry("✅ Audio extrait (AAC)")
                return True
            
            # Tentative alternative en WAV
            audio_path_wav = Path(config.TEMP_DIR) / f"job_{job.id}_audio.wav"
            ffmpeg_cmd_wav = [
                "ffmpeg", "-i", job.input_video_path,
                "-vn", "-acodec", "pcm_s16le",
                "-threads", str(min(config.FFMPEG_THREADS, 4)),
                str(audio_path_wav), "-loglevel", "error"
            ]
            
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd_wav,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            
            if process.returncode == 0 and audio_path_wav.exists():
                job.media_info.audio_extraction_path = str(audio_path_wav)
                job.add_log_entry("✅ Audio extrait (WAV)")
                return True
            
            job.add_warning("Impossible d'extraire l'audio")
            return False
            
        except Exception as e:
            self.logger.error(f"Erreur extraction audio: {e}")
            job.add_warning(f"Erreur extraction audio: {e}")
            return False
    
    async def _extract_all_subtitles(self, job: Job) -> bool:
        """Extrait tous les sous-titres de la vidéo"""
        try:
            if not job.has_subtitles or not job.subtitle_tracks:
                return True
            
            job.add_log_entry(f"Extraction de {len(job.subtitle_tracks)} piste(s) de sous-titres")
            
            success_count = 0
            for track in job.subtitle_tracks:
                if await self._extract_single_subtitle_track(job, track):
                    success_count += 1
            
            job.add_log_entry(f"Extraction sous-titres terminée: {success_count}/{len(job.subtitle_tracks)}")
            return success_count > 0
            
        except Exception as e:
            self.logger.error(f"Erreur extraction sous-titres: {e}")
            job.add_warning(f"Erreur extraction sous-titres: {e}")
            return False
    
    async def _extract_single_subtitle_track(self, job: Job, track: SubtitleTrack) -> bool:
        """Extrait une piste de sous-titres spécifique"""
        try:
            # Déterminer l'extension selon le codec
            ext = self._get_subtitle_extension(track.codec)
            
            # Chemin de sortie pour ce sous-titre
            subtitle_path = Path(config.TEMP_DIR) / f"job_{job.id}_subtitle_{track.index}_{track.language}.{ext}"
            
            # Commande FFmpeg pour extraire ce sous-titre
            cmd = [
                "ffmpeg", "-i", job.input_video_path,
                "-map", f"0:s:{track.index}",
                "-c", "copy" if ext != 'srt' else 'srt',
                str(subtitle_path),
                "-loglevel", "error"
            ]
            
            # Si le codec n'est pas compatible, essayer de convertir en SRT
            if track.codec not in ['subrip', 'srt'] and ext == 'srt':
                cmd[cmd.index("-c")+1] = "srt"
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0 and subtitle_path.exists():
                track.extracted = True
                track.extraction_path = str(subtitle_path)
                track.extraction_format = ext
                
                # Mise à jour des informations du fichier
                file_size = subtitle_path.stat().st_size
                if file_size > 0:
                    job.add_log_entry(f"✅ Sous-titre extrait: {track.get_display_name()} -> {subtitle_path.name}")
                    return True
                else:
                    track.extraction_error = "Fichier vide"
                    job.add_warning(f"Fichier de sous-titres vide: {track.get_display_name()}")
            else:
                error_msg = stderr.decode() if stderr else "Erreur inconnue"
                track.extraction_error = error_msg
                job.add_warning(f"Échec extraction {track.get_display_name()}: {error_msg}")
            
            return False
            
        except Exception as e:
            track.extraction_error = str(e)
            job.add_warning(f"Erreur extraction {track.get_display_name()}: {e}")
            return False
    
    def _get_subtitle_extension(self, codec: str) -> str:
        """Détermine l'extension de fichier selon le codec"""
        codec_ext_map = {
            'subrip': 'srt',
            'srt': 'srt',
            'ass': 'ass',
            'ssa': 'ssa',
            'webvtt': 'vtt',
            'dvd_subtitle': 'sub',
            'dvdsub': 'sub',
            'hdmv_pgs_subtitle': 'sup',
            'mov_text': 'srt',
            'text': 'srt'
        }
        return codec_ext_map.get(codec.lower(), 'srt')  # Fallback vers SRT
    
    async def assemble_video(self, job: Job) -> bool:
        """Assemble la vidéo finale à partir des frames upscalées avec audio et sous-titres"""
        try:
            self.logger.info(f"Assemblage de la vidéo pour le job {job.id}")
            
            upscaled_dir = Path(config.TEMP_DIR) / f"job_{job.id}_upscaled"
            
            # Vérification que tous les frames upscalés sont présents
            if not await self._verify_upscaled_frames(job, upscaled_dir):
                self.logger.error("Frames upscalés manquants")
                return False
            
            # Construction de la commande FFmpeg optimisée avec sous-titres
            ffmpeg_cmd = self._build_advanced_ffmpeg_assemble_command(job, upscaled_dir)
            
            self.logger.debug(f"Commande assemblage: {' '.join(ffmpeg_cmd)}")
            
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
            
            # Vérifications post-assemblage
            await self._post_assembly_verifications(job)
            
            # Nettoyage des fichiers temporaires
            await self._cleanup_job_files(job)
            
            extracted_count = len(job.get_extracted_subtitle_tracks())
            self.logger.info(f"Assemblage terminé: {job.output_video_path} "
                           f"(audio: {'oui' if job.has_audio else 'non'}, "
                           f"sous-titres: {extracted_count})")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur assemblage vidéo: {e}")
            return False
    
    def _build_advanced_ffmpeg_assemble_command(self, job: Job, upscaled_dir: Path) -> List[str]:
        """Construit la commande FFmpeg avancée pour l'assemblage avec sous-titres"""
        cmd = ["ffmpeg"]
        
        # Entrée vidéo (frames upscalées)
        cmd.extend(["-framerate", str(job.frame_rate)])
        cmd.extend(["-i", str(upscaled_dir / "frame_%06d.png")])
        
        input_count = 1
        
        # Ajout de l'audio si présent
        audio_path = getattr(job.media_info, 'audio_extraction_path', '')
        if job.has_audio and audio_path and Path(audio_path).exists():
            cmd.extend(["-i", audio_path])
            input_count += 1
        
        # Ajout des sous-titres extraits comme fichiers séparés
        subtitle_inputs = []
        extracted_subtitles = job.get_extracted_subtitle_tracks()
        
        for subtitle in extracted_subtitles:
            if subtitle.extraction_path and Path(subtitle.extraction_path).exists():
                cmd.extend(["-i", subtitle.extraction_path])
                subtitle_inputs.append(subtitle)
                input_count += 1
        
        # Mapping des streams
        cmd.extend(["-map", "0:v:0"])  # Stream vidéo
        
        if job.has_audio and audio_path:
            cmd.extend(["-map", f"1:a:0"])  # Stream audio
        
        # Mapping des sous-titres
        for i, subtitle in enumerate(subtitle_inputs):
            audio_offset = 1 if (job.has_audio and audio_path) else 0
            subtitle_input_index = 1 + audio_offset + i
            cmd.extend(["-map", f"{subtitle_input_index}:s:0"])
        
        # Configuration vidéo optimisée
        cmd.extend(["-c:v", "libx264"])
        cmd.extend(["-crf", str(job.processing_settings.crf)])
        cmd.extend(["-pix_fmt", "yuv420p"])
        cmd.extend(["-threads", str(config.FFMPEG_THREADS)])
        cmd.extend(["-vsync", "cfr"])
        cmd.extend(["-preset", job.processing_settings.preset])
        
        # Optimisations x264 selon le matériel
        system_status = optimized_realesrgan.get_system_status()
        
        if system_status.get('is_laptop', False):
            # Optimisations laptop
            cmd.extend(["-x264-params", "ref=2:bframes=1:subme=6:me=hex"])
        elif system_status.get('cpu_cores', 8) >= 16:
            # CPU puissant, optimisations avancées
            cmd.extend(["-x264-params", "ref=4:bframes=3:subme=8:me=umh"])
        
        # Configuration audio
        if job.has_audio and audio_path:
            cmd.extend(["-c:a", "aac"])
            cmd.extend(["-b:a", f"{job.processing_settings.audio_bitrate_kbps}k"])
            cmd.extend(["-async", "1"])
        
        # Configuration des sous-titres
        if subtitle_inputs:
            # Codec pour les sous-titres (mov_text pour MP4)
            cmd.extend(["-c:s", job.processing_settings.subtitle_format])
            
            # Métadonnées pour chaque piste de sous-titres
            for i, subtitle in enumerate(subtitle_inputs):
                if subtitle.language and subtitle.language != 'unknown':
                    cmd.extend([f"-metadata:s:s:{i}", f"language={subtitle.language}"])
                
                if subtitle.title:
                    cmd.extend([f"-metadata:s:s:{i}", f"title={subtitle.title}"])
                
                # Gestion des dispositions
                if subtitle.default:
                    cmd.extend([f"-disposition:s:s:{i}", "default"])
                elif subtitle.forced:
                    cmd.extend([f"-disposition:s:s:{i}", "forced"])
                else:
                    cmd.extend([f"-disposition:s:s:{i}", "0"])
        
        # Options avancées
        if job.processing_settings.enable_deinterlacing:
            cmd.extend(["-vf", "yadif"])
        
        # Fichier de sortie
        cmd.extend([job.output_video_path])
        cmd.extend(["-loglevel", "warning", "-stats"])
        
        return cmd
    
    async def _verify_upscaled_frames(self, job: Job, upscaled_dir: Path) -> bool:
        """Vérifie que les frames upscalés sont disponibles"""
        expected_frames = job.total_frames
        upscaled_frames = list(upscaled_dir.glob("frame_*.png"))
        
        if len(upscaled_frames) < expected_frames:
            completion_rate = len(upscaled_frames) / expected_frames if expected_frames > 0 else 0
            job.add_log_entry(f"⚠️ Frames manquants: {len(upscaled_frames)}/{expected_frames} ({completion_rate*100:.1f}%)")
            
            # Vérification de la complétude (au moins 90%)
            if completion_rate < 0.9:
                job.add_warning(f"Trop de frames manquants: {completion_rate*100:.1f}% seulement")
                return False
            else:
                job.add_warning(f"Frames manquants acceptables: {completion_rate*100:.1f}%")
        
        return len(upscaled_frames) > 0
    
    async def _post_assembly_verifications(self, job: Job):
        """Effectue les vérifications post-assemblage"""
        try:
            # Vérification de la durée de la vidéo
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
                expected_duration = job.total_frames / job.frame_rate
                diff = abs(duration - expected_duration)
                
                job.add_log_entry(f"Durée vidéo finale: {duration:.2f}s (attendu: {expected_duration:.2f}s)")
                
                if diff > 2.0:  # Plus de 2 secondes de différence
                    job.add_warning(f"Décalage durée significatif: {diff:.2f}s")
                else:
                    job.add_log_entry("✅ Durée vidéo cohérente")
            
            # Vérification des sous-titres intégrés
            if job.get_extracted_subtitle_tracks():
                await self._verify_integrated_subtitles(job)
            
        except Exception as e:
            job.add_warning(f"Erreur vérifications post-assemblage: {e}")
            self.logger.warning(f"Erreur vérifications post-assemblage: {e}")
    
    async def _verify_integrated_subtitles(self, job: Job):
        """Vérifie que les sous-titres ont été correctement intégrés"""
        try:
            ffprobe_cmd = [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_streams", "-select_streams", "s",
                job.output_video_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *ffprobe_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                data = json.loads(stdout.decode())
                integrated_subtitles = data.get('streams', [])
                
                expected_count = len(job.get_extracted_subtitle_tracks())
                actual_count = len(integrated_subtitles)
                
                if actual_count == expected_count:
                    job.add_log_entry(f"✅ {actual_count} piste(s) de sous-titres intégrée(s)")
                else:
                    job.add_warning(f"Sous-titres intégrés: {actual_count}/{expected_count}")
                
                # Vérification des métadonnées des sous-titres
                for i, stream in enumerate(integrated_subtitles):
                    lang = stream.get('tags', {}).get('language', 'unknown')
                    codec = stream.get('codec_name', 'unknown')
                    job.add_log_entry(f"  Piste {i+1}: {lang} ({codec})")
            else:
                job.add_warning("Impossible de vérifier l'intégration des sous-titres")
                
        except Exception as e:
            job.add_warning(f"Erreur vérification sous-titres intégrés: {e}")
    
    async def _cleanup_job_files(self, job: Job):
        """Nettoie les fichiers temporaires d'un job"""
        try:
            temp_dirs = [
                Path(config.TEMP_DIR) / f"job_{job.id}_frames",
                Path(config.TEMP_DIR) / f"job_{job.id}_upscaled"
            ]
            
            temp_files = []
            
            # Fichiers audio
            audio_path = getattr(job.media_info, 'audio_extraction_path', '')
            if audio_path:
                temp_files.append(Path(audio_path))
            
            # Fichiers de sous-titres
            for track in job.subtitle_tracks:
                if track.extraction_path:
                    temp_files.append(Path(track.extraction_path))
            
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
            
            job.add_log_entry("🧹 Fichiers temporaires nettoyés")
            
        except Exception as e:
            self.logger.warning(f"Erreur nettoyage fichiers temporaires: {e}")
            job.add_warning(f"Erreur nettoyage: {e}")
    
    # Méthodes utilitaires pour les sous-titres
    
    def get_supported_subtitle_formats(self) -> List[str]:
        """Retourne la liste des formats de sous-titres supportés"""
        return [
            'srt',     # SubRip Text (le plus compatible)
            'ass',     # Advanced SubStation Alpha 
            'ssa',     # SubStation Alpha
            'vtt',     # WebVTT
            'mov_text',# MP4 Timed Text
            'sub',     # MicroDVD/DVD Subtitle
            'sup',     # Blu-ray PGS (image)
            'idx',     # VobSub (image + index)
            'smi',     # SAMI
            'ttml',    # Timed Text Markup Language
            'dfxp'     # Distribution Format Exchange Profile
        ]
    
    def analyze_subtitle_compatibility(self, job: Job) -> Dict[str, Any]:
        """Analyse la compatibilité des sous-titres avec le format de sortie MP4"""
        if not job.has_subtitles:
            return {
                'compatible': True,
                'total_tracks': 0,
                'compatible_tracks': 0,
                'warnings': [],
                'recommendations': []
            }
        
        warnings = []
        recommendations = []
        compatible_tracks = []
        
        for track in job.subtitle_tracks:
            if track.is_compatible_with_mp4():
                compatible_tracks.append(track)
            else:
                warnings.append(f"{track.get_display_name()}: {track.get_conversion_recommendation()}")
        
        # Recommandations générales
        if not any(track.default for track in job.subtitle_tracks):
            recommendations.append("Considérer marquer une piste comme défaut")
        
        languages = set(track.language for track in job.subtitle_tracks if track.language != "unknown")
        if len(languages) > 3:
            recommendations.append(f"Nombreuses langues détectées ({len(languages)})")
        
        return {
            'compatible': len(compatible_tracks) > 0,
            'total_tracks': len(job.subtitle_tracks),
            'compatible_tracks': len(compatible_tracks),
            'extracted_tracks': len(job.get_extracted_subtitle_tracks()),
            'warnings': warnings,
            'recommendations': recommendations,
            'languages': list(languages)
        }
    
    async def create_subtitle_preview(self, job: Job) -> Optional[str]:
        """Crée un aperçu textuel des sous-titres"""
        if not job.has_subtitles:
            return None
        
        try:
            preview_lines = []
            preview_lines.append(f"=== SOUS-TITRES - JOB {job.id[:8]} ===")
            preview_lines.append(f"Fichier source: {Path(job.input_video_path).name}")
            preview_lines.append(f"Pistes détectées: {len(job.subtitle_tracks)}")
            preview_lines.append("")
            
            for i, track in enumerate(job.subtitle_tracks):
                status_icon = "✅" if track.extracted else "❌" if track.extraction_error else "⏳"
                preview_lines.append(f"{i+1}. {status_icon} {track.get_display_name()}")
                preview_lines.append(f"   Codec: {track.codec}")
                
                if track.extracted:
                    preview_lines.append(f"   Fichier: {Path(track.extraction_path).name}")
                    if track.frame_count > 0:
                        preview_lines.append(f"   Événements: {track.frame_count}")
                    if track.duration_ms > 0:
                        duration_str = f"{track.duration_ms // 60000}:{(track.duration_ms % 60000) // 1000:02d}"
                        preview_lines.append(f"   Durée: {duration_str}")
                elif track.extraction_error:
                    preview_lines.append(f"   ❌ Erreur: {track.extraction_error}")
                
                preview_lines.append("")
            
            # Analyse de compatibilité
            compat = self.analyze_subtitle_compatibility(job)
            if compat['warnings']:
                preview_lines.append("⚠️  AVERTISSEMENTS:")
                for warning in compat['warnings']:
                    preview_lines.append(f"   - {warning}")
                preview_lines.append("")
            
            if compat['recommendations']:
                preview_lines.append("💡 RECOMMANDATIONS:")
                for rec in compat['recommendations']:
                    preview_lines.append(f"   - {rec}")
                preview_lines.append("")
            
            preview_lines.append(f"Résumé: {len(compat['compatible_tracks'])}/{compat['total_tracks']} pistes compatibles MP4")
            
            return "\n".join(preview_lines)
            
        except Exception as e:
            self.logger.error(f"Erreur création aperçu sous-titres: {e}")
            return f"Erreur lors de la création de l'aperçu: {str(e)}"
    
    async def export_subtitle_tracks(self, job: Job, output_directory: str) -> Dict[str, Any]:
        """Exporte toutes les pistes de sous-titres extraites"""
        if not job.has_subtitles:
            return {'success': False, 'error': 'Aucun sous-titre à exporter'}
        
        try:
            output_dir = Path(output_directory)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            exported_files = []
            errors = []
            
            base_name = Path(job.input_video_path).stem
            
            for track in job.get_extracted_subtitle_tracks():
                try:
                    if not track.extraction_path or not Path(track.extraction_path).exists():
                        errors.append(f"{track.get_display_name()}: Fichier source introuvable")
                        continue
                    
                    # Nom de fichier pour l'export
                    export_filename = track.get_filename(base_name)
                    export_path = output_dir / export_filename
                    
                    # Copie du fichier
                    shutil.copy2(track.extraction_path, export_path)
                    exported_files.append({
                        'track': track.get_display_name(),
                        'filename': export_filename,
                        'language': track.language,
                        'format': track.extraction_format
                    })
                    
                except Exception as e:
                    errors.append(f"{track.get_display_name()}: {str(e)}")
            
            return {
                'success': len(exported_files) > 0,
                'exported_count': len(exported_files),
                'total_count': len(job.get_extracted_subtitle_tracks()),
                'exported_files': exported_files,
                'errors': errors,
                'output_directory': str(output_dir)
            }
            
        except Exception as e:
            return {'success': False, 'error': f"Erreur export: {str(e)}"}
    
    def validate_subtitle_files(self, job: Job) -> Dict[str, Any]:
        """Valide l'intégrité des fichiers de sous-titres extraits"""
        validation_results = {
            'valid_files': [],
            'invalid_files': [],
            'missing_files': [],
            'total_tracks': len(job.subtitle_tracks),
            'validation_passed': True
        }
        
        for track in job.subtitle_tracks:
            if not track.extracted:
                continue
                
            if not track.extraction_path:
                validation_results['missing_files'].append({
                    'track': track.get_display_name(),
                    'issue': 'Chemin d\'extraction manquant'
                })
                continue
            
            file_path = Path(track.extraction_path)
            
            if not file_path.exists():
                validation_results['missing_files'].append({
                    'track': track.get_display_name(),
                    'path': str(file_path),
                    'issue': 'Fichier introuvable'
                })
                validation_results['validation_passed'] = False
                continue
            
            # Vérification de la taille
            file_size = file_path.stat().st_size
            if file_size == 0:
                validation_results['invalid_files'].append({
                    'track': track.get_display_name(),
                    'path': str(file_path),
                    'issue': 'Fichier vide'
                })
                validation_results['validation_passed'] = False
                continue
            
            # Vérification du format
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read(1000)  # Lire les premiers 1000 caractères
                
                # Validation basique selon le format
                if track.extraction_format == 'srt':
                    if not re.search(r'^\d+', content, re.MULTILINE):
                        raise ValueError("Format SRT invalide")
                elif track.extraction_format == 'ass':
                    if '[Script Info]' not in content:
                        raise ValueError("Format ASS invalide")
                elif track.extraction_format == 'webvtt':
                    if not content.startswith('WEBVTT'):
                        raise ValueError("Format WebVTT invalide")
                
                validation_results['valid_files'].append({
                    'track': track.get_display_name(),
                    'path': str(file_path),
                    'size_bytes': file_size,
                    'format': track.extraction_format
                })
                
            except Exception as e:
                validation_results['invalid_files'].append({
                    'track': track.get_display_name(),
                    'path': str(file_path),
                    'issue': f'Contenu invalide: {str(e)}'
                })
                validation_results['validation_passed'] = False
        
        return validation_results
    
    async def repair_subtitle_extraction(self, job: Job, track_index: int) -> bool:
        """Tente de réparer l'extraction d'une piste de sous-titres échouée"""
        if track_index < 0 or track_index >= len(job.subtitle_tracks):
            return False
        
        track = job.subtitle_tracks[track_index]
        
        if track.extracted:
            return True  # Déjà extrait avec succès
        
        job.add_log_entry(f"Tentative de réparation: {track.get_display_name()}")
        
        try:
            # Réinitialiser les informations d'extraction
            track.extracted = False
            track.extraction_path = ""
            track.extraction_error = ""
            
            # Nouvelle tentative d'extraction avec paramètres plus permissifs
            success = await self._extract_single_subtitle_track(job, track)
            
            if success:
                job.add_log_entry(f"✅ Réparation réussie: {track.get_display_name()}")
                return True
            else:
                job.add_log_entry(f"❌ Réparation échouée: {track.get_display_name()}")
                return False
                
        except Exception as e:
            job.add_log_entry(f"❌ Erreur réparation {track.get_display_name()}: {e}")
            return False
    
    def get_processing_statistics(self, job: Job) -> Dict[str, Any]:
        """Retourne les statistiques détaillées de traitement"""
        processing_summary = job.get_processing_summary()
        
        # Ajout de statistiques spécifiques au processeur vidéo
        video_stats = {
            'extraction_success': job.status.value != "failed" and job.total_frames > 0,
            'frames_extracted': job.total_frames,
            'audio_extraction_success': job.has_audio and bool(getattr(job.media_info, 'audio_extraction_path', '')),
            'subtitle_extraction_summary': {
                'total_detected': len(job.subtitle_tracks),
                'successfully_extracted': len(job.get_extracted_subtitle_tracks()),
                'extraction_rate': len(job.get_extracted_subtitle_tracks()) / len(job.subtitle_tracks) * 100 if job.subtitle_tracks else 0,
                'languages_extracted': list(set(track.language for track in job.get_extracted_subtitle_tracks() if track.language != "unknown"))
            }
        }
        
        # Fusion avec le résumé existant
        processing_summary['video_processing'] = video_stats
        
        return processing_summary
    
    def get_optimization_recommendations(self, job: Job) -> List[str]:
        """Génère des recommandations d'optimisation pour le traitement vidéo"""
        recommendations = []
        
        # Analyse de la résolution
        if job.media_info.width * job.media_info.height > 1920 * 1080:
            recommendations.append("Vidéo haute résolution détectée - Temps de traitement prolongé attendu")
        
        # Analyse du framerate
        if job.frame_rate > 30:
            recommendations.append(f"Framerate élevé ({job.frame_rate}fps) - Impact sur le temps de traitement")
        
        # Analyse de la durée
        if job.media_info.duration_seconds > 3600:  # Plus d'1 heure
            recommendations.append("Vidéo longue détectée - Considérer le traitement en plusieurs sessions")
        
        # Analyse des sous-titres
        if len(job.subtitle_tracks) > 5:
            recommendations.append("Nombreuses pistes de sous-titres - Sélectionner seulement celles nécessaires")
        
        # Recommandations basées sur les erreurs
        if job.warnings:
            recommendations.append("Avertissements détectés - Vérifier la configuration avant traitement")
        
        return recommendations
    
    # Méthode de compatibilité pour l'ancien code
    async def get_video_info(self, video_path: str) -> Optional[dict]:
        """Version simple pour compatibilité (wrapper vers get_video_info_complete)"""
        complete_info = await self.get_video_info_complete(video_path)
        if not complete_info:
            return None
        
        # Retourne une version simplifiée pour compatibilité
        return {
            "frame_rate": complete_info.get('frame_rate', 30.0),
            "has_audio": complete_info.get('has_audio', False),
            "width": complete_info.get('width', 0),
            "height": complete_info.get('height', 0),
            "duration": complete_info.get('duration', 0),
            "video_codec": complete_info.get('video_codec', ''),
            "has_subtitles": complete_info.get('subtitles', {}).get('count', 0) > 0
        }