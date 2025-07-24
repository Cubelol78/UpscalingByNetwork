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
        
        # Configuration par défaut
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
                "max_retries": 3
            },
            "storage": {
                "work_directory": "./work",
                "input_directory": "./input",
                "output_directory": "./output",
                "temp_directory": "./temp",
                "batches_directory": "./batches",
                "logs_directory": "./logs",
                "auto_cleanup": True,
                "min_free_space_gb": 5
            },
            "security": {
                "enable_encryption": True,
                "key_exchange_timeout": 30,
                "session_key_size": 256,
                "allowed_clients": []
            },
            "realesrgan": {
                "executable_path": "./dependencies/realesrgan-ncnn-vulkan.exe",
                "models_directory": "./models",
                "default_model": "RealESRGAN_x4plus",
                "default_scale": 4,
                "tile_size": 256,
                "gpu_id": 0,
                "thread_load": "1:2:2",
                "tta_mode": False
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
                "auto_refresh_interval": 2000,
                "show_detailed_logs": True,
                "enable_notifications": True,
                "charts_history_points": 100
            }
        }
        
        # Chargement de la configuration
        self.config = self.load_config()
        
        # COMPATIBILITÉ RÉTROACTIVE : Création des attributs directs
        self._setup_legacy_attributes()
    
    def _setup_legacy_attributes(self):
        """Configure les attributs pour la compatibilité avec l'ancien code"""
        # Serveur
        self.HOST = self.get("server.host", "0.0.0.0")
        self.PORT = self.get("server.port", 8765)
        self.MAX_CLIENTS = self.get("server.max_clients", 10)
        
        # Processing
        self.BATCH_SIZE = self.get("processing.batch_size", 50)
        self.MAX_CONCURRENT_BATCHES = self.get("processing.max_concurrent_batches", 5)
        self.REALESRGAN_MODEL = self.get("processing.realesrgan_model", "RealESRGAN_x4plus")
        self.TILE_SIZE = self.get("processing.tile_size", 256)
        self.MAX_RETRIES = self.get("processing.max_retries", 3)
        self.OUTPUT_FORMAT = self.get("processing.output_format", "png")
        
        # Storage
        self.WORK_DIRECTORY = self.get("storage.work_directory", "./work")
        self.INPUT_DIRECTORY = self.get("storage.input_directory", "./input")
        self.OUTPUT_DIRECTORY = self.get("storage.output_directory", "./output")
        self.TEMP_DIRECTORY = self.get("storage.temp_directory", "./temp")
        self.BATCHES_DIRECTORY = self.get("storage.batches_directory", "./batches")
        self.AUTO_CLEANUP = self.get("storage.auto_cleanup", True)
        self.MIN_FREE_SPACE_GB = self.get("storage.min_free_space_gb", 5)
        
        # Security
        self.USE_ENCRYPTION = self.get("security.enable_encryption", True)
        
        # Real-ESRGAN
        self.REALESRGAN_PATH = self.get("realesrgan.executable_path", "./dependencies/realesrgan-ncnn-vulkan.exe")
        
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
            "processing.batch_size": "BATCH_SIZE",
            "processing.max_concurrent_batches": "MAX_CONCURRENT_BATCHES",
            "processing.realesrgan_model": "REALESRGAN_MODEL",
            "processing.tile_size": "TILE_SIZE",
            "processing.max_retries": "MAX_RETRIES",
            "processing.output_format": "OUTPUT_FORMAT",
            "storage.work_directory": "WORK_DIRECTORY",
            "storage.input_directory": "INPUT_DIRECTORY",
            "storage.output_directory": "OUTPUT_DIRECTORY",
            "storage.temp_directory": "TEMP_DIRECTORY",
            "storage.batches_directory": "BATCHES_DIRECTORY",
            "storage.auto_cleanup": "AUTO_CLEANUP",
            "storage.min_free_space_gb": "MIN_FREE_SPACE_GB",
            "security.enable_encryption": "USE_ENCRYPTION",
            "realesrgan.executable_path": "REALESRGAN_PATH"
        }
        
        if key_path in legacy_mapping:
            setattr(self, legacy_mapping[key_path], value)
    
    def get_work_directories(self) -> Dict[str, Path]:
        """Retourne tous les répertoires de travail"""
        directories = {
            'work': Path(self.get("storage.work_directory")),
            'input': Path(self.get("storage.input_directory")),
            'output': Path(self.get("storage.output_directory")),
            'temp': Path(self.get("storage.temp_directory")),
            'batches': Path(self.get("storage.batches_directory")),
            'logs': Path(self.get("storage.logs_directory"))
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
            realesrgan_path = Path(self.get("realesrgan.executable_path"))
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
            'model': self.get('processing.realesrgan_model'),
            'scale': self.get('processing.upscale_factor'),
            'format': self.get('processing.output_format'),
            'tile_size': self.get('processing.tile_size'),
            'executable_path': self.get('realesrgan.executable_path'),
            'gpu_id': self.get('realesrgan.gpu_id'),
            'thread_load': self.get('realesrgan.thread_load')
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

# Instance globale
config = ServerConfig()

# Constantes pour la compatibilité avec l'ancien code
BATCH_SIZE = config.BATCH_SIZE
DUPLICATE_THRESHOLD = config.get("processing.duplicate_threshold", 5)
MAX_CONCURRENT_BATCHES = config.MAX_CONCURRENT_BATCHES