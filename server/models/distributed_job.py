# UpscalingByNetwork/server/models/distributed_job.py

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum
import time
from datetime import datetime
import uuid

class JobStatus(Enum):
    """États d'un job distribué"""
    CREATED = "created"           # Créé mais pas démarré
    EXTRACTING = "extracting"     # Extraction des frames
    PROCESSING = "processing"     # Distribution et traitement
    ASSEMBLING = "assembling"     # Assemblage final
    COMPLETED = "completed"       # Terminé avec succès
    FAILED = "failed"            # Échec
    CANCELLED = "cancelled"      # Annulé
    PAUSED = "paused"           # En pause

@dataclass
class DistributedJob:
    """Job d'upscaling distribué"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    input_video_path: str = ""
    output_video_path: str = ""
    status: JobStatus = JobStatus.CREATED
    created_at: float = field(default_factory=time.time)
    start_time: Optional[float] = None
    completion_time: Optional[float] = None
    
    # Informations vidéo
    total_frames: int = 0
    frame_rate: float = 30.0
    video_duration: float = 0.0
    video_width: int = 0
    video_height: int = 0
    has_audio: bool = False
    audio_path: str = ""
    
    # Gestion des lots
    batch_ids: List[str] = field(default_factory=list)
    completed_batches: int = 0
    failed_batches: int = 0
    
    # Configuration
    batch_size: int = 50
    upscale_factor: int = 4
    model_name: str = "realesr-animevideov3"
    
    # Statistiques
    total_processing_time: float = 0.0
    frames_processed: int = 0
    
    # Paramètres de distribution
    max_concurrent_batches: int = 10
    allow_duplicates: bool = True
    priority: int = 0  # 0 = normal, 1 = high, -1 = low
    
    # Métadonnées
    error_message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def progress(self) -> float:
        """Progression globale (0-100)"""
        if not self.batch_ids:
            return 0.0
        return (self.completed_batches / len(self.batch_ids)) * 100.0
    
    @property
    def total_batches(self) -> int:
        """Nombre total de lots"""
        return len(self.batch_ids)
    
    @property
    def pending_batches(self) -> int:
        """Nombre de lots en attente"""
        return self.total_batches - self.completed_batches - self.failed_batches
    
    @property
    def estimated_remaining_time(self) -> Optional[float]:
        """Estimation du temps restant en secondes"""
        if self.completed_batches == 0 or not self.start_time:
            return None
        
        elapsed = time.time() - self.start_time
        avg_time_per_batch = elapsed / self.completed_batches
        remaining_batches = self.total_batches - self.completed_batches
        
        return remaining_batches * avg_time_per_batch
    
    @property
    def estimated_completion_time(self) -> Optional[float]:
        """Estimation du timestamp de fin"""
        remaining = self.estimated_remaining_time
        if remaining:
            return time.time() + remaining
        return None
    
    @property
    def frames_per_second_processed(self) -> float:
        """Vitesse de traitement en images/seconde"""
        if not self.start_time:
            return 0.0
        
        elapsed = time.time() - self.start_time
        if elapsed <= 0:
            return 0.0
        
        return self.frames_processed / elapsed
    
    def start(self):
        """Démarre le job"""
        self.status = JobStatus.PROCESSING
        self.start_time = time.time()
    
    def complete(self):
        """Marque le job comme terminé"""
        self.status = JobStatus.COMPLETED
        self.completion_time = time.time()
        
        if self.start_time:
            self.total_processing_time = self.completion_time - self.start_time
    
    def fail(self, error: str = ""):
        """Marque le job comme échoué"""
        self.status = JobStatus.FAILED
        self.completion_time = time.time()
        self.error_message = error
        
        if self.start_time:
            self.total_processing_time = self.completion_time - self.start_time
    
    def cancel(self):
        """Annule le job"""
        self.status = JobStatus.CANCELLED
        self.completion_time = time.time()
        
        if self.start_time:
            self.total_processing_time = self.completion_time - self.start_time
    
    def pause(self):
        """Met le job en pause"""
        if self.status == JobStatus.PROCESSING:
            self.status = JobStatus.PAUSED
    
    def resume(self):
        """Reprend le job"""
        if self.status == JobStatus.PAUSED:
            self.status = JobStatus.PROCESSING
    
    def update_batch_completion(self, batch_id: str, success: bool, frames_count: int = 0):
        """Met à jour le compteur de lots terminés"""
        if success:
            self.completed_batches += 1
            self.frames_processed += frames_count
        else:
            self.failed_batches += 1
    
    def get_completion_stats(self) -> dict:
        """Retourne les statistiques de completion"""
        return {
            'total_batches': self.total_batches,
            'completed_batches': self.completed_batches,
            'failed_batches': self.failed_batches,
            'pending_batches': self.pending_batches,
            'progress_percent': self.progress,
            'frames_processed': self.frames_processed,
            'total_frames': self.total_frames,
            'frames_progress_percent': (self.frames_processed / self.total_frames * 100) if self.total_frames > 0 else 0
        }
    
    def get_time_stats(self) -> dict:
        """Retourne les statistiques de temps"""
        return {
            'created_at': self.created_at,
            'start_time': self.start_time,
            'completion_time': self.completion_time,
            'total_processing_time': self.total_processing_time,
            'estimated_remaining_time': self.estimated_remaining_time,
            'estimated_completion_time': self.estimated_completion_time,
            'frames_per_second': self.frames_per_second_processed
        }
    
    def to_dict(self) -> dict:
        """Convertit en dictionnaire pour sérialisation"""
        return {
            'id': self.id,
            'input_video_path': self.input_video_path,
            'output_video_path': self.output_video_path,
            'status': self.status.value,
            'created_at': self.created_at,
            'start_time': self.start_time,
            'completion_time': self.completion_time,
            'total_frames': self.total_frames,
            'frame_rate': self.frame_rate,
            'video_duration': self.video_duration,
            'video_width': self.video_width,
            'video_height': self.video_height,
            'has_audio': self.has_audio,
            'batch_size': self.batch_size,
            'upscale_factor': self.upscale_factor,
            'model_name': self.model_name,
            'priority': self.priority,
            'error_message': self.error_message,
            **self.get_completion_stats(),
            **self.get_time_stats()
        }
