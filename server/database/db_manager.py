"""
Gestionnaire de base de données SQLite pour le serveur
Configuration stockée dans la table parameters au lieu d'un fichier JSON
"""

import sqlite3
import os
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

from server.database.models import (
    Parameter, Video, Batch, ClientHistory,
    SQL_CREATE_PARAMETERS_TABLE, SQL_CREATE_VIDEOS_TABLE,
    SQL_CREATE_BATCHES_TABLE, SQL_CREATE_CLIENTS_HISTORY_TABLE,
    SQL_CREATE_INDEXES
)
from shared.utils.logger import GetModuleLogger
from shared.utils.constants import JobStatus, BatchStatus


# Paramètres par défaut du serveur
DEFAULT_PARAMETERS = {
    "server_ip": ("0.0.0.0", "Adresse IP d'écoute du serveur"),
    "server_port": ("8765", "Port de contrôle du serveur (handshake, heartbeat)"),
    "server_data_port": ("8766", "Port de données du serveur (transferts de batches)"),
    "server_password": ("", "Mot de passe du serveur (vide = désactivé)"),
    "work_directory": ("./work", "Répertoire de travail pour les fichiers"),
    "batch_size": ("100", "Nombre d'images par batch"),
    "compression_level": ("5", "Niveau de compression réseau (1=rapide, 10=max)"),
    "max_concurrent_batches": ("3", "Nombre maximum d'envois simultanés de batches"),
}


