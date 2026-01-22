"""
Hiérarchie unifiée d'exceptions pour le projet d'upscaling réseau.
Toutes les exceptions personnalisées héritent de UpscalingNetworkError.
"""

from enum import Enum
from typing import Optional, Dict, Any


class ErrorAction(Enum):
    """Actions suggérées pour la gestion des erreurs"""
    RETRY = "retry"
    REASSIGN = "reassign"
    ABORT = "abort"
    CLEANUP = "cleanup"
    IGNORE = "ignore"


class UpscalingNetworkError(Exception):
    """Exception de base pour toutes les erreurs du projet"""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        is_recoverable: bool = False,
        suggested_action: ErrorAction = ErrorAction.ABORT
    ):
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__
        self.details = details or {}
        self.is_recoverable = is_recoverable
        self.suggested_action = suggested_action

    def __str__(self) -> str:
        base = f"[{self.code}] {self.message}"
        if self.details:
            details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            base += f" ({details_str})"
        return base

    def ToDict(self) -> Dict[str, Any]:
        """Convertit l'exception en dictionnaire pour sérialisation"""
        return {
            "type": self.__class__.__name__,
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "is_recoverable": self.is_recoverable,
            "suggested_action": self.suggested_action.value
        }


# =============================================================================
# Erreurs Réseau
# =============================================================================

class NetworkError(UpscalingNetworkError):
    """Erreur de base pour les problèmes réseau"""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        is_recoverable: bool = True,
        suggested_action: ErrorAction = ErrorAction.RETRY
    ):
        super().__init__(message, code, details, is_recoverable, suggested_action)


class ConnectionTimeoutError(NetworkError):
    """Timeout lors de la connexion"""

    def __init__(self, host: str, port: int, timeout: float):
        super().__init__(
            f"Timeout de connexion vers {host}:{port} après {timeout}s",
            code="NET_CONN_TIMEOUT",
            details={"host": host, "port": port, "timeout": timeout},
            is_recoverable=True,
            suggested_action=ErrorAction.RETRY
        )


class ConnectionRefusedError(NetworkError):
    """Connexion refusée par le serveur"""

    def __init__(self, host: str, port: int, reason: str = ""):
        super().__init__(
            f"Connexion refusée par {host}:{port}" + (f": {reason}" if reason else ""),
            code="NET_CONN_REFUSED",
            details={"host": host, "port": port, "reason": reason},
            is_recoverable=False,
            suggested_action=ErrorAction.ABORT
        )


class HandshakeFailedError(NetworkError):
    """Échec du handshake de connexion"""

    def __init__(self, reason: str, client_id: Optional[str] = None):
        super().__init__(
            f"Échec du handshake: {reason}",
            code="NET_HANDSHAKE_FAILED",
            details={"reason": reason, "client_id": client_id},
            is_recoverable=False,
            suggested_action=ErrorAction.ABORT
        )


class AuthenticationFailedError(NetworkError):
    """Échec de l'authentification"""

    def __init__(self, reason: str, client_id: Optional[str] = None):
        super().__init__(
            f"Échec de l'authentification: {reason}",
            code="NET_AUTH_FAILED",
            details={"reason": reason, "client_id": client_id},
            is_recoverable=False,
            suggested_action=ErrorAction.ABORT
        )


class SendError(NetworkError):
    """Erreur lors de l'envoi de données"""

    def __init__(self, reason: str, bytes_sent: int = 0, total_bytes: int = 0):
        super().__init__(
            f"Erreur d'envoi: {reason}",
            code="NET_SEND_ERROR",
            details={"reason": reason, "bytes_sent": bytes_sent, "total_bytes": total_bytes},
            is_recoverable=True,
            suggested_action=ErrorAction.RETRY
        )


class ReceiveError(NetworkError):
    """Erreur lors de la réception de données"""

    def __init__(self, reason: str, bytes_received: int = 0, expected_bytes: int = 0):
        super().__init__(
            f"Erreur de réception: {reason}",
            code="NET_RECEIVE_ERROR",
            details={"reason": reason, "bytes_received": bytes_received, "expected_bytes": expected_bytes},
            is_recoverable=True,
            suggested_action=ErrorAction.RETRY
        )


class MessageTooLargeError(NetworkError):
    """Message trop volumineux"""

    def __init__(self, size: int, max_size: int):
        super().__init__(
            f"Message trop volumineux: {size} bytes (max: {max_size})",
            code="NET_MSG_TOO_LARGE",
            details={"size": size, "max_size": max_size},
            is_recoverable=False,
            suggested_action=ErrorAction.ABORT
        )


# =============================================================================
# Erreurs de Chiffrement
# =============================================================================

class EncryptionError(UpscalingNetworkError):
    """Erreur de base pour les problèmes de chiffrement"""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        is_recoverable: bool = False,
        suggested_action: ErrorAction = ErrorAction.ABORT
    ):
        super().__init__(message, code, details, is_recoverable, suggested_action)


