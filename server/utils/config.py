# server/utils/config.py
"""
Configuration centralisée pour le serveur d'upscaling distribué
"""

import os
import json
from pathlib import Path
import time
from typing import Dict, Any, Optional, List
import logging

class ConfigManager:
    """Gestionnaire de configuration centralisé"""
    
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
                "gpu_memory_limit": 8192
            },
            "storage": {
                "work_directory": "./work",
                "input_directory": "./input",
                "output_directory": "./output",
                "temp_directory": "./temp",
                "batches_directory": "./batches",
                "logs_directory": "./logs",
                "max_disk_usage_gb": 100
            },
            "security": {
                "enable_encryption": True,
                "encryption_algorithm": "AES-256",
                "key_exchange_method": "ECDH",
                "session_timeout": 3600,
                "max_failed_attempts": 5
            },
            "monitoring": {
                "log_level": "INFO",
                "enable_metrics": True,
                "metrics_interval": 60,
                "performance_monitoring": True,
                "resource_monitoring": True
            },
            "video": {
                "supported_formats": ["mp4", "avi", "mkv", "mov", "webm"],
                "ffmpeg_quality": "high",
                "preserve_audio": True,
                "frame_extraction_format": "png",
                "fps_preservation": True
            },
            "optimization": {
                "adaptive_batch_size": True,
                "dynamic_quality_adjustment": True,
                "smart_client_selection": True,
                "load_balancing": True,
                "failover_enabled": True
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
                self.logger.info(f"Configuration chargée depuis: {self.config_file}")
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
    
    def get_work_directories(self) -> Dict[str, Path]:
        """Retourne les chemins de tous les dossiers de travail"""
        storage_config = self.get('storage')
        directories = {}
        
        for key, path_str in storage_config.items():
            if key.endswith('_directory'):
                name = key.replace('_directory', '')
                directories[name] = Path(path_str).resolve()
        
        return directories
    
    def ensure_directories(self):
        """S'assure que tous les dossiers nécessaires existent"""
        directories = self.get_work_directories()
        
        for name, path in directories.items():
            try:
                path.mkdir(parents=True, exist_ok=True)
                self.logger.debug(f"Dossier {name} vérifié: {path}")
            except Exception as e:
                self.logger.error(f"Impossible de créer le dossier {name} ({path}): {e}")
                raise
    
    def validate_config(self) -> Dict[str, Any]:
        """Valide la configuration actuelle"""
        errors = []
        warnings = []
        
        try:
            # Vérification des ports
            port = self.get('server.port')
            if not isinstance(port, int) or not (1024 <= port <= 65535):
                errors.append("Port serveur invalide (doit être entre 1024 et 65535)")
            
            # Vérification des chemins
            directories = self.get_work_directories()
            for name, path in directories.items():
                try:
                    path.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    errors.append(f"Impossible d'accéder au dossier {name}: {e}")
            
            # Vérification de la sécurité
            if self.get('security.enable_encryption') and not self.get('server.enable_ssl'):
                warnings.append("Chiffrement activé mais SSL désactivé")
            
            # Vérification des ressources
            max_clients = self.get('server.max_clients')
            max_batches = self.get('processing.max_concurrent_batches')
            if max_batches > max_clients * 2:
                warnings.append("Nombre de lots concurrent élevé par rapport aux clients")
            
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
            'gpu_enabled': self.get('processing.enable_gpu'),
            'gpu_memory': self.get('processing.gpu_memory_limit')
        }
    
    def export_config(self, file_path: Optional[Path] = None) -> str:
        """Exporte la configuration vers un fichier"""
        if file_path is None:
            file_path = Path(f"config_export_{int(time.time())}.json")
        
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

# Instance globale de configuration
config = ConfigManager()