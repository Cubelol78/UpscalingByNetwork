# server/security/__init__.py
"""
Module de sécurité pour le serveur d'upscaling distribué
"""

# Import sécurisé des modules de sécurité
try:
    from .server_security import ServerSecurity
    __all__ = ['ServerSecurity']
except ImportError as e:
    print(f"⚠️ Erreur import module sécurité serveur: {e}")
    ServerSecurity = None
    __all__ = []

# Classe de secours pour la sécurité
class FallbackSecurity:
    """Classe de sécurité de secours sans chiffrement"""
    
    def __init__(self):
        self.logger = None
        
    def generate_session_key(self, client_id: str):
        return b"fallback_key"
    
    def encrypt_data(self, data: bytes, client_id: str):
        return data  # Pas de chiffrement en mode secours
    
    def decrypt_data(self, data: bytes, client_id: str):
        return data  # Pas de déchiffrement en mode secours
    
    def is_session_valid(self, client_id: str):
        return True  # Toujours valide en mode secours

# Si le module principal n'est pas disponible, utiliser le fallback
if ServerSecurity is None:
    print("🔄 Utilisation du module de sécurité de secours (SANS CHIFFREMENT)")
    ServerSecurity = FallbackSecurity
    __all__.append('ServerSecurity')