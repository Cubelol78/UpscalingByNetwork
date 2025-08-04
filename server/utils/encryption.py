"""
Gestionnaire de sécurité et chiffrement pour le système distribué
UpscalingByNetwork/server/utils/encryption.py
"""

import secrets
import hashlib
import hmac
import json
import time
from typing import Dict, Optional, Tuple, Any
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import logging

class SecurityManager:
    """Gestionnaire de sécurité pour les communications WAN"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Clés de session par client et lot
        self.session_keys: Dict[str, Dict[str, bytes]] = {}  # {client_mac: {batch_id: key}}
        
        # Clés temporaires pour handshake
        self.temp_keys: Dict[str, Tuple[bytes, bytes]] = {}  # {client_mac: (public, private)}
        
        # Configuration
        self.key_size = 32  # AES-256
        self.session_timeout = 3600  # 1 heure
        
        # Clé maître pour dérivation
        self.master_key = self._generate_master_key()
        
        self.logger.info("Gestionnaire de sécurité initialisé")
    
    def _generate_master_key(self) -> bytes:
        """Génère une clé maître pour la session serveur"""
        return secrets.token_bytes(self.key_size)
    
    def generate_session_key(self) -> bytes:
        """Génère une nouvelle clé de session"""
        return secrets.token_bytes(self.key_size)
    
    def store_session_key(self, client_mac: str, batch_id: str, session_key: bytes):
        """Stocke une clé de session pour un client/lot"""
        if client_mac not in self.session_keys:
            self.session_keys[client_mac] = {}
        
        self.session_keys[client_mac][batch_id] = session_key
        self.logger.debug(f"Clé de session stockée pour {client_mac}/{batch_id}")
    
    def get_session_key(self, client_mac: str, batch_id: str = None) -> Optional[bytes]:
        """Récupère une clé de session"""
        if client_mac not in self.session_keys:
            return None
        
        if batch_id:
            return self.session_keys[client_mac].get(batch_id)
        else:
            # Retourne la première clé disponible pour ce client
            client_keys = self.session_keys[client_mac]
            if client_keys:
                return list(client_keys.values())[0]
        
        return None
    
    def cleanup_session_keys(self, client_mac: str, batch_id: str = None):
        """Nettoie les clés de session"""
        if client_mac in self.session_keys:
            if batch_id:
                self.session_keys[client_mac].pop(batch_id, None)
            else:
                # Supprime toutes les clés du client
                del self.session_keys[client_mac]
    
    async def handshake_with_client(self, client_mac: str, websocket) -> Optional[bytes]:
        """Effectue un handshake sécurisé avec un client"""
        try:
            # Génération d'une paire de clés RSA temporaire
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
            public_key = private_key.public_key()
            
            # Sérialisation de la clé publique
            public_pem = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            
            # Stockage temporaire
            self.temp_keys[client_mac] = (public_key, private_key)
            
            # Envoi de la clé publique au client
            handshake_init = {
                'type': 'handshake_init',
                'public_key': public_pem.decode(),
                'timestamp': time.time()
            }
            
            await websocket.send(json.dumps(handshake_init))
            self.logger.debug(f"Clé publique envoyée à {client_mac}")
            
            # Attente de la réponse du client
            response = await websocket.recv()
            response_data = json.loads(response)
            
            if response_data.get('type') != 'handshake_response':
                raise Exception("Réponse handshake invalide")
            
            # Génération et chiffrement de la clé de session
            session_key = self.generate_session_key()
            
            # Pour simplifier dans cette implémentation, on accepte la connexion
            # Dans un vrai système, on chiffrerait la clé avec RSA
            
            # Confirmation
            confirmation = {
                'type': 'handshake_complete',
                'status': 'success',
                'timestamp': time.time()
            }
            
            await websocket.send(json.dumps(confirmation))
            
            # Nettoyage des clés temporaires
            self.temp_keys.pop(client_mac, None)
            
            self.logger.info(f"Handshake complété avec {client_mac}")
            return session_key
            
        except Exception as e:
            self.logger.error(f"Erreur handshake avec {client_mac}: {e}")
            self.temp_keys.pop(client_mac, None)
            return None
    
    def encrypt_batch(self, data: bytes, session_key: bytes) -> bytes:
        """Chiffre un lot avec AES-256-CBC"""
        try:
            # Génération d'un IV aléatoire
            iv = secrets.token_bytes(16)
            
            # Padding PKCS7
            padded_data = self._pad_pkcs7(data, 16)
            
            # Chiffrement AES-256-CBC
            cipher = Cipher(
                algorithms.AES(session_key),
                modes.CBC(iv),
                backend=default_backend()
            )
            
            encryptor = cipher.encryptor()
            encrypted_data = encryptor.update(padded_data) + encryptor.finalize()
            
            # IV + données chiffrées + HMAC pour intégrité
            message = iv + encrypted_data
            mac = self._calculate_hmac(message, session_key)
            
            return message + mac
            
        except Exception as e:
            self.logger.error(f"Erreur chiffrement: {e}")
            raise
    
    def decrypt_batch(self, encrypted_data: bytes, session_key: bytes) -> bytes:
        """Déchiffre un lot"""
        try:
            # Vérification de la taille minimale
            if len(encrypted_data) < 48:  # 16 (IV) + 16 (min data) + 16 (HMAC)
                raise ValueError("Données chiffrées trop courtes")
            
            # Extraction des composants
            mac = encrypted_data[-32:]  # 32 bytes pour HMAC-SHA256
            message = encrypted_data[:-32]
            iv = message[:16]
            ciphertext = message[16:]
            
            # Vérification de l'intégrité
            expected_mac = self._calculate_hmac(message, session_key)
            if not hmac.compare_digest(mac, expected_mac):
                raise ValueError("Intégrité des données compromise")
            
            # Déchiffrement
            cipher = Cipher(
                algorithms.AES(session_key),
                modes.CBC(iv),
                backend=default_backend()
            )
            
            decryptor = cipher.decryptor()
            padded_data = decryptor.update(ciphertext) + decryptor.finalize()
            
            # Suppression du padding
            return self._unpad_pkcs7(padded_data)
            
        except Exception as e:
            self.logger.error(f"Erreur déchiffrement: {e}")
            raise
    
    def _pad_pkcs7(self, data: bytes, block_size: int) -> bytes:
        """Applique le padding PKCS7"""
        padding_length = block_size - (len(data) % block_size)
        padding = bytes([padding_length] * padding_length)
        return data + padding
    
    def _unpad_pkcs7(self, padded_data: bytes) -> bytes:
        """Supprime le padding PKCS7"""
        if not padded_data:
            raise ValueError("Données vides")
        
        padding_length = padded_data[-1]
        
        if padding_length == 0 or padding_length > 16:
            raise ValueError("Padding invalide")
        
        # Vérification du padding
        for i in range(padding_length):
            if padded_data[-(i + 1)] != padding_length:
                raise ValueError("Padding PKCS7 invalide")
        
        return padded_data[:-padding_length]
    
    def _calculate_hmac(self, data: bytes, key: bytes) -> bytes:
        """Calcule un HMAC-SHA256"""
        return hmac.new(key, data, hashlib.sha256).digest()
    
    def generate_auth_token(self, client_mac: str, validity_seconds: int = 3600) -> str:
        """Génère un token d'authentification"""
        expiry = time.time() + validity_seconds
        payload = {
            'client_mac': client_mac,
            'expiry': expiry,
            'nonce': secrets.token_hex(16)
        }
        
        payload_json = json.dumps(payload, sort_keys=True)
        payload_bytes = payload_json.encode()
        
        # Signature avec la clé maître
        signature = self._calculate_hmac(payload_bytes, self.master_key)
        
        # Encodage base64 sûr pour URL
        import base64
        token_data = payload_bytes + signature
        return base64.urlsafe_b64encode(token_data).decode()
    
    def verify_auth_token(self, token: str, client_mac: str) -> bool:
        """Vérifie un token d'authentification"""
        try:
            import base64
            token_data = base64.urlsafe_b64decode(token.encode())
            
            # Séparation payload et signature
            payload_bytes = token_data[:-32]
            signature = token_data[-32:]
            
            # Vérification de la signature
            expected_signature = self._calculate_hmac(payload_bytes, self.master_key)
            if not hmac.compare_digest(signature, expected_signature):
                return False
            
            # Vérification du contenu
            payload = json.loads(payload_bytes.decode())
            
            if payload.get('client_mac') != client_mac:
                return False
            
            if payload.get('expiry', 0) < time.time():
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur vérification token: {e}")
            return False
    
    def secure_compare(self, a: bytes, b: bytes) -> bool:
        """Comparaison sécurisée contre les attaques temporelles"""
        return hmac.compare_digest(a, b)
    
    def hash_password(self, password: str, salt: bytes = None) -> Tuple[bytes, bytes]:
        """Hash sécurisé d'un mot de passe avec PBKDF2"""
        if salt is None:
            salt = secrets.token_bytes(32)
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        
        key = kdf.derive(password.encode())
        return key, salt
    
    def verify_password(self, password: str, hashed: bytes, salt: bytes) -> bool:
        """Vérifie un mot de passe"""
        try:
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
                backend=default_backend()
            )
            
            kdf.verify(password.encode(), hashed)
            return True
        except Exception:
            return False
    
    def get_security_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de sécurité"""
        total_keys = sum(len(keys) for keys in self.session_keys.values())
        
        return {
            'connected_clients': len(self.session_keys),
            'active_session_keys': total_keys,
            'temp_handshakes': len(self.temp_keys),
            'key_size_bits': self.key_size * 8,
            'session_timeout': self.session_timeout
        }
    
    def cleanup_expired_sessions(self):
        """Nettoie les sessions expirées (à appeler périodiquement)"""
        # Implémentation simplifiée - dans un vrai système,
        # on devrait tracker les timestamps des clés
        pass