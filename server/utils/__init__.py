# UpscalingByNetwork/server/utils/__init__.py
"""
Utilitaires pour le serveur
"""

# Import conditionnel des utilitaires
try:
    from .ffmpeg_handler import FFmpegHandler
    from .realesrgan_handler import RealESRGANHandler
    from .encryption_manager import EncryptionManager
    
    UTILS_AVAILABLE = True
except ImportError:
    FFmpegHandler = None
    RealESRGANHandler = None
    EncryptionManager = None
    UTILS_AVAILABLE = False

__all__ = ['FFmpegHandler', 'RealESRGANHandler', 'EncryptionManager', 'UTILS_AVAILABLE']