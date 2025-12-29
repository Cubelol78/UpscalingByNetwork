"""
Modèles de données pour la base de données SQLite du serveur
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from shared.utils.constants import JobStatus, BatchStatus


@dataclass
class Parameter:
    """Modèle pour un paramètre du serveur"""

    Key: str
    Value: str
    Description: Optional[str] = None
    UpdatedAt: Optional[datetime] = None

    def ToDict(self):
        """Convertit en dictionnaire"""
        return {
            "key": self.Key,
            "value": self.Value,
            "description": self.Description,
            "updated_at": self.UpdatedAt.isoformat() if self.UpdatedAt else None
        }

    @classmethod
    def FromDict(cls, Data: dict) -> 'Parameter':
        """Crée depuis un dictionnaire"""
        return cls(
            Key=Data["key"],
            Value=Data["value"],
            Description=Data.get("description"),
            UpdatedAt=datetime.fromisoformat(Data["updated_at"]) if Data.get("updated_at") else None
        )


@dataclass
class Video:
    """Modèle pour une vidéo en traitement"""

    VideoId: str
    VideoPath: str
    Status: str = JobStatus.QUEUED
    UpscaleFactor: int = 4
    Model: str = "realesr-animevideov3"
    TtaMode: bool = False  # Mode TTA (meilleure qualité, plus lent)
    TotalBatches: int = 0
    CompletedBatches: int = 0
    Progress: float = 0.0
    Framerate: Optional[float] = None
    TotalFrames: Optional[int] = None
    OutputPath: Optional[str] = None
    ErrorMessage: Optional[str] = None
    CreatedAt: Optional[datetime] = None
    StartedAt: Optional[datetime] = None
    CompletedAt: Optional[datetime] = None

    def ToDict(self):
        """Convertit en dictionnaire"""
        return {
            "video_id": self.VideoId,
            "video_path": self.VideoPath,
            "status": self.Status,
            "upscale_factor": self.UpscaleFactor,
            "model": self.Model,
            "tta_mode": self.TtaMode,
            "total_batches": self.TotalBatches,
            "completed_batches": self.CompletedBatches,
            "progress": self.Progress,
            "framerate": self.Framerate,
            "total_frames": self.TotalFrames,
            "output_path": self.OutputPath,
            "error_message": self.ErrorMessage,
            "created_at": self.CreatedAt.isoformat() if self.CreatedAt else None,
            "started_at": self.StartedAt.isoformat() if self.StartedAt else None,
            "completed_at": self.CompletedAt.isoformat() if self.CompletedAt else None
        }

    @classmethod
    def FromDict(cls, Data: dict) -> 'Video':
        """Crée depuis un dictionnaire"""
        return cls(
            VideoId=Data["video_id"],
            VideoPath=Data["video_path"],
            Status=Data.get("status", JobStatus.QUEUED),
            UpscaleFactor=Data.get("upscale_factor", 4),
            Model=Data.get("model", "realesr-animevideov3"),
            TtaMode=bool(Data.get("tta_mode", False)),
            TotalBatches=Data.get("total_batches", 0),
            CompletedBatches=Data.get("completed_batches", 0),
            Progress=Data.get("progress", 0.0),
            Framerate=Data.get("framerate"),
            TotalFrames=Data.get("total_frames"),
            OutputPath=Data.get("output_path"),
            ErrorMessage=Data.get("error_message"),
            CreatedAt=datetime.fromisoformat(Data["created_at"]) if Data.get("created_at") else None,
            StartedAt=datetime.fromisoformat(Data["started_at"]) if Data.get("started_at") else None,
            CompletedAt=datetime.fromisoformat(Data["completed_at"]) if Data.get("completed_at") else None
        )

    def UpdateProgress(self):
        """Calcule et met à jour la progression"""
        if self.TotalBatches > 0:
            self.Progress = self.CompletedBatches / self.TotalBatches
        else:
            self.Progress = 0.0


@dataclass
class Batch:
    """Modèle pour un paquet d'images"""

    BatchId: str
    VideoId: str
    Status: str = BatchStatus.PENDING
    StartFrame: int = 0
    EndFrame: int = 0
    FrameCount: int = 0
    AssignedClientId: Optional[str] = None
    AssignedAt: Optional[datetime] = None
    CompletedAt: Optional[datetime] = None
    RetryCount: int = 0
    ErrorMessage: Optional[str] = None

    def ToDict(self):
        """Convertit en dictionnaire"""
        return {
            "batch_id": self.BatchId,
            "video_id": self.VideoId,
            "status": self.Status,
            "start_frame": self.StartFrame,
            "end_frame": self.EndFrame,
            "frame_count": self.FrameCount,
            "assigned_client_id": self.AssignedClientId,
            "assigned_at": self.AssignedAt.isoformat() if self.AssignedAt else None,
            "completed_at": self.CompletedAt.isoformat() if self.CompletedAt else None,
            "retry_count": self.RetryCount,
            "error_message": self.ErrorMessage
        }

    @classmethod
    def FromDict(cls, Data: dict) -> 'Batch':
        """Crée depuis un dictionnaire"""
        return cls(
            BatchId=Data["batch_id"],
            VideoId=Data["video_id"],
            Status=Data.get("status", BatchStatus.PENDING),
            StartFrame=Data.get("start_frame", 0),
            EndFrame=Data.get("end_frame", 0),
            FrameCount=Data.get("frame_count", 0),
            AssignedClientId=Data.get("assigned_client_id"),
            AssignedAt=datetime.fromisoformat(Data["assigned_at"]) if Data.get("assigned_at") else None,
            CompletedAt=datetime.fromisoformat(Data["completed_at"]) if Data.get("completed_at") else None,
            RetryCount=Data.get("retry_count", 0),
            ErrorMessage=Data.get("error_message")
        )


