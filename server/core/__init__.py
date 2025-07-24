# server/core/__init__.py
"""
Module core pour le serveur d'upscaling distribué
"""

# Import sécurisé des modules core
try:
    from .processor import ServerProcessor
    __all__ = ['ServerProcessor']
except ImportError as e:
    print(f"⚠️ Erreur import processeur serveur: {e}")
    ServerProcessor = None
    __all__ = []

try:
    from .optimized_real_esrgan import optimized_realesrgan, OptimizedRealESRGAN
    __all__.extend(['optimized_realesrgan', 'OptimizedRealESRGAN'])
except ImportError as e:
    print(f"⚠️ Erreur import Real-ESRGAN optimisé: {e}")
    optimized_realesrgan = None

# Classe de secours pour le processeur
class FallbackServerProcessor:
    """Processeur serveur de secours"""
    
    def __init__(self, server_instance):
        self.server = server_instance
        self.connected_clients = {}
        
    def register_client(self, client_id: str, client_info: dict):
        self.connected_clients[client_id] = client_info
        return b"fallback_key"
    
    def unregister_client(self, client_id: str):
        self.connected_clients.pop(client_id, None)
    
    def get_server_stats(self):
        return {
            'clients': {'connected': len(self.connected_clients)},
            'fallback_mode': True
        }

# Si le processeur principal n'est pas disponible, utiliser le fallback
if ServerProcessor is None:
    print("🔄 Utilisation du processeur serveur de secours")
    ServerProcessor = FallbackServerProcessor
    __all__.append('ServerProcessor')