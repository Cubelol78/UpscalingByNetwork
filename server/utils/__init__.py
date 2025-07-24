# server/utils/__init__.py
"""
Module utils pour le serveur d'upscaling distribué
"""

# Import sécurisé de la configuration
try:
    from .config import config, ServerConfig
    __all__ = ['config', 'ServerConfig']
except ImportError as e:
    print(f"⚠️ Erreur import config dans utils: {e}")
    config = None
    __all__ = []

# Fonction pour créer une configuration de secours
def create_fallback_config():
    """Crée une configuration de secours en cas d'erreur"""
    class FallbackConfig:
        def __init__(self):
            self.REALESRGAN_MODEL = "RealESRGAN_x4plus"
            self.BATCH_SIZE = 50
            self.TILE_SIZE = 256
            self.MAX_RETRIES = 3
            self.PORT = 8765
            self.HOST = "0.0.0.0"
            self.MAX_CLIENTS = 10
            self.USE_ENCRYPTION = True
            
        def get(self, key, default=None):
            """Méthode get compatible"""
            key_map = {
                "processing.realesrgan_model": "RealESRGAN_x4plus",
                "processing.batch_size": 50,
                "processing.tile_size": 256,
                "processing.max_retries": 3,
                "server.port": 8765,
                "server.host": "0.0.0.0",
                "server.max_clients": 10,
                "security.enable_encryption": True
            }
            return key_map.get(key, default)
    
    return FallbackConfig()

# Si la configuration principale n'est pas disponible, utiliser la configuration de secours
if config is None:
    print("🔄 Utilisation de la configuration de secours...")
    config = create_fallback_config()
    __all__.append('config')