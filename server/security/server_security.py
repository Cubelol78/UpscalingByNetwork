# server/security/server_security.py
"""
Module de sécurité pour le serveur d'upscaling distribué
"""

import os
import hashlib
import hmac
import time
from typing import Optional, Dict, Any, Tuple
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import logging

class ServerSecurity:
    """Gestionnaire de sécurité pour le serveur"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.session_keys: Dict[str, bytes] = {}
        self.client_sessions: Dict[str, Dict[str, Any]] = {}
        
        # Clé maître pour le serveur (à générer de manière sécurisée en production)
        self.master_key = self._generate_master_key()
        
    def _generate_master_key(self) -> bytes:
        """Génère ou charge la clé maître du serveur"""
        # En production, cette clé devrait être stockée de manière sécurisée
        # Pour le développement, on utilise une clé dérivée d'un secret
        secret = b"upscaling_server_master_key_2025"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"server_salt",
            iterations=100000,
        )
        return kdf.derive(secret)
    
    def generate_session_key(self, client_id: str) -> bytes:
        """Génère une clé de session pour un client"""
        session_key = Fernet.generate_key()
        self.session_keys[client_id] = session_key
        
        # Enregistrement de la session client
        self.client_sessions[client_id] = {
            'created_at': time.time(),
            'last_activity': time.time(),
            'key_established': True
        }
        
        self.logger.info(f"Clé de session générée pour le client {client_id}")
        return session_key
    
    def get_session_key(self, client_id: str) -> Optional[bytes]:
        """Récupère la clé de session d'un client"""
        return self.session_keys.get(client_id)
    
    def encrypt_data(self, data: bytes, client_id: str) -> Optional[bytes]:
        """Chiffre des données pour un client spécifique"""
        try:
            session_key = self.get_session_key(client_id)
            if not session_key:
                self.logger.error(f"Clé de session non trouvée pour le client {client_id}")
                return None
            
            fernet = Fernet(session_key)
            encrypted_data = fernet.encrypt(data)
            
            # Mise à jour de la dernière activité
            if client_id in self.client_sessions:
                self.client_sessions[client_id]['last_activity'] = time.time()
            
            return encrypted_data
            
        except Exception as e:
            self.logger.error(f"Erreur chiffrement pour {client_id}: {e}")
            return None
    
    def decrypt_data(self, encrypted_data: bytes, client_id: str) -> Optional[bytes]:
        """Déchiffre des données d'un client spécifique"""
        try:
            session_key = self.get_session_key(client_id)
            if not session_key:
                self.logger.error(f"Clé de session non trouvée pour le client {client_id}")
                return None
            
            fernet = Fernet(session_key)
            decrypted_data = fernet.decrypt(encrypted_data)
            
            # Mise à jour de la dernière activité
            if client_id in self.client_sessions:
                self.client_sessions[client_id]['last_activity'] = time.time()
            
            return decrypted_data
            
        except Exception as e:
            self.logger.error(f"Erreur déchiffrement pour {client_id}: {e}")
            return None
    
    def validate_client_signature(self, data: bytes, signature: str, client_id: str) -> bool:
        """Valide la signature d'un client"""
        try:
            session_key = self.get_session_key(client_id)
            if not session_key:
                return False
            
            expected_signature = hmac.new(
                session_key,
                data,
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(signature, expected_signature)
            
        except Exception as e:
            self.logger.error(f"Erreur validation signature pour {client_id}: {e}")
            return False
    
    def generate_client_signature(self, data: bytes, client_id: str) -> Optional[str]:
        """Génère une signature pour des données à envoyer au client"""
        try:
            session_key = self.get_session_key(client_id)
            if not session_key:
                return None
            
            signature = hmac.new(
                session_key,
                data,
                hashlib.sha256
            ).hexdigest()
            
            return signature
            
        except Exception as e:
            self.logger.error(f"Erreur génération signature pour {client_id}: {e}")
            return None
    
    def cleanup_expired_sessions(self, max_age_seconds: int = 3600):
        """Nettoie les sessions expirées"""
        current_time = time.time()
        expired_clients = []
        
        for client_id, session_info in self.client_sessions.items():
            if current_time - session_info['last_activity'] > max_age_seconds:
                expired_clients.append(client_id)
        
        for client_id in expired_clients:
            self.remove_client_session(client_id)
            self.logger.info(f"Session expirée supprimée pour le client {client_id}")
    
    def remove_client_session(self, client_id: str):
        """Supprime la session d'un client"""
        self.session_keys.pop(client_id, None)
        self.client_sessions.pop(client_id, None)
        self.logger.info(f"Session supprimée pour le client {client_id}")
    
    def get_session_info(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Récupère les informations de session d'un client"""
        return self.client_sessions.get(client_id)
    
    def is_session_valid(self, client_id: str) -> bool:
        """Vérifie si la session d'un client est valide"""
        return (
            client_id in self.session_keys and
            client_id in self.client_sessions and
            self.client_sessions[client_id].get('key_established', False)
        )
    
    def get_security_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de sécurité"""
        current_time = time.time()
        active_sessions = 0
        
        for session_info in self.client_sessions.values():
            if current_time - session_info['last_activity'] < 300:  # 5 minutes
                active_sessions += 1
        
        return {
            'total_sessions': len(self.client_sessions),
            'active_sessions': active_sessions,
            'session_keys_count': len(self.session_keys),
            'master_key_loaded': self.master_key is not None
        }