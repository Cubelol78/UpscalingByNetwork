# models/job.py - Version complète avec support sous-titres
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum
import time
from datetime import datetime
import uuid

class JobStatus(Enum):
    """États d'un job d'upscaling"""
    CREATED = "created"           # Créé mais pas démarré
    EXTRACTING = "extracting"     # Extraction des frames et médias
    PROCESSING = "processing"     # Traitement des lots
    ASSEMBLING = "assembling"     # Assemblage de la vidéo finale
    COMPLETED = "completed"       # Terminé avec succès
    FAILED = "failed"            # Échec
    CANCELLED = "cancelled"      # Annulé par l'utilisateur

@dataclass
class SubtitleTrack:
    """Représente une piste de sous-titres"""
    index: int                           # Index dans le fichier source
    language: str = "unknown"            # Code langue (fr, en, etc.)
    language_name: str = ""              # Nom complet de la langue
    codec: str = "unknown"               # Codec des sous-titres
    title: str = ""                      # Titre/description
    forced: bool = False                 # Sous-titres forcés
    default: bool = False                # Piste par défaut
    hearing_impaired: bool = False       # Pour malentendants
    
    # Informations d'extraction
    extracted: bool = False              # Extrait avec succès
    extraction_path: str = ""            # Chemin du fichier extrait
    extraction_format: str = ""          # Format après extraction (srt, ass, etc.)
    extraction_error: str = ""           # Erreur d'extraction le cas échéant
    
    # Métadonnées additionnelles
    charset: str = ""                    # Encodage caractères
    frame_count: int = 0                 # Nombre d'événements/sous-titres
    duration_ms: int = 0                 # Durée en millisecondes
    
    def get_display_name(self) -> str:
        """Retourne le nom d'affichage de la piste"""
        name_parts = []
        
        if self.language_name:
            name_parts.append(self.language_name)
        elif self.language and self.language != "unknown":
            name_parts.append(self.language.upper())
        else:
            name_parts.append("Langue inconnue")
        
        if self.title:
            name_parts.append(f"({self.title})")
        
        # Indicateurs spéciaux
        indicators = []
        if self.forced:
            indicators.append("FORCÉ")
        if self.default:
            indicators.append("DÉFAUT")
        if self.hearing_impaired:
            indicators.append("SDH")
        
        if indicators:
            name_parts.append(f"[{', '.join(indicators)}]")
        
        return " ".join(name_parts)
    
    def get_filename(self, base_name: str) -> str:
        """Génère un nom de fichier pour cette piste"""
        parts = [base_name]
        
        if self.language and self.language != "unknown":
            parts.append(self.language)
        
        if self.forced:
            parts.append("forced")
        
        if self.hearing_impaired:
            parts.append("sdh")
        
        extension = self.extraction_format or "srt"
        if not extension.startswith('.'):
            extension = f".{extension}"
        
        return "_".join(parts) + extension
    
    def is_compatible_with_mp4(self) -> bool:
        """Vérifie si la piste est compatible avec le conteneur MP4"""
        compatible_codecs = [
            'mov_text', 'subrip', 'srt', 'ass', 'ssa', 'webvtt'
        ]
        return self.codec.lower() in compatible_codecs
    
    def get_conversion_recommendation(self) -> str:
        """Recommande une conversion si nécessaire"""
        if self.is_compatible_with_mp4():
            return "Compatible MP4"
        
        # Recommandations de conversion
        conversion_map = {
            'dvd_subtitle': 'Convertir en SRT (sous-titres image → texte)',
            'dvdsub': 'Convertir en SRT (sous-titres image → texte)',
            'hdmv_pgs_subtitle': 'Convertir en SRT (PGS → texte)',
            'vobsub': 'Convertir en SRT (VobSub → texte)',
            'xsub': 'Convertir en SRT (XSub → texte)'
        }
        
        return conversion_map.get(self.codec.lower(), f"Convertir {self.codec} en SRT")

