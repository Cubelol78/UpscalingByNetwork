"""
Protocole de messages pour la communication serveur-client
Tous les messages sont sérialisables en JSON
"""

import json
import base64
from typing import Dict, Any, Optional, List
from datetime import datetime
from shared.utils.constants import MessageType, ErrorCode, ClientStatus, JobStatus, BatchStatus


class BaseMessage:
    """Classe de base pour tous les messages"""

    def __init__(self, MessageType: str, Payload: Optional[Dict[str, Any]] = None):
        """
        Initialise un message de base

        Args:
            MessageType: Type du message
            Payload: Données du message
        """
        self.MessageType = MessageType
        self.Payload = Payload or {}
        self.Timestamp = datetime.now().isoformat()

    def ToDict(self) -> Dict[str, Any]:
        """Convertit le message en dictionnaire"""
        return {
            "message_type": self.MessageType,
            "payload": self.Payload,
            "timestamp": self.Timestamp
        }

    def ToJson(self) -> str:
        """Convertit le message en JSON"""
        return json.dumps(self.ToDict())

    def ToBytes(self) -> bytes:
        """Convertit le message en bytes"""
        return self.ToJson().encode('utf-8')

    @classmethod
    def FromDict(cls, Data: Dict[str, Any]) -> 'BaseMessage':
        """Crée un message depuis un dictionnaire"""
        MessageTypeStr = Data.get("message_type", "")
        Payload = Data.get("payload", {})
        Timestamp = Data.get("timestamp", "")

        # Crée une instance vide sans appeler __init__ des sous-classes
        Message = object.__new__(cls)
        Message.MessageType = MessageTypeStr
        Message.Payload = Payload
        Message.Timestamp = Timestamp
        return Message

    @classmethod
    def FromJson(cls, JsonStr: str) -> 'BaseMessage':
        """Crée un message depuis une chaîne JSON"""
        Data = json.loads(JsonStr)
        return cls.FromDict(Data)

    @classmethod
    def FromBytes(cls, BytesData: bytes) -> 'BaseMessage':
        """Crée un message depuis des bytes"""
        JsonStr = BytesData.decode('utf-8')
        return cls.FromJson(JsonStr)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} type={self.MessageType} timestamp={self.Timestamp}>"


# ============================================================================
# MESSAGES HANDSHAKE ET AUTHENTIFICATION
# ============================================================================

class HandshakeRequest(BaseMessage):
    """Demande de handshake du client"""

    def __init__(self, PublicKey: bytes, ProtocolVersion: str = "1.0"):
        """
        Args:
            PublicKey: Clé publique du client (bytes)
            ProtocolVersion: Version du protocole
        """
        Payload = {
            "public_key": base64.b64encode(PublicKey).decode('utf-8'),
            "protocol_version": ProtocolVersion
        }
        super().__init__(MessageType.HANDSHAKE_REQUEST, Payload)

    def GetPublicKey(self) -> bytes:
        """Récupère la clé publique"""
        return base64.b64decode(self.Payload["public_key"])


class HandshakeResponse(BaseMessage):
    """Réponse de handshake du serveur"""

    def __init__(self, PublicKey: bytes, Success: bool = True, Message: str = ""):
        """
        Args:
            PublicKey: Clé publique du serveur (bytes)
            Success: Handshake réussi
            Message: Message optionnel
        """
        Payload = {
            "public_key": base64.b64encode(PublicKey).decode('utf-8'),
            "success": Success,
            "message": Message
        }
        super().__init__(MessageType.HANDSHAKE_RESPONSE, Payload)

    def GetPublicKey(self) -> bytes:
        """Récupère la clé publique"""
        return base64.b64decode(self.Payload["public_key"])

    def IsSuccess(self) -> bool:
        """Vérifie si le handshake a réussi"""
        return self.Payload.get("success", False)