class KeyExchangeError(EncryptionError):
    """Erreur lors de l'échange de clés"""

    def __init__(self, reason: str):
        super().__init__(
            f"Échec de l'échange de clés: {reason}",
            code="ENC_KEY_EXCHANGE",
            details={"reason": reason},
            is_recoverable=False,
            suggested_action=ErrorAction.ABORT
        )


class DecryptionError(EncryptionError):
    """Erreur lors du déchiffrement"""

    def __init__(self, reason: str):
        super().__init__(
            f"Échec du déchiffrement: {reason}",
            code="ENC_DECRYPTION",
            details={"reason": reason},
            is_recoverable=False,
            suggested_action=ErrorAction.ABORT
        )


# =============================================================================
# Erreurs de Compression (garde compatibilité avec l'existant)
# =============================================================================

class CompressionError(UpscalingNetworkError):
    """Erreur de base pour les problèmes de compression"""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        is_recoverable: bool = False,
        suggested_action: ErrorAction = ErrorAction.ABORT
    ):
        super().__init__(message, code, details, is_recoverable, suggested_action)


class CompressionFailedError(CompressionError):
    """Erreur lors de la compression"""

    def __init__(self, reason: str, data_size: int = 0):
        super().__init__(
            f"Échec de la compression: {reason}",
            code="COMP_FAILED",
            details={"reason": reason, "data_size": data_size},
            is_recoverable=False,
            suggested_action=ErrorAction.ABORT
        )


class DecompressionFailedError(CompressionError):
    """Erreur lors de la décompression"""

    def __init__(self, reason: str, data_size: int = 0):
        super().__init__(
            f"Échec de la décompression: {reason}",
            code="DECOMP_FAILED",
            details={"reason": reason, "data_size": data_size},
            is_recoverable=False,
            suggested_action=ErrorAction.ABORT
        )


# =============================================================================
# Erreurs de Traitement
# =============================================================================

class ProcessingError(UpscalingNetworkError):
    """Erreur de base pour les problèmes de traitement"""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        is_recoverable: bool = False,
        suggested_action: ErrorAction = ErrorAction.ABORT
    ):
        super().__init__(message, code, details, is_recoverable, suggested_action)


class FFmpegError(ProcessingError):
    """Erreur FFmpeg générique"""

    def __init__(self, operation: str, stderr: str = "", return_code: int = -1):
        super().__init__(
            f"Erreur FFmpeg lors de {operation}",
            code="PROC_FFMPEG",
            details={"operation": operation, "stderr": stderr[:500], "return_code": return_code},
            is_recoverable=False,
            suggested_action=ErrorAction.CLEANUP
        )


class ExtractionError(FFmpegError):
    """Erreur lors de l'extraction (audio, sous-titres, frames)"""

    def __init__(self, extraction_type: str, source: str, stderr: str = ""):
        super().__init__(
            operation=f"extraction {extraction_type}",
            stderr=stderr
        )
        self.code = "PROC_EXTRACTION"
        self.details["extraction_type"] = extraction_type
        self.details["source"] = source


class ReassemblyError(FFmpegError):
    """Erreur lors du réassemblage vidéo"""

    def __init__(self, video_id: str, stderr: str = ""):
        super().__init__(
            operation="réassemblage vidéo",
            stderr=stderr
        )
        self.code = "PROC_REASSEMBLY"
        self.details["video_id"] = video_id


class EncodingError(FFmpegError):
    """Erreur lors de l'encodage (AV1, etc.)"""

    def __init__(self, codec: str, output_path: str, stderr: str = ""):
        super().__init__(
            operation=f"encodage {codec}",
            stderr=stderr
        )
        self.code = "PROC_ENCODING"
        self.details["codec"] = codec
        self.details["output_path"] = output_path


class UpscalingError(ProcessingError):
    """Erreur d'upscaling générique"""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        is_recoverable: bool = True,
        suggested_action: ErrorAction = ErrorAction.REASSIGN
    ):
        super().__init__(message, code, details, is_recoverable, suggested_action)


class RealESRGANError(UpscalingError):
    """Erreur Real-ESRGAN"""

    def __init__(self, reason: str, model: str = "", stderr: str = ""):
        super().__init__(
            f"Erreur Real-ESRGAN: {reason}",
            code="PROC_REALESRGAN",
            details={"reason": reason, "model": model, "stderr": stderr[:500]},
            is_recoverable=True,
            suggested_action=ErrorAction.REASSIGN
        )


class RealCUGANError(UpscalingError):
    """Erreur Real-CUGAN"""

    def __init__(self, reason: str, model: str = "", stderr: str = ""):
        super().__init__(
            f"Erreur Real-CUGAN: {reason}",
            code="PROC_REALCUGAN",
            details={"reason": reason, "model": model, "stderr": stderr[:500]},
            is_recoverable=True,
            suggested_action=ErrorAction.REASSIGN
        )


class GPUMemoryError(UpscalingError):
    """Erreur de mémoire GPU"""

    def __init__(self, required_memory: int = 0, available_memory: int = 0):
        super().__init__(
            "Mémoire GPU insuffisante",
            code="PROC_GPU_MEMORY",
            details={"required_memory": required_memory, "available_memory": available_memory},
            is_recoverable=True,
            suggested_action=ErrorAction.REASSIGN
        )


