# client/windows/security/__init__.py
"""
Module de sécurité pour le client Windows d'upscaling distribué
"""

# Import sécurisé des modules de sécurité
try:
    from .client_security import ClientSecurity
    __all__ = ['ClientSecurity']
except ImportError as e:
    print(f"⚠️ Erreur import module sécurité client: {e}")
    ClientSecurity = None
    __all__ = []

# Classe de secours pour la sécurité client
class FallbackClientSecurity:
    """Classe de sécurité client de secours sans chiffrement"""
    
    def __init__(self):
        self.session_key = None
        
    def set_session_key(self, key: bytes):
        self.session_key = key
    
    def encrypt_data(self, data: bytes):
        return data  # Pas de chiffrement en mode secours
    
    def decrypt_data(self, data: bytes):
        return data  # Pas de déchiffrement en mode secours
    
    def is_session_established(self):
        return True  # Toujours établie en mode secours

# Si le module principal n'est pas disponible, utiliser le fallback
if ClientSecurity is None:
    print("🔄 Utilisation du module de sécurité client de secours (SANS CHIFFREMENT)")
    ClientSecurity = FallbackClientSecurity
    __all__.append('ClientSecurity')