class AuthRequest(BaseMessage):
    """Demande d'authentification du client"""

    def __init__(self, Password: str, ClientId: Optional[str] = None):
        """
        Args:
            Password: Mot de passe (sera chiffré lors de l'envoi)
            ClientId: ID du client (optionnel)
        """
        Payload = {
            "password": Password,
            "client_id": ClientId
        }
        super().__init__(MessageType.AUTH_REQUEST, Payload)

    def GetPassword(self) -> str:
        """Récupère le mot de passe"""
        return self.Payload.get("password", "")


class AuthResponse(BaseMessage):
    """Réponse d'authentification du serveur"""

    def __init__(self, Success: bool, ClientId: str = "", Message: str = ""):
        """
        Args:
            Success: Authentification réussie
            ClientId: ID assigné au client
            Message: Message d'erreur si échec
        """
        Payload = {
            "success": Success,
            "client_id": ClientId,
            "message": Message
        }
        super().__init__(MessageType.AUTH_RESPONSE, Payload)

    def IsSuccess(self) -> bool:
        """Vérifie si l'authentification a réussi"""
        return self.Payload.get("success", False)

    def GetClientId(self) -> str:
        """Récupère l'ID du client"""
        return self.Payload.get("client_id", "")


# ============================================================================
# MESSAGES HEARTBEAT
# ============================================================================

class HeartbeatPing(BaseMessage):
    """Ping de heartbeat du serveur vers le client"""

    def __init__(self, Timestamp: Optional[float] = None):
        """
        Args:
            Timestamp: Timestamp du ping
        """
        import time
        Payload = {
            "timestamp": Timestamp or time.time()
        }
        super().__init__(MessageType.HEARTBEAT_PING, Payload)


class HeartbeatPong(BaseMessage):
    """Réponse heartbeat du client vers le serveur"""

    def __init__(self, PingTimestamp: float, ClientStatus: str = ClientStatus.IDLE):
        """
        Args:
            PingTimestamp: Timestamp du ping reçu
            ClientStatus: Statut actuel du client
        """
        import time
        Payload = {
            "ping_timestamp": PingTimestamp,
            "pong_timestamp": time.time(),
            "client_status": ClientStatus
        }
        super().__init__(MessageType.HEARTBEAT_PONG, Payload)


# ============================================================================
# MESSAGES DISTRIBUTION DE PAQUETS
# ============================================================================

class BatchAssignment(BaseMessage):
    """Assignment d'un paquet d'images à un client"""

    def __init__(self, BatchId: str, VideoId: str, Images: List[Dict[str, Any]],
                 UpscaleFactor: int, Model: str):
        """
        Args:
            BatchId: ID du paquet
            VideoId: ID de la vidéo
            Images: Liste des images (format: [{id, number, data}])
            UpscaleFactor: Facteur d'upscaling (2, 3, ou 4)
            Model: Modèle Real-ESRGAN à utiliser
        """
        Payload = {
            "batch_id": BatchId,
            "video_id": VideoId,
            "images": Images,
            "upscale_factor": UpscaleFactor,
            "model": Model,
            "image_count": len(Images)
        }
        super().__init__(MessageType.BATCH_ASSIGNMENT, Payload)

    def GetBatchId(self) -> str:
        """Récupère l'ID du paquet"""
        return self.Payload.get("batch_id", "")

    def GetImages(self) -> List[Dict[str, Any]]:
        """Récupère la liste des images"""
        return self.Payload.get("images", [])


class BatchResult(BaseMessage):
    """Résultat d'un paquet traité par le client"""

    def __init__(self, BatchId: str, Success: bool,
                 UpscaledImages: Optional[List[Dict[str, Any]]] = None,
                 ErrorMessage: str = ""):
        """
        Args:
            BatchId: ID du paquet
            Success: Traitement réussi
            UpscaledImages: Images upscalées (format: [{id, number, data}])
            ErrorMessage: Message d'erreur si échec
        """
        Payload = {
            "batch_id": BatchId,
            "success": Success,
            "upscaled_images": UpscaledImages or [],
            "error_message": ErrorMessage,
            "image_count": len(UpscaledImages) if UpscaledImages else 0
        }
        super().__init__(MessageType.BATCH_RESULT, Payload)

    def IsSuccess(self) -> bool:
        """Vérifie si le traitement a réussi"""
        return self.Payload.get("success", False)

    def GetUpscaledImages(self) -> List[Dict[str, Any]]:
        """Récupère les images upscalées"""
        return self.Payload.get("upscaled_images", [])