@dataclass 
class MediaInfo:
    """Informations sur les médias du job"""
    # Vidéo
    width: int = 0
    height: int = 0
    duration_seconds: float = 0
    bitrate_kbps: int = 0
    video_codec: str = ""
    
    # Audio
    has_audio: bool = False
    audio_tracks: List[Dict[str, Any]] = field(default_factory=list)
    audio_extraction_path: str = ""
    
    # Sous-titres
    has_subtitles: bool = False
    subtitle_tracks: List[SubtitleTrack] = field(default_factory=list)
    
    def get_resolution_display(self) -> str:
        """Retourne l'affichage de la résolution"""
        if self.width and self.height:
            return f"{self.width}×{self.height}"
        return "Inconnue"
    
    def get_duration_display(self) -> str:
        """Retourne l'affichage de la durée"""
        if self.duration_seconds > 0:
            hours = int(self.duration_seconds // 3600)
            minutes = int((self.duration_seconds % 3600) // 60)
            seconds = int(self.duration_seconds % 60)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return "00:00:00"
    
    def get_audio_summary(self) -> str:
        """Résumé des pistes audio"""
        if not self.has_audio or not self.audio_tracks:
            return "Aucun audio"
        
        if len(self.audio_tracks) == 1:
            track = self.audio_tracks[0]
            codec = track.get('codec', 'unknown')
            channels = track.get('channels', 0)
            return f"{codec} {channels}ch"
        else:
            return f"{len(self.audio_tracks)} pistes audio"
    
    def get_subtitle_summary(self) -> str:
        """Résumé des sous-titres"""
        if not self.has_subtitles or not self.subtitle_tracks:
            return "Aucun sous-titre"
        
        total = len(self.subtitle_tracks)
        extracted = sum(1 for track in self.subtitle_tracks if track.extracted)
        
        if extracted == total:
            return f"{total} sous-titre(s) ✅"
        elif extracted == 0:
            return f"{total} sous-titre(s) ⏳"
        else:
            return f"{extracted}/{total} sous-titres ⚠️"
    
    def get_languages_list(self) -> List[str]:
        """Liste des langues de sous-titres disponibles"""
        languages = []
        for track in self.subtitle_tracks:
            if track.language and track.language != "unknown":
                lang_display = track.language_name or track.language.upper()
                if lang_display not in languages:
                    languages.append(lang_display)
        return languages

@dataclass
class ProcessingSettings:
    """Paramètres de traitement pour le job"""
    # Real-ESRGAN
    model: str = "realesr-animevideov3"
    scale_factor: int = 4
    tile_size: int = 256
    gpu_id: int = 0
    
    # Qualité vidéo
    output_codec: str = "libx264"
    crf: int = 20
    preset: str = "medium"
    
    # Sous-titres
    include_subtitles: bool = True
    subtitle_format: str = "mov_text"  # Format pour MP4
    burn_subtitles: bool = False       # Graver dans la vidéo
    default_subtitle_language: str = ""
    
    # Options avancées
    preserve_original_framerate: bool = True
    audio_bitrate_kbps: int = 192
    enable_deinterlacing: bool = False
    
    def get_output_resolution(self, input_width: int, input_height: int) -> tuple:
        """Calcule la résolution de sortie"""
        return (input_width * self.scale_factor, input_height * self.scale_factor)
    
    def estimate_output_filesize_mb(self, duration_seconds: float, input_width: int, input_height: int) -> float:
        """Estime la taille du fichier de sortie"""
        # Calcul basique basé sur la résolution et durée
        output_width, output_height = self.get_output_resolution(input_width, input_height)
        pixels_per_second = output_width * output_height * 30  # Assume 30fps
        
        # Estimation bitrate selon CRF et résolution
        base_bitrate_kbps = 5000  # Base pour 1080p CRF 20
        resolution_factor = (output_width * output_height) / (1920 * 1080)
        crf_factor = 2 ** ((20 - self.crf) / 6)  # CRF impact
        
        estimated_bitrate = base_bitrate_kbps * resolution_factor * crf_factor
        estimated_size_mb = (estimated_bitrate * duration_seconds) / (8 * 1024)  # Conversion en MB
        
        return estimated_size_mb

@dataclass
class Job:
    """Représente un job d'upscaling complet avec support avancé des sous-titres"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    # Fichiers
    input_video_path: str = ""
    output_video_path: str = ""
    
    # État et progression
    status: JobStatus = JobStatus.CREATED
    progress: float = 0.0  # 0-100%
    
    # Horodatage
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Informations médias
    media_info: MediaInfo = field(default_factory=MediaInfo)
    processing_settings: ProcessingSettings = field(default_factory=ProcessingSettings)
    
    # Traitement
    total_frames: int = 0
    frame_rate: float = 30.0
    batches: List[str] = field(default_factory=list)  # IDs des lots
    completed_batches: int = 0
    failed_batches: int = 0
    
    # Messages et erreurs
    error_message: str = ""
    warnings: List[str] = field(default_factory=list)
    processing_log: List[str] = field(default_factory=list)
    
    # Métadonnées
    user_notes: str = ""
    tags: List[str] = field(default_factory=list)
    priority: int = 0  # 0=normal, positif=haute priorité, négatif=basse priorité
    
    @property
    def processing_time(self) -> Optional[int]:
        """Temps de traitement total en secondes"""
        if self.started_at and self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds())
        return None
    
    @property
    def estimated_remaining_time(self) -> Optional[int]:
        """Estimation du temps restant en secondes"""
        if self.completed_batches == 0 or not self.started_at:
            return None
        
        elapsed = (datetime.now() - self.started_at).total_seconds()
        remaining_batches = len(self.batches) - self.completed_batches
        
        if remaining_batches <= 0:
            return 0
        
        avg_time_per_batch = elapsed / self.completed_batches
        return int(remaining_batches * avg_time_per_batch)
    
    @property
    def success_rate(self) -> float:
        """Taux de succès des lots"""
        total_processed = self.completed_batches + self.failed_batches
        if total_processed == 0:
            return 0.0
        return (self.completed_batches / total_processed) * 100.0
    
    @property
    def has_audio(self) -> bool:
        """Raccourci pour vérifier la présence d'audio"""
        return self.media_info.has_audio
    
    @property
    def has_subtitles(self) -> bool:
        """Raccourci pour vérifier la présence de sous-titres"""
        return self.media_info.has_subtitles
    
    @property
    def subtitle_tracks(self) -> List[SubtitleTrack]:
        """Raccourci pour accéder aux pistes de sous-titres"""
        return self.media_info.subtitle_tracks
    
    def start(self):
        """Démarre le job"""
        self.status = JobStatus.PROCESSING
        self.started_at = datetime.now()
        self.add_log_entry("Job démarré")
    
    def complete(self):
        """Marque le job comme terminé"""
        self.status = JobStatus.COMPLETED
        self.completed_at = datetime.now()
        self.progress = 100.0
        self.add_log_entry("Job terminé avec succès")
    
    def fail(self, error: str = ""):
        """Marque le job comme échoué"""
        self.status = JobStatus.FAILED
        self.completed_at = datetime.now()
        self.error_message = error
        self.add_log_entry(f"Job échoué: {error}")
    
    def cancel(self):
        """Annule le job"""
        self.status = JobStatus.CANCELLED
        self.completed_at = datetime.now()
        self.add_log_entry("Job annulé par l'utilisateur")
    
    def add_log_entry(self, message: str):
        """Ajoute une entrée au log de traitement"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.processing_log.append(f"[{timestamp}] {message}")
        
        # Limiter la taille du log
        if len(self.processing_log) > 100:
            self.processing_log.pop(0)
    
    def add_warning(self, warning: str):
        """Ajoute un avertissement"""
        if warning not in self.warnings:
            self.warnings.append(warning)
            self.add_log_entry(f"⚠️ {warning}")
    
    def update_progress(self, completed_batches: int = None):
        """Met à jour la progression du job"""
        if completed_batches is not None:
            self.completed_batches = completed_batches
        
        if len(self.batches) > 0:
            self.progress = (self.completed_batches / len(self.batches)) * 100.0
        else:
            self.progress = 0.0
    
    def get_subtitle_by_language(self, language: str) -> Optional[SubtitleTrack]:
        """Récupère une piste de sous-titres par langue"""
        for track in self.subtitle_tracks:
            if track.language.lower() == language.lower():
                return track
        return None
    
    def get_default_subtitle_track(self) -> Optional[SubtitleTrack]:
        """Récupère la piste de sous-titres par défaut"""
        # 1. Chercher une piste marquée comme défaut
        for track in self.subtitle_tracks:
            if track.default and track.extracted:
                return track
        
        # 2. Chercher une piste forcée
        for track in self.subtitle_tracks:
            if track.forced and track.extracted:
                return track
        
        # 3. Première piste extraite avec succès
        for track in self.subtitle_tracks:
            if track.extracted:
                return track
        
        return None
    
    def get_extracted_subtitle_tracks(self) -> List[SubtitleTrack]:
        """Retourne la liste des pistes extraites avec succès"""
        return [track for track in self.subtitle_tracks if track.extracted]
    
    def add_subtitle_track(self, track: SubtitleTrack):
        """Ajoute une piste de sous-titres"""
        self.media_info.subtitle_tracks.append(track)
        self.media_info.has_subtitles = True
        self.add_log_entry(f"Piste sous-titres ajoutée: {track.get_display_name()}")
    
    def update_subtitle_extraction(self, track_index: int, success: bool, 
                                 extraction_path: str = "", error: str = ""):
        """Met à jour le statut d'extraction d'une piste de sous-titres"""
        if 0 <= track_index < len(self.subtitle_tracks):
            track = self.subtitle_tracks[track_index]
            track.extracted = success
            track.extraction_path = extraction_path
            track.extraction_error = error
            
            if success:
                self.add_log_entry(f"✅ Sous-titres extraits: {track.get_display_name()}")
            else:
                self.add_log_entry(f"❌ Échec extraction sous-titres: {track.get_display_name()} - {error}")
                self.add_warning(f"Impossible d'extraire les sous-titres {track.get_display_name()}")
    
    def get_subtitle_compatibility_report(self) -> Dict[str, Any]:
        """Génère un rapport de compatibilité des sous-titres"""
        if not self.has_subtitles:
            return {
                'has_subtitles': False,
                'total_tracks': 0,
                'compatible_tracks': 0,
                'problematic_tracks': [],
                'recommendations': []
            }
        
        total_tracks = len(self.subtitle_tracks)
        compatible_tracks = []
        problematic_tracks = []
        recommendations = []
        
        for track in self.subtitle_tracks:
            if track.is_compatible_with_mp4():
                compatible_tracks.append(track)
            else:
                problematic_tracks.append({
                    'track': track,
                    'issue': f"Codec {track.codec} non compatible MP4",
                    'recommendation': track.get_conversion_recommendation()
                })
        
        # Génération des recommandations
        if problematic_tracks:
            recommendations.append(f"{len(problematic_tracks)} piste(s) nécessitent une conversion")
        
        if not any(track.default for track in self.subtitle_tracks):
            recommendations.append("Aucune piste marquée par défaut")
        
        # Vérification des langues
        languages = set(track.language for track in self.subtitle_tracks if track.language != "unknown")
        if len(languages) > 1:
            recommendations.append(f"Plusieurs langues détectées: {', '.join(sorted(languages))}")
        
        return {
            'has_subtitles': True,
            'total_tracks': total_tracks,
            'compatible_tracks': len(compatible_tracks),
            'extracted_tracks': len(self.get_extracted_subtitle_tracks()),
            'problematic_tracks': problematic_tracks,
            'recommendations': recommendations,
            'languages': list(languages)
        }
    
    def get_processing_summary(self) -> Dict[str, Any]:
        """Retourne un résumé complet du traitement"""
        subtitle_compat = self.get_subtitle_compatibility_report()
        
        return {
            'job_info': {
                'id': self.id,
                'status': self.status.value,
                'progress': self.progress,
                'created_at': self.created_at.isoformat(),
                'processing_time': self.processing_time,
                'estimated_remaining': self.estimated_remaining_time
            },
            'files': {
                'input': self.input_video_path,
                'output': self.output_video_path,
                'input_size_mb': self._get_file_size_mb(self.input_video_path),
                'output_size_mb': self._get_file_size_mb(self.output_video_path) if self.status == JobStatus.COMPLETED else None
            },
            'media': {
                'resolution': self.media_info.get_resolution_display(),
                'duration': self.media_info.get_duration_display(),
                'framerate': self.frame_rate,
                'total_frames': self.total_frames,
                'video_codec': self.media_info.video_codec,
                'audio_summary': self.media_info.get_audio_summary(),
                'subtitle_summary': self.media_info.get_subtitle_summary()
            },
            'processing': {
                'model': self.processing_settings.model,
                'scale_factor': self.processing_settings.scale_factor,
                'output_resolution': self.processing_settings.get_output_resolution(
                    self.media_info.width, self.media_info.height
                ),
                'batches_total': len(self.batches),
                'batches_completed': self.completed_batches,
                'batches_failed': self.failed_batches,
                'success_rate': self.success_rate
            },
            'subtitles': subtitle_compat,
            'quality': {
                'warnings_count': len(self.warnings),
                'has_errors': bool(self.error_message),
                'log_entries': len(self.processing_log)
            }
        }
    
    def _get_file_size_mb(self, file_path: str) -> Optional[float]:
        """Récupère la taille d'un fichier en MB"""
        try:
            from pathlib import Path
            if file_path and Path(file_path).exists():
                size_bytes = Path(file_path).stat().st_size
                return size_bytes / (1024 * 1024)
        except Exception:
            pass
        return None
    
    def export_subtitle_info(self) -> Dict[str, Any]:
        """Exporte les informations des sous-titres pour sauvegarde/transfert"""
        return {
            'has_subtitles': self.has_subtitles,
            'tracks': [
                {
                    'index': track.index,
                    'language': track.language,
                    'language_name': track.language_name,
                    'codec': track.codec,
                    'title': track.title,
                    'forced': track.forced,
                    'default': track.default,
                    'hearing_impaired': track.hearing_impaired,
                    'extracted': track.extracted,
                    'extraction_path': track.extraction_path,
                    'extraction_format': track.extraction_format,
                    'extraction_error': track.extraction_error,
                    'charset': track.charset,
                    'frame_count': track.frame_count,
                    'duration_ms': track.duration_ms
                }
                for track in self.subtitle_tracks
            ]
        }
    
    def import_subtitle_info(self, subtitle_data: Dict[str, Any]):
        """Importe les informations des sous-titres depuis une sauvegarde"""
        self.media_info.has_subtitles = subtitle_data.get('has_subtitles', False)
        self.media_info.subtitle_tracks = []
        
        for track_data in subtitle_data.get('tracks', []):
            track = SubtitleTrack(
                index=track_data.get('index', 0),
                language=track_data.get('language', 'unknown'),
                language_name=track_data.get('language_name', ''),
                codec=track_data.get('codec', 'unknown'),
                title=track_data.get('title', ''),
                forced=track_data.get('forced', False),
                default=track_data.get('default', False),
                hearing_impaired=track_data.get('hearing_impaired', False),
                extracted=track_data.get('extracted', False),
                extraction_path=track_data.get('extraction_path', ''),
                extraction_format=track_data.get('extraction_format', ''),
                extraction_error=track_data.get('extraction_error', ''),
                charset=track_data.get('charset', ''),
                frame_count=track_data.get('frame_count', 0),
                duration_ms=track_data.get('duration_ms', 0)
            )
            self.media_info.subtitle_tracks.append(track)
    
    def validate_job_integrity(self) -> List[str]:
        """Valide l'intégrité du job et retourne les problèmes détectés"""
        issues = []
        
        # Vérification des fichiers
        from pathlib import Path
        
        if not self.input_video_path or not Path(self.input_video_path).exists():
            issues.append("Fichier d'entrée manquant ou introuvable")
        
        if self.status == JobStatus.COMPLETED:
            if not self.output_video_path or not Path(self.output_video_path).exists():
                issues.append("Fichier de sortie manquant alors que le job est marqué terminé")
        
        # Vérification de la cohérence des lots
        if len(self.batches) == 0 and self.status in [JobStatus.PROCESSING, JobStatus.COMPLETED]:
            issues.append("Aucun lot défini alors que le traitement a commencé")
        
        if self.completed_batches > len(self.batches):
            issues.append("Nombre de lots terminés supérieur au total des lots")
        
        # Vérification des sous-titres extraits
        for track in self.subtitle_tracks:
            if track.extracted and track.extraction_path:
                if not Path(track.extraction_path).exists():
                    issues.append(f"Fichier de sous-titres manquant: {track.get_display_name()}")
        
        # Vérification temporelle
        if self.started_at and self.completed_at:
            if self.completed_at < self.started_at:
                issues.append("Date de fin antérieure à la date de début")
        
        return issues
    
    def cleanup_temporary_files(self):
        """Nettoie les fichiers temporaires du job"""
        from pathlib import Path
        
        files_cleaned = []
        
        # Nettoyage des sous-titres temporaires
        for track in self.subtitle_tracks:
            if track.extraction_path and track.extraction_path.startswith("temp"):
                temp_path = Path(track.extraction_path)
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                        files_cleaned.append(str(temp_path))
                        track.extraction_path = ""  # Marquer comme nettoyé
                    except Exception as e:
                        self.add_warning(f"Impossible de supprimer {temp_path}: {e}")
        
        # Nettoyage de l'audio temporaire
        if hasattr(self.media_info, 'audio_extraction_path') and self.media_info.audio_extraction_path:
            audio_path = Path(self.media_info.audio_extraction_path)
            if audio_path.exists() and "temp" in str(audio_path):
                try:
                    audio_path.unlink()
                    files_cleaned.append(str(audio_path))
                    self.media_info.audio_extraction_path = ""
                except Exception as e:
                    self.add_warning(f"Impossible de supprimer {audio_path}: {e}")
        
        if files_cleaned:
            self.add_log_entry(f"🧹 Nettoyé {len(files_cleaned)} fichier(s) temporaire(s)")
        
        return files_cleaned
    
    def __str__(self) -> str:
        """Représentation textuelle du job"""
        from pathlib import Path
        filename = Path(self.input_video_path).name if self.input_video_path else "Fichier inconnu"
        return f"Job {self.id[:8]} - {filename} ({self.status.value})"
    
    def __repr__(self) -> str:
        """Représentation détaillée du job"""
        return (f"Job(id={self.id[:8]}, status={self.status.value}, "
                f"progress={self.progress:.1f}%, batches={len(self.batches)}, "
                f"subtitles={len(self.subtitle_tracks)})")

# Fonctions utilitaires pour la gestion des jobs

def create_job_from_video_info(video_path: str, video_info: Dict[str, Any]) -> Job:
    """Crée un job à partir des informations vidéo détectées"""
    from pathlib import Path
    
    job = Job()
    job.input_video_path = video_path
    
    # Configuration du fichier de sortie
    input_path = Path(video_path)
    output_filename = f"{input_path.stem}_upscaled_4x{input_path.suffix}"
    job.output_video_path = str(input_path.parent / output_filename)
    
    # Informations médias de base
    job.media_info.width = video_info.get('width', 0)
    job.media_info.height = video_info.get('height', 0)
    job.media_info.duration_seconds = video_info.get('duration', 0)
    job.media_info.video_codec = video_info.get('video_codec', '')
    job.frame_rate = video_info.get('frame_rate', 30.0)
    
    # Calcul du nombre de frames
    if job.media_info.duration_seconds > 0 and job.frame_rate > 0:
        job.total_frames = int(job.media_info.duration_seconds * job.frame_rate)
    
    # Audio
    job.media_info.has_audio = video_info.get('has_audio', False)
    if 'audio_streams' in video_info:
        job.media_info.audio_tracks = video_info['audio_streams']
    
    # Sous-titres
    subtitles_info = video_info.get('subtitles', {})
    if subtitles_info.get('count', 0) > 0:
        job.media_info.has_subtitles = True
        
        for stream_data in subtitles_info.get('streams', []):
            track = SubtitleTrack(
                index=stream_data.get('index', 0),
                language=stream_data.get('language', 'unknown'),
                codec=stream_data.get('codec', 'unknown'),
                title=stream_data.get('title', ''),
                forced=stream_data.get('forced', False),
                default=stream_data.get('default', False)
            )
            job.add_subtitle_track(track)
    
    job.add_log_entry(f"Job créé pour {Path(video_path).name}")
    return job

def estimate_job_requirements(job: Job) -> Dict[str, Any]:
    """Estime les ressources nécessaires pour un job"""
    # Estimation de l'espace disque
    input_size_mb = job._get_file_size_mb(job.input_video_path) or 1000
    
    # Frames originales (PNG)
    frames_space_mb = job.total_frames * 0.5  # ~500KB par frame PNG
    
    # Frames upscalées (4x plus grandes)
    upscaled_frames_mb = job.total_frames * 2.0  # ~2MB par frame upscalée
    
    # Vidéo de sortie
    estimated_output_mb = job.processing_settings.estimate_output_filesize_mb(
        job.media_info.duration_seconds,
        job.media_info.width,
        job.media_info.height
    )
    
    # Total avec marge de sécurité
    total_space_mb = (frames_space_mb + upscaled_frames_mb + estimated_output_mb + input_size_mb) * 1.2
    
    # Estimation du temps
    base_time_per_frame = 2.0  # secondes par frame (estimation conservative)
    estimated_time_hours = (job.total_frames * base_time_per_frame) / 3600
    
    return {
        'disk_space_mb': total_space_mb,
        'disk_space_gb': total_space_mb / 1024,
        'estimated_time_hours': estimated_time_hours,
        'estimated_time_display': f"{int(estimated_time_hours)}h {int((estimated_time_hours % 1) * 60)}min",
        'frame_processing_breakdown': {
            'original_frames_mb': frames_space_mb,
            'upscaled_frames_mb': upscaled_frames_mb,
            'output_video_mb': estimated_output_mb
        }
    }

# Ajoutez ces méthodes à la classe Job dans server/models/job.py

@property 
def extracted_audio_tracks(self) -> List[Dict[str, Any]]:
    """Raccourci pour accéder aux pistes audio extraites"""
    return getattr(self.media_info, 'extracted_audio_files', [])

@property
def audio_languages(self) -> List[str]:
    """Liste des langues audio disponibles"""
    languages = []
    for track in self.media_info.audio_tracks:
        lang = track.get('language', 'und')
        if lang != 'und' and lang not in languages:
            languages.append(lang)
    return languages

def get_audio_track_by_language(self, language: str) -> Optional[Dict[str, Any]]:
    """Récupère une piste audio par langue"""
    for track in self.media_info.audio_tracks:
        if track.get('language', '').lower() == language.lower():
            return track
    return None

def get_default_audio_track(self) -> Optional[Dict[str, Any]]:
    """Récupère la piste audio par défaut"""
    # 1. Chercher une piste extraite avec succès
    for track in self.media_info.audio_tracks:
        if track.get('extraction_success', False):
            return track
    
    # 2. Première piste disponible
    if self.media_info.audio_tracks:
        return self.media_info.audio_tracks[0]
    
    return None

def get_extracted_audio_tracks(self) -> List[Dict[str, Any]]:
    """Retourne la liste des pistes audio extraites avec succès"""
    return [track for track in self.media_info.audio_tracks 
            if track.get('extraction_success', False)]

def add_audio_track_info(self, track_data: Dict[str, Any]):
    """Ajoute les informations d'une piste audio"""
    self.media_info.audio_tracks.append(track_data)
    self.add_log_entry(f"Piste audio détectée: {self._get_audio_display_name(track_data)}")

def update_audio_extraction(self, track_index: int, success: bool, 
                          extraction_path: str = "", error: str = ""):
    """Met à jour le statut d'extraction d'une piste audio"""
    for track in self.media_info.audio_tracks:
        if track['index'] == track_index:
            track['extraction_success'] = success
            track['extraction_path'] = extraction_path
            track['extraction_error'] = error
            
            if success:
                self.add_log_entry(f"✅ Audio extrait: {self._get_audio_display_name(track)}")
            else:
                self.add_log_entry(f"❌ Échec extraction audio: {self._get_audio_display_name(track)} - {error}")
                self.add_warning(f"Impossible d'extraire l'audio {self._get_audio_display_name(track)}")
            break

def _get_audio_display_name(self, audio_track: Dict[str, Any]) -> str:
    """Génère un nom d'affichage pour une piste audio"""
    parts = []
    
    # Langue
    language = audio_track.get('language', 'und')
    if language != 'und':
        # Mapping basique des langues
        language_map = {
            'fr': 'Français', 'en': 'English', 'es': 'Español', 
            'de': 'Deutsch', 'it': 'Italiano', 'ja': '日本語'
        }
        language_name = language_map.get(language.lower(), language.upper())
        parts.append(language_name)
    else:
        parts.append('Langue inconnue')
    
    # Codec et canaux
    codec = audio_track.get('codec', 'unknown')
    channels = audio_track.get('channels', 0)
    if channels > 0:
        channel_desc = f"{channels}ch"
        if channels == 1:
            channel_desc = "Mono"
        elif channels == 2:
            channel_desc = "Stéréo"
        elif channels == 6:
            channel_desc = "5.1"
        elif channels == 8:
            channel_desc = "7.1"
        
        parts.append(f"{codec} {channel_desc}")
    else:
        parts.append(codec)
    
    # Titre si présent
    title = audio_track.get('title', '')
    if title:
        parts.append(f"({title})")
    
    return " ".join(parts)

def get_audio_compatibility_report(self) -> Dict[str, Any]:
    """Génère un rapport de compatibilité des pistes audio"""
    if not self.has_audio:
        return {
            'has_audio': False,
            'total_tracks': 0,
            'compatible_tracks': 0,
            'problematic_tracks': [],
            'recommendations': []
        }
    
    compatible_codecs = ['aac', 'mp3', 'ac3']
    problematic_tracks = []
    recommendations = []
    compatible_count = 0
    
    for track in self.media_info.audio_tracks:
        codec = track.get('codec', 'unknown').lower()
        
        if codec in compatible_codecs:
            compatible_count += 1
        else:
            problematic_tracks.append({
                'track': self._get_audio_display_name(track),
                'codec': codec,
                'recommendation': f"Sera converti de {codec} vers AAC pour compatibilité MP4"
            })
    
    # Recommandations générales
    if len(self.media_info.audio_tracks) > 3:
        recommendations.append(f"Nombreuses pistes audio ({len(self.media_info.audio_tracks)}) - Impact sur la taille du fichier")
    
    # Vérification des langues
    languages = set(track.get('language', 'und') for track in self.media_info.audio_tracks)
    if len(languages) > 1:
        lang_list = [lang for lang in languages if lang != 'und']
        recommendations.append(f"Langues détectées: {', '.join(lang_list)}")
    
    return {
        'has_audio': True,
        'total_tracks': len(self.media_info.audio_tracks),
        'compatible_tracks': compatible_count,
        'extracted_tracks': len(self.get_extracted_audio_tracks()),
        'problematic_tracks': problematic_tracks,
        'recommendations': recommendations,
        'languages': list(languages)
    }

def export_audio_info(self) -> Dict[str, Any]:
    """Exporte les informations des pistes audio pour sauvegarde/transfert"""
    return {
        'has_audio': self.has_audio,
        'tracks': [
            {
                'index': track.get('index', 0),
                'codec': track.get('codec', 'unknown'),
                'language': track.get('language', 'und'),
                'title': track.get('title', ''),
                'channels': track.get('channels', 0),
                'sample_rate': track.get('sample_rate', 0),
                'bitrate': track.get('bitrate', 0),
                'duration': track.get('duration', 0),
                'extraction_success': track.get('extraction_success', False),
                'extraction_path': track.get('extraction_path', ''),
                'extraction_format': track.get('extraction_format', ''),
                'extraction_error': track.get('extraction_error', '')
            }
            for track in self.media_info.audio_tracks
        ]
    }

def import_audio_info(self, audio_data: Dict[str, Any]):
    """Importe les informations des pistes audio depuis une sauvegarde"""
    self.media_info.has_audio = audio_data.get('has_audio', False)
    self.media_info.audio_tracks = []
    
    for track_data in audio_data.get('tracks', []):
        self.media_info.audio_tracks.append(track_data)

def cleanup_audio_files(self):
    """Nettoie les fichiers audio temporaires"""
    from pathlib import Path
    files_cleaned = []
    
    # Nettoyage des fichiers audio extraits
    if hasattr(self.media_info, 'extracted_audio_files'):
        for audio_file in self.media_info.extracted_audio_files:
            audio_path = Path(audio_file['path'])
            if audio_path.exists() and "temp" in str(audio_path):
                try:
                    audio_path.unlink()
                    files_cleaned.append(str(audio_path))
                except Exception as e:
                    self.add_warning(f"Impossible de supprimer {audio_path}: {e}")
    
    # Nettoyage du fichier audio principal
    if hasattr(self.media_info, 'audio_extraction_path') and self.media_info.audio_extraction_path:
        audio_path = Path(self.media_info.audio_extraction_path)
        if audio_path.exists() and "temp" in str(audio_path):
            try:
                audio_path.unlink()
                files_cleaned.append(str(audio_path))
                self.media_info.audio_extraction_path = ""
            except Exception as e:
                self.add_warning(f"Impossible de supprimer {audio_path}: {e}")
    
    if files_cleaned:
        self.add_log_entry(f"🧹 Nettoyé {len(files_cleaned)} fichier(s) audio temporaire(s)")
    
    return files_cleaned