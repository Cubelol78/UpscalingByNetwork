# models/client.py
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum
import time
from datetime import datetime
import uuid

class ClientStatus(Enum):
    """États d'un client"""
    CONNECTING = "connecting"     # En cours de connexion
    CONNECTED = "connected"       # Connecté et idle
    PROCESSING = "processing"     # En cours de traitement
    DISCONNECTED = "disconnected" # Déconnecté
    ERROR = "error"              # En erreur

@dataclass
class Client:
    """Représente un client connecté"""
    mac_address: str
    ip_address: str = ""
    hostname: str = ""
    platform: str = ""  # Windows/Linux
    status: ClientStatus = ClientStatus.CONNECTING
    connected_at: datetime = field(default_factory=datetime.now)
    last_heartbeat: datetime = field(default_factory=datetime.now)
    current_batch: Optional[str] = None  # ID du lot en cours
    batches_completed: int = 0
    batches_failed: int = 0
    total_processing_time: int = 0  # en secondes
    average_batch_time: float = 0.0  # temps moyen par lot
    gpu_info: Dict[str, Any] = field(default_factory=dict)
    cpu_info: Dict[str, Any] = field(default_factory=dict)
    capabilities: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_online(self) -> bool:
        """Vérifie si le client est en ligne"""
        from config.settings import config
        time_diff = datetime.now() - self.last_heartbeat
        return time_diff.total_seconds() < config.CLIENT_TIMEOUT
    
    @property
    def success_rate(self) -> float:
        """Taux de succès du client"""
        total = self.batches_completed + self.batches_failed
        if total == 0:
            return 0.0
        return (self.batches_completed / total) * 100.0
    
    @property
    def connection_time(self) -> int:
        """Temps de connexion en secondes"""
        return int((datetime.now() - self.connected_at).total_seconds())
    
    def update_heartbeat(self):
        """Met à jour le heartbeat"""
        self.last_heartbeat = datetime.now()
        if self.status == ClientStatus.DISCONNECTED:
            self.status = ClientStatus.CONNECTED
    
    def assign_batch(self, batch_id: str):
        """Assigne un lot au client"""
        self.current_batch = batch_id
        self.status = ClientStatus.PROCESSING
    
    def complete_batch(self, processing_time: int):
        """Marque un lot comme terminé"""
        self.current_batch = None
        self.status = ClientStatus.CONNECTED
        self.batches_completed += 1
        self.total_processing_time += processing_time
        self.average_batch_time = self.total_processing_time / self.batches_completed
    
    def fail_batch(self):
        """Marque un lot comme échoué"""
        self.current_batch = None
        self.status = ClientStatus.CONNECTED
        self.batches_failed += 1
    
    def disconnect(self):
        """Marque le client comme déconnecté"""
        self.status = ClientStatus.DISCONNECTED
        self.current_batch = None