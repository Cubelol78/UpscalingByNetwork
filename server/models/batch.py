# server/src/models/batch.py
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum
from datetime import datetime
import uuid
import os

class BatchStatus(Enum):
    """États possibles d'un lot d'images"""
    PENDING = "pending"           # En attente d'assignation
    ASSIGNED = "assigned"         # Assigné à un client
    PROCESSING = "processing"     # En cours de traitement
    COMPLETED = "completed"       # Terminé avec succès
    FAILED = "failed"            # Échec de traitement
    TIMEOUT = "timeout"          # Timeout dépassé
    DUPLICATE = "duplicate"      # Lot dupliqué pour accélération

@dataclass
class Batch:
    """
    Représente un lot d'images à traiter pour l'upscaling.
    Un lot = un dossier contenant ~50 images avec workflow complet
    """
    # Identifiants
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = ""  # ID de la vidéo source
    
    # Définition du lot
    frame_start: int = 0  # Index de la première image
    frame_end: int = 0    # Index de la dernière image  
    frame_paths: List[str] = field(default_factory=list)  # Noms des fichiers (relatifs)
    
    # Dossiers de travail
    batch_folder: Optional[str] = None  # Chemin vers le dossier du lot
    
    # État et assignation
    status: BatchStatus = BatchStatus.PENDING
    assigned_client: Optional[str] = None  # Adresse MAC du client assigné
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    assigned_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Gestion des erreurs et reprises
    retry_count: int = 0
    max_retries: int = 3
    error_message: str = ""
    
    # Progression et métriques
    progress: float = 0.0  # Pourcentage de progression (0-100)
    estimated_time: Optional[int] = None  # Temps estimé en secondes
    
    # Paramètres d'upscaling
    scale_factor: int = 4  # Facteur d'agrandissement (2x, 4x, etc.)
    model_name: str = "realesrgan-x4plus"  # Modèle Real-ESRGAN à utiliser
    
    # Métriques de transfert
    original_size_mb: float = 0.0  # Taille du lot original en MB
    compressed_size_mb: float = 0.0  # Taille compressée en MB
    upscaled_size_mb: float = 0.0  # Taille après upscaling en MB
    
    @property
    def frame_count(self) -> int:
        """Retourne le nombre d'images dans le lot"""
        return len(self.frame_paths)
    
    @property
    def processing_time(self) -> Optional[int]:
        """Retourne le temps de traitement en secondes"""
        if self.started_at and self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds())
        return None
    
    @property
    def is_completed(self) -> bool:
        """Vérifie si le lot est terminé (succès ou échec définitif)"""
        return self.status in [BatchStatus.COMPLETED, BatchStatus.FAILED]
    
    @property
    def can_retry(self) -> bool:
        """Vérifie si le lot peut être réessayé"""
        return (self.status in [BatchStatus.FAILED, BatchStatus.TIMEOUT] and 
                self.retry_count < self.max_retries)
    
    @property
    def age_minutes(self) -> float:
        """Retourne l'âge du lot en minutes"""
        return (datetime.now() - self.created_at).total_seconds() / 60
    
    @property
    def batch_folder_exists(self) -> bool:
        """Vérifie si le dossier du lot existe"""
        return self.batch_folder and os.path.exists(self.batch_folder)
    
    @property
    def compression_ratio(self) -> float:
        """Calcule le ratio de compression (0-1)"""
        if self.original_size_mb > 0 and self.compressed_size_mb > 0:
            return self.compressed_size_mb / self.original_size_mb
        return 1.0
    
    def assign_to_client(self, client_mac: str) -> None:
        """Assigne le lot à un client spécifique"""
        self.assigned_client = client_mac
        self.status = BatchStatus.ASSIGNED
        self.assigned_at = datetime.now()
    
    def start_processing(self) -> None:
        """Marque le lot comme en cours de traitement"""
        self.status = BatchStatus.PROCESSING
        self.started_at = datetime.now()
    
    def update_progress(self, progress: float) -> None:
        """Met à jour la progression du lot (0-100)"""
        self.progress = max(0, min(100, progress))
    
    def complete(self) -> None:
        """Marque le lot comme terminé avec succès"""
        self.status = BatchStatus.COMPLETED
        self.completed_at = datetime.now()
        self.progress = 100.0
    
    def fail(self, error_message: str = "") -> None:
        """Marque le lot comme échoué"""
        self.status = BatchStatus.FAILED
        self.completed_at = datetime.now()
        self.error_message = error_message
        self.retry_count += 1
    
    def timeout(self) -> None:
        """Marque le lot comme ayant dépassé le timeout"""
        self.status = BatchStatus.TIMEOUT
        self.completed_at = datetime.now()
        self.error_message = f"Timeout après {self.processing_time}s"
        self.retry_count += 1
    
    def reset_for_retry(self) -> None:
        """Remet le lot en état d'attente pour un nouvel essai"""
        if self.can_retry:
            self.status = BatchStatus.PENDING
            self.assigned_client = None
            self.assigned_at = None
            self.started_at = None
            self.completed_at = None
            self.progress = 0.0
            # Note: on garde error_message pour debugging
    
    def create_duplicate(self) -> 'Batch':
        """Crée un lot dupliqué pour accélération (partage le même dossier)"""
        duplicate = Batch(
            job_id=self.job_id,
            frame_start=self.frame_start,
            frame_end=self.frame_end,
            frame_paths=self.frame_paths.copy(),
            batch_folder=self.batch_folder,  # Même dossier source
            scale_factor=self.scale_factor,
            model_name=self.model_name,
            status=BatchStatus.DUPLICATE,
            original_size_mb=self.original_size_mb
        )
        return duplicate
    
    def calculate_folder_size(self) -> float:
        """Calcule la taille du dossier du lot en MB"""
        if not self.batch_folder_exists:
            return 0.0
        
        total_size = 0
        for root, dirs, files in os.walk(self.batch_folder):
            for file in files:
                file_path = os.path.join(root, file)
                if os.path.exists(file_path):
                    total_size += os.path.getsize(file_path)
        
        size_mb = total_size / (1024 * 1024)
        self.original_size_mb = size_mb
        return size_mb
    
    def to_dict(self) -> dict:
        """Convertit le lot en dictionnaire pour transmission réseau"""
        return {
            'id': self.id,
            'job_id': self.job_id,
            'frame_start': self.frame_start,
            'frame_end': self.frame_end,
            'frame_paths': self.frame_paths,
            'frame_count': self.frame_count,
            'status': self.status.value,
            'assigned_client': self.assigned_client,
            'created_at': self.created_at.isoformat(),
            'progress': self.progress,
            'retry_count': self.retry_count,
            'error_message': self.error_message,
            'scale_factor': self.scale_factor,
            'model_name': self.model_name,
            'estimated_time': self.estimated_time,
            'original_size_mb': self.original_size_mb,
            'compressed_size_mb': self.compressed_size_mb,
            'upscaled_size_mb': self.upscaled_size_mb,
            'processing_time': self.processing_time
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Batch':
        """Crée un lot depuis un dictionnaire"""
        batch = cls(
            id=data['id'],
            job_id=data['job_id'],
            frame_start=data['frame_start'],
            frame_end=data['frame_end'],
            frame_paths=data['frame_paths'],
            scale_factor=data.get('scale_factor', 4),
            model_name=data.get('model_name', 'realesrgan-x4plus'),
            progress=data.get('progress', 0.0),
            retry_count=data.get('retry_count', 0),
            error_message=data.get('error_message', ''),
            estimated_time=data.get('estimated_time'),
            original_size_mb=data.get('original_size_mb', 0.0),
            compressed_size_mb=data.get('compressed_size_mb', 0.0),
            upscaled_size_mb=data.get('upscaled_size_mb', 0.0)
        )
        
        # Conversion du statut
        batch.status = BatchStatus(data['status'])
        batch.assigned_client = data.get('assigned_client')
        
        # Conversion des dates
        if data.get('created_at'):
            batch.created_at = datetime.fromisoformat(data['created_at'])
        
        return batch

# Utilitaires pour la gestion des lots
class BatchUtils:
    """Utilitaires pour la manipulation des lots avec dossiers"""
    
    @staticmethod
    def get_pending_batches(batches: List[Batch]) -> List[Batch]:
        """Retourne les lots en attente de traitement"""
        return [b for b in batches if b.status == BatchStatus.PENDING]
    
    @staticmethod
    def get_processing_batches(batches: List[Batch]) -> List[Batch]:
        """Retourne les lots en cours de traitement"""
        return [b for b in batches if b.status == BatchStatus.PROCESSING]
    
    @staticmethod
    def get_completed_batches(batches: List[Batch]) -> List[Batch]:
        """Retourne les lots terminés avec succès"""
        return [b for b in batches if b.status == BatchStatus.COMPLETED]
    
    @staticmethod
    def get_failed_batches(batches: List[Batch]) -> List[Batch]:
        """Retourne les lots échoués qui peuvent être réessayés"""
        return [b for b in batches if b.status in [BatchStatus.FAILED, BatchStatus.TIMEOUT] and b.can_retry]
    
    @staticmethod
    def get_duplicate_batches(batches: List[Batch]) -> List[Batch]:
        """Retourne les lots dupliqués"""
        return [b for b in batches if b.status == BatchStatus.DUPLICATE]
    
    @staticmethod
    def calculate_job_progress(batches: List[Batch]) -> dict:
        """Calcule la progression globale d'une tâche"""
        if not batches:
            return {
                'progress': 0, 
                'total': 0, 
                'completed': 0, 
                'processing': 0, 
                'failed': 0,
                'pending': 0,
                'duplicates': 0,
                'total_frames': 0,
                'completed_frames': 0
            }
        
        # Exclusion des doublons du calcul de progression principal
        main_batches = [b for b in batches if b.status != BatchStatus.DUPLICATE]
        
        total = len(main_batches)
        completed = len([b for b in main_batches if b.status == BatchStatus.COMPLETED])
        processing = len([b for b in main_batches if b.status == BatchStatus.PROCESSING])
        failed = len([b for b in main_batches if b.status == BatchStatus.FAILED and not b.can_retry])
        pending = len([b for b in main_batches if b.status == BatchStatus.PENDING])
        duplicates = len([b for b in batches if b.status == BatchStatus.DUPLICATE])
        
        # Calcul basé sur les lots principaux uniquement
        progress = (completed / total) * 100 if total > 0 else 0
        
        # Calcul des frames totales
        total_frames = sum(len(b.frame_paths) for b in main_batches)
        completed_frames = sum(len(b.frame_paths) for b in main_batches if b.status == BatchStatus.COMPLETED)
        
        return {
            'progress': round(progress, 2),
            'total': total,
            'completed': completed,
            'processing': processing,
            'failed': failed,
            'pending': pending,
            'duplicates': duplicates,
            'total_frames': total_frames,
            'completed_frames': completed_frames,
            'frame_progress': round((completed_frames / total_frames) * 100, 2) if total_frames > 0 else 0
        }
    
    @staticmethod
    def get_batch_by_client(batches: List[Batch], client_mac: str) -> Optional[Batch]:
        """Trouve le lot assigné à un client spécifique"""
        for batch in batches:
            if batch.assigned_client == client_mac and batch.status in [BatchStatus.ASSIGNED, BatchStatus.PROCESSING]:
                return batch
        return None
    
    @staticmethod
    def cleanup_completed_batches(batches: List[Batch], keep_hours: int = 24) -> List[str]:
        """
        Nettoie les lots terminés depuis plus de X heures
        
        Args:
            batches: Liste des lots
            keep_hours: Nombre d'heures à conserver
            
        Returns:
            Liste des IDs de lots nettoyés
        """
        from datetime import timedelta
        
        cutoff_time = datetime.now() - timedelta(hours=keep_hours)
        cleaned_ids = []
        
        for batch in batches:
            if (batch.status == BatchStatus.COMPLETED and 
                batch.completed_at and 
                batch.completed_at < cutoff_time):
                
                # Nettoyage du dossier si il existe encore
                if batch.batch_folder_exists:
                    try:
                        import shutil
                        shutil.rmtree(batch.batch_folder)
                        cleaned_ids.append(batch.id)
                    except Exception:
                        pass  # Ignore les erreurs de nettoyage
        
        return cleaned_ids
    
    @staticmethod
    def estimate_transfer_time(batch: Batch, bandwidth_mbps: float) -> dict:
        """
        Estime les temps de transfert pour un lot
        
        Args:
            batch: Le lot à analyser
            bandwidth_mbps: Bande passante en Mbps
            
        Returns:
            Dictionnaire avec les estimations
        """
        if bandwidth_mbps <= 0:
            return {'download_seconds': 0, 'upload_seconds': 0, 'total_seconds': 0}
        
        # Conversion Mbps en MB/s
        bandwidth_mbs = bandwidth_mbps / 8
        
        # Estimation taille upscalée (facteur 4 = 16x plus de pixels, mais compression PNG)
        estimated_upscaled_mb = batch.original_size_mb * 12  # Estimation conservative
        
        download_time = batch.compressed_size_mb / bandwidth_mbs if batch.compressed_size_mb > 0 else batch.original_size_mb / bandwidth_mbs
        upload_time = estimated_upscaled_mb / bandwidth_mbs
        total_time = download_time + upload_time
        
        return {
            'download_seconds': round(download_time, 1),
            'upload_seconds': round(upload_time, 1), 
            'total_seconds': round(total_time, 1),
            'estimated_upscaled_mb': round(estimated_upscaled_mb, 1)
        }
    
    @staticmethod
    def validate_batch_integrity(batch: Batch) -> dict:
        """
        Valide l'intégrité d'un lot
        
        Returns:
            Dictionnaire avec le résultat de validation
        """
        issues = []
        
        # Vérification dossier
        if not batch.batch_folder:
            issues.append("Aucun dossier défini")
        elif not batch.batch_folder_exists:
            issues.append("Dossier inexistant")
        
        # Vérification cohérence frames
        if batch.frame_count == 0:
            issues.append("Aucune image définie")
        
        expected_count = batch.frame_end - batch.frame_start + 1
        if batch.frame_count != expected_count:
            issues.append(f"Incohérence nombre d'images: {batch.frame_count} vs {expected_count} attendu")
        
        # Vérification fichiers physiques
        if batch.batch_folder_exists:
            import os
            actual_files = [f for f in os.listdir(batch.batch_folder) if f.endswith('.png')]
            missing_files = []
            
            for frame_name in batch.frame_paths:
                frame_path = os.path.join(batch.batch_folder, frame_name)
                if not os.path.exists(frame_path):
                    missing_files.append(frame_name)
            
            if missing_files:
                issues.append(f"Fichiers manquants: {missing_files[:3]}..." if len(missing_files) > 3 else f"Fichiers manquants: {missing_files}")
        
        # Vérification état cohérent
        if batch.status == BatchStatus.COMPLETED and not batch.completed_at:
            issues.append("Lot marqué terminé sans timestamp")
        
        if batch.status == BatchStatus.PROCESSING and not batch.started_at:
            issues.append("Lot en traitement sans timestamp de début")
        
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'severity': 'error' if any('manquant' in issue.lower() or 'inexistant' in issue.lower() for issue in issues) else 'warning'
        }

