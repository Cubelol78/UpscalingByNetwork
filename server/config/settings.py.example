"""
Configuration du serveur d'upscaling distribué avec sauvegarde persistante
"""

import os
import shutil
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, Any

@dataclass
class ServerConfig:
    """Configuration du serveur"""
    
    # Configuration réseau
    HOST: str = "0.0.0.0"
    PORT: int = 8888
    MAX_CLIENTS: int = 50
    HEARTBEAT_INTERVAL: int = 30  # secondes
    CLIENT_TIMEOUT: int = 120     # secondes
    
    # Configuration des lots
    BATCH_SIZE: int = 50          # nombre d'images par lot
    MAX_RETRIES: int = 3          # nombre de tentatives par lot
    DUPLICATE_THRESHOLD: int = 5   # seuil pour envoyer des doublons
    
    # Configuration stockage
    WORK_DRIVE: str = ""          # Disque de travail choisi
    TEMP_DIR: str = "temp"        # Dossier temporaire
    OUTPUT_DIR: str = "output"    # Dossier de sortie
    FRAMES_DIR: str = "frames"    # Dossier frames extraites
    UPSCALED_DIR: str = "upscaled" # Dossier frames upscalées
    AUTO_CLEANUP: bool = True     # Nettoyage automatique
    MIN_FREE_SPACE_GB: int = 50   # Espace libre minimum requis (Go)
    
    # Configuration sécurité
    ENCRYPTION_KEY_SIZE: int = 32
    USE_ENCRYPTION: bool = True
    AUTH_TOKEN_LENGTH: int = 64
    
    # Configuration Real-ESRGAN
    REALESRGAN_MODEL: str = "realesr-animevideov3"
    REALESRGAN_SCALE: int = 4
    TILE_SIZE: int = 256
    GPU_ID: int = 0
    
    # Configuration FFmpeg
    FFMPEG_CRF: int = 20
    FFMPEG_PRESET: str = "medium"
    FFMPEG_THREADS: int = 12
    
    # Configuration de l'interface
    GUI_UPDATE_INTERVAL: int = 1000  # millisecondes
    LOG_MAX_LINES: int = 1000
    
    def __post_init__(self):
        """Initialisation post-construction"""
        # Chargement de la configuration sauvegardée
        self.load_config()
        
        # Détermination du disque de travail si pas défini
        if not self.WORK_DRIVE:
            self.WORK_DRIVE = self.get_best_drive()
        
        # Mise à jour des chemins avec le disque de travail
        self.update_paths()
        
        # Création des dossiers nécessaires
        self.create_directories()
    
    def get_config_file_path(self) -> Path:
        """Retourne le chemin du fichier de configuration"""
        # Dossier utilisateur pour la configuration persistante
        if os.name == 'nt':  # Windows
            config_dir = Path(os.environ.get('APPDATA', '.')) / 'DistributedUpscaling'
        else:  # Linux/Mac
            config_dir = Path.home() / '.config' / 'distributed-upscaling'
        
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / 'server_config.json'
    
    def save_config(self):
        """Sauvegarde la configuration sur disque"""
        try:
            config_file = self.get_config_file_path()
            
            # Conversion en dictionnaire pour sérialisation JSON
            config_dict = asdict(self)
            
            # Sauvegarde avec indentation pour lisibilité
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config_dict, f, indent=2, ensure_ascii=False)
            
            print(f"Configuration sauvegardée dans: {config_file}")
            return True
            
        except Exception as e:
            print(f"Erreur sauvegarde configuration: {e}")
            return False
    
    def load_config(self):
        """Charge la configuration depuis le disque"""
        try:
            config_file = self.get_config_file_path()
            
            if not config_file.exists():
                print("Aucune configuration sauvegardée trouvée, utilisation des valeurs par défaut")
                return False
            
            with open(config_file, 'r', encoding='utf-8') as f:
                config_dict = json.load(f)
            
            # Application des valeurs chargées avec validation
            for key, value in config_dict.items():
                if hasattr(self, key):
                    # Validation spéciale pour le disque de travail
                    if key == 'WORK_DRIVE':
                        if value and os.path.exists(value):
                            setattr(self, key, value)
                        else:
                            print(f"Disque de travail {value} non trouvé, utilisation du meilleur disque disponible")
                            setattr(self, key, self.get_best_drive())
                    else:
                        setattr(self, key, value)
            
            print(f"Configuration chargée depuis: {config_file}")
            print(f"Disque de travail configuré: {self.WORK_DRIVE}")
            return True
            
        except Exception as e:
            print(f"Erreur chargement configuration: {e}")
            return False
    
    def reset_to_defaults(self):
        """Remet la configuration aux valeurs par défaut"""
        defaults = ServerConfig()
        
        # Copie des valeurs par défaut
        for field_name in asdict(defaults).keys():
            if field_name != 'WORK_DRIVE':  # Garde le disque actuel
                setattr(self, field_name, getattr(defaults, field_name))
        
        # Sauvegarde immédiate
        self.save_config()
    
    def get_best_drive(self) -> str:
        """Trouve le disque avec le plus d'espace libre"""
        try:
            import psutil
            
            best_drive = ""
            max_free_space = 0
            
            # Parcourir tous les disques
            for disk in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(disk.mountpoint)
                    free_gb = usage.free / (1024**3)
                    
                    if free_gb > max_free_space:
                        max_free_space = free_gb
                        best_drive = disk.mountpoint
                        
                except (PermissionError, OSError):
                    continue
            
            return best_drive if best_drive else str(Path.cwd().drive)
            
        except ImportError:
            # Fallback si psutil n'est pas disponible
            return str(Path.cwd().drive)
    
    def set_work_drive(self, drive_path: str):
        """Change le disque de travail et sauvegarde"""
        self.WORK_DRIVE = drive_path
        self.update_paths()
        self.create_directories()
        self.save_config()  # Sauvegarde automatique
    
    def update_paths(self):
        """Met à jour les chemins avec le disque de travail"""
        if self.WORK_DRIVE:
            base_path = Path(self.WORK_DRIVE) / "UpscalingWork"
            self.TEMP_DIR = str(base_path / "temp")
            self.OUTPUT_DIR = str(base_path / "output")
            self.FRAMES_DIR = str(base_path / "frames")
            self.UPSCALED_DIR = str(base_path / "upscaled")
    
    def create_directories(self):
        """Crée les dossiers nécessaires"""
        for dir_path in [self.TEMP_DIR, self.OUTPUT_DIR, 
                        self.FRAMES_DIR, self.UPSCALED_DIR]:
            Path(dir_path).mkdir(parents=True, exist_ok=True)
    
    def get_available_drives(self) -> Dict[str, Dict[str, Any]]:
        """Retourne la liste des disques disponibles avec leurs informations"""
        drives = {}
        
        try:
            import psutil
            
            for disk in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(disk.mountpoint)
                    
                    drives[disk.mountpoint] = {
                        'device': disk.device,
                        'mountpoint': disk.mountpoint,
                        'fstype': disk.fstype,
                        'total_gb': usage.total / (1024**3),
                        'free_gb': usage.free / (1024**3),
                        'used_gb': usage.used / (1024**3),
                        'percent_used': (usage.used / usage.total) * 100
                    }
                    
                except (PermissionError, OSError):
                    continue
                    
        except ImportError:
            # Fallback basique si psutil n'est pas disponible
            current_drive = str(Path.cwd().drive)
            try:
                total, used, free = shutil.disk_usage(current_drive)
                drives[current_drive] = {
                    'device': current_drive,
                    'mountpoint': current_drive,
                    'fstype': 'unknown',
                    'total_gb': total / (1024**3),
                    'free_gb': free / (1024**3),
                    'used_gb': used / (1024**3),
                    'percent_used': (used / total) * 100
                }
            except:
                pass
        
        return drives
    
    def check_space_requirements(self, video_path: str) -> Dict[str, Any]:
        """Estime l'espace disque requis pour un fichier vidéo"""
        try:
            # Taille du fichier vidéo
            video_size = Path(video_path).stat().st_size / (1024**3)  # GB
            
            # Estimation conservative
            estimated_frames = int(video_size * 1000)
            
            # Espace requis en GB
            frames_space = (estimated_frames * 3) / 1024  # Frames originales
            upscaled_space = (estimated_frames * 30) / 1024  # Frames upscalées
            temp_space = video_size * 2  # Fichiers temporaires
            output_space = video_size * 1.5  # Vidéo de sortie
            
            total_required = frames_space + upscaled_space + temp_space + output_space
            
            # Vérification de l'espace disponible
            drives_info = self.get_available_drives()
            current_drive_info = drives_info.get(self.WORK_DRIVE, {})
            available_space = current_drive_info.get('free_gb', 0)
            
            return {
                'video_size_gb': video_size,
                'estimated_frames': estimated_frames,
                'frames_space_gb': frames_space,
                'upscaled_space_gb': upscaled_space,
                'temp_space_gb': temp_space,
                'output_space_gb': output_space,
                'total_required_gb': total_required,
                'available_space_gb': available_space,
                'sufficient_space': available_space >= (total_required + self.MIN_FREE_SPACE_GB),
                'work_drive': self.WORK_DRIVE
            }
            
        except Exception as e:
            return {
                'error': str(e),
                'sufficient_space': False
            }
    
    def cleanup_temp_files(self, job_id: str = None):
        """Nettoie les fichiers temporaires"""
        try:
            temp_path = Path(self.TEMP_DIR)
            
            if job_id:
                # Nettoyage spécifique à un job
                patterns = [f"job_{job_id}_*"]
            else:
                # Nettoyage général
                patterns = ["job_*_frames", "job_*_upscaled", "job_*_audio.*"]
            
            for pattern in patterns:
                for item in temp_path.glob(pattern):
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                        
            return True
            
        except Exception as e:
            print(f"Erreur nettoyage: {e}")
            return False
    
    def apply_and_save(self, **kwargs):
        """Applique les modifications et sauvegarde automatiquement"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        
        return self.save_config()

# Configuration globale
config = ServerConfig()

# Variables d'environnement (appliquées après chargement du fichier)
ENV_MAPPINGS = {
    'UPSCALING_HOST': 'HOST',
    'UPSCALING_PORT': 'PORT',
    'UPSCALING_MAX_CLIENTS': 'MAX_CLIENTS',
    'UPSCALING_BATCH_SIZE': 'BATCH_SIZE',
    'UPSCALING_USE_ENCRYPTION': 'USE_ENCRYPTION',
    'UPSCALING_GPU_ID': 'GPU_ID',
    'UPSCALING_WORK_DRIVE': 'WORK_DRIVE',
}

# Application des variables d'environnement (priorité sur fichier config)
for env_var, config_attr in ENV_MAPPINGS.items():
    env_value = os.getenv(env_var)
    if env_value is not None:
        # Conversion de type automatique
        current_value = getattr(config, config_attr)
        if isinstance(current_value, bool):
            setattr(config, config_attr, env_value.lower() in ('true', '1', 'yes'))
        elif isinstance(current_value, int):
            setattr(config, config_attr, int(env_value))
        else:
            setattr(config, config_attr, env_value)

# Chemins par défaut
BASE_DIR = Path(__file__).parent.parent
ASSETS_DIR = BASE_DIR / "assets"
LOGS_DIR = BASE_DIR / "logs"

# Création des dossiers
LOGS_DIR.mkdir(exist_ok=True)
ASSETS_DIR.mkdir(exist_ok=True)