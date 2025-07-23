"""
Processeur vidéo optimisé avec détection automatique du matériel et gestion des sous-titres
"""

import os
import subprocess
import asyncio
import shutil
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
import re
import json

from models.job import Job, JobStatus
from models.batch import Batch
from config.settings import config
from utils.logger import get_logger
from utils.file_utils import ensure_dir, get_video_info
from core.optimized_real_esrgan import optimized_realesrgan
from utils.hardware_detector import hardware_detector

class VideoProcessor:
    """Gestionnaire du traitement vidéo optimisé avec gestion des sous-titres"""
    
    def __init__(self, server):
        self.server = server
        self.logger = get_logger(__name__)
        
        # Initialisation des optimisations matérielles
        self._initialize_hardware_optimizations()
    
    def _initialize_hardware_optimizations(self):
        """Initialise les optimisations basées sur le matériel détecté"""
        try:
            # Récupération du statut système
            system_status = optimized_realesrgan.get_system_status()
            
            if system_status['system_detected']:
                self.logger.info("Optimisations matérielles activées")
                
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
                    config.FFMPEG_CRF = min(config.FFMPEG_CRF + 2, 28)  # CRF plus élevé = moins de calcul
                    config.FFMPEG_PRESET = "fast"  # Preset plus rapide
                    self.logger.info("Ajustements laptop appliqués (CRF +2, preset fast)")
                
            else:
                self.logger.warning("Détection matérielle échouée, utilisation des paramètres par défaut")
                
        except Exception as e:
            self.logger.error(f"Erreur initialisation optimisations: {e}")
    
    async def create_job_from_video(self, input_video_path: str) -> Optional[Job]:
        """Crée un job à partir d'un fichier vidéo avec analyse optimisée et gestion sous-titres"""
        try:
            if not os.path.exists(input_video_path):
                self.logger.error(f"Fichier vidéo introuvable: {input_video_path}")
                return None
            
            # Analyse préliminaire du fichier
            self.logger.info(f"Analyse du fichier: {Path(input_video_path).name}")
            
            # Estimation de l'espace requis avec la fonction améliorée
            space_analysis = self._analyze_video_requirements(input_video_path)
            if not space_analysis['sufficient_space']:
                self.logger.error(f"Espace disque insuffisant: {space_analysis['required_gb']:.1f}GB requis, "
                                f"{space_analysis['available_gb']:.1f}GB disponible")
                return None
            
            # Création du job
            video_name = Path(input_video_path).stem
            output_path = os.path.join(config.OUTPUT_DIR, f"{video_name}_upscaled_1080p.mp4")
            
            job = Job(
                input_video_path=input_video_path,
                output_video_path=output_path
            )
            
            # Analyse vidéo détaillée avec sous-titres
            video_info = await self.get_video_info_complete(input_video_path)
            if not video_info:
                return None
            
            job.frame_rate = video_info["frame_rate"]
            job.has_audio = video_info["has_audio"]
            
            # Ajout des informations sur les sous-titres
            if not hasattr(job, 'subtitle_info'):
                # Si le modèle Job n'a pas subtitle_info, on l'ajoute dynamiquement
                job.subtitle_info = video_info.get("subtitles", {})
                job.has_subtitles = len(job.subtitle_info.get("streams", [])) > 0
            
            # Estimation du temps de traitement basée sur le matériel
            estimated_time = self._estimate_processing_time(video_info, space_analysis)
            self.logger.info(f"Temps de traitement estimé: {estimated_time // 60:.0f}min {estimated_time % 60:.0f}s")
            
            subtitle_count = len(job.subtitle_info.get("streams", []))
            self.logger.info(f"Job créé: {job.id} pour {video_name} ({video_info['frame_rate']}fps, "
                           f"audio: {'oui' if job.has_audio else 'non'}, "
                           f"sous-titres: {subtitle_count})")
            return job
            
        except Exception as e:
            self.logger.error(f"Erreur création job: {e}")
            return None
    
    async def get_video_info_complete(self, video_path: str) -> Optional[Dict[str, Any]]:
        """Obtient les informations complètes d'une vidéo incluant les sous-titres"""
        try:
            # Commande ffprobe pour obtenir toutes les informations
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', video_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                info = json.loads(result.stdout)
                
                video_stream = None
                audio_streams = []
                subtitle_streams = []
                
                # Analyse de tous les streams
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
                            'sample_rate': stream.get('sample_rate', 0)
                        })
                    elif stream['codec_type'] == 'subtitle':
                        subtitle_streams.append({
                            'index': i,
                            'codec': stream.get('codec_name', 'unknown'),
                            'language': stream.get('tags', {}).get('language', 'und'),
                            'title': stream.get('tags', {}).get('title', ''),
                            'forced': stream.get('disposition', {}).get('forced', 0) == 1,
                            'default': stream.get('disposition', {}).get('default', 0) == 1
                        })
                
                if video_stream:
                    # Calcul du framerate
                    r_frame_rate = video_stream.get('r_frame_rate', '30/1')
                    if '/' in r_frame_rate:
                        num, den = r_frame_rate.split('/')
                        frame_rate = float(num) / float(den) if float(den) != 0 else 30.0
                    else:
                        frame_rate = float(r_frame_rate)
                    
                    return {
                        'width': int(video_stream.get('width', 0)),
                        'height': int(video_stream.get('height', 0)),
                        'frame_rate': round(frame_rate, 3),
                        'duration': float(info['format'].get('duration', 0)),
                        'has_audio': len(audio_streams) > 0,
                        'video_codec': video_stream.get('codec_name', ''),
                        'audio_streams': audio_streams,
                        'subtitles': {
                            'count': len(subtitle_streams),
                            'streams': subtitle_streams
                        }
                    }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Erreur analyse vidéo complète: {e}")
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
    
    def _estimate_processing_time(self, video_info: dict, space_analysis: dict) -> int:
        """Estime le temps de traitement basé sur le matériel et la vidéo"""
        base_frames = space_analysis.get('video_info', {}).get('total_frames', 1000)
        
        # Temps de base par frame (en secondes)
        base_time_per_frame = 0.5  # 0.5s par frame par défaut
        
        try:
            system_status = optimized_realesrgan.get_system_status()
            
            if system_status['system_detected']:
                # Ajustement selon le GPU
                if system_status['gpu_count'] > 0:
                    gpu = system_status['gpus'][0]
                    
                    if gpu['tier'] == 'extreme':
                        base_time_per_frame *= 0.3  # 70% plus rapide
                    elif gpu['tier'] == 'high':
                        base_time_per_frame *= 0.5  # 50% plus rapide
                    elif gpu['tier'] == 'medium':
                        base_time_per_frame *= 0.8  # 20% plus rapide
                    else:  # low
                        base_time_per_frame *= 1.5  # 50% plus lent
                else:
                    base_time_per_frame *= 3.0  # CPU uniquement, beaucoup plus lent
                
                # Ajustement selon la VRAM
                if system_status['gpu_count'] > 0:
                    vram_mb = system_status['gpus'][0]['memory_mb']
                    if vram_mb >= 16384:  # >= 16GB
                        base_time_per_frame *= 0.8
                    elif vram_mb <= 4096:  # <= 4GB
                        base_time_per_frame *= 1.3
                
                # Ajustement laptop (thermique)
                if system_status.get('is_laptop', False):
                    base_time_per_frame *= 1.2
            
        except Exception as e:
            self.logger.debug(f"Erreur estimation temps: {e}")
        
        total_seconds = int(base_frames * base_time_per_frame)
        return max(total_seconds, 60)  # Minimum 1 minute
    
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
            if hasattr(job, 'subtitle_info') and job.subtitle_info.get('count', 0) > 0:
                await self._extract_subtitles(job)
            
            # Création des lots avec taille optimisée
            frame_paths = [str(f) for f in sorted(frame_files)]
            optimal_batch_size = optimized_realesrgan.get_optimal_batch_size()
            
            # Utilisation de la taille optimale pour ce job spécifique
            batches = self.server.batch_manager.create_batches_from_frames(
                job, frame_paths, batch_size=optimal_batch_size
            )
            job.batches = [batch.id for batch in batches]
            
            job.start()
            subtitle_count = job.subtitle_info.get('count', 0) if hasattr(job, 'subtitle_info') else 0
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
                "-threads", str(min(config.FFMPEG_THREADS, 4)),  # Audio n'a pas besoin de beaucoup de threads
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
    
    async def _extract_subtitles(self, job: Job) -> bool:
        """Extrait tous les sous-titres de la vidéo"""
        try:
            if not hasattr(job, 'subtitle_info') or job.subtitle_info.get('count', 0) == 0:
                return True
            
            self.logger.info(f"Extraction de {job.subtitle_info['count']} pistes de sous-titres")
            
            job.subtitle_paths = []
            
            for subtitle_stream in job.subtitle_info['streams']:
                stream_index = subtitle_stream['index']
                language = subtitle_stream.get('language', 'und')
                codec = subtitle_stream.get('codec', 'unknown')
                
                # Déterminer l'extension selon le codec
                if codec in ['subrip', 'srt']:
                    ext = 'srt'
                elif codec in ['ass', 'ssa']:
                    ext = 'ass'
                elif codec in ['webvtt']:
                    ext = 'vtt'
                elif codec in ['dvd_subtitle', 'dvdsub']:
                    ext = 'sub'
                elif codec in ['hdmv_pgs_subtitle']:
                    ext = 'sup'
                else:
                    ext = 'srt'  # Fallback vers SRT
                
                # Chemin de sortie pour ce sous-titre
                subtitle_path = Path(config.TEMP_DIR) / f"job_{job.id}_subtitle_{stream_index}_{language}.{ext}"
                
                try:
                    # Commande FFmpeg pour extraire ce sous-titre
                    cmd = [
                        "ffmpeg", "-i", job.input_video_path,
                        "-map", f"0:s:{len([s for s in job.subtitle_info['streams'] if s['index'] < stream_index])}",
                        "-c", "copy" if ext != 'srt' else 'srt',
                        str(subtitle_path),
                        "-loglevel", "error"
                    ]
                    
                    # Si le codec n'est pas compatible, essayer de convertir en SRT
                    if codec not in ['subrip', 'srt'] and ext == 'srt':
                        cmd[cmd.index("-c")+1] = "srt"
                    
                    process = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    
                    stdout, stderr = await process.communicate()
                    
                    if process.returncode == 0 and subtitle_path.exists():
                        job.subtitle_paths.append({
                            'path': str(subtitle_path),
                            'language': language,
                            'codec': codec,
                            'index': stream_index,
                            'title': subtitle_stream.get('title', ''),
                            'forced': subtitle_stream.get('forced', False),
                            'default': subtitle_stream.get('default', False)
                        })
                        self.logger.info(f"Sous-titre extrait: {language} ({codec}) -> {subtitle_path.name}")
                    else:
                        self.logger.warning(f"Échec extraction sous-titre {stream_index} ({language})")
                        
                except Exception as e:
                    self.logger.warning(f"Erreur extraction sous-titre {stream_index}: {e}")
                    continue
            
            self.logger.info(f"Extraction sous-titres terminée: {len(job.subtitle_paths)} / {job.subtitle_info['count']}")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur extraction sous-titres: {e}")
            return False
    
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
            ffmpeg_cmd = self._build_optimized_ffmpeg_assemble_command_with_subtitles(job, upscaled_dir)
            
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
            
            # Vérification de la synchronisation audio/vidéo
            if job.has_audio:
                await self._verify_av_sync(job)
            
            # Nettoyage des fichiers temporaires
            await self._cleanup_job_files(job)
            
            subtitle_count = len(getattr(job, 'subtitle_paths', []))
            self.logger.info(f"Assemblage terminé: {job.output_video_path} "
                           f"(audio: {'oui' if job.has_audio else 'non'}, "
                           f"sous-titres: {subtitle_count})")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur assemblage vidéo: {e}")
            return False
    
    def _build_optimized_ffmpeg_assemble_command_with_subtitles(self, job: Job, upscaled_dir: Path) -> List[str]:
        """Construit la commande FFmpeg optimisée pour l'assemblage avec sous-titres"""
        cmd = ["ffmpeg"]
        
        # Entrée vidéo (frames upscalées)
        cmd.extend(["-framerate", str(job.frame_rate)])
        cmd.extend(["-i", str(upscaled_dir / "frame_%06d.png")])
        
        input_count = 1
        
        # Ajout de l'audio si présent
        if job.has_audio and hasattr(job, 'audio_path') and job.audio_path:
            cmd.extend(["-i", job.audio_path])
            input_count += 1
        
        # Ajout des sous-titres comme fichiers séparés
        subtitle_inputs = []
        if hasattr(job, 'subtitle_paths') and job.subtitle_paths:
            for subtitle in job.subtitle_paths:
                cmd.extend(["-i", subtitle['path']])
                subtitle_inputs.append(subtitle)
                input_count += 1
        
        # Configuration vidéo optimisée
        cmd.extend(["-c:v", "libx264"])
        cmd.extend(["-crf", str(config.FFMPEG_CRF)])
        cmd.extend(["-pix_fmt", "yuv420p"])
        cmd.extend(["-threads", str(config.FFMPEG_THREADS)])
        cmd.extend(["-vsync", "cfr"])
        cmd.extend(["-preset", config.FFMPEG_PRESET])
        
        # Optimisations x264 selon le matériel
        system_status = optimized_realesrgan.get_system_status()
        
        if system_status.get('is_laptop', False):
            # Optimisations laptop
            cmd.extend(["-x264-params", "ref=2:bframes=1:subme=6:me=hex"])
        elif system_status.get('cpu_cores', 8) >= 16:
            # CPU puissant, optimisations avancées
            cmd.extend(["-x264-params", "ref=4:bframes=3:subme=8:me=umh"])
        
        # Configuration audio
        if job.has_audio and hasattr(job, 'audio_path') and job.audio_path:
            cmd.extend(["-c:a", "aac"])
            cmd.extend(["-async", "1"])
        
        # Configuration des sous-titres
        if subtitle_inputs:
            # Mapper tous les sous-titres
            for i, subtitle in enumerate(subtitle_inputs):
                subtitle_index = 1 + (1 if job.has_audio else 0) + i  # Index dans les inputs FFmpeg
                cmd.extend(["-map", f"{subtitle_index}"])
            
            # Codec pour les sous-titres (mov_text pour MP4)
            cmd.extend(["-c:s", "mov_text"])
            
            # Métadonnées pour les sous-titres
            for i, subtitle in enumerate(subtitle_inputs):
                if subtitle.get('language') and subtitle['language'] != 'und':
                    cmd.extend([f"-metadata:s:s:{i}", f"language={subtitle['language']}"])
                if subtitle.get('title'):
                    cmd.extend([f"-metadata:s:s:{i}", f"title={subtitle['title']}"])
                
                # Marquer comme défaut si c'était le défaut dans l'original
                if subtitle.get('default', False):
                    cmd.extend([f"-disposition:s:{i}", "default"])
                elif subtitle.get('forced', False):
                    cmd.extend([f"-disposition:s:{i}", "forced"])
        
        # Fichier de sortie
        cmd.extend([job.output_video_path])
        cmd.extend(["-loglevel", "error"])
        
        return cmd
    
    async def _verify_upscaled_frames(self, job: Job, upscaled_dir: Path) -> bool:
        """Vérifie que tous les frames upscalés sont présents"""
        expected_frames = job.total_frames
        upscaled_frames = list(upscaled_dir.glob("frame_*.png"))
        
        if len(upscaled_frames) < expected_frames:
            self.logger.warning(f"Frames manquants: {len(upscaled_frames)}/{expected_frames}")
            
            # Vérification de la complétude (au moins 95%)
            completion_rate = len(upscaled_frames) / expected_frames
            if completion_rate < 0.95:
                self.logger.error(f"Trop de frames manquants: {completion_rate*100:.1f}% complétés")
                return False
            else:
                self.logger.warning(f"Frames manquants acceptables: {completion_rate*100:.1f}% complétés")
        
        return len(upscaled_frames) > 0
    
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
                
                # Vérification cohérence durée
                expected_duration = job.total_frames / job.frame_rate
                diff = abs(duration - expected_duration)
                
                if diff > 1.0:  # Plus d'1 seconde de différence
                    self.logger.warning(f"Décalage durée détecté: {diff:.2f}s "
                                      f"(attendu: {expected_duration:.2f}s, réel: {duration:.2f}s)")
            
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
            
            # Ajout des fichiers de sous-titres à nettoyer
            if hasattr(job, 'subtitle_paths') and job.subtitle_paths:
                for subtitle in job.subtitle_paths:
                    temp_files.append(Path(subtitle['path']))
            
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
        """Obtient les informations d'une vidéo avec optimisations (version simple pour compatibilité)"""
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
    
    def get_supported_subtitle_formats(self) -> List[str]:
        """Retourne la liste des formats de sous-titres supportés"""
        return [
            'srt',     # SubRip Text
            'ass',     # Advanced SubStation Alpha
            'ssa',     # SubStation Alpha
            'vtt',     # WebVTT
            'sub',     # MicroDVD/DVD Subtitle
            'sup',     # Blu-ray PGS
            'idx',     # VobSub
            'smi',     # SAMI
            'ttml',    # Timed Text Markup Language
            'dfxp'     # Distribution Format Exchange Profile
        ]
    
    def analyze_subtitle_compatibility(self, job: Job) -> Dict[str, Any]:
        """Analyse la compatibilité des sous-titres avec le format de sortie"""
        if not hasattr(job, 'subtitle_info') or not job.subtitle_info.get('streams'):
            return {'compatible': True, 'warnings': []}
        
        compatible_codecs = ['subrip', 'srt', 'ass', 'ssa', 'webvtt', 'mov_text']
        warnings = []
        compatible_streams = []
        
        for stream in job.subtitle_info['streams']:
            codec = stream.get('codec', 'unknown')
            
            if codec in compatible_codecs:
                compatible_streams.append(stream)
            elif codec in ['dvd_subtitle', 'dvdsub', 'hdmv_pgs_subtitle']:
                warnings.append(f"Sous-titre {stream['language']} ({codec}) sera converti en SRT")
                compatible_streams.append(stream)
            else:
                warnings.append(f"Sous-titre {stream['language']} ({codec}) pourrait ne pas être compatible")
        
        return {
            'compatible': len(compatible_streams) > 0,
            'compatible_streams': compatible_streams,
            'total_streams': len(job.subtitle_info['streams']),
            'warnings': warnings
        }
    
    async def create_subtitle_preview(self, job: Job) -> Optional[str]:
        """Crée un aperçu des sous-titres disponibles dans la vidéo"""
        if not hasattr(job, 'subtitle_info') or not job.subtitle_info.get('streams'):
            return None
        
        try:
            preview_lines = []
            preview_lines.append(f"=== SOUS-TITRES DÉTECTÉS ({job.subtitle_info['count']}) ===")
            
            for i, stream in enumerate(job.subtitle_info['streams']):
                language = stream.get('language', 'unknown')
                codec = stream.get('codec', 'unknown')
                title = stream.get('title', '')
                forced = ' [FORCÉ]' if stream.get('forced') else ''
                default = ' [DÉFAUT]' if stream.get('default') else ''
                
                preview_lines.append(f"{i+1}. {language.upper()} ({codec}){forced}{default}")
                if title:
                    preview_lines.append(f"   Titre: {title}")
            
            preview_lines.append("")
            
            # Analyse de compatibilité
            compat = self.analyze_subtitle_compatibility(job)
            if compat['warnings']:
                preview_lines.append("⚠️  AVERTISSEMENTS:")
                for warning in compat['warnings']:
                    preview_lines.append(f"   - {warning}")
                preview_lines.append("")
            
            preview_lines.append(f"✅ {len(compat['compatible_streams'])}/{compat['total_streams']} pistes compatibles")
            
            return "\n".join(preview_lines)
            
        except Exception as e:
            self.logger.error(f"Erreur création aperçu sous-titres: {e}")
            return None
    
    def get_processing_statistics(self, job: Job) -> Dict[str, Any]:
        """Retourne les statistiques de traitement pour un job"""
        stats = {
            'job_id': job.id,
            'input_file': Path(job.input_video_path).name if job.input_video_path else 'Unknown',
            'total_frames': job.total_frames,
            'frame_rate': job.frame_rate,
            'has_audio': job.has_audio,
            'audio_extracted': hasattr(job, 'audio_path') and job.audio_path is not None,
            'subtitles': {
                'detected': getattr(job, 'subtitle_info', {}).get('count', 0),
                'extracted': len(getattr(job, 'subtitle_paths', [])),
                'languages': []
            },
            'batches': {
                'total': len(job.batches),
                'completed': job.completed_batches,
                'progress_percent': job.progress
            },
            'timing': {
                'created_at': job.created_at.isoformat(),
                'processing_time': job.processing_time,
                'estimated_remaining': job.estimated_remaining_time
            },
            'status': job.status.value
        }
        
        # Ajout des langues de sous-titres
        if hasattr(job, 'subtitle_paths') and job.subtitle_paths:
            stats['subtitles']['languages'] = [
                {
                    'language': sub.get('language', 'unknown'),
                    'title': sub.get('title', ''),
                    'codec': sub.get('codec', 'unknown'),
                    'forced': sub.get('forced', False),
                    'default': sub.get('default', False)
                }
                for sub in job.subtitle_paths
            ]
        
        return stats