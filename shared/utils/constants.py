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

    # Authentification canal Data
    DATA_CHANNEL_AUTH = "data_channel_auth"
    DATA_CHANNEL_AUTH_RESPONSE = "data_channel_auth_response"


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
    DEFAULT_DATA_PORT = 8766  # Port dédié aux transferts de données (batches)
    DEFAULT_HOST = "0.0.0.0"
    MAX_MESSAGE_SIZE = 10 * 1024 * 1024 * 1024  # 10 GB - Les batches d'images upscalées peuvent être très lourds
    HEARTBEAT_INTERVAL = 10  # secondes
    HEARTBEAT_TIMEOUT = 30  # secondes
    CONNECTION_TIMEOUT = 15  # secondes - Réduit de 60s pour feedback rapide
    HANDSHAKE_TIMEOUT = 10  # secondes - Timeout spécifique pour handshake
    AUTH_TIMEOUT = 10  # secondes - Timeout spécifique pour authentification
    BATCH_TIMEOUT = 120  # 2 minutes - Timeout avec vérification heartbeat sur Control

    # Reconnexion automatique
    RECONNECT_ENABLED = True  # Active la reconnexion automatique
    RECONNECT_BASE_DELAY = 2  # Délai de base en secondes (backoff: 2s, 4s, 8s, 16s, 32s max)
    RECONNECT_MAX_DELAY = 32  # Délai maximum entre deux tentatives (32 secondes)
    RECONNECT_INFINITE = -1  # Valeur spéciale pour tentatives infinies


# ============================================================================
# CONFIGURATION COMPRESSION
# ============================================================================

class CompressionConfig:
    """Configuration de la compression réseau"""

    # Algorithmes supportés
    ALGO_NONE = "none"
    ALGO_ZSTD = "zstd"
    ALGO_ZLIB = "zlib"

    # Algorithme par défaut et fallback
    DEFAULT_ALGORITHM = ALGO_ZSTD
    FALLBACK_ALGORITHM = ALGO_ZLIB

    # Échelle commune de compression (1-10)
    LEVEL_MIN = 1
    LEVEL_MAX = 10
    LEVEL_DEFAULT = 5

    # Plages natives des algorithmes
    ZSTD_LEVEL_MIN = 1
    ZSTD_LEVEL_MAX = 22

    ZLIB_LEVEL_MIN = 1
    ZLIB_LEVEL_MAX = 9

    # Niveaux de compression par défaut (valeurs natives)
    ZSTD_LEVEL = 3   # zstd: 1-22, 3 = bon équilibre vitesse/compression
    ZLIB_LEVEL = 6   # zlib: 1-9, 6 = défaut Python


# ============================================================================
# CONFIGURATION TRAITEMENT
# ============================================================================