class BatchStatistics:
    """Calculs statistiques avancés pour les lots"""
    
    @staticmethod
    def calculate_performance_metrics(batches: List[Batch]) -> dict:
        """Calcule les métriques de performance globales"""
        completed_batches = [b for b in batches if b.status == BatchStatus.COMPLETED and b.processing_time]
        
        if not completed_batches:
            return {
                'average_processing_time': 0,
                'fastest_batch_time': 0,
                'slowest_batch_time': 0,
                'total_frames_processed': 0,
                'average_frames_per_second': 0,
                'total_data_processed_mb': 0,
                'efficiency_score': 0
            }
        
        processing_times = [b.processing_time for b in completed_batches]
        total_frames = sum(b.frame_count for b in completed_batches)
        total_processing_time = sum(processing_times)
        total_data_mb = sum(b.original_size_mb for b in completed_batches)
        
        return {
            'average_processing_time': round(sum(processing_times) / len(processing_times), 2),
            'fastest_batch_time': min(processing_times),
            'slowest_batch_time': max(processing_times),
            'total_frames_processed': total_frames,
            'average_frames_per_second': round(total_frames / total_processing_time, 2) if total_processing_time > 0 else 0,
            'total_data_processed_mb': round(total_data_mb, 2),
            'efficiency_score': BatchStatistics._calculate_efficiency_score(completed_batches)
        }
    
    @staticmethod
    def _calculate_efficiency_score(batches: List[Batch]) -> float:
        """Calcule un score d'efficacité basé sur plusieurs facteurs"""
        if not batches:
            return 0.0
        
        # Facteurs d'efficacité
        total_score = 0
        
        for batch in batches:
            batch_score = 100  # Score de base
            
            # Pénalité pour les retries
            batch_score -= batch.retry_count * 10
            
            # Bonus pour traitement rapide (moins de 2s par frame)
            if batch.processing_time and batch.frame_count > 0:
                time_per_frame = batch.processing_time / batch.frame_count
                if time_per_frame < 2.0:
                    batch_score += 20
                elif time_per_frame > 5.0:
                    batch_score -= 10
            
            total_score += max(0, batch_score)
        
        return round(total_score / len(batches), 1)
    
    @staticmethod
    def get_client_performance_summary(batches: List[Batch]) -> dict:
        """Résumé des performances par client"""
        client_stats = {}
        
        for batch in batches:
            if not batch.assigned_client or batch.status != BatchStatus.COMPLETED:
                continue
            
            client_mac = batch.assigned_client
            if client_mac not in client_stats:
                client_stats[client_mac] = {
                    'batches_completed': 0,
                    'total_frames': 0,
                    'total_processing_time': 0,
                    'average_time_per_frame': 0,
                    'fastest_batch': None,
                    'slowest_batch': None,
                    'retry_count': 0
                }
            
            stats = client_stats[client_mac]
            stats['batches_completed'] += 1
            stats['total_frames'] += batch.frame_count
            stats['retry_count'] += batch.retry_count
            
            if batch.processing_time:
                stats['total_processing_time'] += batch.processing_time
                
                if not stats['fastest_batch'] or batch.processing_time < stats['fastest_batch']:
                    stats['fastest_batch'] = batch.processing_time
                
                if not stats['slowest_batch'] or batch.processing_time > stats['slowest_batch']:
                    stats['slowest_batch'] = batch.processing_time
        
        # Calcul des moyennes
        for client_mac, stats in client_stats.items():
            if stats['total_frames'] > 0 and stats['total_processing_time'] > 0:
                stats['average_time_per_frame'] = round(stats['total_processing_time'] / stats['total_frames'], 2)
        
        return client_stats