class BatchRequest(BaseMessage):
    """Demande de paquet par un client"""

    def __init__(self, ClientId: str):
        """
        Args:
            ClientId: ID du client demandeur
        """
        Payload = {
            "client_id": ClientId
        }
        super().__init__(MessageType.BATCH_REQUEST, Payload)


# ============================================================================
# MESSAGES DE STATUT
# ============================================================================

class StatusUpdate(BaseMessage):
    """Mise à jour de statut générique"""

    def __init__(self, Status: str, Message: str = "", Data: Optional[Dict] = None):
        """
        Args:
            Status: Statut
            Message: Message descriptif
            Data: Données additionnelles
        """
        Payload = {
            "status": Status,
            "message": Message,
            "data": Data or {}
        }
        super().__init__(MessageType.STATUS_UPDATE, Payload)


class ClientStatusMessage(BaseMessage):
    """Statut d'un client"""

    def __init__(self, ClientId: str, Status: str, CurrentBatch: Optional[str] = None):
        """
        Args:
            ClientId: ID du client
            Status: Statut du client
            CurrentBatch: ID du paquet en cours de traitement
        """
        Payload = {
            "client_id": ClientId,
            "status": Status,
            "current_batch": CurrentBatch
        }
        super().__init__(MessageType.CLIENT_STATUS, Payload)


class ServerStatusMessage(BaseMessage):
    """Statut du serveur"""

    def __init__(self, Running: bool, ConnectedClients: int,
                 CurrentJob: Optional[str] = None, QueuedJobs: int = 0):
        """
        Args:
            Running: Serveur en cours d'exécution
            ConnectedClients: Nombre de clients connectés
            CurrentJob: ID du job en cours
            QueuedJobs: Nombre de jobs en attente
        """
        Payload = {
            "running": Running,
            "connected_clients": ConnectedClients,
            "current_job": CurrentJob,
            "queued_jobs": QueuedJobs
        }
        super().__init__(MessageType.SERVER_STATUS, Payload)


# ============================================================================
# MESSAGES DE JOB
# ============================================================================

class JobStartMessage(BaseMessage):
    """Démarrage d'un job de traitement vidéo"""

    def __init__(self, JobId: str, VideoPath: str, TotalBatches: int):
        """
        Args:
            JobId: ID du job
            VideoPath: Chemin de la vidéo
            TotalBatches: Nombre total de paquets
        """
        Payload = {
            "job_id": JobId,
            "video_path": VideoPath,
            "total_batches": TotalBatches
        }
        super().__init__(MessageType.JOB_START, Payload)


class JobProgressMessage(BaseMessage):
    """Progression d'un job"""

    def __init__(self, JobId: str, CompletedBatches: int, TotalBatches: int,
                 Progress: float, Status: str):
        """
        Args:
            JobId: ID du job
            CompletedBatches: Paquets complétés
            TotalBatches: Total de paquets
            Progress: Progression (0.0 à 1.0)
            Status: Statut du job
        """
        Payload = {
            "job_id": JobId,
            "completed_batches": CompletedBatches,
            "total_batches": TotalBatches,
            "progress": Progress,
            "status": Status
        }
        super().__init__(MessageType.JOB_PROGRESS, Payload)


class JobCompleteMessage(BaseMessage):
    """Job terminé avec succès"""

    def __init__(self, JobId: str, OutputPath: str, Duration: float):
        """
        Args:
            JobId: ID du job
            OutputPath: Chemin de la vidéo finale
            Duration: Durée du traitement en secondes
        """
        Payload = {
            "job_id": JobId,
            "output_path": OutputPath,
            "duration": Duration
        }
        super().__init__(MessageType.JOB_COMPLETE, Payload)


