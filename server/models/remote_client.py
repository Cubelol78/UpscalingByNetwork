# UpscalingByNetwork/server/models/remote_client.py

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum
import time
from datetime import datetime

class ClientStatus(Enum):
    """États d'un client distant"""
    CONNECTING = "connecting"     # En cours de connexion
    CONNECTED = "connected"       # Connecté mais inactif
    IDLE = "idle"                # Disponible pour traitement
    PROCESSING = "processing"     # En cours de traitement
    ERROR = "error"              # Erreur
    TIMEOUT = "timeout"          # Timeout
    DISCONNECTED = "disconnected" # Déconnecté

@dataclass
class RemoteClient:
    """Client distant pour traitement distribué"""
    mac_address: str = ""
    client_id: str = ""
    status: ClientStatus = ClientStatus.CONNECTING
    connected_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    disconnected_at: Optional[float] = None
    
    # Lot en cours
    current_batch_id: Optional[str] = None
    current_progress: float = 0.0
    batch_start_time: Optional[float] = None
    
    # Statistiques
    batches_completed: int = 0
    batches_failed: int = 0
    total_processing_time: float = 0.0
    total_frames_processed: int = 0
    
    # Informations système
    system_info: Dict[str, Any] = field(default_factory=dict)
    capabilities: Dict[str, Any] = field(default_factory=dict)
    
    # Configuration
    max_concurrent_batches: int = 1
    preferred_batch_size: int = 50
    
    # Réseau
    ip_address: str = ""
    connection_quality: float = 100.0  # 0-100
    
    @property
    def is_online(self) -> bool:
        """Vérifie si le client est en ligne"""
        return self.status not in [ClientStatus.DISCONNECTED, ClientStatus.TIMEOUT]
    
    @property
    def is_available(self) -> bool:
        """Vérifie si le client est disponible pour un nouveau lot"""
        return self.status == ClientStatus.IDLE and self.current_batch_id is None
    
    @property
    def connection_duration(self) -> float:
        """Durée de connexion en secondes"""
        if self.disconnected_at:
            return self.disconnected_at - self.connected_at
        return time.time() - self.connected_at
    
    @property
    def average_processing_time(self) -> float:
        """Temps moyen de traitement par lot"""
        if self.batches_completed == 0:
            return 0.0
        return self.total_processing_time / self.batches_completed
    
    @property
    def success_rate(self) -> float:
        """Taux de succès (0-100)"""
        total = self.batches_completed + self.batches_failed
        if total == 0:
            return 100.0
        return (self.batches_completed / total) * 100.0
    
    @property
    def is_stale(self) -> bool:
        """Vérifie si le client n'a pas donné signe de vie"""
        return time.time() - self.last_activity > 120  # 2 minutes
    
    def update_heartbeat(self, system_load: Dict[str, Any] = None):
        """Met à jour le heartbeat"""
        self.last_heartbeat = time.time()
        self.last_activity = time.time()
        
        if system_load:
            self.system_info.update(system_load)
    
    def assign_batch(self, batch_id: str):
        """Assigne un lot au client"""
        self.current_batch_id = batch_id
        self.status = ClientStatus.PROCESSING
        self.batch_start_time = time.time()
        self.current_progress = 0.0
        self.last_activity = time.time()
    
    def update_batch_progress(self, progress: float):
        """Met à jour la progression du lot"""
        self.current_progress = max(0, min(100, progress))
        self.last_activity = time.time()
    
    def complete_batch(self, processing_time: float, frames_processed: int):
        """Marque le lot comme terminé"""
        self.current_batch_id = None
        self.current_progress = 0.0
        self.status = ClientStatus.IDLE
        self.batch_start_time = None
        
        self.batches_completed += 1
        self.total_processing_time += processing_time
        self.total_frames_processed += frames_processed
        self.last_activity = time.time()
    
    def fail_batch(self, error: str = ""):
        """Marque le lot comme échoué"""
        self.current_batch_id = None
        self.current_progress = 0.0
        self.status = ClientStatus.IDLE
        self.batch_start_time = None
        
        self.batches_failed += 1
        self.last_activity = time.time()
    
    def disconnect(self):
        """Marque le client comme déconnecté"""
        self.status = ClientStatus.DISCONNECTED
        self.disconnected_at = time.time()
        self.current_batch_id = None
        self.current_progress = 0.0
    
    def reconnect(self):
        """Reconnecte le client"""
        self.status = ClientStatus.CONNECTED
        self.connected_at = time.time()
        self.last_activity = time.time()
        self.last_heartbeat = time.time()
        self.disconnected_at = None
        
        # Transition vers IDLE si pas de traitement en cours
        if not self.current_batch_id:
            self.status = ClientStatus.IDLE
    
    def set_error(self, error: str = ""):
        """Met le client en erreur"""
        self.status = ClientStatus.ERROR
        self.last_activity = time.time()
    
    def set_timeout(self):
        """Met le client en timeout"""
        self.status = ClientStatus.TIMEOUT
        self.current_batch_id = None
        self.current_progress = 0.0
    
    def get_performance_score(self) -> float:
        """Calcule un score de performance (0-100)"""
        # Facteurs: taux de succès, vitesse, stabilité connexion
        success_score = self.success_rate
        
        # Score de vitesse (inversement proportionnel au temps moyen)
        if self.average_processing_time > 0:
            # Référence: 1 seconde par image = 100%, plus rapide = bonus
            speed_score = min(100, (50 / self.average_processing_time) * 100)
        else:
            speed_score = 100
        
        # Score de stabilité (basé sur la qualité de connexion)
        stability_score = self.connection_quality
        
        # Score global pondéré
        performance = (success_score * 0.4 + speed_score * 0.4 + stability_score * 0.2)
        return max(0, min(100, performance))
    
    def to_dict(self) -> dict:
        """Convertit en dictionnaire pour sérialisation"""
        return {
            'mac_address': self.mac_address,
            'client_id': self.client_id,
            'status': self.status.value,
            'connected_at': self.connected_at,
            'last_activity': self.last_activity,
            'last_heartbeat': self.last_heartbeat,
            'disconnected_at': self.disconnected_at,
            'current_batch_id': self.current_batch_id,
            'current_progress': self.current_progress,
            'batches_completed': self.batches_completed,
            'batches_failed': self.batches_failed,
            'total_processing_time': self.total_processing_time,
            'total_frames_processed': self.total_frames_processed,
            'system_info': self.system_info,
            'capabilities': self.capabilities,
            'ip_address': self.ip_address,
            'connection_quality': self.connection_quality,
            'is_online': self.is_online,
            'is_available': self.is_available,
            'connection_duration': self.connection_duration,
            'average_processing_time': self.average_processing_time,
            'success_rate': self.success_rate,
            'performance_score': self.get_performance_score(),
            'is_stale': self.is_stale
        }