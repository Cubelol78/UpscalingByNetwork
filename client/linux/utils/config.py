"""
Configuration manager for the Linux client
Uses XDG Base Directory Specification for Linux compatibility
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
import logging


class ClientConfig:
    """Configuration manager with cross-platform support"""

    def __init__(self, config_path: Optional[Path] = None):
        self.logger = logging.getLogger(__name__)

        # Determine config directory using XDG specification
        if config_path is None:
            xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
            if xdg_config_home:
                config_dir = Path(xdg_config_home) / "upscaling-client"
            else:
                config_dir = Path.home() / ".config" / "upscaling-client"

            self.config_file = config_dir / "config.json"
        else:
            self.config_file = Path(config_path)

        self.config_file.parent.mkdir(parents=True, exist_ok=True)

        # Default configuration
        self.default_config = {
            "client": {
                "name": "Linux-Client",
                "log_level": "INFO",
                "auto_connect": False,
                "retry_attempts": 3,
                "retry_delay": 5,
                "heartbeat_interval": 30,
            },
            "server": {
                "host": "localhost",
                "port": 8765,
                "timeout": 30,
                "use_ssl": False,
                "ssl_verify": True,
                "reconnect_delay": 10,
                "max_reconnection_attempts": 0,  # 0 = unlimited
            },
            "processing": {
                "use_gpu": True,
                "gpu_id": 0,
                "tile_size": 256,
                "realesrgan_model": "RealESRGAN_x4plus",
                "scale": 4,
                "output_format": "png",
                "max_batch_size": 50,
                "timeout_per_frame": 30,
                "tta_mode": False,
            },
            "storage": {
                "work_directory": None,  # Will use XDG_DATA_HOME
                "temp_directory": None,  # Will use /tmp or XDG_RUNTIME_DIR
                "max_disk_usage_gb": 50,
                "cleanup_age_hours": 24,
            },
            "security": {
                "enable_encryption": True,
                "key_exchange_timeout": 30,
                "session_timeout": 3600,
            },
            "hardware": {
                "auto_detect": True,
                "cpu_threads": 0,  # 0 = auto
                "memory_limit_mb": 8192,
                "enable_monitoring": True,
            },
            "gui": {
                "theme": "default",
                "start_minimized": False,
                "show_notifications": True,
                "update_interval": 1000,
            },
            "cli": {
                "use_colors": True,
                "progress_bar": True,
                "verbose": False,
            },
            "paths": {
                "realesrgan_executable": None,  # Auto-detect
                "models_directory": None,  # Auto-detect
            },
        }

        # Load configuration
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or create default"""
        try:
            if self.config_file.exists():
                with open(self.config_file, "r", encoding="utf-8") as f:
                    loaded_config = json.load(f)

                # Merge with defaults
                config = self._merge_config(self.default_config, loaded_config)
                self.logger.info(f"Configuration loaded from: {self.config_file}")
                return config
            else:
                self.logger.info(
                    "No configuration file found, using defaults"
                )
                self.save_config()
                return self.default_config.copy()

        except Exception as e:
            self.logger.error(f"Error loading configuration: {e}")
            return self.default_config.copy()

    def _merge_config(self, default: Dict, loaded: Dict) -> Dict:
        """Recursively merge loaded config with defaults"""
        merged = default.copy()

        for key, value in loaded.items():
            if (
                key in merged
                and isinstance(merged[key], dict)
                and isinstance(value, dict)
            ):
                merged[key] = self._merge_config(merged[key], value)
            else:
                merged[key] = value

        return merged

    def save_config(self):
        """Save current configuration to file"""
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            self.logger.debug(f"Configuration saved to: {self.config_file}")
        except Exception as e:
            self.logger.error(f"Error saving configuration: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation

        Args:
            key: Configuration key (e.g., "server.host")
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        keys = key.split(".")
        value = self.config

        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def set(self, key: str, value: Any, save: bool = True):
        """
        Set configuration value using dot notation

        Args:
            key: Configuration key (e.g., "server.host")
            value: Value to set
            save: Whether to save to file immediately
        """
        keys = key.split(".")
        config_ref = self.config

        # Navigate to parent
        for k in keys[:-1]:
            if k not in config_ref:
                config_ref[k] = {}
            config_ref = config_ref[k]

        # Set value
        config_ref[keys[-1]] = value

        if save:
            self.save_config()

        self.logger.debug(f"Configuration updated: {key} = {value}")

    def get_work_directory(self) -> Path:
        """Get work directory, creating if necessary"""
        work_dir = self.get("storage.work_directory")

        if work_dir is None:
            # Use XDG data directory
            xdg_data_home = os.environ.get("XDG_DATA_HOME")
            if xdg_data_home:
                work_dir = Path(xdg_data_home) / "upscaling-client"
            else:
                work_dir = Path.home() / ".local" / "share" / "upscaling-client"
        else:
            work_dir = Path(work_dir)

        work_dir = work_dir.resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        return work_dir

    def get_temp_directory(self) -> Path:
        """Get temporary directory"""
        temp_dir = self.get("storage.temp_directory")

        if temp_dir is None:
            # Try XDG_RUNTIME_DIR first, fallback to /tmp
            xdg_runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
            if xdg_runtime_dir:
                temp_dir = Path(xdg_runtime_dir) / "upscaling-client"
            else:
                temp_dir = Path("/tmp") / "upscaling-client"
        else:
            temp_dir = Path(temp_dir)

        temp_dir = temp_dir.resolve()
        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir

    def get_log_directory(self) -> Path:
        """Get log directory"""
        xdg_data_home = os.environ.get("XDG_DATA_HOME")
        if xdg_data_home:
            log_dir = Path(xdg_data_home) / "upscaling-client" / "logs"
        else:
            log_dir = Path.home() / ".local" / "share" / "upscaling-client" / "logs"

        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir

    def validate_config(self) -> bool:
        """Validate current configuration"""
        try:
            # Validate port
            port = self.get("server.port")
            if not isinstance(port, int) or not (1024 <= port <= 65535):
                self.logger.error(f"Invalid port: {port}")
                return False

            # Validate directories
            try:
                self.get_work_directory()
                self.get_temp_directory()
            except Exception as e:
                self.logger.error(f"Cannot create directories: {e}")
                return False

            # Validate resource limits
            memory_limit = self.get("hardware.memory_limit_mb")
            if memory_limit < 512 or memory_limit > 65536:
                self.logger.warning(f"Suspicious memory limit: {memory_limit}MB")

            return True

        except Exception as e:
            self.logger.error(f"Configuration validation error: {e}")
            return False

    def reset_to_defaults(self):
        """Reset configuration to defaults"""
        self.config = self.default_config.copy()
        self.save_config()
        self.logger.info("Configuration reset to defaults")

    def export_config(self, export_path: Path) -> bool:
        """Export configuration to a file"""
        try:
            with open(export_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            self.logger.info(f"Configuration exported to: {export_path}")
            return True
        except Exception as e:
            self.logger.error(f"Error exporting configuration: {e}")
            return False

    def import_config(self, import_path: Path) -> bool:
        """Import configuration from a file"""
        try:
            with open(import_path, "r", encoding="utf-8") as f:
                imported_config = json.load(f)

            if not isinstance(imported_config, dict):
                raise ValueError("Invalid configuration format")

            self.config = self._merge_config(self.default_config, imported_config)
            self.save_config()
            self.logger.info(f"Configuration imported from: {import_path}")
            return True

        except Exception as e:
            self.logger.error(f"Error importing configuration: {e}")
            return False

    def __repr__(self) -> str:
        return f"ClientConfig(file={self.config_file})"


# Global configuration instance
config = ClientConfig()
