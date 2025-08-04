# UpscalingByNetwork/config/settings.py
"""
Configuration centralisée pour UpscalingByNetwork
Paramètres par défaut et configuration du système
"""

import os
import platform
from pathlib import Path
from typing import Dict, Any, List

# Informations de version
VERSION = "1.0.0"
PROJECT_NAME = "UpscalingByNetwork"
PROJECT_DESCRIPTION = "Système distribué d'upscaling vidéo avec Real-ESRGAN"

# Chemins du projet
PROJECT_ROOT = Path(__file__).parent.parent
SERVER_ROOT = PROJECT_ROOT / "server"
CLIENT_ROOT = PROJECT_ROOT / "client"
SHARED_ROOT = PROJECT_ROOT / "shared"

# Configuration réseau par défaut
DEFAULT_SERVER_HOST = "0.0.0.0"
DEFAULT_SERVER_PORT = 8888
DEFAULT_CLIENT_HOST = "localhost"
DEFAULT_CLIENT_PORT = 8888

# Configuration de traitement
DEFAULT_BATCH_SIZE = 50
DEFAULT_SCALE_FACTOR = 4
DEFAULT_MODEL = "realesr-animevideov3"
DEFAULT_TILE_SIZE = 0  # Auto-détection

# Modèles supportés
SUPPORTED_MODELS = {
    'realesr-animevideov3': {
        'name': 'Real-ESRGAN Anime Video v3',
        'scales': [2, 3, 4],
        'description': 'Optimisé pour anime, animation et dessins animés',
        'tile_size_recommend': 128
    },
    'realesrgan-x4plus': {
        'name': 'Real-ESRGAN x4 Plus',
        'scales': [4],
        'description': 'Modèle général pour photos et images réelles',
        'tile_size_recommend': 200
    },
    'realesrgan-x4plus-anime': {
        'name': 'Real-ESRGAN x4 Plus Anime',
        'scales': [4],
        'description': 'Spécialisé pour anime et illustrations',
        'tile_size_recommend': 128
    },
    'RealESRNet_x4plus': {
        'name': 'RealESRNet x4 Plus',
        'scales': [4],
        'description': 'Version conservative pour upscaling subtil',
        'tile_size_recommend': 400
    }
}

# Formats de fichiers supportés
SUPPORTED_VIDEO_FORMATS = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v']
SUPPORTED_IMAGE_FORMATS = ['.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.webp']

# Configuration de chiffrement
ENCRYPTION_ENABLED = True
RSA_KEY_SIZE = 2048
AES_KEY_SIZE = 32  # AES-256
SESSION_TIMEOUT = 3600  # 1 heure

# Configuration de logging
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Limites système
MAX_CLIENTS = 50
MAX_CONCURRENT_JOBS = 5
MAX_BATCH_RETRY_ATTEMPTS = 3
CLIENT_TIMEOUT = 300  # 5 minutes
HEARTBEAT_INTERVAL = 30  # secondes

# Configuration de performance
GUI_UPDATE_INTERVAL = 1000  # ms
STATS_UPDATE_INTERVAL = 5000  # ms
MONITORING_HISTORY_SIZE = 60  # échantillons

# Seuils d'alerte système
ALERT_THRESHOLDS = {
    'cpu_percent': 90.0,
    'memory_percent': 85.0,
    'disk_percent': 90.0,
    'gpu_percent': 95.0,
    'temperature': 80.0
}

# Configuration des dossiers de travail
WORK_DIRS = {
    'server': {
        'work': 'server_work',
        'jobs': 'server_work/jobs',
        'temp': 'server_work/temp',
        'encryption_keys': 'server_work/temp/encryption_keys',
        'logs': 'logs',
        'output': 'output'
    },
    'client': {
        'work': 'client_work',
        'temp': 'client_work/temp',
        'received_batches': 'client_work/temp/received_batches',
        'processed_batches': 'client_work/temp/processed_batches',
        'logs': 'client_work/logs'
    }
}

# Chemins des exécutables par plateforme
EXECUTABLE_PATHS = {
    'Windows': {
        'ffmpeg': 'ffmpeg/ffmpeg.exe',
        'ffprobe': 'ffmpeg/ffprobe.exe',
        'realesrgan': 'realesrgan-ncnn-vulkan/realesrgan-ncnn-vulkan.exe'
    },
    'Linux': {
        'ffmpeg': 'ffmpeg/ffmpeg',
        'ffprobe': 'ffmpeg/ffprobe',
        'realesrgan': 'realesrgan-ncnn-vulkan/realesrgan-ncnn-vulkan'
    },
    'Darwin': {  # macOS
        'ffmpeg': 'ffmpeg/ffmpeg',
        'ffprobe': 'ffmpeg/ffprobe',
        'realesrgan': 'realesrgan-ncnn-vulkan/realesrgan-ncnn-vulkan'
    }
}

