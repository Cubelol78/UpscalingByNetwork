# client/windows/security/client_security.py
"""
Module de sécurité pour le client Windows d'upscaling distribué
"""

import os
import hashlib
import hmac
import time
from typing import Optional, bytes
import logging

try:
    from cryptography.fernet import Fernet
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

class ClientSecurity:
    """Gestionnaire de sécurité pour le client"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.session_key: Optional[bytes] = None
        self.session_established = False
        
        if not CRYPTO_AVAILABLE:
            self.logger.warning("Cryptography non disponible - Mode non sécurisé activé")
    
    def set_session_key(self, key: bytes):
        """Définit la clé de session reçue du serveur"""
        try:
            if CRYPTO_AVAILABLE:
                # Validation de la clé
                Fernet(key)  # Test si la clé est valide
                self.session_key = key
                self.session_established = True
                self.logger.info("Clé de session établie avec succès")
            else:
                # Mode non sécurisé
                self.session_key = key
                self.session_established = True
                self.logger.warning("Clé de session définie en mode non sécurisé")
                
        except Exception as e:
            self.logger.error(f"Erreur définition clé de session: {e}")
            self.session_established = False
    
    def encrypt_data(self, data: bytes) -> Optional[bytes]:
        """Chiffre des données avec la clé de session"""
        try:
            if not self.session_established or not self.session_key:
                self.logger.error("Session non établie, impossible de chiffrer")
                return None
            
            if CRYPTO_AVAILABLE:
                fernet = Fernet(self.session_key)
                encrypted_data = fernet.encrypt(data)
                return encrypted_data
            else:
                # Mode non sécurisé - retourne les données sans chiffrement
                self.logger.warning("Données non chiffrées (crypto non disponible)")
                return data
                
        except Exception as e:
            self.logger.error(f"Erreur chiffrement: {e}")
            return None
    
    def decrypt_data(self, encrypted_data: bytes) -> Optional[bytes]:
        """Déchiffre des données avec la clé de session"""
        try:
            if not self.session_established or not self.session_key:
                self.logger.error("Session non établie, impossible de déchiffrer")
                return None
            
            if CRYPTO_AVAILABLE:
                fernet = Fernet(self.session_key)
                decrypted_data = fernet.decrypt(encrypted_data)
                return decrypted_data
            else:
                # Mode non sécurisé - retourne les données sans déchiffrement
                self.logger.warning("Données non déchiffrées (crypto non disponible)")
                return encrypted_data
                
        except Exception as e:
            self.logger.error(f"Erreur déchiffrement: {e}")
            return None
    
    def generate_signature(self, data: bytes) -> Optional[str]:
        """Génère une signature HMAC pour des données"""
        try:
            if not self.session_key:
                return None
            
            signature = hmac.new(
                self.session_key,
                data,
                hashlib.sha256
            ).hexdigest()
            
            return signature
            
        except Exception as e:
            self.logger.error(f"Erreur génération signature: {e}")
            return None
    
    def verify_signature(self, data: bytes, signature: str) -> bool:
        """Vérifie une signature HMAC"""
        try:
            if not self.session_key:
                return False
            
            expected_signature = hmac.new(
                self.session_key,
                data,
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(signature, expected_signature)
            
        except Exception as e:
            self.logger.error(f"Erreur vérification signature: {e}")
            return False
    
    def is_session_established(self) -> bool:
        """Vérifie si la session est établie"""
        return self.session_established and self.session_key is not None
    
    def reset_session(self):
        """Remet à zéro la session"""
        self.session_key = None
        self.session_established = False
        self.logger.info("Session réinitialisée")
    
    def get_security_info(self) -> dict:
        """Retourne les informations de sécurité"""
        return {
            'session_established': self.session_established,
            'crypto_available': CRYPTO_AVAILABLE,
            'has_session_key': self.session_key is not None,
            'security_mode': 'encrypted' if CRYPTO_AVAILABLE else 'unencrypted'
        }