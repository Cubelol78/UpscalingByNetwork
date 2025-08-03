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
    """Représente un job d'upscaling complet"""
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
    has_audio: bool = False
    audio_path: str = ""
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