# server/src/security/encryption.py
import os
import secrets
import hashlib
import base64
import logging
from typing import Dict, Optional, Tuple, bytes
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization

class EncryptionManager:
    """
    Gestionnaire de chiffrement pour sécuriser les communications WAN
    Gère les clés de session, le chiffrement des données et l'authentification
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Clés de session par client (MAC -> clé)
        self.session_keys: Dict[str, bytes] = {}
        self.session_timestamps: Dict[str, datetime] = {}
        
        # Clé maître du serveur
        self.master_key = self._generate_master_key()
        
        # Clés RSA pour l'échange initial sécurisé
        self.rsa_private_key, self.rsa_public_key = self._generate_rsa_keys()
        
        # Configuration
        self.session_timeout_hours = 24  # Renouvellement toutes les 24h
        self.max_sessions = 100  # Limite mémoire
        
        self.logger.info("Gestionnaire de chiffrement initialisé")
    
    def _generate_master_key(self) -> bytes:
        """Génère ou charge la clé maître du serveur"""
        master_key_file = "server_master.key"
        
        if os.path.exists(master_key_file):
            try:
                with open(master_key_file, 'rb') as f:
                    master_key = f.read()
                self.logger.info("Clé maître chargée depuis le fichier")
                return master_key
            except Exception as e:
                self.logger.warning(f"Erreur chargement clé maître: {e}")
        
        # Génération nouvelle clé maître
        master_key = Fernet.generate_key()
        
        try:
            with open(master_key_file, 'wb') as f:
                f.write(master_key)
            self.logger.info("Nouvelle clé maître générée et sauvegardée")
        except Exception as e:
            self.logger.warning(f"Erreur sauvegarde clé maître: {e}")
        
        return master_key
    
    def _generate_rsa_keys(self) -> Tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
        """Génère les clés RSA pour l'échange initial"""
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        public_key = private_key.public_key()
        
        self.logger.debug("Clés RSA générées pour échange sécurisé")
        return private_key, public_key
    
    def get_public_key_pem(self) -> str:
        """Retourne la clé publique RSA au format PEM pour les clients"""
        pem = self.rsa_public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return pem.decode('utf-8')
    
    def create_session_key(self, client_mac: str) -> str:
        """
        Crée une nouvelle clé de session pour un client
        
        Args:
            client_mac: Adresse MAC du client
            
        Returns:
            Clé de session encodée en base64
        """
        # Nettoyage des sessions expirées
        self._cleanup_expired_sessions()
        
        # Génération clé de session unique
        session_key = secrets.token_bytes(32)  # 256 bits
        
        # Stockage sécurisé
        self.session_keys[client_mac] = session_key
        self.session_timestamps[client_mac] = datetime.now()
        
        # Encodage pour transmission
        session_key_b64 = base64.b64encode(session_key).decode('utf-8')
        
        self.logger.info(f"Clé de session créée pour client {client_mac}")
        return session_key_b64
    
    def encrypt_session_key_for_client(self, session_key_b64: str, client_public_key_pem: str) -> str:
        """
        Chiffre la clé de session avec la clé publique du client
        
        Args:
            session_key_b64: Clé de session encodée
            client_public_key_pem: Clé publique du client au format PEM
            
        Returns:
            Clé de session chiffrée encodée en base64
        """
        try:
            # Chargement clé publique client
            client_public_key = serialization.load_pem_public_key(
                client_public_key_pem.encode('utf-8')
            )
            
            # Chiffrement de la clé de session
            session_key_bytes = base64.b64decode(session_key_b64)
            encrypted_session_key = client_public_key.encrypt(
                session_key_bytes,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            
            # Encodage pour transmission
            encrypted_b64 = base64.b64encode(encrypted_session_key).decode('utf-8')
            
            self.logger.debug("Clé de session chiffrée pour client")
            return encrypted_b64
            
        except Exception as e:
            self.logger.error(f"Erreur chiffrement clé de session: {e}")
            raise
    
    def get_session_key(self, client_mac: str) -> Optional[bytes]:
        """
        Récupère la clé de session d'un client
        
        Args:
            client_mac: Adresse MAC du client
            
        Returns:
            Clé de session ou None si inexistante/expirée
        """
        if client_mac not in self.session_keys:
            return None
        
        # Vérification expiration
        if self._is_session_expired(client_mac):
            self._remove_session(client_mac)
            return None
        
        return self.session_keys[client_mac]
    
    def encrypt_data(self, data: bytes, session_key: bytes) -> bytes:
        """
        Chiffre des données avec une clé de session
        
        Args:
            data: Données à chiffrer
            session_key: Clé de session
            
        Returns:
            Données chiffrées
        """
        try:
            # Création de l'objet Fernet avec la clé de session
            fernet_key = base64.urlsafe_b64encode(session_key)
            fernet = Fernet(fernet_key)
            
            # Chiffrement
            encrypted_data = fernet.encrypt(data)
            
            self.logger.debug(f"Données chiffrées: {len(data)} -> {len(encrypted_data)} bytes")
            return encrypted_data
            
        except Exception as e:
            self.logger.error(f"Erreur chiffrement données: {e}")
            raise
    
    def decrypt_data(self, encrypted_data: bytes, session_key: bytes) -> bytes:
        """
        Déchiffre des données avec une clé de session
        
        Args:
            encrypted_data: Données chiffrées
            session_key: Clé de session
            
        Returns:
            Données déchiffrées
        """
        try:
            # Création de l'objet Fernet avec la clé de session
            fernet_key = base64.urlsafe_b64encode(session_key)
            fernet = Fernet(fernet_key)
            
            # Déchiffrement
            decrypted_data = fernet.decrypt(encrypted_data)
            
            self.logger.debug(f"Données déchiffrées: {len(encrypted_data)} -> {len(decrypted_data)} bytes")
            return decrypted_data
            
        except Exception as e:
            self.logger.error(f"Erreur déchiffrement données: {e}")
            raise
    
    def create_data_hash(self, data: bytes) -> str:
        """
        Crée un hash SHA-256 des données pour vérification d'intégrité
        
        Args:
            data: Données à hasher
            
        Returns:
            Hash en hexadécimal
        """
        hash_object = hashlib.sha256(data)
        return hash_object.hexdigest()
    
    def verify_data_hash(self, data: bytes, expected_hash: str) -> bool:
        """
        Vérifie l'intégrité des données avec un hash
        
        Args:
            data: Données à vérifier
            expected_hash: Hash attendu
            
        Returns:
            True si l'intégrité est vérifiée
        """
        actual_hash = self.create_data_hash(data)
        return actual_hash == expected_hash
    
    def _is_session_expired(self, client_mac: str) -> bool:
        """Vérifie si une session est expirée"""
        if client_mac not in self.session_timestamps:
            return True
        
        session_time = self.session_timestamps[client_mac]
        expiry_time = session_time + timedelta(hours=self.session_timeout_hours)
        
        return datetime.now() > expiry_time
    
    def _remove_session(self, client_mac: str):
        """Supprime une session client"""
        self.session_keys.pop(client_mac, None)
        self.session_timestamps.pop(client_mac, None)
        self.logger.debug(f"Session supprimée pour client {client_mac}")
    
    def _cleanup_expired_sessions(self):
        """Nettoie les sessions expirées"""
        expired_clients = []
        
        for client_mac in list(self.session_keys.keys()):
            if self._is_session_expired(client_mac):
                expired_clients.append(client_mac)
        
        for client_mac in expired_clients:
            self._remove_session(client_mac)
        
        if expired_clients:
            self.logger.info(f"Nettoyage: {len(expired_clients)} sessions expirées supprimées")
        
        # Limitation du nombre de sessions actives
        if len(self.session_keys) > self.max_sessions:
            # Suppression des plus anciennes sessions
            sorted_sessions = sorted(
                self.session_timestamps.items(),
                key=lambda x: x[1]
            )
            
            to_remove = len(self.session_keys) - self.max_sessions + 10
            for client_mac, _ in sorted_sessions[:to_remove]:
                self._remove_session(client_mac)
            
            self.logger.warning(f"Limite de sessions atteinte, {to_remove} sessions supprimées")
    
    def get_session_stats(self) -> dict:
        """Retourne les statistiques des sessions"""
        active_sessions = len(self.session_keys)
        
        # Calcul de l'âge moyen des sessions
        if self.session_timestamps:
            now = datetime.now()
            total_age = sum(
                (now - timestamp).total_seconds() 
                for timestamp in self.session_timestamps.values()
            )
            average_age_hours = total_age / len(self.session_timestamps) / 3600
        else:
            average_age_hours = 0
        
        return {
            'active_sessions': active_sessions,
            'max_sessions': self.max_sessions,
            'average_age_hours': round(average_age_hours, 2),
            'session_timeout_hours': self.session_timeout_hours
        }

class AuthenticationManager:
    """Gestionnaire d'authentification pour les clients"""
    
    def __init__(self, encryption_manager: EncryptionManager):
        self.encryption = encryption_manager
        self.logger = logging.getLogger(__name__)
        
        # Liste blanche des clients autorisés (MAC -> info)
        self.authorized_clients: Dict[str, dict] = {}
        
        # Tokens d'authentification actifs (token -> client_mac)
        self.active_tokens: Dict[str, str] = {}
        self.token_timestamps: Dict[str, datetime] = {}
        
        # Configuration
        self.token_timeout_hours = 12
        self.max_tokens = 200
    
    def authorize_client(self, client_mac: str, client_name: str = "") -> str:
        """
        Autorise un nouveau client et génère un token d'authentification
        
        Args:
            client_mac: Adresse MAC du client
            client_name: Nom convivial du client
            
        Returns:
            Token d'authentification
        """
        # Ajout à la liste blanche
        self.authorized_clients[client_mac] = {
            'name': client_name or f"Client-{client_mac[-6:]}",
            'authorized_at': datetime.now(),
            'last_seen': datetime.now()
        }
        
        # Génération token
        auth_token = self._generate_auth_token()
        self.active_tokens[auth_token] = client_mac
        self.token_timestamps[auth_token] = datetime.now()
        
        self.logger.info(f"Client autorisé: {client_mac} ({client_name})")
        return auth_token
    
    def validate_token(self, auth_token: str) -> Optional[str]:
        """
        Valide un token d'authentification
        
        Args:
            auth_token: Token à valider
            
        Returns:
            MAC du client si token valide, None sinon
        """
        if auth_token not in self.active_tokens:
            return None
        
        # Vérification expiration
        if self._is_token_expired(auth_token):
            self._remove_token(auth_token)
            return None
        
        client_mac = self.active_tokens[auth_token]
        
        # Mise à jour dernière activité
        if client_mac in self.authorized_clients:
            self.authorized_clients[client_mac]['last_seen'] = datetime.now()
        
        return client_mac
    
    def is_client_authorized(self, client_mac: str) -> bool:
        """Vérifie si un client est autorisé"""
        return client_mac in self.authorized_clients
    
    def revoke_client(self, client_mac: str):
        """Révoque l'autorisation d'un client"""
        # Suppression de la liste blanche
        self.authorized_clients.pop(client_mac, None)
        
        # Suppression des tokens actifs
        tokens_to_remove = []
        for token, mac in self.active_tokens.items():
            if mac == client_mac:
                tokens_to_remove.append(token)
        
        for token in tokens_to_remove:
            self._remove_token(token)
        
        self.logger.info(f"Client révoqué: {client_mac}")
    
    def _generate_auth_token(self) -> str:
        """Génère un token d'authentification sécurisé"""
        return secrets.token_urlsafe(32)
    
    def _is_token_expired(self, auth_token: str) -> bool:
        """Vérifie si un token est expiré"""
        if auth_token not in self.token_timestamps:
            return True
        
        token_time = self.token_timestamps[auth_token]
        expiry_time = token_time + timedelta(hours=self.token_timeout_hours)
        
        return datetime.now() > expiry_time
    
    def _remove_token(self, auth_token: str):
        """Supprime un token"""
        self.active_tokens.pop(auth_token, None)
        self.token_timestamps.pop(auth_token, None)
    
    def cleanup_expired_tokens(self):
        """Nettoie les tokens expirés"""
        expired_tokens = []
        
        for token in list(self.active_tokens.keys()):
            if self._is_token_expired(token):
                expired_tokens.append(token)
        
        for token in expired_tokens:
            self._remove_token(token)
        
        if expired_tokens:
            self.logger.debug(f"Nettoyage: {len(expired_tokens)} tokens expirés")
    
    def get_authorized_clients(self) -> dict:
        """Retourne la liste des clients autorisés"""
        return self.authorized_clients.copy()
    
    def get_auth_stats(self) -> dict:
        """Retourne les statistiques d'authentification"""
        return {
            'authorized_clients': len(self.authorized_clients),
            'active_tokens': len(self.active_tokens),
            'max_tokens': self.max_tokens,
            'token_timeout_hours': self.token_timeout_hours
        }