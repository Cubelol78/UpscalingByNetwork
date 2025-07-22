"""
Module de sécurité pour le chiffrement des communications réseau
"""

import asyncio
import json
import base64
import hashlib
import secrets
import time
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from config.settings import config
from utils.logger import get_logger

class NetworkSecurity:
    """Gestionnaire de sécurité réseau pour les communications client-serveur"""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        
        # Clés de chiffrement
        self._server_private_key = None
        self._server_public_key = None
        self._client_symmetric_keys: Dict[str, bytes] = {}  # MAC -> Clé symétrique
        
        # Tokens d'authentification
        self._auth_tokens: Dict[str, dict] = {}  # Token -> Info client
        self._token_expiry = 3600  # 1 heure
        
        # Nonces pour éviter les attaques de rejeu
        self._used_nonces: Dict[str, float] = {}  # Nonce -> Timestamp
        self._nonce_cleanup_interval = 300  # 5 minutes
        
        # Génération des clés serveur
        self._generate_server_keys()
        
        # Démarrage du nettoyage automatique
        asyncio.create_task(self._cleanup_expired_data())
    
    def _generate_server_keys(self):
        """Génère les clés RSA du serveur"""
        try:
            self._server_private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048
            )
            self._server_public_key = self._server_private_key.public_key()
            
            self.logger.info("Clés RSA du serveur générées")
            
        except Exception as e:
            self.logger.error(f"Erreur génération clés serveur: {e}")
            raise
    
    def get_public_key_pem(self) -> str:
        """Retourne la clé publique du serveur au format PEM"""
        pem = self._server_public_key.public_key_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return pem.decode('utf-8')
    
    def generate_auth_token(self, client_mac: str, client_info: dict) -> str:
        """Génère un token d'authentification pour un client"""
        token = secrets.token_urlsafe(config.AUTH_TOKEN_LENGTH)
        
        self._auth_tokens[token] = {
            'client_mac': client_mac,
            'client_info': client_info,
            'created_at': time.time(),
            'expires_at': time.time() + self._token_expiry
        }
        
        self.logger.debug(f"Token généré pour client {client_mac}")
        return token
    
    def verify_auth_token(self, token: str) -> Optional[dict]:
        """Vérifie et retourne les informations d'un token"""
        if token not in self._auth_tokens:
            return None
        
        token_info = self._auth_tokens[token]
        
        # Vérification de l'expiration
        if time.time() > token_info['expires_at']:
            del self._auth_tokens[token]
            return None
        
        return token_info
    
    def establish_symmetric_key(self, client_mac: str, encrypted_key: str) -> bool:
        """Établit une clé symétrique avec un client"""
        try:
            # Déchiffrement de la clé symétrique avec RSA
            encrypted_key_bytes = base64.b64decode(encrypted_key)
            
            symmetric_key = self._server_private_key.decrypt(
                encrypted_key_bytes,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            
            self._client_symmetric_keys[client_mac] = symmetric_key
            self.logger.debug(f"Clé symétrique établie pour client {client_mac}")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur établissement clé symétrique: {e}")
            return False
    
    def encrypt_message(self, client_mac: str, message: dict) -> Optional[str]:
        """Chiffre un message pour un client"""
        if not config.USE_ENCRYPTION:
            return json.dumps(message)
        
        if client_mac not in self._client_symmetric_keys:
            self.logger.warning(f"Pas de clé symétrique pour client {client_mac}")
            return None
        
        try:
            # Ajout d'un nonce et timestamp
            message['_nonce'] = secrets.token_hex(16)
            message['_timestamp'] = time.time()
            
            # Sérialisation et chiffrement
            message_json = json.dumps(message)
            
            fernet = Fernet(self._client_symmetric_keys[client_mac])
            encrypted = fernet.encrypt(message_json.encode())
            
            return base64.b64encode(encrypted).decode()
            
        except Exception as e:
            self.logger.error(f"Erreur chiffrement message: {e}")
            return None
    
    def decrypt_message(self, client_mac: str, encrypted_message: str) -> Optional[dict]:
        """Déchiffre un message d'un client"""
        if not config.USE_ENCRYPTION:
            try:
                return json.loads(encrypted_message)
            except json.JSONDecodeError:
                return None
        
        if client_mac not in self._client_symmetric_keys:
            self.logger.warning(f"Pas de clé symétrique pour client {client_mac}")
            return None
        
        try:
            # Déchiffrement
            encrypted_bytes = base64.b64decode(encrypted_message)
            
            fernet = Fernet(self._client_symmetric_keys[client_mac])
            decrypted = fernet.decrypt(encrypted_bytes)
            
            message = json.loads(decrypted.decode())
            
            # Vérification du nonce (anti-rejeu)
            nonce = message.get('_nonce')
            timestamp = message.get('_timestamp', 0)
            
            if nonce:
                if nonce in self._used_nonces:
                    self.logger.warning(f"Nonce déjà utilisé: {nonce}")
                    return None
                
                # Vérification du timestamp (message pas trop ancien)
                if time.time() - timestamp > 300:  # 5 minutes max
                    self.logger.warning(f"Message trop ancien: {timestamp}")
                    return None
                
                self._used_nonces[nonce] = timestamp
            
            # Suppression des métadonnées de sécurité
            message.pop('_nonce', None)
            message.pop('_timestamp', None)
            
            return message
            
        except Exception as e:
            self.logger.error(f"Erreur déchiffrement message: {e}")
            return None
    
    def hash_data(self, data: bytes, salt: bytes = None) -> Tuple[str, bytes]:
        """Hash des données avec salt"""
        if salt is None:
            salt = secrets.token_bytes(32)
        
        digest = hashes.Hash(hashes.SHA256())
        digest.update(salt)
        digest.update(data)
        
        hash_value = digest.finalize()
        return base64.b64encode(hash_value).decode(), salt
    
    def verify_hash(self, data: bytes, hash_value: str, salt: bytes) -> bool:
        """Vérifie le hash de données"""
        try:
            expected_hash, _ = self.hash_data(data, salt)
            return secrets.compare_digest(hash_value, expected_hash)
        except Exception:
            return False
    
    def sign_data(self, data: bytes) -> str:
        """Signe des données avec la clé privée du serveur"""
        try:
            signature = self._server_private_key.sign(
                data,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            return base64.b64encode(signature).decode()
            
        except Exception as e:
            self.logger.error(f"Erreur signature données: {e}")
            return ""
    
    def create_secure_handshake(self, client_mac: str) -> dict:
        """Crée un handshake sécurisé pour un client"""
        challenge = secrets.token_bytes(32)
        timestamp = time.time()
        
        # Stockage du challenge pour vérification
        challenge_key = f"{client_mac}:{timestamp}"
        self._auth_tokens[challenge_key] = {
            'challenge': challenge,
            'timestamp': timestamp,
            'client_mac': client_mac
        }
        
        return {
            'type': 'handshake_challenge',
            'challenge': base64.b64encode(challenge).decode(),
            'timestamp': timestamp,
            'public_key': self.get_public_key_pem()
        }
    
    def verify_handshake_response(self, client_mac: str, response: dict) -> bool:
        """Vérifie la réponse de handshake d'un client"""
        try:
            challenge_response = base64.b64decode(response.get('challenge_response', ''))
            timestamp = response.get('timestamp', 0)
            client_public_key_pem = response.get('public_key', '')
            
            # Recherche du challenge
            challenge_key = f"{client_mac}:{timestamp}"
            if challenge_key not in self._auth_tokens:
                return False
            
            stored_challenge = self._auth_tokens[challenge_key]['challenge']
            
            # Chargement de la clé publique du client
            client_public_key = serialization.load_pem_public_key(
                client_public_key_pem.encode()
            )
            
            # Vérification de la signature du challenge
            try:
                client_public_key.verify(
                    challenge_response,
                    stored_challenge,
                    padding.PSS(
                        mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.MAX_LENGTH
                    ),
                    hashes.SHA256()
                )
                
                # Nettoyage du challenge utilisé
                del self._auth_tokens[challenge_key]
                
                self.logger.info(f"Handshake réussi pour client {client_mac}")
                return True
                
            except Exception as e:
                self.logger.warning(f"Échec vérification signature handshake: {e}")
                return False
                
        except Exception as e:
            self.logger.error(f"Erreur vérification handshake: {e}")
            return False
    
    def encrypt_file_chunk(self, client_mac: str, chunk_data: bytes) -> Optional[str]:
        """Chiffre un chunk de fichier pour un client"""
        if not config.USE_ENCRYPTION:
            return base64.b64encode(chunk_data).decode()
        
        if client_mac not in self._client_symmetric_keys:
            return None
        
        try:
            fernet = Fernet(self._client_symmetric_keys[client_mac])
            encrypted = fernet.encrypt(chunk_data)
            return base64.b64encode(encrypted).decode()
            
        except Exception as e:
            self.logger.error(f"Erreur chiffrement chunk: {e}")
            return None
    
    def decrypt_file_chunk(self, client_mac: str, encrypted_chunk: str) -> Optional[bytes]:
        """Déchiffre un chunk de fichier d'un client"""
        if not config.USE_ENCRYPTION:
            try:
                return base64.b64decode(encrypted_chunk)
            except Exception:
                return None
        
        if client_mac not in self._client_symmetric_keys:
            return None
        
        try:
            encrypted_bytes = base64.b64decode(encrypted_chunk)
            fernet = Fernet(self._client_symmetric_keys[client_mac])
            return fernet.decrypt(encrypted_bytes)
            
        except Exception as e:
            self.logger.error(f"Erreur déchiffrement chunk: {e}")
            return None
    
    def revoke_client_access(self, client_mac: str):
        """Révoque l'accès d'un client"""
        # Suppression de la clé symétrique
        if client_mac in self._client_symmetric_keys:
            del self._client_symmetric_keys[client_mac]
        
        # Suppression des tokens associés
        tokens_to_remove = []
        for token, info in self._auth_tokens.items():
            if info.get('client_mac') == client_mac:
                tokens_to_remove.append(token)
        
        for token in tokens_to_remove:
            del self._auth_tokens[token]
        
        self.logger.info(f"Accès révoqué pour client {client_mac}")
    
    async def _cleanup_expired_data(self):
        """Nettoie périodiquement les données expirées"""
        while True:
            try:
                current_time = time.time()
                
                # Nettoyage des tokens expirés
                expired_tokens = [
                    token for token, info in self._auth_tokens.items()
                    if info.get('expires_at', 0) < current_time
                ]
                
                for token in expired_tokens:
                    del self._auth_tokens[token]
                
                # Nettoyage des nonces anciens
                expired_nonces = [
                    nonce for nonce, timestamp in self._used_nonces.items()
                    if current_time - timestamp > self._nonce_cleanup_interval
                ]
                
                for nonce in expired_nonces:
                    del self._used_nonces[nonce]
                
                if expired_tokens or expired_nonces:
                    self.logger.debug(f"Nettoyage: {len(expired_tokens)} tokens, {len(expired_nonces)} nonces")
                
                # Attendre 5 minutes avant le prochain nettoyage
                await asyncio.sleep(300)
                
            except Exception as e:
                self.logger.error(f"Erreur nettoyage données expirées: {e}")
                await asyncio.sleep(60)
    
    def get_security_stats(self) -> dict:
        """Retourne les statistiques de sécurité"""
        return {
            'active_symmetric_keys': len(self._client_symmetric_keys),
            'active_auth_tokens': len(self._auth_tokens),
            'used_nonces': len(self._used_nonces),
            'encryption_enabled': config.USE_ENCRYPTION
        }

# Instance globale du gestionnaire de sécurité
network_security = NetworkSecurity()