@dataclass
class ClientHistory:
    """Modèle pour l'historique d'un client"""

    ClientId: str
    IpAddress: str
    ConnectedAt: datetime
    DisconnectedAt: Optional[datetime] = None
    TotalBatchesProcessed: int = 0
    TotalBatchesFailed: int = 0
    AverageProcessingTime: Optional[float] = None
    LastSeen: Optional[datetime] = None

    def ToDict(self):
        """Convertit en dictionnaire"""
        return {
            "client_id": self.ClientId,
            "ip_address": self.IpAddress,
            "connected_at": self.ConnectedAt.isoformat(),
            "disconnected_at": self.DisconnectedAt.isoformat() if self.DisconnectedAt else None,
            "total_batches_processed": self.TotalBatchesProcessed,
            "total_batches_failed": self.TotalBatchesFailed,
            "average_processing_time": self.AverageProcessingTime,
            "last_seen": self.LastSeen.isoformat() if self.LastSeen else None
        }

    @classmethod
    def FromDict(cls, Data: dict) -> 'ClientHistory':
        """Crée depuis un dictionnaire"""
        return cls(
            ClientId=Data["client_id"],
            IpAddress=Data["ip_address"],
            ConnectedAt=datetime.fromisoformat(Data["connected_at"]),
            DisconnectedAt=datetime.fromisoformat(Data["disconnected_at"]) if Data.get("disconnected_at") else None,
            TotalBatchesProcessed=Data.get("total_batches_processed", 0),
            TotalBatchesFailed=Data.get("total_batches_failed", 0),
            AverageProcessingTime=Data.get("average_processing_time"),
            LastSeen=datetime.fromisoformat(Data["last_seen"]) if Data.get("last_seen") else None
        )


# ============================================================================
# SCHÉMAS SQL
# ============================================================================

SQL_CREATE_PARAMETERS_TABLE = """
CREATE TABLE IF NOT EXISTS parameters (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

SQL_CREATE_VIDEOS_TABLE = """
CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY,
    video_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    upscale_factor INTEGER NOT NULL DEFAULT 4,
    model TEXT NOT NULL DEFAULT 'realesr-animevideov3',
    tta_mode INTEGER NOT NULL DEFAULT 0,
    total_batches INTEGER DEFAULT 0,
    completed_batches INTEGER DEFAULT 0,
    progress REAL DEFAULT 0.0,
    framerate REAL,
    total_frames INTEGER,
    output_path TEXT,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
)
"""

SQL_CREATE_BATCHES_TABLE = """
CREATE TABLE IF NOT EXISTS batches (
    batch_id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    start_frame INTEGER NOT NULL,
    end_frame INTEGER NOT NULL,
    frame_count INTEGER NOT NULL,
    assigned_client_id TEXT,
    assigned_at TIMESTAMP,
    completed_at TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    FOREIGN KEY (video_id) REFERENCES videos(video_id)
)
"""

SQL_CREATE_CLIENTS_HISTORY_TABLE = """
CREATE TABLE IF NOT EXISTS clients_history (
    client_id TEXT PRIMARY KEY,
    ip_address TEXT NOT NULL,
    connected_at TIMESTAMP NOT NULL,
    disconnected_at TIMESTAMP,
    total_batches_processed INTEGER DEFAULT 0,
    total_batches_failed INTEGER DEFAULT 0,
    average_processing_time REAL,
    last_seen TIMESTAMP
)
"""

# Index pour améliorer les performances
SQL_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status)",
    "CREATE INDEX IF NOT EXISTS idx_batches_video_id ON batches(video_id)",
    "CREATE INDEX IF NOT EXISTS idx_batches_status ON batches(status)",
    "CREATE INDEX IF NOT EXISTS idx_batches_assigned_client ON batches(assigned_client_id)",
    "CREATE INDEX IF NOT EXISTS idx_clients_connected_at ON clients_history(connected_at)"
]
