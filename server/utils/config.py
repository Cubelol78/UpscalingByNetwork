# server/utils/config.py
"""
Configuration centralisée pour le serveur d'upscaling distribué
Version corrigée avec compatibilité ancienne/nouvelle API
"""

import os
import json
from pathlib import Path
import time
from typing import Dict, Any, Optional, List
import logging

class ServerConfig:
    """Configuration centralisée du serveur avec compatibilité rétroactive"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Chemin vers le fichier de configuration
        self.config_file = Path(__file__).parent.parent / "config" / "server_config.json"
        self.config_file.parent.mkdir(exist_ok=True)
        
        # Initialisation des chemins détectés (sera mis à jour après)
        self.detected_paths = {
            'realesrgan': "./realesrgan-ncnn-vulkan/realesrgan-ncnn-vulkan.exe",
            'ffmpeg': "./ffmpeg/ffmpeg.exe"
        }
        
        # Configuration par défaut (AVANT la détection des exécutables)
        self._setup_default_config()
        
        # Chargement de la configuration
        self.config = self.load_config()
        
        # COMPATIBILITÉ RÉTROACTIVE : Création des attributs directs
        self._setup_legacy_attributes()
        
        # Détection des exécutables (APRÈS l'initialisation)
        self._setup_executable_paths()
    
    def _setup_default_config(self):
        """Configure la configuration par défaut"""
        self.default_config = {
            "server": {
                "host": "0.0.0.0",
                "port": 8765,
                "max_clients": 10,
                "heartbeat_interval": 30,
                "client_timeout": 120,
                "enable_ssl": False,
                "ssl_cert_path": "",
                "ssl_key_path": ""
            },
            "processing": {
                "batch_size": 50,
                "max_concurrent_batches": 5,
                "upscale_factor": 4,
                "realesrgan_model": "RealESRGAN_x4plus",
                "output_format": "png",
                "compression_level": 0,
                "enable_gpu": True,
                "gpu_memory_limit": 8192,
                "tile_size": 256,
                "max_retries": 3,
                "duplicate_threshold": 5,
                "ffmpeg_path": "./ffmpeg/ffmpeg.exe"
            },
            "storage": {
                "work_directory": "./work",
                "work_drive": "",
                "input_directory": "./input",
                "output_directory": "./output",
                "temp_directory": "./temp",
                "batches_directory": "./batches",
                "frames_directory": "./frames",
                "upscaled_directory": "./upscaled",
                "logs_directory": "./logs",
                "auto_cleanup": True,
                "auto_cleanup_age_hours": 24,
                "min_free_space_gb": 5
            },
            "security": {
                "enable_encryption": True,
                "key_exchange_timeout": 30,
                "session_key_size": 256,
                "auth_token_length": 64,
                "allowed_clients": []
            },
            "realesrgan": {
                "executable_path": "./realesrgan-ncnn-vulkan/realesrgan-ncnn-vulkan.exe",
                "models_directory": "./models",
                "default_model": "RealESRGAN_x4plus",
                "default_scale": 4,
                "tile_size": 256,
                "gpu_id": 0,
                "thread_load": "1:2:2",
                "use_fp16": False,
                "tta_mode": False
            },
            "ffmpeg": {
                "crf": 20,
                "preset": "medium",
                "threads": 12,
                "audio_bitrate": "192k",
                "video_codec": "libx264",
                "pixel_format": "yuv420p"
            },
            "monitoring": {
                "enable_performance_monitoring": True,
                "log_level": "INFO",
                "max_log_files": 10,
                "metrics_retention_days": 30,
                "enable_gpu_monitoring": True
            },
            "gui": {
                "theme": "dark",
                "auto_refresh_interval": 1000,
                "show_detailed_logs": True,
                "enable_notifications": True,
                "charts_history_points": 100,
                "log_max_lines": 1000
            }
        }

    def _setup_executable_paths(self):
        """Configure les chemins des exécutables avec détection automatique"""
        try:
            from .executable_detector import executable_detector
            
            # Détection automatique des exécutables
            realesrgan_path = executable_detector.find_realesrgan()
            ffmpeg_path = executable_detector.find_ffmpeg()
            
            # Mise à jour des chemins détectés
            if realesrgan_path:
                self.detected_paths['realesrgan'] = realesrgan_path
                # Mise à jour de la config en cours si elle existe
                if hasattr(self, 'config'):
                    self.set("realesrgan.executable_path", realesrgan_path)
            
            if ffmpeg_path:
                self.detected_paths['ffmpeg'] = ffmpeg_path
                # Mise à jour de la config en cours si elle existe
                if hasattr(self, 'config'):
                    self.set("processing.ffmpeg_path", ffmpeg_path)
            
            self.logger.info(f"Chemins détectés - Real-ESRGAN: {realesrgan_path}, FFmpeg: {ffmpeg_path}")
            
        except ImportError:
            # Fallback si le détecteur n'est pas disponible
            self.logger.warning("Détecteur d'exécutables non disponible, utilisation chemins par défaut")
        except Exception as e:
            self.logger.warning(f"Erreur détection exécutables: {e}")
    
    def get_executable_path(self, executable_name: str) -> str:
        """Retourne le chemin d'un exécutable avec détection automatique"""
        if executable_name == 'realesrgan':
            return self.detected_paths.get('realesrgan', self.get("realesrgan.executable_path", "./realesrgan-ncnn-vulkan/realesrgan-ncnn-vulkan.exe"))
        elif executable_name == 'ffmpeg':
            return self.detected_paths.get('ffmpeg', self.get("processing.ffmpeg_path", "./ffmpeg/ffmpeg.exe"))
        else:
            return self.get(f"executables.{executable_name}", "")
    
    def update_executable_paths(self):
        """Met à jour les chemins des exécutables avec une nouvelle détection"""
        self._setup_executable_paths()
        self.logger.info("Chemins d'exécutables mis à jour")
    
    def validate_executables(self) -> Dict[str, Any]:
        """Valide la disponibilité des exécutables"""
        try:
            from .executable_detector import executable_detector
            return executable_detector.get_all_executables_status()
        except ImportError:
            return {
                'summary': {'all_ready': False},
                'error': 'Détecteur d\'exécutables non disponible'
            }
    
    def _setup_legacy_attributes(self):
        """Configure les attributs pour la compatibilité avec l'ancien code"""
        # Serveur
        self.HOST = self.get("server.host", "0.0.0.0")
        self.PORT = self.get("server.port", 8765)
        self.MAX_CLIENTS = self.get("server.max_clients", 10)
        self.HEARTBEAT_INTERVAL = self.get("server.heartbeat_interval", 30)
        self.CLIENT_TIMEOUT = self.get("server.client_timeout", 120)

        # Processing
        self.BATCH_SIZE = self.get("processing.batch_size", 50)
        self.MAX_CONCURRENT_BATCHES = self.get("processing.max_concurrent_batches", 5)
        self.REALESRGAN_MODEL = self.get("processing.realesrgan_model", "RealESRGAN_x4plus")
        self.REALESRGAN_SCALE = self.get("realesrgan.default_scale", 4)
        self.TILE_SIZE = self.get("processing.tile_size", 256)
        self.MAX_RETRIES = self.get("processing.max_retries", 3)
        self.OUTPUT_FORMAT = self.get("processing.output_format", "png")
        self.DUPLICATE_THRESHOLD = self.get("processing.duplicate_threshold", 5)

        # Storage
        self.WORK_DIRECTORY = self.get("storage.work_directory", "./work")
        self.WORK_DRIVE = self.get("storage.work_drive", "")
        self.INPUT_DIRECTORY = self.get("storage.input_directory", "./input")
        self.OUTPUT_DIRECTORY = self.get("storage.output_directory", "./output")
        self.OUTPUT_DIR = self.OUTPUT_DIRECTORY  # Alias
        self.TEMP_DIRECTORY = self.get("storage.temp_directory", "./temp")
        self.TEMP_DIR = self.TEMP_DIRECTORY  # Alias
        self.BATCHES_DIRECTORY = self.get("storage.batches_directory", "./batches")
        self.FRAMES_DIR = self.get("storage.frames_directory", "./frames")
        self.UPSCALED_DIR = self.get("storage.upscaled_directory", "./upscaled")
        self.AUTO_CLEANUP = self.get("storage.auto_cleanup", True)
        self.AUTO_CLEANUP_AGE_HOURS = self.get("storage.auto_cleanup_age_hours", 24)
        self.MIN_FREE_SPACE_GB = self.get("storage.min_free_space_gb", 5)

        # Security
        self.USE_ENCRYPTION = self.get("security.enable_encryption", True)
        self.ENCRYPTION_KEY_SIZE = self.get("security.session_key_size", 256) // 8
        self.AUTH_TOKEN_LENGTH = self.get("security.auth_token_length", 64)

        # Real-ESRGAN
        self.REALESRGAN_PATH = self.get("realesrgan.executable_path", "./realesrgan-ncnn-vulkan/realesrgan-ncnn-vulkan.exe")
        self.GPU_ID = self.get("realesrgan.gpu_id", 0)
        self.USE_FP16 = self.get("realesrgan.use_fp16", False)
        self.TTA_MODE = self.get("realesrgan.tta_mode", False)

        # FFmpeg
        self.FFMPEG_CRF = self.get("ffmpeg.crf", 20)
        self.FFMPEG_PRESET = self.get("ffmpeg.preset", "medium")
        self.FFMPEG_THREADS = self.get("ffmpeg.threads", 12)
        self.AUDIO_BITRATE = self.get("ffmpeg.audio_bitrate", "192k")
        self.VIDEO_CODEC = self.get("ffmpeg.video_codec", "libx264")
        self.PIXEL_FORMAT = self.get("ffmpeg.pixel_format", "yuv420p")

        # GUI
        self.GUI_UPDATE_INTERVAL = self.get("gui.auto_refresh_interval", 1000)
        self.LOG_MAX_LINES = self.get("gui.log_max_lines", 1000)

        self.logger.info("Configuration legacy initialisée avec compatibilité rétroactive")
    
    def load_config(self) -> Dict[str, Any]:
        """Charge la configuration depuis le fichier"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                
                # Fusion avec la configuration par défaut
                merged_config = self._merge_configs(self.default_config, loaded_config)
                self.logger.info(f"Configuration chargée depuis {self.config_file}")
                return merged_config
                
            except Exception as e:
                self.logger.error(f"Erreur lors du chargement de la configuration: {e}")
                self.logger.info("Utilisation de la configuration par défaut")
                
        # Sauvegarde de la configuration par défaut si le fichier n'existe pas
        self.save_config(self.default_config)
        return self.default_config.copy()
    
    def _merge_configs(self, default: Dict, loaded: Dict) -> Dict:
        """Fusionne récursivement les configurations"""
        result = default.copy()
        
        for key, value in loaded.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def save_config(self, config_data: Optional[Dict] = None):
        """Sauvegarde la configuration"""
        try:
            data_to_save = config_data or self.config
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=4, ensure_ascii=False)
            
            self.logger.info(f"Configuration sauvegardée dans {self.config_file}")
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la sauvegarde de la configuration: {e}")
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Récupère une valeur de configuration avec notation pointée
        Exemple: get("server.host") ou get("processing.batch_size")
        """
        if not hasattr(self, 'config') or not self.config:
            return default
            
        keys = key_path.split('.')
        current = self.config
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        
        return current
    
    def set(self, key_path: str, value: Any):
        """
        Définit une valeur de configuration avec notation pointée
        Exemple: set("server.host", "0.0.0.0")
        """
        if not hasattr(self, 'config'):
            return
            
        keys = key_path.split('.')
        current = self.config
        
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        current[keys[-1]] = value
        
        # Mise à jour des attributs legacy si nécessaire
        self._update_legacy_attribute(key_path, value)
        
        # Sauvegarde automatique
        self.save_config()
    
    def _update_legacy_attribute(self, key_path: str, value: Any):
        """Met à jour les attributs legacy quand la configuration change"""
        legacy_mapping = {
            "server.host": "HOST",
            "server.port": "PORT",
            "server.max_clients": "MAX_CLIENTS",
            "server.heartbeat_interval": "HEARTBEAT_INTERVAL",
            "server.client_timeout": "CLIENT_TIMEOUT",
            "processing.batch_size": "BATCH_SIZE",
            "processing.max_concurrent_batches": "MAX_CONCURRENT_BATCHES",
            "processing.realesrgan_model": "REALESRGAN_MODEL",
            "processing.tile_size": "TILE_SIZE",
            "processing.max_retries": "MAX_RETRIES",
            "processing.output_format": "OUTPUT_FORMAT",
            "processing.duplicate_threshold": "DUPLICATE_THRESHOLD",
            "storage.work_directory": "WORK_DIRECTORY",
            "storage.work_drive": "WORK_DRIVE",
            "storage.input_directory": "INPUT_DIRECTORY",
            "storage.output_directory": ["OUTPUT_DIRECTORY", "OUTPUT_DIR"],
            "storage.temp_directory": ["TEMP_DIRECTORY", "TEMP_DIR"],
            "storage.batches_directory": "BATCHES_DIRECTORY",
            "storage.frames_directory": "FRAMES_DIR",
            "storage.upscaled_directory": "UPSCALED_DIR",
            "storage.auto_cleanup": "AUTO_CLEANUP",
            "storage.auto_cleanup_age_hours": "AUTO_CLEANUP_AGE_HOURS",
            "storage.min_free_space_gb": "MIN_FREE_SPACE_GB",
            "security.enable_encryption": "USE_ENCRYPTION",
            "security.session_key_size": "ENCRYPTION_KEY_SIZE",
            "security.auth_token_length": "AUTH_TOKEN_LENGTH",
            "realesrgan.executable_path": "REALESRGAN_PATH",
            "realesrgan.default_scale": "REALESRGAN_SCALE",
            "realesrgan.gpu_id": "GPU_ID",
            "realesrgan.use_fp16": "USE_FP16",
            "realesrgan.tta_mode": "TTA_MODE",
            "ffmpeg.crf": "FFMPEG_CRF",
            "ffmpeg.preset": "FFMPEG_PRESET",
            "ffmpeg.threads": "FFMPEG_THREADS",
            "ffmpeg.audio_bitrate": "AUDIO_BITRATE",
            "ffmpeg.video_codec": "VIDEO_CODEC",
            "ffmpeg.pixel_format": "PIXEL_FORMAT",
            "gui.auto_refresh_interval": "GUI_UPDATE_INTERVAL",
            "gui.log_max_lines": "LOG_MAX_LINES",
        }

        if key_path in legacy_mapping:
            attrs = legacy_mapping[key_path]
            if isinstance(attrs, list):
                for attr in attrs:
                    setattr(self, attr, value)
            else:
                setattr(self, attrs, value)
    
    def get_work_directories(self) -> Dict[str, Path]:
        """Retourne tous les répertoires de travail"""
        directories = {
            'work': Path(self.get("storage.work_directory", "./work")),
            'input': Path(self.get("storage.input_directory", "./input")),
            'output': Path(self.get("storage.output_directory", "./output")),
            'temp': Path(self.get("storage.temp_directory", "./temp")),
            'batches': Path(self.get("storage.batches_directory", "./batches")),
            'logs': Path(self.get("storage.logs_directory", "./logs"))
        }
        
        # Création des répertoires s'ils n'existent pas
        for dir_path in directories.values():
            dir_path.mkdir(parents=True, exist_ok=True)
        
        return directories
    
    def validate_config(self) -> Dict[str, Any]:
        """Valide la configuration et retourne les erreurs"""
        errors = []
        warnings = []
        
        try:
            # Validation des ports
            port = self.get("server.port")
            if not isinstance(port, int) or port < 1 or port > 65535:
                errors.append("Le port serveur doit être entre 1 et 65535")
            
            # Validation des répertoires
            try:
                directories = self.get_work_directories()
                for name, path in directories.items():
                    if not path.exists():
                        warnings.append(f"Le répertoire {name} sera créé: {path}")
            except Exception as e:
                errors.append(f"Erreur validation répertoires: {e}")
            
            # Validation Real-ESRGAN
            realesrgan_path = Path(self.get("realesrgan.executable_path", ""))
            if not realesrgan_path.exists():
                warnings.append(f"Exécutable Real-ESRGAN non trouvé: {realesrgan_path}")
            
            # Validation SSL si activé
            if self.get("server.enable_ssl"):
                cert_file = self.get("server.ssl_cert_path")
                key_file = self.get("server.ssl_key_path")
                
                if not cert_file or not Path(cert_file).exists():
                    errors.append("Fichier certificat SSL manquant ou invalide")
                if not key_file or not Path(key_file).exists():
                    errors.append("Fichier clé SSL manquant ou invalide")
            
        except Exception as e:
            errors.append(f"Erreur lors de la validation: {e}")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        }
    
    def get_realesrgan_config(self) -> Dict[str, Any]:
        """Retourne la configuration spécifique à Real-ESRGAN"""
        return {
            'model': self.get('processing.realesrgan_model', 'RealESRGAN_x4plus'),
            'scale': self.get('processing.upscale_factor', 4),
            'format': self.get('processing.output_format', 'png'),
            'tile_size': self.get('processing.tile_size', 256),
            'executable_path': self.get('realesrgan.executable_path', ''),
            'gpu_id': self.get('realesrgan.gpu_id', 0),
            'thread_load': self.get('realesrgan.thread_load', '1:2:2')
        }
    
    def reload_config(self):
        """Recharge la configuration depuis le fichier"""
        self.config = self.load_config()
        self._setup_legacy_attributes()
        self.logger.info("Configuration rechargée")
    
    def reset_to_default(self):
        """Remet la configuration par défaut"""
        self.config = self.default_config.copy()
        self._setup_legacy_attributes()
        self.save_config()
        self.logger.info("Configuration remise à zéro (valeurs par défaut)")

    def reset_to_defaults(self):
        """Alias pour reset_to_default (compatibilité settings.py)"""
        self.reset_to_default()

    def get_config_file_path(self) -> Path:
        """Retourne le chemin du fichier de configuration"""
        return self.config_file

    def apply_and_save(self, **kwargs) -> bool:
        """Applique les modifications et sauvegarde automatiquement (compatibilité settings.py)"""
        try:
            for key, value in kwargs.items():
                # Conversion des clés en majuscules vers les chemins de configuration
                key_mappings = {
                    'HOST': 'server.host',
                    'PORT': 'server.port',
                    'MAX_CLIENTS': 'server.max_clients',
                    'HEARTBEAT_INTERVAL': 'server.heartbeat_interval',
                    'CLIENT_TIMEOUT': 'server.client_timeout',
                    'BATCH_SIZE': 'processing.batch_size',
                    'MAX_RETRIES': 'processing.max_retries',
                    'DUPLICATE_THRESHOLD': 'processing.duplicate_threshold',
                    'REALESRGAN_MODEL': 'processing.realesrgan_model',
                    'REALESRGAN_SCALE': 'realesrgan.default_scale',
                    'TILE_SIZE': 'processing.tile_size',
                    'GPU_ID': 'realesrgan.gpu_id',
                    'USE_FP16': 'realesrgan.use_fp16',
                    'TTA_MODE': 'realesrgan.tta_mode',
                    'FFMPEG_CRF': 'ffmpeg.crf',
                    'FFMPEG_PRESET': 'ffmpeg.preset',
                    'FFMPEG_THREADS': 'ffmpeg.threads',
                    'AUDIO_BITRATE': 'ffmpeg.audio_bitrate',
                    'VIDEO_CODEC': 'ffmpeg.video_codec',
                    'PIXEL_FORMAT': 'ffmpeg.pixel_format',
                    'AUTO_CLEANUP': 'storage.auto_cleanup',
                    'AUTO_CLEANUP_AGE_HOURS': 'storage.auto_cleanup_age_hours',
                    'MIN_FREE_SPACE_GB': 'storage.min_free_space_gb',
                    'USE_ENCRYPTION': 'security.enable_encryption',
                    'WORK_DRIVE': 'storage.work_drive',
                }

                # Obtenir le chemin de configuration ou utiliser la clé telle quelle
                config_path = key_mappings.get(key, key)

                # Mise à jour directe de l'attribut ET de la config
                if hasattr(self, key):
                    setattr(self, key, value)

                # Mise à jour de la configuration interne
                keys = config_path.split('.')
                current = self.config
                for k in keys[:-1]:
                    if k not in current:
                        current[k] = {}
                    current = current[k]
                current[keys[-1]] = value

            # Sauvegarde unique après toutes les modifications
            self.save_config()
            return True

        except Exception as e:
            self.logger.error(f"Erreur lors de apply_and_save: {e}")
            return False

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
            import shutil
            current_drive = str(Path.cwd().drive) if hasattr(Path.cwd(), 'drive') else '/'
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

    def set_work_drive(self, drive_path: str):
        """Change le disque de travail et sauvegarde (compatibilité settings.py)"""
        self.set("storage.work_drive", drive_path)
        self.WORK_DRIVE = drive_path
        # Mise à jour des attributs legacy
        self._setup_legacy_attributes()

    def cleanup_temp_files(self, job_id: str = None) -> bool:
        """Nettoie les fichiers temporaires"""
        try:
            import shutil
            temp_path = Path(self.get("storage.temp_directory", "./temp"))

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
            self.logger.error(f"Erreur nettoyage: {e}")
            return False

# Instance globale
config = ServerConfig()

# Constantes pour la compatibilité avec l'ancien code
BATCH_SIZE = config.BATCH_SIZE
DUPLICATE_THRESHOLD = config.get("processing.duplicate_threshold", 5)
MAX_CONCURRENT_BATCHES = config.MAX_CONCURRENT_BATCHES