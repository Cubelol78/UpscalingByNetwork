"""
Modèles de données pour le système distribué
UpscalingByNetwork/server/models/network_batch.py
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum
import time
from datetime import datetime
import uuid

class BatchStatus(Enum):
    """États d'un lot dans le système distribué"""
    PENDING = "pending"           # En attente d'assignation
    ASSIGNED = "assigned"         # Assigné à un client
    PROCESSING = "processing"     # En cours de traitement
    COMPLETED = "completed"       # Terminé avec succès
    FAILED = "failed"            # Échec de traitement
    TIMEOUT = "timeout"          # Timeout client
    DUPLICATE = "duplicate"      # Lot dupliqué pour accélération
    CANCELLED = "cancelled"      # Annulé

@dataclass
class NetworkBatch:
    """Lot d'images pour traitement distribué"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = ""
    frame_start: int = 0
    frame_end: int = 0
    frame_paths: List[str] = field(default_factory=list)
    status: BatchStatus = BatchStatus.PENDING
    assigned_client: Optional[str] = None  # MAC address
    created_at: float = field(default_factory=time.time)
    assigned_at: Optional[float] = None
    start_time: Optional[float] = None
    completion_time: Optional[float] = None
    retry_count: int = 0
    max_retries: int = 3
    error_message: str = ""
    progress: float = 0.0  # 0-100
    zip_path: str = ""  # Chemin vers le ZIP du lot
    encrypted_path: str = ""  # Chemin vers la version chiffrée
    result_path: str = ""  # Chemin vers les résultats
    session_key: Optional[bytes] = None
    
    # Statistiques de traitement
    frames_processed: int = 0
    processing_time: float = 0.0
    
    # Métadonnées
    is_duplicate: bool = False
    original_batch_id: Optional[str] = None
    
    @property
    def frame_count(self) -> int:
        """Nombre d'images dans le lot"""
        return len(self.frame_paths)
    
    @property
    def total_processing_time(self) -> Optional[float]:
        """Temps total de traitement en secondes"""
        if self.start_time and self.completion_time:
            return self.completion_time - self.start_time
        return None
    
    @property
    def is_expired(self) -> bool:
        """Vérifie si le lot a expiré (timeout)"""
        if self.assigned_at and self.status in [BatchStatus.ASSIGNED, BatchStatus.PROCESSING]:
            # Timeout après 30 minutes
            return time.time() - self.assigned_at > 1800
        return False
    
    @property
    def can_retry(self) -> bool:
        """Vérifie si le lot peut être retenté"""
        return self.retry_count < self.max_retries
    
    def assign_to_client(self, client_mac: str):
        """Assigne le lot à un client"""
        self.assigned_client = client_mac
        self.status = BatchStatus.ASSIGNED
        self.assigned_at = time.time()
    
    def start_processing(self):
        """Démarre le traitement"""
        self.status = BatchStatus.PROCESSING
        self.start_time = time.time()
    
    def update_progress(self, progress: float, frames_processed: int = None):
        """Met à jour la progression"""
        self.progress = max(0, min(100, progress))
        if frames_processed is not None:
            self.frames_processed = frames_processed
    
    def complete(self, processing_time: float = None):
        """Marque le lot comme terminé"""
        self.status = BatchStatus.COMPLETED
        self.completion_time = time.time()
        self.progress = 100.0
        
        if processing_time:
            self.processing_time = processing_time
        elif self.start_time:
            self.processing_time = self.completion_time - self.start_time
    
    def fail(self, error: str = "", can_retry: bool = True):
        """Marque le lot comme échoué"""
        self.status = BatchStatus.FAILED
        self.completion_time = time.time()
        self.error_message = error
        
        if can_retry and self.can_retry:
            self.retry_count += 1
        
        if self.start_time:
            self.processing_time = self.completion_time - self.start_time
    
    def timeout(self):
        """Marque le lot comme timeout"""
        self.status = BatchStatus.TIMEOUT
        self.completion_time = time.time()
        self.error_message = "Timeout client"
        
        if self.can_retry:
            self.retry_count += 1
    
    def reset_for_retry(self):
        """Remet le lot en attente pour nouvelle tentative"""
        if not self.can_retry:
            return False
        
        self.status = BatchStatus.PENDING
        self.assigned_client = None
        self.assigned_at = None
        self.start_time = None
        self.completion_time = None
        self.progress = 0.0
        self.frames_processed = 0
        self.session_key = None
        
        return True
    
    def cancel(self):
        """Annule le lot"""
        self.status = BatchStatus.CANCELLED
        self.completion_time = time.time()
    
    def create_duplicate(self) -> 'NetworkBatch':
        """Crée un lot dupliqué pour accélération"""
        duplicate = NetworkBatch(
            job_id=self.job_id,
            frame_start=self.frame_start,
            frame_end=self.frame_end,
            frame_paths=self.frame_paths.copy(),
            status=BatchStatus.DUPLICATE,
            zip_path=self.zip_path,  # Même fichier source
            is_duplicate=True,
            original_batch_id=self.id
        )
        return duplicate
    
    def to_dict(self) -> dict:
        """Convertit en dictionnaire pour sérialisation"""
        return {
            'id': self.id,
            'job_id': self.job_id,
            'frame_start': self.frame_start,
            'frame_end': self.frame_end,
            'frame_count': self.frame_count,
            'status': self.status.value,
            'assigned_client': self.assigned_client,
            'created_at': self.created_at,
            'assigned_at': self.assigned_at,
            'start_time': self.start_time,
            'completion_time': self.completion_time,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'error_message': self.error_message,
            'progress': self.progress,
            'frames_processed': self.frames_processed,
            'processing_time': self.processing_time,
            'total_processing_time': self.total_processing_time,
            'is_duplicate': self.is_duplicate,
            'original_batch_id': self.original_batch_id,
            'can_retry': self.can_retry,
            'is_expired': self.is_expired
        }