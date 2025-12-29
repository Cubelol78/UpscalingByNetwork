"""
Constantes partagées entre le serveur et les clients
"""

# ============================================================================
# TYPES DE MESSAGES
# ============================================================================

class MessageType:
    """Types de messages échangés entre serveur et clients"""

    # Handshake et authentification
    HANDSHAKE_REQUEST = "handshake_request"
    HANDSHAKE_RESPONSE = "handshake_response"
    AUTH_REQUEST = "auth_request"
    AUTH_RESPONSE = "auth_response"

    # Heartbeat
    HEARTBEAT_PING = "heartbeat_ping"
    HEARTBEAT_PONG = "heartbeat_pong"

    # Distribution de paquets
    BATCH_ASSIGNMENT = "batch_assignment"
    BATCH_RESULT = "batch_result"
    BATCH_REQUEST = "batch_request"

    # Mises à jour de statut
    STATUS_UPDATE = "status_update"
    CLIENT_STATUS = "client_status"
    SERVER_STATUS = "server_status"

    # Gestion des jobs
    JOB_START = "job_start"
    JOB_PROGRESS = "job_progress"
    JOB_COMPLETE = "job_complete"
    JOB_FAILED = "job_failed"

    # Erreurs
    ERROR_MESSAGE = "error_message"

    # Déconnexion
    DISCONNECT = "disconnect"


# ============================================================================
# CODES D'ERREUR
# ============================================================================

class ErrorCode:
    """Codes d'erreur standardisés"""

    # Erreurs d'authentification
    AUTH_FAILED = 1001
    AUTH_INVALID_PASSWORD = 1002
    AUTH_TIMEOUT = 1003

    # Erreurs de handshake
    HANDSHAKE_FAILED = 2001
    HANDSHAKE_INVALID_KEY = 2002
    HANDSHAKE_TIMEOUT = 2003

    # Erreurs de traitement
    PROCESSING_FAILED = 3001
    PROCESSING_TIMEOUT = 3002
    PROCESSING_INVALID_DATA = 3003

    # Erreurs réseau
    NETWORK_ERROR = 4001
    NETWORK_TIMEOUT = 4002
    NETWORK_DISCONNECTED = 4003

    # Erreurs de fichier
    FILE_NOT_FOUND = 5001
    FILE_READ_ERROR = 5002
    FILE_WRITE_ERROR = 5003

    # Erreurs générales
    UNKNOWN_ERROR = 9999


# ============================================================================
# STATUTS CLIENT
# ============================================================================

class ClientStatus:
    """Statuts possibles d'un client"""

    CONNECTING = "connecting"
    IDLE = "idle"
    PROCESSING = "processing"
    SENDING = "sending"
    RECEIVING = "receiving"
    DISCONNECTED = "disconnected"
    ERROR = "error"


# ============================================================================
# STATUTS JOB
# ============================================================================

class JobStatus:
    """Statuts possibles d'un job de traitement vidéo"""

    QUEUED = "queued"
    EXTRACTING = "extracting"
    DISTRIBUTING = "distributing"
    PROCESSING = "processing"
    REASSEMBLING = "reassembling"
    ENCODING = "encoding"
    COMPLETED = "completed"
    FAILED = "failed"


# ============================================================================
# STATUTS BATCH
# ============================================================================

class BatchStatus:
    """Statuts possibles d'un paquet d'images"""

    PENDING = "pending"
    ASSIGNED = "assigned"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


# ============================================================================
# CONFIGURATION RÉSEAU
# ============================================================================

class NetworkConfig:
    """Configuration réseau par défaut"""

    DEFAULT_PORT = 8765
    DEFAULT_HOST = "0.0.0.0"
    MAX_MESSAGE_SIZE = 5 * 1024 * 1024 * 1024  # 5 GB - Les batches d'images upscalées peuvent être très lourds
    HEARTBEAT_INTERVAL = 10  # secondes
    HEARTBEAT_TIMEOUT = 30  # secondes
    CONNECTION_TIMEOUT = 60  # secondes
    BATCH_TIMEOUT = 300  # 5 minutes