class JobFailedMessage(BaseMessage):
    """Job échoué"""

    def __init__(self, JobId: str, ErrorMessage: str, ErrorCode: int):
        """
        Args:
            JobId: ID du job
            ErrorMessage: Message d'erreur
            ErrorCode: Code d'erreur
        """
        Payload = {
            "job_id": JobId,
            "error_message": ErrorMessage,
            "error_code": ErrorCode
        }
        super().__init__(MessageType.JOB_FAILED, Payload)


# ============================================================================
# MESSAGES D'ERREUR
# ============================================================================

class ErrorMessage(BaseMessage):
    """Message d'erreur générique"""

    def __init__(self, ErrorCode: int, ErrorMessage: str,
                 Context: Optional[str] = None):
        """
        Args:
            ErrorCode: Code d'erreur
            ErrorMessage: Message d'erreur
            Context: Contexte de l'erreur
        """
        Payload = {
            "error_code": ErrorCode,
            "error_message": ErrorMessage,
            "context": Context or ""
        }
        super().__init__(MessageType.ERROR_MESSAGE, Payload)

    def GetErrorCode(self) -> int:
        """Récupère le code d'erreur"""
        return self.Payload.get("error_code", ErrorCode.UNKNOWN_ERROR)

    def GetErrorMessage(self) -> str:
        """Récupère le message d'erreur"""
        return self.Payload.get("error_message", "")


# ============================================================================
# MESSAGE DE DÉCONNEXION
# ============================================================================

class DisconnectMessage(BaseMessage):
    """Message de déconnexion"""

    def __init__(self, Reason: str = ""):
        """
        Args:
            Reason: Raison de la déconnexion
        """
        Payload = {
            "reason": Reason
        }
        super().__init__(MessageType.DISCONNECT, Payload)


# ============================================================================
# FACTORY DE MESSAGES
# ============================================================================

class MessageFactory:
    """Factory pour créer les messages appropriés selon leur type"""

    MESSAGE_CLASSES = {
        MessageType.HANDSHAKE_REQUEST: HandshakeRequest,
        MessageType.HANDSHAKE_RESPONSE: HandshakeResponse,
        MessageType.AUTH_REQUEST: AuthRequest,
        MessageType.AUTH_RESPONSE: AuthResponse,
        MessageType.HEARTBEAT_PING: HeartbeatPing,
        MessageType.HEARTBEAT_PONG: HeartbeatPong,
        MessageType.BATCH_ASSIGNMENT: BatchAssignment,
        MessageType.BATCH_RESULT: BatchResult,
        MessageType.BATCH_REQUEST: BatchRequest,
        MessageType.STATUS_UPDATE: StatusUpdate,
        MessageType.CLIENT_STATUS: ClientStatusMessage,
        MessageType.SERVER_STATUS: ServerStatusMessage,
        MessageType.JOB_START: JobStartMessage,
        MessageType.JOB_PROGRESS: JobProgressMessage,
        MessageType.JOB_COMPLETE: JobCompleteMessage,
        MessageType.JOB_FAILED: JobFailedMessage,
        MessageType.ERROR_MESSAGE: ErrorMessage,
        MessageType.DISCONNECT: DisconnectMessage,
    }

    @classmethod
    def CreateFromDict(cls, Data: Dict[str, Any]) -> BaseMessage:
        """
        Crée un message depuis un dictionnaire en déterminant automatiquement le type

        Args:
            Data: Dictionnaire contenant le message

        Returns:
            Instance du message approprié
        """
        MessageTypeStr = Data.get("message_type", "")

        MessageClass = cls.MESSAGE_CLASSES.get(MessageTypeStr, BaseMessage)
        return MessageClass.FromDict(Data)

    @classmethod
    def CreateFromJson(cls, JsonStr: str) -> BaseMessage:
        """Crée un message depuis une chaîne JSON"""
        Data = json.loads(JsonStr)
        return cls.CreateFromDict(Data)

    @classmethod
    def CreateFromBytes(cls, BytesData: bytes) -> BaseMessage:
        """Crée un message depuis des bytes"""
        JsonStr = BytesData.decode('utf-8')
        return cls.CreateFromJson(JsonStr)
