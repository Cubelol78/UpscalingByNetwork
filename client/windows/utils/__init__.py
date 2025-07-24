# client/windows/utils/__init__.py
"""
Module utils pour le client Windows d'upscaling distribué
"""

# Import sécurisé du détecteur d'exécutables
try:
    from .executable_detector import client_executable_detector, ClientExecutableDetector
    __all__ = ['client_executable_detector', 'ClientExecutableDetector']
except ImportError as e:
    print(f"⚠️ Erreur import détecteur exécutables client: {e}")
    client_executable_detector = None
    __all__ = []

# Fonction pour créer un détecteur de secours
def create_fallback_detector():
    """Crée un détecteur de secours en cas d'erreur"""
    class FallbackDetector:
        def __init__(self):
            self.client_root = None
            
        def find_realesrgan(self):
            return None
            
        def find_ffmpeg(self):
            return None
            
        def is_client_ready(self):
            return False
            
        def get_all_executables_status(self):
            return {
                'summary': {'client_ready': False},
                'error': 'Détecteur non disponible'
            }
    
    return FallbackDetector()

# Si le détecteur principal n'est pas disponible, utiliser le détecteur de secours
if client_executable_detector is None:
    print("🔄 Utilisation du détecteur de secours...")
    client_executable_detector = create_fallback_detector()
    __all__.append('client_executable_detector')