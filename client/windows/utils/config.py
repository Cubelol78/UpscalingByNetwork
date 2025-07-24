# client/windows/utils/config.py
"""
Configuration pour le client Windows
"""
import os
import json
from pathlib import Path
from typing import Dict, Any, Optional

class ClientConfig:
    """Gestionnaire de configuration pour le client"""
    
    def __init__(self):
        self.config_dir = Path.home() / ".distributed_upscaler_client"
        self.config_file = self.config_dir / "config.json"
        self.config_dir.mkdir(exist_ok=True)
        
        # Configuration par défaut
        self.default_config = {
            "server": {
                "host": "localhost",
                "port": 8765,
                "use_ssl": False,
                "reconnect_attempts": 5,
                "reconnect_delay": 10,
                "heartbeat_interval": 30
            },
            "security": {
                "auto_generate_key": True,
                "key_exchange_timeout": 30
            },
            "processing": {
                "max_concurrent_batches": 1,
                "work_directory": str(Path.home() / "DistributedUpscaler" / "work"),
                "keep_temp_files": False,
                "compression_level": 0,  # Pas de compression pour les images
                "realesrgan_model": "RealESRGAN_x4plus",
                "tile_size": 256,
                "use_gpu": True
            },
            "client": {
                "auto_connect": False,
                "notify_on_completion": True,
                "log_level": "INFO",
                "max_log_files": 5,
                "client_name": ""
            },
            "paths": {
                "realesrgan_executable": "",
                "models_directory": "./models",
                "temp_directory": ""
            }
        }
        
        # Chargement de la configuration
        self.config = self.load_config()
    
    def load_config(self) -> Dict[str, Any]:
        """Charge la configuration depuis le fichier"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                
                # Fusion avec la configuration par défaut
                config = self.default_config.copy()
                self._merge_config(config, loaded_config)
                return config
                
            except Exception as e:
                print(f"Erreur chargement configuration: {e}")
                return self.default_config.copy()
        else:
            # Sauvegarde de la configuration par défaut
            self.save_config(self.default_config)
            return self.default_config.copy()
    
    def save_config(self, config: Optional[Dict[str, Any]] = None):
        """Sauvegarde la configuration dans le fichier"""
        config_to_save = config or self.config
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_to_save, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Erreur sauvegarde configuration: {e}")
    
    def _merge_config(self, base: Dict[str, Any], update: Dict[str, Any]):
        """Fusionne récursivement deux dictionnaires de configuration"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Récupère une valeur de configuration avec notation pointée
        Exemple: get("server.host") -> config["server"]["host"]
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
        Exemple: set("server.host", "192.168.1.100")
        """
        keys = key_path.split('.')
        current = self.config
        
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        current[keys[-1]] = value
        self.save_config()
    
    def get_server_config(self) -> Dict[str, Any]:
        """Retourne la configuration serveur"""
        return self.config.get("server", {})
    
    def get_processing_config(self) -> Dict[str, Any]:
        """Retourne la configuration de traitement"""
        return self.config.get("processing", {})
    
    def get_security_config(self) -> Dict[str, Any]:
        """Retourne la configuration de sécurité"""
        return self.config.get("security", {})
    
    def get_work_directory(self) -> Path:
        """Retourne le répertoire de travail"""
        work_dir = Path(self.get("processing.work_directory"))
        work_dir.mkdir(parents=True, exist_ok=True)
        return work_dir
    
    def validate_config(self) -> bool:
        """Valide la configuration actuelle"""
        required_keys = [
            "server.host",
            "server.port",
            "processing.work_directory"
        ]
        
        for key in required_keys:
            if self.get(key) is None:
                print(f"Configuration manquante: {key}")
                return False
        
        return True

# Instance globale
config = ClientConfig()