class Config:
    """Classe de configuration principale"""
    
    def __init__(self):
        self.platform = platform.system()
        self.is_windows = self.platform == 'Windows'
        self.is_linux = self.platform == 'Linux'
        self.is_macos = self.platform == 'Darwin'
        
        # Chemins spécifiques à la plateforme
        self.executable_paths = EXECUTABLE_PATHS.get(self.platform, EXECUTABLE_PATHS['Linux'])
        
        # Configuration par défaut
        self.server_host = DEFAULT_SERVER_HOST
        self.server_port = DEFAULT_SERVER_PORT
        self.batch_size = DEFAULT_BATCH_SIZE
        self.scale_factor = DEFAULT_SCALE_FACTOR
        self.model = DEFAULT_MODEL
        self.tile_size = DEFAULT_TILE_SIZE
        
        # Chargement depuis variables d'environnement
        self.load_from_environment()
    
    def load_from_environment(self):
        """Charge la configuration depuis les variables d'environnement"""
        self.server_host = os.getenv('UPSCALING_SERVER_HOST', self.server_host)
        self.server_port = int(os.getenv('UPSCALING_SERVER_PORT', self.server_port))
        self.batch_size = int(os.getenv('UPSCALING_BATCH_SIZE', self.batch_size))
        self.scale_factor = int(os.getenv('UPSCALING_SCALE_FACTOR', self.scale_factor))
        self.model = os.getenv('UPSCALING_MODEL', self.model)
        self.tile_size = int(os.getenv('UPSCALING_TILE_SIZE', self.tile_size))
        
        # Log level
        log_level = os.getenv('UPSCALING_LOG_LEVEL', LOG_LEVEL)
        if log_level in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            global LOG_LEVEL
            LOG_LEVEL = log_level
    
    def get_executable_path(self, tool: str, base_dir: Path = None) -> Path:
        """Récupère le chemin d'un exécutable"""
        if tool not in self.executable_paths:
            raise ValueError(f"Outil non supporté: {tool}")
        
        relative_path = self.executable_paths[tool]
        
        if base_dir:
            return base_dir / relative_path
        else:
            return Path(relative_path)
    
    def get_work_dirs(self, component: str) -> Dict[str, Path]:
        """Récupère les chemins de travail pour un composant"""
        if component not in WORK_DIRS:
            raise ValueError(f"Composant non supporté: {component}")
        
        dirs = {}
        for name, path in WORK_DIRS[component].items():
            dirs[name] = Path(path)
        
        return dirs
    
    def create_work_directories(self, component: str, base_dir: Path = None):
        """Crée les dossiers de travail pour un composant"""
        work_dirs = self.get_work_dirs(component)
        
        for name, path in work_dirs.items():
            if base_dir:
                full_path = base_dir / path
            else:
                full_path = path
            
            full_path.mkdir(parents=True, exist_ok=True)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit la configuration en dictionnaire"""
        return {
            'version': VERSION,
            'platform': self.platform,
            'server_host': self.server_host,
            'server_port': self.server_port,
            'batch_size': self.batch_size,
            'scale_factor': self.scale_factor,
            'model': self.model,
            'tile_size': self.tile_size,
            'supported_models': list(SUPPORTED_MODELS.keys()),
            'supported_video_formats': SUPPORTED_VIDEO_FORMATS,
            'supported_image_formats': SUPPORTED_IMAGE_FORMATS,
            'encryption_enabled': ENCRYPTION_ENABLED,
            'max_clients': MAX_CLIENTS
        }

# Instance globale de configuration
config = Config()

# Configuration spécifique pour le développement
class DevelopmentConfig(Config):
    """Configuration pour le développement"""
    
    def __init__(self):
        super().__init__()
        self.server_host = "localhost"
        self.batch_size = 10  # Plus petit pour les tests
        global LOG_LEVEL
        LOG_LEVEL = "DEBUG"

# Configuration pour la production
class ProductionConfig(Config):
    """Configuration pour la production"""
    
    def __init__(self):
        super().__init__()
        self.server_host = "0.0.0.0"
        global LOG_LEVEL
        LOG_LEVEL = "INFO"

# Configuration pour Docker
class DockerConfig(Config):
    """Configuration pour Docker"""
    
    def __init__(self):
        super().__init__()
        self.server_host = "0.0.0.0"
        # Pas de GUI en Docker
        self.gui_enabled = False

def get_config(environment: str = None) -> Config:
    """Factory pour récupérer la configuration selon l'environnement"""
    env = environment or os.getenv('UPSCALING_ENV', 'production')
    
    if env == 'development':
        return DevelopmentConfig()
    elif env == 'docker':
        return DockerConfig()
    else:
        return ProductionConfig()

# Utilitaires de configuration
def validate_model(model: str) -> bool:
    """Valide qu'un modèle est supporté"""
    return model in SUPPORTED_MODELS

def validate_scale_for_model(model: str, scale: int) -> bool:
    """Valide qu'une échelle est supportée pour un modèle"""
    if not validate_model(model):
        return False
    return scale in SUPPORTED_MODELS[model]['scales']

def get_recommended_tile_size(model: str) -> int:
    """Récupère la taille de tuile recommandée pour un modèle"""
    if not validate_model(model):
        return DEFAULT_TILE_SIZE
    return SUPPORTED_MODELS[model]['tile_size_recommend']

def is_video_file(file_path: Path) -> bool:
    """Vérifie si un fichier est une vidéo supportée"""
    return file_path.suffix.lower() in SUPPORTED_VIDEO_FORMATS

def is_image_file(file_path: Path) -> bool:
    """Vérifie si un fichier est une image supportée"""
    return file_path.suffix.lower() in SUPPORTED_IMAGE_FORMATS