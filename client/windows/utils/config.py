# client/windows/utils/config.py
"""
Configuration du client d'upscaling distribué
"""

import os
import json
from pathlib import Path
import time
from typing import Dict, Any, Optional
import logging

class ClientConfig:
    """Gestionnaire de configuration pour le client"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Chemin vers le fichier de configuration
        self.config_file = Path(__file__).parent.parent / "config" / "client_config.json"
        self.config_file.parent.mkdir(exist_ok=True)
        
        # Configuration par défaut
        self.default_config = {
            "client": {
                "name": "Client-Windows",
                "log_level": "INFO",
                "auto_connect": False,
                "retry_attempts": 3,
                "retry_delay": 5,
                "heartbeat_interval": 30
            },
            "server": {
                "host": "localhost",
                "port": 8765,
                "timeout": 30,
                "ssl_enabled": False,
                "ssl_verify": True
            },
            "processing": {
                "enable_gpu": True,
                "thread_count": 4,
                "gpu_memory_limit": 4096,
                "realesrgan_model": "RealESRGAN_x4plus",
                "output_format": "png",
                "max_batch_size": 50,
                "timeout_per_frame": 30
            },
            "storage": {
                "work_directory": "./client_work",
                "temp_directory": "./temp",
                "logs_directory": "./logs",
                "max_disk_usage_gb": 50
            },
            "security": {
                "enable_encryption": True,
                "key_exchange_timeout": 30,
                "session_timeout": 3600
            },
            "hardware": {
                "auto_detect": True,
                "preferred_gpu": "",
                "memory_limit_mb": 8192,
                "cpu_threads": 0,  # 0 = auto-detect
                "enable_monitoring": True
            },
            "gui": {
                "theme": "default",
                "minimize_to_tray": True,
                "start_minimized": False,
                "show_notifications": True,
                "update_interval": 1000
            }
        }
        
        # Charger la configuration
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Charge la configuration depuis le fichier"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                
                # Fusion avec la configuration par défaut
                config = self._merge_config(self.default_config, loaded_config)
                self.logger.info(f"Configuration client chargée depuis: {self.config_file}")
                return config
            else:
                self.logger.info("Aucun fichier de configuration trouvé, utilisation des valeurs par défaut")
                self._save_config(self.default_config)
                return self.default_config.copy()
                
        except Exception as e:
            self.logger.error(f"Erreur lors du chargement de la configuration: {e}")
            return self.default_config.copy()
    
    def _merge_config(self, default: Dict, loaded: Dict) -> Dict:
        """Fusionne la configuration chargée avec les valeurs par défaut"""
        merged = default.copy()
        
        for key, value in loaded.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = self._merge_config(merged[key], value)
            else:
                merged[key] = value
        
        return merged
    
    def _save_config(self, config_data: Dict[str, Any]):
        """Sauvegarde la configuration dans le fichier"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=4, ensure_ascii=False)
            self.logger.info(f"Configuration sauvegardée dans: {self.config_file}")
        except Exception as e:
            self.logger.error(f"Erreur lors de la sauvegarde: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Récupère une valeur de configuration avec notation pointée"""
        keys = key.split('.')
        value = self.config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            if default is not None:
                return default
            raise KeyError(f"Clé de configuration non trouvée: {key}")
    
    def set(self, key: str, value: Any, save: bool = True):
        """Définit une valeur de configuration avec notation pointée"""
        keys = key.split('.')
        config_ref = self.config
        
        # Navigation jusqu'à l'avant-dernière clé
        for k in keys[:-1]:
            if k not in config_ref:
                config_ref[k] = {}
            config_ref = config_ref[k]
        
        # Définition de la valeur
        config_ref[keys[-1]] = value
        
        if save:
            self._save_config(self.config)
        
        self.logger.info(f"Configuration mise à jour: {key} = {value}")
    
    def get_work_directory(self) -> Path:
        """Retourne le dossier de travail du client"""
        work_dir = Path(self.get('storage.work_directory')).resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        return work_dir
    
    def get_server_config(self) -> Dict[str, Any]:
        """Retourne la configuration serveur"""
        return {
            'host': self.get('server.host'),
            'port': self.get('server.port'),
            'timeout': self.get('server.timeout'),
            'ssl_enabled': self.get('server.ssl_enabled'),
            'ssl_verify': self.get('server.ssl_verify')
        }
    
    def get_processing_config(self) -> Dict[str, Any]:
        """Retourne la configuration de traitement"""
        return {
            'enable_gpu': self.get('processing.enable_gpu'),
            'thread_count': self.get('processing.thread_count'),
            'gpu_memory_limit': self.get('processing.gpu_memory_limit'),
            'realesrgan_model': self.get('processing.realesrgan_model'),
            'output_format': self.get('processing.output_format'),
            'max_batch_size': self.get('processing.max_batch_size'),
            'timeout_per_frame': self.get('processing.timeout_per_frame')
        }
    
    def get_hardware_config(self) -> Dict[str, Any]:
        """Retourne la configuration matérielle"""
        return {
            'auto_detect': self.get('hardware.auto_detect'),
            'preferred_gpu': self.get('hardware.preferred_gpu'),
            'memory_limit_mb': self.get('hardware.memory_limit_mb'),
            'cpu_threads': self.get('hardware.cpu_threads'),
            'enable_monitoring': self.get('hardware.enable_monitoring')
        }
    
    def validate_config(self) -> bool:
        """Valide la configuration actuelle"""
        try:
            # Vérification des ports
            port = self.get('server.port')
            if not isinstance(port, int) or not (1024 <= port <= 65535):
                self.logger.error("Port serveur invalide")
                return False
            
            # Vérification des dossiers
            work_dir = self.get_work_directory()
            if not work_dir.exists():
                work_dir.mkdir(parents=True, exist_ok=True)
            
            # Vérification des limites de ressources
            gpu_memory = self.get('processing.gpu_memory_limit')
            if gpu_memory < 512 or gpu_memory > 32768:
                self.logger.warning("Limite mémoire GPU suspecte")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la validation: {e}")
            return False
    
    def export_config(self, file_path: Optional[Path] = None) -> str:
        """Exporte la configuration vers un fichier"""
        if file_path is None:
            file_path = Path(f"client_config_export_{int(time.time())}.json")
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            
            self.logger.info(f"Configuration exportée vers: {file_path}")
            return str(file_path)
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'export: {e}")
            raise
    
    def import_config(self, file_path: Path):
        """Importe une configuration depuis un fichier"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                imported_config = json.load(f)
            
            # Validation basique
            if not isinstance(imported_config, dict):
                raise ValueError("Format de configuration invalide")
            
            # Fusion et sauvegarde
            self.config = self._merge_config(self.default_config, imported_config)
            self._save_config(self.config)
            
            self.logger.info(f"Configuration importée depuis: {file_path}")
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'import: {e}")
            raise
    
    def reset_to_defaults(self):
        """Remet la configuration aux valeurs par défaut"""
        self.config = self.default_config.copy()
        self._save_config(self.config)
        self.logger.info("Configuration remise aux valeurs par défaut")

# Instance globale de configuration
config = ClientConfig()