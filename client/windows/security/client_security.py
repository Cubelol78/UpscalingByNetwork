# client/windows/security/client_security.py
"""
Gestionnaire de sécurité pour le client
Gère le chiffrement, déchiffrement et échange de clés
"""

import os
import hashlib
import secrets
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import base64
import logging
from typing import Optional, Tuple, bytes as Bytes

class ClientSecurity:
    """
    Gestionnaire de sécurité côté client
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Clés de session
        self.session_key = None
        self.fernet = None
        
        # Clés RSA pour l'échange initial
        self.private_key = None
        self.public_key = None
        self.server_public_key = None
        
        # État de la sécurité
        self.security_initialized = False
        self.session_established = False
        
        self._generate_rsa_keys()
        
        self.logger.info("Gestionnaire de sécurité client initialisé")
    
    def _generate_rsa_keys(self):
        """Génère une paire de clés RSA pour l'échange de clés"""
        try:
            self.private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
            self.public_key = self.private_key.public_key()
            self.security_initialized = True
            
            self.logger.info("Clés RSA générées avec succès")
            
        except Exception as e:
            self.logger.error(f"Erreur génération clés RSA: {e}")
            raise
    
    def get_public_key_pem(self) -> str:
        """Retourne la clé publique au format PEM"""
        if not self.public_key:
            raise Exception("Clés RSA non initialisées")
        
        pem = self.public_key.public_key_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        return pem.decode('utf-8')
    
    def set_server_public_key(self, server_public_key_pem: str):
        """Définit la clé publique du serveur"""
        try:
            self.server_public_key = serialization.load_pem_public_key(
                server_public_key_pem.encode('utf-8'),
                backend=default_backend()
            )
            self.logger.info("Clé publique serveur configurée")
            
        except Exception as e:
            self.logger.error(f"Erreur configuration clé publique serveur: {e}")
            raise
    
    def decrypt_session_key(self, encrypted_session_key: Bytes) -> bool:
        """
        Déchiffre la clé de session envoyée par le serveur
        
        Args:
            encrypted_session_key: Clé de session chiffrée avec notre clé publique
            
        Returns:
            True si le déchiffrement a réussi
        """
        try:
            if not self.private_key:
                raise Exception("Clé privée non disponible")
            
            # Déchiffrement de la clé de session
            decrypted_key = self.private_key.decrypt(
                encrypted_session_key,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            
            # Configuration de Fernet avec la clé de session
            self.session_key = decrypted_key
            self.fernet = Fernet(base64.urlsafe_b64encode(self.session_key[:32]))
            self.session_established = True
            
            self.logger.info("Clé de session établie avec succès")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur déchiffrement clé de session: {e}")
            return False
    
    def encrypt_data(self, data: Bytes) -> Optional[Bytes]:
        """
        Chiffre des données avec la clé de session
        
        Args:
            data: Données à chiffrer
            
        Returns:
            Données chiffrées ou None en cas d'erreur
        """
        if not self.session_established or not self.fernet:
            self.logger.error("Session de sécurité non établie")
            return None
        
        try:
            encrypted_data = self.fernet.encrypt(data)
            return encrypted_data
            
        except Exception as e:
            self.logger.error(f"Erreur chiffrement données: {e}")
            return None
    
    def decrypt_data(self, encrypted_data: Bytes) -> Optional[Bytes]:
        """
        Déchiffre des données avec la clé de session
        
        Args:
            encrypted_data: Données chiffrées
            
        Returns:
            Données déchiffrées ou None en cas d'erreur
        """
        if not self.session_established or not self.fernet:
            self.logger.error("Session de sécurité non établie")
            return None
        
        try:
            decrypted_data = self.fernet.decrypt(encrypted_data)
            return decrypted_data
            
        except Exception as e:
            self.logger.error(f"Erreur déchiffrement données: {e}")
            return None
    
    def encrypt_file(self, file_path: str, output_path: str) -> bool:
        """
        Chiffre un fichier
        
        Args:
            file_path: Chemin du fichier source
            output_path: Chemin du fichier chiffré
            
        Returns:
            True si le chiffrement a réussi
        """
        try:
            with open(file_path, 'rb') as input_file:
                file_data = input_file.read()
            
            encrypted_data = self.encrypt_data(file_data)
            if encrypted_data is None:
                return False
            
            with open(output_path, 'wb') as output_file:
                output_file.write(encrypted_data)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur chiffrement fichier {file_path}: {e}")
            return False
    
    def decrypt_file(self, encrypted_file_path: str, output_path: str) -> bool:
        """
        Déchiffre un fichier
        
        Args:
            encrypted_file_path: Chemin du fichier chiffré
            output_path: Chemin du fichier déchiffré
            
        Returns:
            True si le déchiffrement a réussi
        """
        try:
            with open(encrypted_file_path, 'rb') as input_file:
                encrypted_data = input_file.read()
            
            decrypted_data = self.decrypt_data(encrypted_data)
            if decrypted_data is None:
                return False
            
            with open(output_path, 'wb') as output_file:
                output_file.write(decrypted_data)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur déchiffrement fichier {encrypted_file_path}: {e}")
            return False
    
    def generate_client_id(self) -> str:
        """Génère un identifiant unique pour ce client"""
        # Utilisation de l'adresse MAC + timestamp + random
        import uuid
        import time
        
        mac = uuid.getnode()
        timestamp = int(time.time())
        random_part = secrets.randbits(64)
        
        client_data = f"{mac}-{timestamp}-{random_part}".encode('utf-8')
        client_id = hashlib.sha256(client_data).hexdigest()[:16]
        
        return client_id
    
    def verify_data_integrity(self, data: Bytes, expected_hash: str) -> bool:
        """
        Vérifie l'intégrité des données avec un hash
        
        Args:
            data: Données à vérifier
            expected_hash: Hash attendu (SHA256)
            
        Returns:
            True si l'intégrité est vérifiée
        """
        try:
            actual_hash = hashlib.sha256(data).hexdigest()
            return actual_hash == expected_hash
            
        except Exception as e:
            self.logger.error(f"Erreur vérification intégrité: {e}")
            return False
    
    def reset_session(self):
        """Remet à zéro la session de sécurité"""
        self.session_key = None
        self.fernet = None
        self.session_established = False
        self.server_public_key = None
        
        # Régénération des clés RSA
        self._generate_rsa_keys()
        
        self.logger.info("Session de sécurité réinitialisée")
    
    def is_ready(self) -> bool:
        """Vérifie si la sécurité est prête pour les opérations"""
        return (self.security_initialized and 
                self.session_established and 
                self.fernet is not None)