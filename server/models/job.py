# server/models/job.py
"""
Modèle de données pour les jobs d'upscaling (vidéos complètes)
"""

import os
import hashlib
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, Any, List
from pathlib import Path

class JobStatus(Enum):
    """États possibles d'un job"""
    CREATED = "created"              # Job créé mais pas encore démarré
    EXTRACTING_FRAMES = "extracting_frames"  # Extraction des frames en cours
    PROCESSING = "processing"        # Lots en cours de traitement
    ASSEMBLING = "assembling"        # Assemblage de la vidéo finale
    COMPLETED = "completed"          # Job terminé avec succès
    FAILED = "failed"               # Job échoué
    CANCELLED = "cancelled"          # Job annulé par l'utilisateur
    PAUSED = "paused"               # Job mis en pause

class JobPriority(Enum):
    """Priorités des jobs"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4

class UpscalingModel(Enum):
    """Modèles d'upscaling disponibles"""
    REALESRGAN_X4PLUS = "RealESRGAN_x4plus"
    REALESRGAN_X4PLUS_ANIME = "RealESRGAN_x4plus_anime_6B"
    REALESRGAN_X2PLUS = "RealESRGAN_x2plus"
    ESRGAN_X4 = "ESRGAN_x4"

class Job:
    """
    Représente un job d'upscaling complet (une vidéo)
    """
    
    def __init__(self, 
                 id: str,
                 input_file: str,
                 output_file: str,
                 status: JobStatus = JobStatus.CREATED,
                 priority: JobPriority = JobPriority.NORMAL):
        
        # Identifiants
        self.id = id
        self.name = Path(input_file).stem  # Nom basé sur le fichier d'entrée
        
        # Fichiers
        self.input_file = input_file
        self.output_file = output_file
        self.original_file_size = 0
        self.final_file_size = 0
        
        # État
        self.status = status
        self.priority = priority
        
        # Timing
        self.created_at = datetime.now()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.paused_at: Optional[datetime] = None
        self.total_pause_duration = 0.0  # En secondes
        
        # Configuration d'upscaling
        self.upscaling_config = {
            'model': UpscalingModel.REALESRGAN_X4PLUS.value,
            'scale_factor': 4,
            'tile_size': 256,
            'use_gpu': True,
            'tta_mode': False,
            'preserve_audio': True,
            'preserve_metadata': True,
            'output_format': 'mp4',
            'video_codec': 'libx264',
            'video_quality': 'high',
            'frame_rate': 'auto'  # 'auto' ou valeur numérique
        }
        
        # Informations vidéo
        self.video_info = {
            'duration_seconds': 0.0,
            'fps': 0.0,
            'width': 0,
            'height': 0,
            'total_frames': 0,
            'has_audio': False,
            'codec': '',
            'bitrate': 0
        }
        
        # Progression
        self.total_batches = 0
        self.completed_batches = 0
        self.failed_batches = 0
        self.processing_batches = 0
        
        # Statistiques
        self.frames_processed = 0
        self.processing_time = 0.0  # En secondes
        self.estimated_completion: Optional[datetime] = None
        
        # Gestion d'erreurs
        self.error_message: Optional[str] = None
        self.retry_count = 0
        self.max_retries = 2
        
        # Métadonnées
        self.metadata: Dict[str, Any] = {}
        self.tags: List[str] = []
        self.notes = ""
        
        # Historique des événements
        self.events: List[Dict[str, Any]] = []
        
        # Calcul de la taille du fichier d'entrée
        self._calculate_input_file_size()
    
    def _calculate_input_file_size(self):
        """Calcule la taille du fichier d'entrée"""
        try:
            if os.path.exists(self.input_file):
                self.original_file_size = os.path.getsize(self.input_file)
        except Exception:
            self.original_file_size = 0
    
    @property
    def is_active(self) -> bool:
        """Vérifie si le job est actuellement actif"""
        return self.status in [
            JobStatus.EXTRACTING_FRAMES,
            JobStatus.PROCESSING,
            JobStatus.ASSEMBLING
        ]
    
    @property
    def is_completed(self) -> bool:
        """Vérifie si le job est terminé"""
        return self.status == JobStatus.COMPLETED
    
    @property
    def is_failed(self) -> bool:
        """Vérifie si le job a échoué"""
        return self.status == JobStatus.FAILED
    
    @property
    def is_paused(self) -> bool:
        """Vérifie si le job est en pause"""
        return self.status == JobStatus.PAUSED
    
    @property
    def can_retry(self) -> bool:
        """Vérifie si le job peut être relancé"""
        return (self.status == JobStatus.FAILED and 
                self.retry_count < self.max_retries)
    
    @property
    def progress_percentage(self) -> float:
        """Pourcentage de progression (0-100)"""
        if self.total_batches == 0:
            return 0.0
        return (self.completed_batches / self.total_batches) * 100.0
    
    @property
    def frames_progress_percentage(self) -> float:
        """Pourcentage de progression basé sur les frames"""
        if self.video_info.get('total_frames', 0) == 0:
            return 0.0
        return (self.frames_processed / self.video_info['total_frames']) * 100.0
    
    @property
    def duration(self) -> Optional[float]:
        """Durée totale du job en secondes"""
        if self.started_at:
            end_time = self.completed_at or datetime.now()
            total_time = (end_time - self.started_at).total_seconds()
            return total_time - self.total_pause_duration
        return None
    
    @property
    def estimated_time_remaining(self) -> Optional[float]:
        """Temps estimé restant en secondes"""
        if (self.frames_processed == 0 or 
            self.processing_time == 0 or 
            self.video_info.get('total_frames', 0) == 0):
            return None
        
        frames_remaining = self.video_info['total_frames'] - self.frames_processed
        avg_time_per_frame = self.processing_time / self.frames_processed
        
        return frames_remaining * avg_time_per_frame
    
    @property
    def processing_speed_fps(self) -> float:
        """Vitesse de traitement en frames par seconde"""
        if self.processing_time == 0:
            return 0.0
        return self.frames_processed / self.processing_time
    
    @property
    def scale_factor_actual(self) -> float:
        """Facteur d'échelle réel basé sur la configuration"""
        return self.upscaling_config.get('scale_factor', 4)
    
    @property
    def expected_output_resolution(self) -> tuple:
        """Résolution attendue de sortie (largeur, hauteur)"""
        scale = self.scale_factor_actual
        return (
            self.video_info.get('width', 0) * scale,
            self.video_info.get('height', 0) * scale
        )
    
    def start(self) -> bool:
        """
        Démarre le job
        
        Returns:
            True si démarré avec succès
        """
        if self.status != JobStatus.CREATED:
            return False
        
        self.status = JobStatus.EXTRACTING_FRAMES
        self.started_at = datetime.now()
        self._add_event("job_started", "Job démarré")
        
        return True
    
    def pause(self) -> bool:
        """
        Met le job en pause
        
        Returns:
            True si mis en pause avec succès
        """
        if not self.is_active:
            return False
        
        self.status = JobStatus.PAUSED
        self.paused_at = datetime.now()
        self._add_event("job_paused", "Job mis en pause")
        
        return True
    
    def resume(self) -> bool:
        """
        Reprend le job depuis la pause
        
        Returns:
            True si repris avec succès
        """
        if not self.is_paused:
            return False
        
        if self.paused_at:
            pause_duration = (datetime.now() - self.paused_at).total_seconds()
            self.total_pause_duration += pause_duration
        
        self.status = JobStatus.PROCESSING
        self.paused_at = None
        self._add_event("job_resumed", "Job repris")
        
        return True
    
    def cancel(self) -> bool:
        """
        Annule le job
        
        Returns:
            True si annulé avec succès
        """
        if self.status in [JobStatus.COMPLETED, JobStatus.CANCELLED]:
            return False
        
        self.status = JobStatus.CANCELLED
        self._add_event("job_cancelled", "Job annulé par l'utilisateur")
        
        return True
    
    def complete(self) -> bool:
        """
        Marque le job comme terminé
        
        Returns:
            True si marqué comme terminé
        """
        if self.status != JobStatus.ASSEMBLING:
            return False
        
        self.status = JobStatus.COMPLETED
        self.completed_at = datetime.now()
        
        # Calcul de la taille du fichier final
        try:
            if os.path.exists(self.output_file):
                self.final_file_size = os.path.getsize(self.output_file)
        except Exception:
            pass
        
        self._add_event("job_completed", "Job terminé avec succès")
        
        return True
    
    def fail(self, error_message: str) -> bool:
        """
        Marque le job comme échoué
        
        Args:
            error_message: Message d'erreur
            
        Returns:
            True si marqué comme échoué
        """
        self.status = JobStatus.FAILED
        self.error_message = error_message
        
        self._add_event("job_failed", f"Job échoué: {error_message}")
        
        return True
    
    def retry(self) -> bool:
        """
        Relance le job après un échec
        
        Returns:
            True si relancé avec succès
        """
        if not self.can_retry:
            return False
        
        # Incrémentation du compteur de tentatives
        self.retry_count += 1
        
        # Remise à zéro des statistiques
        self.status = JobStatus.EXTRACTING_FRAMES
        self.error_message = None
        self.started_at = datetime.now()
        self.completed_at = None
        self.processing_time = 0.0
        self.frames_processed = 0
        
        # Remise à zéro des lots
        self.completed_batches = 0
        self.failed_batches = 0
        self.processing_batches = 0
        
        # Réinitialisation des pauses
        self.paused_at = None
        self.total_pause_duration = 0.0
        
        # Réinitialisation de l'estimation
        self.estimated_completion = None
        
        self._add_event("job_retried", f"Job relancé (tentative {self.retry_count})")
        
        return True
    
    def update_video_info(self, video_info: Dict[str, Any]):
        """
        Met à jour les informations vidéo
        
        Args:
            video_info: Dictionnaire avec les informations vidéo
        """
        self.video_info.update(video_info)
        
        # Mise à jour du nombre total de frames si disponible
        if 'total_frames' in video_info:
            self._add_event("video_analyzed", 
                          f"Vidéo analysée: {video_info['total_frames']} frames, "
                          f"{video_info.get('duration_seconds', 0):.1f}s")
    
    def update_batch_counts(self, total: int, completed: int, failed: int, processing: int):
        """
        Met à jour les compteurs de lots
        
        Args:
            total: Nombre total de lots
            completed: Lots terminés
            failed: Lots échoués
            processing: Lots en cours
        """
        self.total_batches = total
        self.completed_batches = completed
        self.failed_batches = failed
        self.processing_batches = processing
        
        # Calcul de l'estimation de fin
        self._update_estimated_completion()
    
    def update_frames_processed(self, frames_count: int, processing_time: float):
        """
        Met à jour le nombre de frames traitées
        
        Args:
            frames_count: Nombre de frames traitées
            processing_time: Temps de traitement en secondes
        """
        self.frames_processed += frames_count
        self.processing_time += processing_time
        
        self._update_estimated_completion()
    
    def _update_estimated_completion(self):
        """Met à jour l'estimation de fin de traitement"""
        remaining_time = self.estimated_time_remaining
        if remaining_time is not None and remaining_time > 0:
            self.estimated_completion = datetime.now() + timedelta(seconds=remaining_time)
        else:
            self.estimated_completion = None
    
    def set_status(self, status: JobStatus, message: str = ""):
        """
        Change le statut du job
        
        Args:
            status: Nouveau statut
            message: Message optionnel
        """
        old_status = self.status
        self.status = status
        
        event_message = message or f"Statut changé: {old_status.value} -> {status.value}"
        self._add_event("status_changed", event_message)
        
        # Actions spéciales selon le statut
        if status == JobStatus.PROCESSING and old_status != JobStatus.PAUSED:
            if not self.started_at:
                self.started_at = datetime.now()
        elif status == JobStatus.COMPLETED:
            self.completed_at = datetime.now()
    
    def update_upscaling_config(self, config: Dict[str, Any]):
        """
        Met à jour la configuration d'upscaling
        
        Args:
            config: Nouvelle configuration
        """
        old_config = self.upscaling_config.copy()
        self.upscaling_config.update(config)
        
        # Log des changements significatifs
        changes = []
        for key, value in config.items():
            if key in old_config and old_config[key] != value:
                changes.append(f"{key}: {old_config[key]} -> {value}")
        
        if changes:
            self._add_event("config_updated", f"Configuration mise à jour: {', '.join(changes)}")
    
    def _add_event(self, event_type: str, message: str, metadata: Dict[str, Any] = None):
        """
        Ajoute un événement à l'historique
        
        Args:
            event_type: Type d'événement
            message: Message descriptif
            metadata: Métadonnées optionnelles
        """
        event = {
            'timestamp': datetime.now().isoformat(),
            'type': event_type,
            'message': message,
            'metadata': metadata or {}
        }
        
        self.events.append(event)
        
        # Limitation de l'historique (garder les 100 derniers événements)
        if len(self.events) > 100:
            self.events = self.events[-100:]
    
    def get_detailed_progress(self) -> Dict[str, Any]:
        """
        Retourne les informations détaillées de progression
        
        Returns:
            Dictionnaire avec la progression détaillée
        """
        return {
            'job_id': self.id,
            'job_name': self.name,
            'status': self.status.value,
            'priority': self.priority.value,
            'progress': {
                'batches': {
                    'total': self.total_batches,
                    'completed': self.completed_batches,
                    'failed': self.failed_batches,
                    'processing': self.processing_batches,
                    'pending': max(0, self.total_batches - self.completed_batches - self.failed_batches - self.processing_batches),
                    'percentage': self.progress_percentage
                },
                'frames': {
                    'total': self.video_info.get('total_frames', 0),
                    'processed': self.frames_processed,
                    'percentage': self.frames_progress_percentage
                }
            },
            'timing': {
                'created_at': self.created_at.isoformat(),
                'started_at': self.started_at.isoformat() if self.started_at else None,
                'completed_at': self.completed_at.isoformat() if self.completed_at else None,
                'duration_seconds': self.duration,
                'estimated_completion': self.estimated_completion.isoformat() if self.estimated_completion else None,
                'estimated_time_remaining_seconds': self.estimated_time_remaining,
                'processing_speed_fps': self.processing_speed_fps
            },
            'video_info': self.video_info,
            'upscaling_config': self.upscaling_config,
            'file_sizes': {
                'input_mb': self.original_file_size / (1024 * 1024) if self.original_file_size else 0,
                'output_mb': self.final_file_size / (1024 * 1024) if self.final_file_size else 0,
                'expected_output_resolution': self.expected_output_resolution
            },
            'error_info': {
                'has_error': bool(self.error_message),
                'error_message': self.error_message,
                'retry_count': self.retry_count,
                'can_retry': self.can_retry
            }
        }
    
    def generate_file_hash(self) -> str:
        """
        Génère un hash du fichier d'entrée pour vérification
        
        Returns:
            Hash SHA256 du fichier
        """
        if not os.path.exists(self.input_file):
            return ""
        
        hasher = hashlib.sha256()
        try:
            with open(self.input_file, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception:
            return ""
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convertit le job en dictionnaire
        
        Returns:
            Représentation en dictionnaire
        """
        return {
            'id': self.id,
            'name': self.name,
            'input_file': self.input_file,
            'output_file': self.output_file,
            'original_file_size': self.original_file_size,
            'final_file_size': self.final_file_size,
            'status': self.status.value,
            'priority': self.priority.value,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'paused_at': self.paused_at.isoformat() if self.paused_at else None,
            'total_pause_duration': self.total_pause_duration,
            'upscaling_config': self.upscaling_config,
            'video_info': self.video_info,
            'batch_counts': {
                'total': self.total_batches,
                'completed': self.completed_batches,
                'failed': self.failed_batches,
                'processing': self.processing_batches
            },
            'progress': {
                'frames_processed': self.frames_processed,
                'processing_time': self.processing_time,
                'progress_percentage': self.progress_percentage,
                'frames_progress_percentage': self.frames_progress_percentage,
                'estimated_completion': self.estimated_completion.isoformat() if self.estimated_completion else None,
                'processing_speed_fps': self.processing_speed_fps
            },
            'error_info': {
                'error_message': self.error_message,
                'retry_count': self.retry_count,
                'max_retries': self.max_retries,
                'can_retry': self.can_retry
            },
            'metadata': self.metadata,
            'tags': self.tags,
            'notes': self.notes,
            'events': self.events[-10:]  # Derniers 10 événements
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Job':
        """
        Crée un job à partir d'un dictionnaire
        
        Args:
            data: Données du job
            
        Returns:
            Instance de Job
        """
        job = cls(
            id=data['id'],
            input_file=data['input_file'],
            output_file=data['output_file'],
            status=JobStatus(data['status']),
            priority=JobPriority(data.get('priority', JobPriority.NORMAL.value))
        )
        
        # Restauration des propriétés
        job.name = data.get('name', job.name)
        job.original_file_size = data.get('original_file_size', 0)
        job.final_file_size = data.get('final_file_size', 0)
        job.total_pause_duration = data.get('total_pause_duration', 0.0)
        
        # Dates
        if data.get('created_at'):
            job.created_at = datetime.fromisoformat(data['created_at'])
        if data.get('started_at'):
            job.started_at = datetime.fromisoformat(data['started_at'])
        if data.get('completed_at'):
            job.completed_at = datetime.fromisoformat(data['completed_at'])
        if data.get('paused_at'):
            job.paused_at = datetime.fromisoformat(data['paused_at'])
        
        # Configuration et informations
        job.upscaling_config = data.get('upscaling_config', {})
        job.video_info = data.get('video_info', {})
        
        # Compteurs de lots
        batch_counts = data.get('batch_counts', {})
        job.total_batches = batch_counts.get('total', 0)
        job.completed_batches = batch_counts.get('completed', 0)
        job.failed_batches = batch_counts.get('failed', 0)
        job.processing_batches = batch_counts.get('processing', 0)
        
        # Progression
        progress = data.get('progress', {})
        job.frames_processed = progress.get('frames_processed', 0)
        job.processing_time = progress.get('processing_time', 0.0)
        if progress.get('estimated_completion'):
            job.estimated_completion = datetime.fromisoformat(progress['estimated_completion'])
        
        # Gestion d'erreurs
        error_info = data.get('error_info', {})
        job.error_message = error_info.get('error_message')
        job.retry_count = error_info.get('retry_count', 0)
        job.max_retries = error_info.get('max_retries', 2)
        
        # Métadonnées
        job.metadata = data.get('metadata', {})
        job.tags = data.get('tags', [])
        job.notes = data.get('notes', '')
        job.events = data.get('events', [])
        
        return job
    
    def __str__(self) -> str:
        return f"Job(id={self.id}, name={self.name}, status={self.status.value}, progress={self.progress_percentage:.1f}%)"
    
    def __repr__(self) -> str:
        return self.__str__()

class JobUtils:
    """Utilitaires pour la gestion des jobs"""
    
    @staticmethod
    def generate_job_id(input_file: str) -> str:
        """
        Génère un ID unique pour un job
        
        Args:
            input_file: Chemin du fichier d'entrée
            
        Returns:
            ID unique du job
        """
        import time
        
        file_name = Path(input_file).stem
        timestamp = int(time.time())
        hash_part = hashlib.md5(f"{input_file}{timestamp}".encode()).hexdigest()[:8]
        
        return f"job_{file_name}_{timestamp}_{hash_part}"
    
    @staticmethod
    def generate_output_filename(input_file: str, suffix: str = "_upscaled") -> str:
        """
        Génère un nom de fichier de sortie
        
        Args:
            input_file: Fichier d'entrée
            suffix: Suffixe à ajouter
            
        Returns:
            Chemin du fichier de sortie
        """
        input_path = Path(input_file)
        output_name = f"{input_path.stem}{suffix}{input_path.suffix}"
        return str(input_path.parent / output_name)
    
    @staticmethod
    def estimate_processing_time(video_info: Dict[str, Any], 
                               avg_fps_processing: float = 1.0) -> float:
        """
        Estime le temps de traitement d'une vidéo
        
        Args:
            video_info: Informations de la vidéo
            avg_fps_processing: Vitesse moyenne de traitement en FPS
            
        Returns:
            Temps estimé en secondes
        """
        total_frames = video_info.get('total_frames', 0)
        if total_frames == 0 or avg_fps_processing <= 0:
            return 0.0
        
        return total_frames / avg_fps_processing
    
    @staticmethod
    def validate_job_config(job_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Valide la configuration d'un job
        
        Args:
            job_config: Configuration à valider
            
        Returns:
            Résultat de la validation
        """
        validation = {
            'valid': True,  
            'errors': [],
            'warnings': []
        }
        
        # Vérification du fichier d'entrée
        input_file = job_config.get('input_file')
        if not input_file:
            validation['errors'].append("Fichier d'entrée manquant")
            validation['valid'] = False
        elif not os.path.exists(input_file):
            validation['errors'].append(f"Fichier d'entrée inexistant: {input_file}")
            validation['valid'] = False
        
        # Vérification du fichier de sortie
        output_file = job_config.get('output_file')
        if not output_file:
            validation['warnings'].append("Fichier de sortie non spécifié")
        elif os.path.exists(output_file):
            validation['warnings'].append(f"Le fichier de sortie existe déjà: {output_file}")
        
        # Vérification de la configuration d'upscaling
        upscaling_config = job_config.get('upscaling_config', {})
        
        scale_factor = upscaling_config.get('scale_factor', 4)
        if not isinstance(scale_factor, (int, float)) or scale_factor <= 1:
            validation['errors'].append("Facteur d'échelle invalide (doit être > 1)")
            validation['valid'] = False
        
        tile_size = upscaling_config.get('tile_size', 256)
        if not isinstance(tile_size, int) or tile_size < 64 or tile_size > 1024:
            validation['warnings'].append("Taille de tuile recommandée entre 64 et 1024")
        
        model = upscaling_config.get('model')
        valid_models = [m.value for m in UpscalingModel]
        if model and model not in valid_models:
            validation['warnings'].append(f"Modèle non reconnu: {model}")
        
        return validation
    
    @staticmethod
    def get_job_statistics(jobs: List[Job]) -> Dict[str, Any]:
        """
        Calcule des statistiques sur une liste de jobs
        
        Args:
            jobs: Liste des jobs
            
        Returns:
            Statistiques des jobs
        """
        if not jobs:
            return {
                'total_jobs': 0,
                'completed_jobs': 0,
                'active_jobs': 0,
                'failed_jobs': 0,
                'total_processing_time': 0,
                'total_frames_processed': 0,
                'average_processing_speed': 0
            }
        
        completed = [j for j in jobs if j.is_completed]
        active = [j for j in jobs if j.is_active]
        failed = [j for j in jobs if j.is_failed]
        
        total_processing_time = sum(j.processing_time for j in jobs)
        total_frames = sum(j.frames_processed for j in jobs)
        
        avg_speed = 0
        if total_processing_time > 0:
            avg_speed = total_frames / total_processing_time
        
        return {
            'total_jobs': len(jobs),
            'completed_jobs': len(completed),
            'active_jobs': len(active),
            'failed_jobs': len(failed),
            'paused_jobs': len([j for j in jobs if j.is_paused]),
            'total_processing_time': total_processing_time,
            'total_frames_processed': total_frames,
            'average_processing_speed_fps': avg_speed,
            'completion_rate': len(completed) / len(jobs) * 100 if jobs else 0,
            'jobs_by_status': {
                status.value: len([j for j in jobs if j.status == status])
                for status in JobStatus
            }
        }


# Fonctions utilitaires pour la création et gestion des jobs

def create_job_from_file(input_file: str, output_file: str = None, 
                        priority: JobPriority = JobPriority.NORMAL,
                        upscaling_config: Dict[str, Any] = None) -> Job:
    """
    Crée un nouveau job à partir d'un fichier vidéo
    
    Args:
        input_file: Chemin du fichier d'entrée
        output_file: Chemin du fichier de sortie (optionnel)
        priority: Priorité du job
        upscaling_config: Configuration d'upscaling personnalisée
        
    Returns:
        Instance de Job configurée
    """
    # Génération de l'ID unique
    job_id = JobUtils.generate_job_id(input_file)
    
    # Génération du fichier de sortie si non fourni
    if not output_file:
        output_file = JobUtils.generate_output_filename(input_file)
    
    # Création du job
    job = Job(
        id=job_id,
        input_file=input_file,
        output_file=output_file,
        priority=priority
    )
    
    # Application de la configuration personnalisée
    if upscaling_config:
        job.update_upscaling_config(upscaling_config)
    
    # Ajout de tags automatiques basés sur le fichier
    input_path = Path(input_file)
    job.tags.extend([
        f"ext_{input_path.suffix[1:].lower()}",  # Extension
        f"size_{job.original_file_size // (1024*1024)}mb"  # Taille approximative
    ])
    
    return job


def estimate_job_requirements(job: Job) -> Dict[str, Any]:
    """
    Estime les ressources nécessaires pour un job
    
    Args:
        job: Job à analyser
        
    Returns:
        Estimation des ressources
    """
    video_info = job.video_info
    upscaling_config = job.upscaling_config
    
    # Calculs de base
    input_resolution = video_info.get('width', 0) * video_info.get('height', 0)
    scale_factor = upscaling_config.get('scale_factor', 4)
    output_resolution = input_resolution * (scale_factor ** 2)
    
    # Estimation de l'espace disque nécessaire
    input_size_mb = job.original_file_size / (1024 * 1024)
    estimated_output_size_mb = input_size_mb * (scale_factor ** 2) * 0.8  # Facteur de compression
    
    # Estimation du temps de traitement
    frames_count = video_info.get('total_frames', 0)
    estimated_processing_fps = 2.0  # FPS moyen estimé
    estimated_time_seconds = frames_count / estimated_processing_fps if frames_count > 0 else 0
    
    # Estimation de la mémoire nécessaire
    tile_size = upscaling_config.get('tile_size', 256)
    estimated_memory_mb = (tile_size ** 2) * 3 * 4 * 2 / (1024 * 1024)  # RGB, float32, input+output
    
    return {
        'disk_space': {
            'input_size_mb': input_size_mb,
            'estimated_output_size_mb': estimated_output_size_mb,
            'temp_space_needed_mb': estimated_output_size_mb * 1.5,  # Espace temporaire
            'total_space_needed_mb': estimated_output_size_mb * 2.5
        },
        'processing': {
            'estimated_duration_seconds': estimated_time_seconds,
            'estimated_duration_formatted': _format_duration(estimated_time_seconds),
            'frames_to_process': frames_count,
            'complexity_score': _calculate_complexity_score(job)
        },
        'memory': {
            'estimated_ram_mb': estimated_memory_mb,
            'recommended_ram_mb': max(estimated_memory_mb * 2, 4096),  # Minimum 4GB
            'gpu_memory_mb': estimated_memory_mb * 1.5 if upscaling_config.get('use_gpu') else 0
        },
        'network': {
            'estimated_data_transfer_mb': estimated_output_size_mb * 2,  # Upload + download
            'recommended_bandwidth_mbps': 10  # Minimum recommandé
        }
    }


def _format_duration(seconds: float) -> str:
    """Formate une durée en secondes en format lisible"""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        remaining_seconds = int(seconds % 60)
        return f"{minutes}m {remaining_seconds}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


def _calculate_complexity_score(job: Job) -> float:
    """
    Calcule un score de complexité pour le job
    
    Args:
        job: Job à analyser
        
    Returns:
        Score de complexité (0-10)
    """
    score = 0.0
    
    # Facteur résolution
    resolution = job.video_info.get('width', 0) * job.video_info.get('height', 0)
    if resolution > 0:
        if resolution <= 720 * 480:      # SD
            score += 1.0
        elif resolution <= 1920 * 1080: # HD
            score += 2.5
        elif resolution <= 3840 * 2160: # 4K
            score += 4.0
        else:                            # 8K+
            score += 6.0
    
    # Facteur durée
    duration = job.video_info.get('duration_seconds', 0)
    if duration > 0:
        if duration <= 60:        # < 1 min
            score += 0.5
        elif duration <= 600:     # < 10 min
            score += 1.0
        elif duration <= 3600:    # < 1h
            score += 2.0
        else:                     # > 1h
            score += 3.0
    
    # Facteur upscaling
    scale_factor = job.upscaling_config.get('scale_factor', 4)
    score += min(scale_factor / 2, 3.0)
    
    # Facteur modèle
    model = job.upscaling_config.get('model', '')
    if 'anime' in model.lower():
        score += 0.5  # Modèles anime généralement plus lents
    
    return min(score, 10.0)


# Classes d'exception spécifiques aux jobs

class JobError(Exception):
    """Exception de base pour les erreurs de job"""
    pass


class JobValidationError(JobError):
    """Erreur de validation de job"""
    pass


class JobProcessingError(JobError):
    """Erreur lors du traitement d'un job"""
    pass


class JobTimeoutError(JobError):
    """Erreur de timeout de job"""
    pass


# Décorateurs utilitaires

def validate_job_state(allowed_states: List[JobStatus]):
    """
    Décorateur pour valider l'état d'un job avant l'exécution d'une méthode
    
    Args:
        allowed_states: États autorisés
    """
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            if self.status not in allowed_states:
                raise JobError(f"Opération non autorisée pour l'état {self.status.value}")
            return func(self, *args, **kwargs)
        return wrapper
    return decorator


# Exemple d'utilisation du décorateur sur les méthodes de Job
# (à appliquer si souhaité)

def log_job_operation(operation_name: str):
    """
    Décorateur pour logger les opérations sur les jobs
    
    Args:
        operation_name: Nom de l'opération
    """
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            self._add_event("operation_start", f"Début: {operation_name}")
            try:
                result = func(self, *args, **kwargs)
                self._add_event("operation_success", f"Succès: {operation_name}")
                return result
            except Exception as e:
                self._add_event("operation_error", f"Erreur {operation_name}: {str(e)}")
                raise
        return wrapper
    return decorator