class ProcessingConfig:
    """Configuration du traitement vidéo"""

    DEFAULT_BATCH_SIZE = 100  # images par paquet
    DEFAULT_UPSCALE_FACTOR = 4
    SUPPORTED_UPSCALE_FACTORS = [2, 3, 4]

    # Engines d'upscaling disponibles
    ENGINE_REALESRGAN = "realesrgan"
    ENGINE_REALCUGAN = "realcugan"
    DEFAULT_ENGINE = ENGINE_REALESRGAN
    SUPPORTED_ENGINES = [ENGINE_REALESRGAN, ENGINE_REALCUGAN]

    # Modèles Real-ESRGAN
    DEFAULT_MODEL = "realesr-animevideov3"
    REALESRGAN_MODELS = [
        "realesr-animevideov3",
        "realesrgan-x4plus-anime",
        "realesrgan-x4plus"
    ]
    # Modèles qui nécessitent un suffixe -x{scale}
    REALESRGAN_MODELS_WITH_SCALE_SUFFIX = ["realesr-animevideov3"]

    # Modèles Real-CUGAN (variantes de dossiers)
    REALCUGAN_MODELS = [
        "models-se",
        "models-pro",
        "models-nose"
    ]
    DEFAULT_REALCUGAN_MODEL = "models-se"
    DEFAULT_REALCUGAN_DENOISE = -1  # -1 = auto, 0 = off, 1/2/3 = niveaux

    # Compatibilité legacy
    SUPPORTED_MODELS = REALESRGAN_MODELS

    # ============================================================================
    # CAPACITÉS DES MODÈLES - Facteurs d'upscaling supportés par modèle
    # ============================================================================

    # Facteurs d'upscaling supportés par modèle Real-ESRGAN
    REALESRGAN_MODEL_SCALES = {
        "realesr-animevideov3": [2, 3, 4],
        "realesrgan-x4plus-anime": [4],
        "realesrgan-x4plus": [4]
    }

    # Facteurs d'upscaling supportés par modèle Real-CUGAN
    REALCUGAN_MODEL_SCALES = {
        "models-se": [2, 3, 4],
        "models-pro": [2, 3],
        "models-nose": [2]
    }

    # Niveaux de denoise supportés par modèle Real-CUGAN
    # -1 = conservative (nécessite up{scale}x-conservative.bin)
    # 0 = no-denoise (nécessite up{scale}x-no-denoise.bin)
    # 1/2/3 = denoise level (nécessite up{scale}x-denoise{N}x.bin)
    REALCUGAN_MODEL_DENOISE_LEVELS = {
        "models-se": [-1, 0, 1, 2, 3],
        "models-pro": [-1, 0, 3],
        "models-nose": [0]  # Seulement no-denoise disponible (pas de conservative.bin)
    }

    @classmethod
    def GetSupportedScales(cls, Engine: str, Model: str) -> list:
        """
        Retourne les facteurs d'upscaling supportés pour un modèle donné

        Args:
            Engine: Engine d'upscaling (realesrgan ou realcugan)
            Model: Nom du modèle

        Returns:
            Liste des facteurs supportés [2, 3, 4] ou sous-ensemble
        """
        if Engine == cls.ENGINE_REALCUGAN:
            return cls.REALCUGAN_MODEL_SCALES.get(Model, [2, 3, 4])
        return cls.REALESRGAN_MODEL_SCALES.get(Model, [4])

    @classmethod
    def ValidateModelScale(cls, Engine: str, Model: str, ScaleFactor: int) -> bool:
        """
        Valide qu'un modèle supporte le facteur d'upscaling donné

        Args:
            Engine: Engine d'upscaling
            Model: Nom du modèle
            ScaleFactor: Facteur d'upscaling souhaité

        Returns:
            True si la combinaison est valide
        """
        return ScaleFactor in cls.GetSupportedScales(Engine, Model)

    @classmethod
    def GetSupportedDenoiseLevels(cls, Model: str) -> list:
        """
        Retourne les niveaux de denoise supportés pour un modèle Real-CUGAN

        Args:
            Model: Nom du modèle Real-CUGAN

        Returns:
            Liste des niveaux de denoise supportés [-1, 0, 1, 2, 3] ou sous-ensemble
        """
        return cls.REALCUGAN_MODEL_DENOISE_LEVELS.get(Model, [-1, 0, 1, 2, 3])

    @classmethod
    def ValidateModelDenoise(cls, Model: str, DenoiseLevel: int) -> bool:
        """
        Valide qu'un modèle Real-CUGAN supporte le niveau de denoise donné

        Args:
            Model: Nom du modèle Real-CUGAN
            DenoiseLevel: Niveau de denoise souhaité

        Returns:
            True si la combinaison est valide
        """
        return DenoiseLevel in cls.GetSupportedDenoiseLevels(Model)

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
    MAX_TILE_SIZE = 8192
    MIN_THREADS = 1
    MAX_THREADS = 999  # Pas de limite pratique

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

    # Note: La configuration est maintenant stockée dans la base de données SQLite
    # au lieu d'un fichier JSON. La DB est située dans ~/.upscaling_server/server.db

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
# CONFIGURATION MISE À JOUR
# ============================================================================

class UpdateConfig:
    """Configuration du système de mise à jour via GitHub"""

    # Repository GitHub
    GITHUB_OWNER = "Cubelol78"
    GITHUB_REPO = "UpscalingByNetwork"
    GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"

    # Canaux de mise à jour
    CHANNEL_DEV = "dev"
    CHANNEL_RELEASE = "release"
    DEFAULT_CHANNEL = CHANNEL_RELEASE

    # Timeouts (en secondes)
    API_TIMEOUT = 30
    DOWNLOAD_TIMEOUT = 300  # 5 minutes

    # Fichiers/dossiers à préserver lors de la mise à jour
    PRESERVE_PATHS = [
        "venv/",
        ".upscaling_server/",
        ".upscaling_client/",
        "work/",
        "logs/",
        ".git/",
        ".gitignore",
    ]


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
    MAX_CONCURRENT_BATCH_SENDS = 3  # Limite par défaut des envois simultanés
    MAX_RETRY_ATTEMPTS = 5  # Nombre de tentatives de retry pour les opérations réseau
    RETRY_DELAY = 5  # Délai en secondes entre chaque tentative de retry


# ============================================================================
# CONFIGURATION RETRY
# ============================================================================

class RetryConfig:
    """Configuration des mécanismes de retry"""

    # Retry réseau (envoi/réception messages)
    NETWORK_MAX_RETRIES = 5
    NETWORK_RETRY_DELAY = 5.0  # secondes

    # Retry envoi batch
    BATCH_SEND_MAX_RETRIES = 5
    BATCH_SEND_RETRY_DELAY = 5.0  # secondes

    # Retry base de données (erreurs transitoires SQLite)
    DATABASE_MAX_RETRIES = 3
    DATABASE_RETRY_DELAY = 1.0  # secondes

    # Retry connexion
    CONNECTION_MAX_RETRIES = 5
    CONNECTION_RETRY_DELAY = 5.0  # secondes