# ============================================================================
# CONFIGURATION TRAITEMENT
# ============================================================================

class ProcessingConfig:
    """Configuration du traitement vidéo"""

    DEFAULT_BATCH_SIZE = 100  # images par paquet
    DEFAULT_UPSCALE_FACTOR = 4
    SUPPORTED_UPSCALE_FACTORS = [2, 3, 4]
    DEFAULT_MODEL = "realesr-animevideov3"
    SUPPORTED_MODELS = [
        "realesr-animevideov3",
        "realesrgan-x4plus-anime",
        "realesrgan-x4plus"
    ]

    # Extensions supportées
    SUPPORTED_VIDEO_EXTENSIONS = [
        ".mp4", ".avi", ".mkv", ".mov", ".flv", ".wmv", ".webm"
    ]
    SUPPORTED_IMAGE_EXTENSIONS = [
        ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"
    ]


# ============================================================================
# CONFIGURATION PERFORMANCE
# ============================================================================

class PerformanceConfig:
    """Configuration des performances Real-ESRGAN"""

    # Tile size selon la VRAM (en MB)
    TILE_SIZE_2GB = 128
    TILE_SIZE_4GB = 256
    TILE_SIZE_6GB = 384
    TILE_SIZE_8GB = 512
    TILE_SIZE_12GB = 768
    TILE_SIZE_16GB = 1024

    # Valeurs limites
    MIN_TILE_SIZE = 32
    MAX_TILE_SIZE = 2048
    MIN_THREADS = 1
    MAX_THREADS = 16

    # Threads par défaut
    DEFAULT_LOAD_THREADS = 1
    DEFAULT_PROCESS_THREADS = 2
    DEFAULT_SAVE_THREADS = 2

    # Mapping VRAM -> Tile size
    TILE_SIZE_MAP = {
        2048: 128,
        4096: 256,
        6144: 384,
        8192: 512,
        12288: 768,
        16384: 1024,
        24576: 1024
    }


# ============================================================================
# CHEMINS RELATIFS
# ============================================================================

class PathConfig:
    """Configuration des chemins relatifs"""

    # Dossiers de travail
    WORK_DIR = "work"
    INPUT_DIR = "input"
    FRAMES_DIR = "frames"
    AUDIO_DIR = "audio"
    SUBTITLES_DIR = "subtitles"
    UPSCALED_DIR = "upscaled"
    OUTPUT_DIR = "output"
    TEMP_DIR = "temp"

    # Base de données
    DATABASE_NAME = "upscaling_server.db"

    # Configuration
    CONFIG_DIR = "config"
    DEFAULT_CONFIG = "default_config.json"
    USER_CONFIG = "user_config.json"

    # Logs
    LOG_DIR = "logs"
    SERVER_LOG = "server.log"
    CLIENT_LOG = "client.log"


# ============================================================================
# VERSIONS ET MÉTADONNÉES
# ============================================================================

class AppMetadata:
    """Métadonnées de l'application"""

    VERSION = "1.0.0"
    PROTOCOL_VERSION = "1.0"
    APP_NAME = "UpscalingByNetwork"
    APP_DESCRIPTION = "Système d'upscaling vidéo distribué avec Real-ESRGAN"


# ============================================================================
# LIMITES ET CONTRAINTES
# ============================================================================

class Limits:
    """Limites et contraintes système"""

    MAX_CLIENTS = 100
    MAX_BATCH_SIZE = 1000
    MIN_BATCH_SIZE = 10
    MAX_VIDEO_SIZE = 100 * 1024 * 1024 * 1024  # 100 GB
    MAX_CONCURRENT_JOBS = 10
    MAX_RETRY_ATTEMPTS = 3
    RETRY_DELAY = 5  # secondes