class DatabaseManager:
    """Gestionnaire de base de données SQLite"""

    @staticmethod
    def GetDefaultDbPath() -> str:
        """
        Retourne le chemin par défaut de la base de données.
        Stockée dans ~/.upscaling_server/server.db pour éviter le problème
        chicken-and-egg avec work_directory.

        Returns:
            Chemin absolu vers la base de données
        """
        HomeDir = Path.home()
        DbDir = HomeDir / ".upscaling_server"
        return str(DbDir / "server.db")

    def __init__(self, DbPath: str = None):
        """
        Initialise le gestionnaire de base de données

        Args:
            DbPath: Chemin vers le fichier de base de données (optionnel, utilise le chemin par défaut si non spécifié)
        """
        self.DbPath = DbPath if DbPath else self.GetDefaultDbPath()
        self.Connection = None
        self.Logger = GetModuleLogger("DatabaseManager")

        # Crée le répertoire si nécessaire
        DbDir = os.path.dirname(self.DbPath)
        if DbDir:
            os.makedirs(DbDir, exist_ok=True)

    def Connect(self) -> bool:
        """
        Connecte à la base de données et initialise les tables

        Returns:
            True si succès
        """
        try:
            self.Connection = sqlite3.connect(
                self.DbPath,
                check_same_thread=False  # Pour utilisation multi-thread
            )
            self.Connection.row_factory = sqlite3.Row  # Permet l'accès par nom de colonne

            self.Logger.info(f"Connexion à la base de données: {self.DbPath}")

            # Crée les tables
            self._CreateTables()

            return True

        except Exception as e:
            self.Logger.error(f"Erreur de connexion à la base de données: {e}")
            return False

    def _CreateTables(self):
        """Crée les tables si elles n'existent pas"""
        try:
            Cursor = self.Connection.cursor()

            # Crée les tables
            Cursor.execute(SQL_CREATE_PARAMETERS_TABLE)
            Cursor.execute(SQL_CREATE_VIDEOS_TABLE)
            Cursor.execute(SQL_CREATE_BATCHES_TABLE)
            Cursor.execute(SQL_CREATE_CLIENTS_HISTORY_TABLE)

            # Crée les index
            for IndexSql in SQL_CREATE_INDEXES:
                Cursor.execute(IndexSql)

            self.Connection.commit()
            self.Logger.info("Tables créées avec succès")

        except Exception as e:
            self.Logger.error(f"Erreur lors de la création des tables: {e}")
            raise

    def Close(self):
        """Ferme la connexion à la base de données"""
        if self.Connection:
            self.Connection.close()
            self.Logger.info("Connexion à la base de données fermée")

    # ========================================================================
    # PARAMÈTRES
    # ========================================================================

    def SetParameter(self, Key: str, Value: str, Description: Optional[str] = None) -> bool:
        """
        Définit un paramètre

        Args:
            Key: Clé du paramètre
            Value: Valeur
            Description: Description optionnelle

        Returns:
            True si succès
        """
        try:
            Cursor = self.Connection.cursor()
            Cursor.execute(
                """
                INSERT OR REPLACE INTO parameters (key, value, description, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (Key, Value, Description, datetime.now())
            )
            self.Connection.commit()
            return True

        except Exception as e:
            self.Logger.error(f"Erreur lors de la définition du paramètre {Key}: {e}")
            return False

    def GetParameter(self, Key: str, Default: Optional[str] = None) -> Optional[str]:
        """
        Récupère un paramètre

        Args:
            Key: Clé du paramètre
            Default: Valeur par défaut si non trouvée

        Returns:
            Valeur du paramètre ou Default
        """
        try:
            Cursor = self.Connection.cursor()
            Result = Cursor.execute(
                "SELECT value FROM parameters WHERE key = ?",
                (Key,)
            ).fetchone()

            return Result["value"] if Result else Default

        except Exception as e:
            self.Logger.error(f"Erreur lors de la récupération du paramètre {Key}: {e}")
            return Default

    def GetAllParameters(self) -> List[Parameter]:
        """
        Récupère tous les paramètres

        Returns:
            Liste des paramètres
        """
        try:
            Cursor = self.Connection.cursor()
            Rows = Cursor.execute("SELECT * FROM parameters").fetchall()

            Parameters = []
            for Row in Rows:
                Parameters.append(Parameter(
                    Key=Row["key"],
                    Value=Row["value"],
                    Description=Row["description"],
                    UpdatedAt=datetime.fromisoformat(Row["updated_at"]) if Row["updated_at"] else None
                ))

            return Parameters

        except Exception as e:
            self.Logger.error(f"Erreur lors de la récupération des paramètres: {e}")
            return []

    def GetParameterInt(self, Key: str, Default: int = 0) -> int:
        """
        Récupère un paramètre comme entier

        Args:
            Key: Clé du paramètre
            Default: Valeur par défaut si non trouvé ou invalide

        Returns:
            Valeur entière du paramètre
        """
        try:
            Value = self.GetParameter(Key)
            if Value is None:
                return Default
            return int(Value)
        except (ValueError, TypeError):
            return Default

    def GetParameterBool(self, Key: str, Default: bool = False) -> bool:
        """
        Récupère un paramètre comme booléen

        Args:
            Key: Clé du paramètre
            Default: Valeur par défaut si non trouvé

        Returns:
            Valeur booléenne du paramètre
        """
        Value = self.GetParameter(Key)
        if Value is None:
            return Default
        return Value.lower() in ('true', '1', 'yes', 'oui')

    def InitializeDefaultParameters(self):
        """
        Initialise les paramètres par défaut s'ils n'existent pas.
        Appelée après Connect() pour s'assurer que tous les paramètres
        nécessaires sont présents dans la base de données.
        """
        try:
            for Key, (DefaultValue, Description) in DEFAULT_PARAMETERS.items():
                # Ne remplace pas les valeurs existantes
                if self.GetParameter(Key) is None:
                    self.SetParameter(Key, DefaultValue, Description)
                    self.Logger.info(f"Paramètre initialisé: {Key} = {DefaultValue}")

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'initialisation des paramètres: {e}")

    def GetServerConfig(self) -> Dict[str, Any]:
        """
        Récupère la configuration complète du serveur depuis la base de données.

        Returns:
            Dictionnaire avec les paramètres serveur
        """
        return {
            'ip': self.GetParameter('server_ip', '0.0.0.0'),
            'port': self.GetParameterInt('server_port', 8765),
            'data_port': self.GetParameterInt('server_data_port', 8766),
            'password': self.GetParameter('server_password', ''),
            'work_directory': self.GetParameter('work_directory', './work'),
            'batch_size': self.GetParameterInt('batch_size', 100),
            'compression_level': self.GetParameterInt('compression_level', 5),
            'max_concurrent_batches': self.GetParameterInt('max_concurrent_batches', 3)
        }

    def SaveServerConfig(self, Config: Dict[str, Any]) -> bool:
        """
        Sauvegarde la configuration serveur dans la base de données.

        Args:
            Config: Dictionnaire avec ip, port, data_port, password, work_directory, batch_size, compression_level

        Returns:
            True si succès
        """
        try:
            if 'ip' in Config:
                self.SetParameter('server_ip', Config['ip'], "Adresse IP d'écoute du serveur")
            if 'port' in Config:
                self.SetParameter('server_port', str(Config['port']), "Port de contrôle du serveur")
            if 'data_port' in Config:
                self.SetParameter('server_data_port', str(Config['data_port']), "Port de données du serveur")
            if 'password' in Config:
                self.SetParameter('server_password', Config['password'], "Mot de passe du serveur")
            if 'work_directory' in Config:
                self.SetParameter('work_directory', Config['work_directory'], "Répertoire de travail")
            if 'batch_size' in Config:
                self.SetParameter('batch_size', str(Config['batch_size']), "Nombre d'images par batch")
            if 'compression_level' in Config:
                self.SetParameter('compression_level', str(Config['compression_level']), "Niveau de compression réseau (1=rapide, 10=max)")
            if 'max_concurrent_batches' in Config:
                self.SetParameter('max_concurrent_batches', str(Config['max_concurrent_batches']), "Nombre maximum d'envois simultanés de batches")
            return True
        except Exception as e:
            self.Logger.error(f"Erreur lors de la sauvegarde de la configuration: {e}")
            return False

    # ========================================================================
    # VIDÉOS
    # ========================================================================

    def AddVideo(self, Video: Video) -> bool:
        """
        Ajoute une vidéo à la file d'attente

        Args:
            Video: Objet Video

        Returns:
            True si succès
        """
        try:
            Cursor = self.Connection.cursor()
            Cursor.execute(
                """
                INSERT INTO videos (
                    video_id, video_path, status, upscale_factor, model, tta_mode,
                    total_batches, completed_batches, progress, framerate,
                    total_frames, output_path, error_message, created_at,
                    started_at, completed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    Video.VideoId, Video.VideoPath, Video.Status, Video.UpscaleFactor,
                    Video.Model, 1 if Video.TtaMode else 0, Video.TotalBatches,
                    Video.CompletedBatches, Video.Progress, Video.Framerate,
                    Video.TotalFrames, Video.OutputPath, Video.ErrorMessage,
                    Video.CreatedAt, Video.StartedAt, Video.CompletedAt
                )
            )
            self.Connection.commit()
            self.Logger.info(f"Vidéo ajoutée: {Video.VideoId}")
            return True

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'ajout de la vidéo: {e}")
            return False

    def GetVideo(self, VideoId: str) -> Optional[Video]:
        """
        Récupère une vidéo par son ID

        Args:
            VideoId: ID de la vidéo

        Returns:
            Objet Video ou None
        """
        try:
            Cursor = self.Connection.cursor()
            Row = Cursor.execute(
                "SELECT * FROM videos WHERE video_id = ?",
                (VideoId,)
            ).fetchone()

            if not Row:
                return None

            return Video.FromDict(dict(Row))

        except Exception as e:
            self.Logger.error(f"Erreur lors de la récupération de la vidéo {VideoId}: {e}")
            return None

    def UpdateVideo(self, Video: Video) -> bool:
        """
        Met à jour une vidéo

        Args:
            Video: Objet Video

        Returns:
            True si succès
        """
        try:
            Cursor = self.Connection.cursor()
            Cursor.execute(
                """
                UPDATE videos SET
                    status = ?, total_batches = ?, completed_batches = ?,
                    progress = ?, framerate = ?, total_frames = ?,
                    output_path = ?, error_message = ?, started_at = ?,
                    completed_at = ?
                WHERE video_id = ?
                """,
                (
                    Video.Status, Video.TotalBatches, Video.CompletedBatches,
                    Video.Progress, Video.Framerate, Video.TotalFrames,
                    Video.OutputPath, Video.ErrorMessage, Video.StartedAt,
                    Video.CompletedAt, Video.VideoId
                )
            )
            self.Connection.commit()
            return True

        except Exception as e:
            self.Logger.error(f"Erreur lors de la mise à jour de la vidéo: {e}")
            return False

    def DeleteVideo(self, VideoId: str) -> bool:
        """
        Supprime une vidéo et tous ses batches associés de la base de données

        Args:
            VideoId: ID de la vidéo à supprimer

        Returns:
            True si succès
        """
        try:
            Cursor = self.Connection.cursor()

            # Supprime d'abord tous les batches associés (contrainte de clé étrangère)
            Cursor.execute("DELETE FROM batches WHERE video_id = ?", (VideoId,))

            # Puis supprime la vidéo
            Cursor.execute("DELETE FROM videos WHERE video_id = ?", (VideoId,))

            self.Connection.commit()
            self.Logger.info(f"Vidéo supprimée de la BDD: {VideoId}")
            return True

        except Exception as e:
            self.Logger.error(f"Erreur lors de la suppression de la vidéo {VideoId}: {e}")
            return False

    def GetQueuedVideos(self) -> List[Video]:
        """
        Récupère toutes les vidéos en attente

        Returns:
            Liste des vidéos en attente
        """
        try:
            Cursor = self.Connection.cursor()
            Rows = Cursor.execute(
                "SELECT * FROM videos WHERE status = ? ORDER BY created_at ASC",
                (JobStatus.QUEUED,)
            ).fetchall()

            return [Video.FromDict(dict(Row)) for Row in Rows]

        except Exception as e:
            self.Logger.error(f"Erreur lors de la récupération des vidéos en attente: {e}")
            return []

    def GetCurrentVideo(self) -> Optional[Video]:
        """
        Récupère la vidéo actuellement en traitement

        Returns:
            Vidéo en cours ou None
        """
        try:
            Cursor = self.Connection.cursor()
            Row = Cursor.execute(
                """
                SELECT * FROM videos
                WHERE status NOT IN (?, ?, ?)
                ORDER BY started_at ASC
                LIMIT 1
                """,
                (JobStatus.QUEUED, JobStatus.COMPLETED, JobStatus.FAILED)
            ).fetchone()

            if not Row:
                return None

            return Video.FromDict(dict(Row))

        except Exception as e:
            self.Logger.error(f"Erreur lors de la récupération de la vidéo courante: {e}")
            return None

    def GetAllVideos(self, Limit: int = None) -> List[Video]:
        """
        Récupère toutes les vidéos

        Args:
            Limit: Nombre maximum de vidéos à retourner (None = toutes)

        Returns:
            Liste des vidéos
        """
        try:
            Cursor = self.Connection.cursor()
            if Limit:
                Rows = Cursor.execute(
                    "SELECT * FROM videos ORDER BY created_at DESC LIMIT ?",
                    (Limit,)
                ).fetchall()
            else:
                Rows = Cursor.execute(
                    "SELECT * FROM videos ORDER BY created_at DESC"
                ).fetchall()

            return [Video.FromDict(dict(Row)) for Row in Rows]

        except Exception as e:
            self.Logger.error(f"Erreur lors de la récupération des vidéos: {e}")
            return []

    # ========================================================================
    # BATCHES
    # ========================================================================

    def AddBatch(self, Batch: Batch) -> bool:
        """
        Ajoute un paquet d'images

        Args:
            Batch: Objet Batch

        Returns:
            True si succès
        """
        try:
            Cursor = self.Connection.cursor()
            Cursor.execute(
                """
                INSERT INTO batches (
                    batch_id, video_id, status, start_frame, end_frame,
                    frame_count, assigned_client_id, assigned_at,
                    completed_at, retry_count, error_message
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    Batch.BatchId, Batch.VideoId, Batch.Status,
                    Batch.StartFrame, Batch.EndFrame, Batch.FrameCount,
                    Batch.AssignedClientId, Batch.AssignedAt,
                    Batch.CompletedAt, Batch.RetryCount, Batch.ErrorMessage
                )
            )
            self.Connection.commit()
            return True

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'ajout du batch: {e}")
            return False

    def GetBatch(self, BatchId: str) -> Optional[Batch]:
        """
        Récupère un batch par son ID

        Args:
            BatchId: ID du batch

        Returns:
            Objet Batch ou None
        """
        try:
            Cursor = self.Connection.cursor()
            Row = Cursor.execute(
                "SELECT * FROM batches WHERE batch_id = ?",
                (BatchId,)
            ).fetchone()

            if not Row:
                return None

            return Batch.FromDict(dict(Row))

        except Exception as e:
            self.Logger.error(f"Erreur lors de la récupération du batch {BatchId}: {e}")
            return None

    def UpdateBatch(self, Batch: Batch) -> bool:
        """
        Met à jour un batch

        Args:
            Batch: Objet Batch

        Returns:
            True si succès
        """
        try:
            Cursor = self.Connection.cursor()
            Cursor.execute(
                """
                UPDATE batches SET
                    status = ?, assigned_client_id = ?, assigned_at = ?,
                    completed_at = ?, retry_count = ?, error_message = ?
                WHERE batch_id = ?
                """,
                (
                    Batch.Status, Batch.AssignedClientId, Batch.AssignedAt,
                    Batch.CompletedAt, Batch.RetryCount, Batch.ErrorMessage,
                    Batch.BatchId
                )
            )
            self.Connection.commit()
            return True

        except Exception as e:
            self.Logger.error(f"Erreur lors de la mise à jour du batch: {e}")
            return False

    def GetPendingBatches(self, VideoId: str) -> List[Batch]:
        """
        Récupère les batches en attente pour une vidéo

        Args:
            VideoId: ID de la vidéo

        Returns:
            Liste des batches en attente
        """
        try:
            Cursor = self.Connection.cursor()
            Rows = Cursor.execute(
                """
                SELECT * FROM batches
                WHERE video_id = ? AND status = ?
                ORDER BY start_frame ASC
                """,
                (VideoId, BatchStatus.PENDING)
            ).fetchall()

            return [Batch.FromDict(dict(Row)) for Row in Rows]

        except Exception as e:
            self.Logger.error(f"Erreur lors de la récupération des batches en attente: {e}")
            return []

    def DeleteBatch(self, BatchId: str) -> bool:
        """
        Supprime un batch de la base de données

        Args:
            BatchId: ID du batch à supprimer

        Returns:
            True si succès
        """
        try:
            Cursor = self.Connection.cursor()
            Cursor.execute(
                "DELETE FROM batches WHERE batch_id = ?",
                (BatchId,)
            )
            self.Connection.commit()
            self.Logger.info(f"Batch supprimé: {BatchId}")
            return True

        except Exception as e:
            self.Logger.error(f"Erreur lors de la suppression du batch {BatchId}: {e}")
            return False

    def GetBatchesByVideo(self, VideoId: str) -> List[Batch]:
        """
        Récupère tous les batches d'une vidéo

        Args:
            VideoId: ID de la vidéo

        Returns:
            Liste des batches
        """
        try:
            Cursor = self.Connection.cursor()
            Rows = Cursor.execute(
                "SELECT * FROM batches WHERE video_id = ? ORDER BY start_frame ASC",
                (VideoId,)
            ).fetchall()

            return [Batch.FromDict(dict(Row)) for Row in Rows]

        except Exception as e:
            self.Logger.error(f"Erreur lors de la récupération des batches: {e}")
            return []

    # ========================================================================
    # HISTORIQUE CLIENTS
    # ========================================================================

    def AddClientHistory(self, ClientHistory: ClientHistory) -> bool:
        """
        Ajoute un historique de client

        Args:
            ClientHistory: Objet ClientHistory

        Returns:
            True si succès
        """
        try:
            Cursor = self.Connection.cursor()
            Cursor.execute(
                """
                INSERT INTO clients_history (
                    client_id, ip_address, connected_at, disconnected_at,
                    total_batches_processed, total_batches_failed,
                    average_processing_time, last_seen
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ClientHistory.ClientId, ClientHistory.IpAddress,
                    ClientHistory.ConnectedAt, ClientHistory.DisconnectedAt,
                    ClientHistory.TotalBatchesProcessed, ClientHistory.TotalBatchesFailed,
                    ClientHistory.AverageProcessingTime, ClientHistory.LastSeen
                )
            )
            self.Connection.commit()
            return True

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'ajout de l'historique client: {e}")
            return False

    def UpdateClientHistory(self, ClientHistory: ClientHistory) -> bool:
        """
        Met à jour un historique de client

        Args:
            ClientHistory: Objet ClientHistory

        Returns:
            True si succès
        """
        try:
            Cursor = self.Connection.cursor()
            Cursor.execute(
                """
                UPDATE clients_history SET
                    disconnected_at = ?, total_batches_processed = ?,
                    total_batches_failed = ?, average_processing_time = ?,
                    last_seen = ?
                WHERE client_id = ?
                """,
                (
                    ClientHistory.DisconnectedAt, ClientHistory.TotalBatchesProcessed,
                    ClientHistory.TotalBatchesFailed, ClientHistory.AverageProcessingTime,
                    ClientHistory.LastSeen, ClientHistory.ClientId
                )
            )
            self.Connection.commit()
            return True

        except Exception as e:
            self.Logger.error(f"Erreur lors de la mise à jour de l'historique client: {e}")
            return False

    def GetClientHistory(self, ClientId: str) -> Optional[ClientHistory]:
        """
        Récupère l'historique d'un client

        Args:
            ClientId: ID du client

        Returns:
            Objet ClientHistory ou None
        """
        try:
            Cursor = self.Connection.cursor()
            Row = Cursor.execute(
                "SELECT * FROM clients_history WHERE client_id = ?",
                (ClientId,)
            ).fetchone()

            if not Row:
                return None

            return ClientHistory.FromDict(dict(Row))

        except Exception as e:
            self.Logger.error(f"Erreur lors de la récupération de l'historique client: {e}")
            return None

    # ========================================================================
    # STATISTIQUES
    # ========================================================================

    def GetStatistics(self) -> Dict[str, Any]:
        """
        Récupère les statistiques générales

        Returns:
            Dictionnaire de statistiques
        """
        try:
            Cursor = self.Connection.cursor()

            # Nombre total de vidéos
            TotalVideos = Cursor.execute("SELECT COUNT(*) as count FROM videos").fetchone()["count"]

            # Vidéos par statut
            VideosByStatus = {}
            Rows = Cursor.execute(
                "SELECT status, COUNT(*) as count FROM videos GROUP BY status"
            ).fetchall()
            for Row in Rows:
                VideosByStatus[Row["status"]] = Row["count"]

            # Nombre total de batches
            TotalBatches = Cursor.execute("SELECT COUNT(*) as count FROM batches").fetchone()["count"]

            # Batches par statut
            BatchesByStatus = {}
            Rows = Cursor.execute(
                "SELECT status, COUNT(*) as count FROM batches GROUP BY status"
            ).fetchall()
            for Row in Rows:
                BatchesByStatus[Row["status"]] = Row["count"]

            # Nombre de clients dans l'historique
            TotalClients = Cursor.execute("SELECT COUNT(*) as count FROM clients_history").fetchone()["count"]

            return {
                "total_videos": TotalVideos,
                "videos_by_status": VideosByStatus,
                "total_batches": TotalBatches,
                "batches_by_status": BatchesByStatus,
                "total_clients": TotalClients
            }

        except Exception as e:
            self.Logger.error(f"Erreur lors de la récupération des statistiques: {e}")
            return {}
