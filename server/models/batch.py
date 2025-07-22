# models/batch.py
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum
import time
from datetime import datetime
import uuid

class BatchStatus(Enum):
    """États d'un lot d'images"""
    PENDING = "pending"           # En attente
    ASSIGNED = "assigned"         # Assigné à un client
    PROCESSING = "processing"     # En cours de traitement
    COMPLETED = "completed"       # Terminé avec succès
    FAILED = "failed"            # Échec
    TIMEOUT = "timeout"          # Timeout
    DUPLICATE = "duplicate"      # Lot dupliqué (pour accélération)

@dataclass
class Batch:
    """Représente un lot d'images à traiter"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = ""
    frame_start: int = 0
    frame_end: int = 0
    frame_paths: List[str] = field(default_factory=list)
    status: BatchStatus = BatchStatus.PENDING
    assigned_client: Optional[str] = None  # MAC address du client
    created_at: datetime = field(default_factory=datetime.now)
    assigned_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    error_message: str = ""
    progress: float = 0.0  # Pourcentage de progression (0-100)
    estimated_time: Optional[int] = None  # Temps estimé en secondes
    
    @property
    def frame_count(self) -> int:
        """Nombre d'images dans le lot"""
        return len(self.frame_paths)
    
    @property
    def processing_time(self) -> Optional[int]:
        """Temps de traitement en secondes"""
        if self.started_at and self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds())
        return None
    
    def assign_to_client(self, client_mac: str):
        """Assigne le lot à un client"""
        self.assigned_client = client_mac
        self.status = BatchStatus.ASSIGNED
        self.assigned_at = datetime.now()
    
    def start_processing(self):
        """Marque le lot comme en cours de traitement"""
        self.status = BatchStatus.PROCESSING
        self.started_at = datetime.now()
    
    def complete(self):
        """Marque le lot comme terminé"""
        self.status = BatchStatus.COMPLETED
        self.completed_at = datetime.now()
        self.progress = 100.0
    
    def fail(self, error: str = ""):
        """Marque le lot comme échoué"""
        self.status = BatchStatus.FAILED
        self.completed_at = datetime.now()
        self.error_message = error
        self.retry_count += 1
    
    def reset(self):
        """Remet le lot en attente"""
        self.status = BatchStatus.PENDING
        self.assigned_client = None
        self.assigned_at = None
        self.started_at = None
        self.completed_at = None
        self.progress = 0.0
        self.error_message = ""