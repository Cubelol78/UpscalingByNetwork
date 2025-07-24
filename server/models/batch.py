# server/models/batch.py
"""
Modèle de données pour les lots (batches) d'upscaling
"""

import hashlib
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
from pathlib import Path

class BatchStatus(Enum):
    """États possibles d'un lot"""
    PENDING = "pending"          # En attente d'assignation
    PROCESSING = "processing"    # En cours de traitement par un client
    COMPLETED = "completed"      # Traitement terminé avec succès
    FAILED = "failed"           # Traitement échoué
    CANCELLED = "cancelled"      # Traitement annulé

class BatchPriority(Enum):
    """Priorités des lots"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4

class Batch:
    """
    Représente un lot d'images à traiter
    """
    
    def __init__(self, 
                 id: str,
                 job_id: str, 
                 frames_count: int,
                 input_directory: str,
                 status: BatchStatus = BatchStatus.PENDING,
                 priority: BatchPriority = BatchPriority.NORMAL):
        
        # Identifiants
        self.id = id
        self.job_id = job_id
        
        # Contenu
        self.frames_count = frames_count
        self.input_directory = input_directory
        self.output_directory: Optional[str] = None
        
        # État
        self.status = status
        self.priority = priority
        
        # Assignation
        self.assigned_to: Optional[str] = None  # MAC address du client
        self.assigned_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        
        # Données
        self.data_hash: Optional[str] = None  # Hash des données pour vérification
        self.data_size_bytes: int = 0
        
        # Gestion d'erreurs
        self.retry_count: int = 0
        self.max_retries: int = 3
        self.error_message: Optional[str] = None
        self.last_error_at: Optional[datetime] = None
        
        # Métadonnées
        self.created_at = datetime.now()
        self.metadata: Dict[str, Any] = {}
        
        # Configuration de traitement
        self.processing_config: Dict[str, Any] = {}
    
    @property
    def is_pending(self) -> bool:
        """Vérifie si le lot est en attente"""
        return self.status == BatchStatus.PENDING
    
    @property
    def is_processing(self) -> bool:
        """Vérifie si le lot est en cours de traitement"""
        return self.status == BatchStatus.PROCESSING
    
    @property
    def is_completed(self) -> bool:
        """Vérifie si le lot est terminé"""
        return self.status == BatchStatus.COMPLETED
    
    @property 
    def is_failed(self) -> bool:
        """Vérifie si le lot a échoué"""
        return self.status == BatchStatus.FAILED
    
    @property
    def can_retry(self) -> bool:
        """Vérifie si le lot peut être relancé"""
        return (self.status == BatchStatus.FAILED and 
                self.retry_count < self.max_retries)
    
    @property
    def processing_duration(self) -> Optional[float]:
        """Durée de traitement en secondes"""
        if self.assigned_at and self.completed_at:
            return (self.completed_at - self.assigned_at).total_seconds()
        elif self.assigned_at and self.status == BatchStatus.PROCESSING:
            return (datetime.now() - self.assigned_at).total_seconds()
        return None
    
    @property
    def total_duration(self) -> float:
        """Durée totale depuis la création en secondes"""
        end_time = self.completed_at or datetime.now()
        return (end_time - self.created_at).total_seconds()
    
    def assign_to_client(self, client_mac: str) -> bool:
        """
        Assigne le lot à un client
        
        Args:
            client_mac: Adresse MAC du client
            
        Returns:
            True si l'assignation a réussi
        """
        if self.status != BatchStatus.PENDING:
            return False
        
        self.assigned_to = client_mac
        self.assigned_at = datetime.now()
        self.status = BatchStatus.PROCESSING
        return True
    
    def mark_completed(self, output_directory: str) -> bool:
        """
        Marque le lot comme terminé
        
        Args:
            output_directory: Dossier contenant les résultats
            
        Returns:
            True si marqué comme terminé
        """
        if self.status != BatchStatus.PROCESSING:
            return False
        
        self.status = BatchStatus.COMPLETED
        self.completed_at = datetime.now()
        self.output_directory = output_directory
        return True
    
    def mark_failed(self, error_message: str) -> bool:
        """
        Marque le lot comme échoué
        
        Args:
            error_message: Message d'erreur
            
        Returns:
            True si marqué comme échoué
        """
        self.status = BatchStatus.FAILED
        self.error_message = error_message
        self.last_error_at = datetime.now()
        self.retry_count += 1
        
        # Libération de l'assignation
        self.assigned_to = None
        self.assigned_at = None
        
        return True
    
    def reset_for_retry(self) -> bool:
        """
        Remet le lot en attente pour un nouveau essai
        
        Returns:
            True si remis en attente
        """
        if not self.can_retry:
            return False
        
        self.status = BatchStatus.PENDING
        self.assigned_to = None
        self.assigned_at = None
        self.error_message = None
        
        return True
    
    def calculate_data_hash(self) -> str:
        """
        Calcule le hash des données du lot
        
        Returns:
            Hash SHA256 des fichiers du lot
        """
        if not self.input_directory or not Path(self.input_directory).exists():
            return ""
        
        hasher = hashlib.sha256()
        input_path = Path(self.input_directory)
        
        # Tri des fichiers pour un hash cohérent
        files = sorted(input_path.glob('*'))
        
        for file_path in files:
            if file_path.is_file():
                with open(file_path, 'rb') as f:
                    for chunk in iter(lambda: f.read(4096), b""):
                        hasher.update(chunk)
        
        self.data_hash = hasher.hexdigest()
        return self.data_hash
    
    def calculate_data_size(self) -> int:
        """
        Calcule la taille totale des données du lot
        
        Returns:
            Taille en bytes
        """
        if not self.input_directory or not Path(self.input_directory).exists():
            return 0
        
        total_size = 0
        input_path = Path(self.input_directory)
        
        for file_path in input_path.glob('*'):
            if file_path.is_file():
                total_size += file_path.stat().st_size
        
        self.data_size_bytes = total_size
        return total_size
    
    def get_frames_list(self) -> list:
        """
        Retourne la liste des fichiers frames du lot
        
        Returns:
            Liste des noms de fichiers
        """
        if not self.input_directory or not Path(self.input_directory).exists():
            return []
        
        input_path = Path(self.input_directory)
        image_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.webp'}
        
        frames = []
        for file_path in sorted(input_path.glob('*')):
            if file_path.is_file() and file_path.suffix.lower() in image_extensions:
                frames.append(file_path.name)
        
        return frames
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convertit le lot en dictionnaire
        
        Returns:
            Représentation en dictionnaire
        """
        return {
            'id': self.id,
            'job_id': self.job_id,
            'frames_count': self.frames_count,
            'input_directory': self.input_directory,
            'output_directory': self.output_directory,
            'status': self.status.value,
            'priority': self.priority.value,
            'assigned_to': self.assigned_to,
            'assigned_at': self.assigned_at.isoformat() if self.assigned_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'created_at': self.created_at.isoformat(),
            'data_hash': self.data_hash,
            'data_size_bytes': self.data_size_bytes,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'error_message': self.error_message,
            'last_error_at': self.last_error_at.isoformat() if self.last_error_at else None,
            'processing_duration': self.processing_duration,
            'total_duration': self.total_duration,
            'metadata': self.metadata,
            'processing_config': self.processing_config,
            'frames_list': self.get_frames_list()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Batch':
        """
        Crée un lot à partir d'un dictionnaire
        
        Args:
            data: Données du lot
            
        Returns:
            Instance de Batch
        """
        batch = cls(
            id=data['id'],
            job_id=data['job_id'],
            frames_count=data['frames_count'],
            input_directory=data['input_directory'],
            status=BatchStatus(data['status']),
            priority=BatchPriority(data.get('priority', BatchPriority.NORMAL.value))
        )
        
        # Restauration des autres propriétés
        batch.output_directory = data.get('output_directory')
        batch.assigned_to = data.get('assigned_to')
        batch.data_hash = data.get('data_hash')
        batch.data_size_bytes = data.get('data_size_bytes', 0)
        batch.retry_count = data.get('retry_count', 0)
        batch.max_retries = data.get('max_retries', 3)
        batch.error_message = data.get('error_message')
        batch.metadata = data.get('metadata', {})
        batch.processing_config = data.get('processing_config', {})
        
        # Dates
        if data.get('assigned_at'):
            batch.assigned_at = datetime.fromisoformat(data['assigned_at'])
        if data.get('completed_at'):
            batch.completed_at = datetime.fromisoformat(data['completed_at'])
        if data.get('created_at'):
            batch.created_at = datetime.fromisoformat(data['created_at'])
        if data.get('last_error_at'):
            batch.last_error_at = datetime.fromisoformat(data['last_error_at'])
        
        return batch
    
    def __str__(self) -> str:
        return f"Batch(id={self.id}, job={self.job_id}, status={self.status.value}, frames={self.frames_count})"
    
    def __repr__(self) -> str:
        return self.__str__()

class BatchUtils:
    """Utilitaires pour la gestion des lots"""
    
    @staticmethod
    def generate_batch_id(job_id: str, batch_number: int) -> str:
        """
        Génère un ID de lot
        
        Args:
            job_id: ID du job parent
            batch_number: Numéro du lot
            
        Returns:
            ID du lot
        """
        return f"{job_id}_batch_{batch_number:04d}"
    
    @staticmethod
    def sort_batches_by_priority(batches: list) -> list:
        """
        Trie les lots par priorité
        
        Args:
            batches: Liste des lots
            
        Returns:
            Liste triée
        """
        return sorted(batches, key=lambda b: (b.priority.value, b.created_at), reverse=True)
    
    @staticmethod
    def filter_pending_batches(batches: list) -> list:
        """
        Filtre les lots en attente
        
        Args:
            batches: Liste des lots
            
        Returns:
            Lots en attente
        """
        return [b for b in batches if b.is_pending]
    
    @staticmethod
    def get_batch_statistics(batches: list) -> Dict[str, Any]:
        """
        Calcule des statistiques sur les lots
        
        Args:
            batches: Liste des lots
            
        Returns:
            Statistiques
        """
        if not batches:
            return {'total': 0, 'pending': 0, 'processing': 0, 'completed': 0, 'failed': 0}
        
        stats = {
            'total': len(batches),
            'pending': len([b for b in batches if b.is_pending]),
            'processing': len([b for b in batches if b.is_processing]),
            'completed': len([b for b in batches if b.is_completed]),
            'failed': len([b for b in batches if b.is_failed])
        }
        
        # Calculs additionnels
        completed_batches = [b for b in batches if b.is_completed]
        if completed_batches:
            durations = [b.processing_duration for b in completed_batches if b.processing_duration]
            if durations:
                stats['average_processing_time'] = sum(durations) / len(durations)
                stats['min_processing_time'] = min(durations)
                stats['max_processing_time'] = max(durations)
        
        stats['total_frames'] = sum(b.frames_count for b in batches)
        stats['completed_frames'] = sum(b.frames_count for b in batches if b.is_completed)
        
        if stats['total_frames'] > 0:
            stats['completion_percentage'] = (stats['completed_frames'] / stats['total_frames']) * 100
        
        return stats