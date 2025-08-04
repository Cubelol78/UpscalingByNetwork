# UpscalingByNetwork/client/windows/utils/__init__.py
"""
Utilitaires pour le client Windows
"""

try:
    from .realesrgan_handler import RealESRGANHandler
    from .encryption_manager import ClientEncryptionManager
    from .system_monitor import SystemMonitor
    
    UTILS_AVAILABLE = True
except ImportError:
    RealESRGANHandler = None
    ClientEncryptionManager = None
    SystemMonitor = None
    UTILS_AVAILABLE = False

__all__ = [
    'RealESRGANHandler', 
    'ClientEncryptionManager', 
    'SystemMonitor', 
    'UTILS_AVAILABLE'
]