class ModelNotFoundError(UpscalingError):
    """Modèle d'upscaling introuvable"""

    def __init__(self, model_name: str, model_path: str = ""):
        super().__init__(
            f"Modèle introuvable: {model_name}",
            code="PROC_MODEL_NOT_FOUND",
            details={"model_name": model_name, "model_path": model_path},
            is_recoverable=False,
            suggested_action=ErrorAction.ABORT
        )


class BatchError(ProcessingError):
    """Erreur de traitement de batch"""

    def __init__(
        self,
        message: str,
        batch_id: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        is_recoverable: bool = True,
        suggested_action: ErrorAction = ErrorAction.REASSIGN
    ):
        details = details or {}
        details["batch_id"] = batch_id
        super().__init__(message, code, details, is_recoverable, suggested_action)


class BatchTimeoutError(BatchError):
    """Timeout lors du traitement d'un batch"""

    def __init__(self, batch_id: str, timeout: float, client_id: Optional[str] = None):
        super().__init__(
            f"Timeout du batch {batch_id} après {timeout}s",
            batch_id=batch_id,
            code="PROC_BATCH_TIMEOUT",
            details={"timeout": timeout, "client_id": client_id},
            is_recoverable=True,
            suggested_action=ErrorAction.REASSIGN
        )


class BatchProcessingFailedError(BatchError):
    """Échec du traitement d'un batch"""

    def __init__(self, batch_id: str, reason: str, client_id: Optional[str] = None):
        super().__init__(
            f"Échec du traitement du batch {batch_id}: {reason}",
            batch_id=batch_id,
            code="PROC_BATCH_FAILED",
            details={"reason": reason, "client_id": client_id},
            is_recoverable=True,
            suggested_action=ErrorAction.REASSIGN
        )


class PartialBatchError(BatchError):
    """Batch partiellement traité"""

    def __init__(self, batch_id: str, processed: int, total: int):
        super().__init__(
            f"Batch {batch_id} partiellement traité: {processed}/{total} images",
            batch_id=batch_id,
            code="PROC_BATCH_PARTIAL",
            details={"processed": processed, "total": total},
            is_recoverable=True,
            suggested_action=ErrorAction.REASSIGN
        )


# =============================================================================
# Erreurs de Base de Données
# =============================================================================

class DatabaseError(UpscalingNetworkError):
    """Erreur de base pour les problèmes de base de données"""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        is_recoverable: bool = True,
        suggested_action: ErrorAction = ErrorAction.RETRY
    ):
        super().__init__(message, code, details, is_recoverable, suggested_action)


class DatabaseConnectionError(DatabaseError):
    """Erreur de connexion à la base de données"""

    def __init__(self, db_path: str, reason: str = ""):
        super().__init__(
            f"Impossible de se connecter à la base de données: {reason}",
            code="DB_CONNECTION",
            details={"db_path": db_path, "reason": reason},
            is_recoverable=True,
            suggested_action=ErrorAction.RETRY
        )


class QueryError(DatabaseError):
    """Erreur lors d'une requête SQL"""

    def __init__(self, query: str, reason: str):
        # Tronquer la requête pour éviter les logs trop longs
        truncated_query = query[:200] + "..." if len(query) > 200 else query
        super().__init__(
            f"Erreur SQL: {reason}",
            code="DB_QUERY",
            details={"query": truncated_query, "reason": reason},
            is_recoverable=True,
            suggested_action=ErrorAction.RETRY
        )


class IntegrityError(DatabaseError):
    """Erreur d'intégrité des données"""

    def __init__(self, table: str, reason: str):
        super().__init__(
            f"Erreur d'intégrité dans {table}: {reason}",
            code="DB_INTEGRITY",
            details={"table": table, "reason": reason},
            is_recoverable=False,
            suggested_action=ErrorAction.ABORT
        )


# =============================================================================
# Erreurs de Nettoyage
# =============================================================================

class CleanupError(UpscalingNetworkError):
    """Erreur lors du nettoyage des ressources"""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        is_recoverable: bool = False,
        suggested_action: ErrorAction = ErrorAction.IGNORE
    ):
        super().__init__(message, code, details, is_recoverable, suggested_action)


class TempFileCleanupError(CleanupError):
    """Erreur lors du nettoyage des fichiers temporaires"""

    def __init__(self, path: str, reason: str):
        super().__init__(
            f"Impossible de nettoyer {path}: {reason}",
            code="CLEANUP_TEMP",
            details={"path": path, "reason": reason},
            is_recoverable=False,
            suggested_action=ErrorAction.IGNORE
        )


class PartialResultCleanupError(CleanupError):
    """Erreur lors du nettoyage des résultats partiels"""

    def __init__(self, batch_id: str, path: str, reason: str):
        super().__init__(
            f"Impossible de nettoyer les résultats partiels du batch {batch_id}: {reason}",
            code="CLEANUP_PARTIAL",
            details={"batch_id": batch_id, "path": path, "reason": reason},
            is_recoverable=False,
            suggested_action=ErrorAction.IGNORE
        )
