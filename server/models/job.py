# models/job.py
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum
import time
from datetime import datetime
import uuid

class JobStatus(Enum):
    """États d'un job d'upscaling"""
    CREATED = "created"           # Créé mais pas démarré
    EXTRACTING = "extracting"     # Extraction des frames
    PROCESSING = "processing"     # Traitement des lots
    ASSEMBLING = "assembling"     # Assemblage de la vidéo finale
    COMPLETED = "completed"       # Terminé avec succès
    FAILED = "failed"            # Échec
    CANCELLED = "cancelled"      # Annulé par l'utilisateur

@dataclass
class Job:
    """Représente un job d'upscaling complet avec support des sous-titres"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    input_video_path: str = ""
    output_video_path: str = ""
    status: JobStatus = JobStatus.CREATED
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_frames: int = 0
    frame_rate: float = 30.0
    batches: List[str] = field(default_factory=list)  # Liste des IDs de lots
    completed_batches: int = 0
    failed_batches: int = 0
    
    # Informations audio
    has_audio: bool = False
    audio_path: str = ""
    
    # Informations sous-titres - NOUVEAU
    has_subtitles: bool = False
    subtitle_info: Dict[str, Any] = field(default_factory=dict)  # Infos détectées
    subtitle_paths: List[Dict[str, Any]] = field(default_factory=list)  # Fichiers extraits
    
    # Autres
    error_message: str = ""
    
    @property
    def progress(self) -> float:
        """Progression globale du job (0-100)"""
        if not self.batches:
            return 0.0
        return (self.completed_batches / len(self.batches)) * 100.0
    
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
        avg_time_per_batch = elapsed / self.completed_batches
        
        return int(remaining_batches * avg_time_per_batch)
    
    @property
    def subtitle_summary(self) -> str:
        """Résumé des sous-titres pour affichage"""
        if not self.has_subtitles:
            return "Aucun sous-titre"
        
        detected = self.subtitle_info.get('count', 0)
        extracted = len(self.subtitle_paths)
        
        if extracted == 0:
            return f"{detected} détecté(s), non extraits"
        elif extracted == detected:
            return f"{extracted} sous-titre(s) OK"
        else:
            return f"{extracted}/{detected} extraits"
    
    @property
    def subtitle_languages(self) -> List[str]:
        """Liste des langues de sous-titres disponibles"""
        if not self.subtitle_paths:
            return []
        
        languages = []
        for subtitle in self.subtitle_paths:
            lang = subtitle.get('language', 'unknown')
            if lang not in languages:
                languages.append(lang)
        
        return languages
    
    def start(self):
        """Démarre le job"""
        self.status = JobStatus.PROCESSING
        self.started_at = datetime.now()
    
    def complete(self):
        """Marque le job comme terminé"""
        self.status = JobStatus.COMPLETED
        self.completed_at = datetime.now()
    
    def fail(self, error: str = ""):
        """Marque le job comme échoué"""
        self.status = JobStatus.FAILED
        self.completed_at = datetime.now()
        self.error_message = error
    
    def cancel(self):
        """Annule le job"""
        self.status = JobStatus.CANCELLED
        self.completed_at = datetime.now()
    
    def get_subtitle_by_language(self, language: str) -> Optional[Dict[str, Any]]:
        """Récupère un sous-titre par langue"""
        for subtitle in self.subtitle_paths:
            if subtitle.get('language') == language:
                return subtitle
        return None
    
    def get_default_subtitle(self) -> Optional[Dict[str, Any]]:
        """Récupère le sous-titre par défaut"""
        # Chercher d'abord un sous-titre marqué comme défaut
        for subtitle in self.subtitle_paths:
            if subtitle.get('default', False):
                return subtitle
        
        # Sinon prendre le premier sous-titre forcé
        for subtitle in self.subtitle_paths:
            if subtitle.get('forced', False):
                return subtitle
        
        # Sinon prendre le premier sous-titre disponible
        return self.subtitle_paths[0] if self.subtitle_paths else None
    
    def add_subtitle_info(self, subtitle_info: Dict[str, Any]):
        """Ajoute les informations de sous-titres détectées"""
        self.subtitle_info = subtitle_info
        self.has_subtitles = subtitle_info.get('count', 0) > 0
    
    def add_extracted_subtitle(self, subtitle_data: Dict[str, Any]):
        """Ajoute un sous-titre extrait"""
        if not self.subtitle_paths:
            self.subtitle_paths = []
        self.subtitle_paths.append(subtitle_data)
    
    def get_processing_summary(self) -> Dict[str, Any]:
        """Retourne un résumé complet du traitement"""
        return {
            'job_id': self.id,
            'status': self.status.value,
            'progress': self.progress,
            'frames': {
                'total': self.total_frames,
                'frame_rate': self.frame_rate
            },
            'batches': {
                'total': len(self.batches),
                'completed': self.completed_batches,
                'failed': self.failed_batches
            },
            'media': {
                'has_audio': self.has_audio,
                'has_subtitles': self.has_subtitles,
                'subtitle_count': len(self.subtitle_paths),
                'subtitle_languages': self.subtitle_languages
            },
            'timing': {
                'created': self.created_at.isoformat(),
                'started': self.started_at.isoformat() if self.started_at else None,
                'completed': self.completed_at.isoformat() if self.completed_at else None,
                'processing_time': self.processing_time,
                'estimated_remaining': self.estimated_remaining_time
            },
            'files': {
                'input': self.input_video_path,
                'output': self.output_video_path,
                'audio': self.audio_path if hasattr(self, 'audio_path') else "",
                'subtitles': self.subtitle_paths
            }
        }