# UpscalingByNetwork/server/utils/encryption_manager.py
"""
Gestionnaire de chiffrement pour les communications sécurisées WAN
Implémente AES-256-CBC avec handshake RSA et validation HMAC
"""

import os
import hashlib
import hmac
import logging
from pathlib import Path
from typing import Dict, Tuple, Optional
import json
import time

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes, serialization, padding as crypto_padding
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key

class EncryptionManager:
    """Gestionnaire central du chiffrement pour le serveur"""
    
    def __init__(self, keys_dir: Path):
        self.logger = logging.getLogger(__name__)
        self.keys_dir = Path(keys_dir)
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        
        # Clés RSA du serveur (pour handshake)
        self.server_private_key = None
        self.server_public_key = None
        
        # Sessions actives avec clés AES
        self.active_sessions: Dict[str, 'SessionManager'] = {}
        
        # Configuration
        self.rsa_key_size = 2048
        self.aes_key_size = 32  # AES-256
        self.iv_size = 16  # 128 bits
        self.hmac_key_size = 32  # SHA-256
        
        # Initialisation
        self.initialize_server_keys()
        
        self.logger.info("Gestionnaire de chiffrement initialisé")
    
    def initialize_server_keys(self):
        """Initialise les clés RSA du serveur"""
        private_key_path = self.keys_dir / "server_private.pem"
        public_key_path = self.keys_dir / "server_public.pem"
        
        try:
            if private_key_path.exists() and public_key_path.exists():
                # Charger les clés existantes
                with open(private_key_path, 'rb') as f:
                    self.server_private_key = load_pem_private_key(
                        f.read(), password=None, backend=default_backend()
                    )
                
                with open(public_key_path, 'rb') as f:
                    self.server_public_key = load_pem_public_key(
                        f.read(), backend=default_backend()
                    )
                
                self.logger.info("Clés serveur RSA chargées")
                
            else:
                # Générer de nouvelles clés
                self.generate_server_keys()
                
        except Exception as e:
            self.logger.error(f"Erreur initialisation clés serveur: {e}")
            self.generate_server_keys()
    
    def generate_server_keys(self):
        """Génère de nouvelles clés RSA pour le serveur"""
        try:
            # Génération de la clé privée
            self.server_private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=self.rsa_key_size,
                backend=default_backend()
            )
            
            self.server_public_key = self.server_private_key.public_key()
            
            # Sauvegarde des clés
            private_key_path = self.keys_dir / "server_private.pem"
            public_key_path = self.keys_dir / "server_public.pem"
            
            # Clé privée
            with open(private_key_path, 'wb') as f:
                f.write(self.server_private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                ))
            
            # Clé publique
            with open(public_key_path, 'wb') as f:
                f.write(self.server_public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo
                ))
            
            # Permissions restrictives
            os.chmod(private_key_path, 0o600)
            os.chmod(public_key_path, 0o644)
            
            self.logger.info("Nouvelles clés serveur RSA générées")
            
        except Exception as e:
            self.logger.error(f"Erreur génération clés serveur: {e}")
            raise
    
    def get_server_public_key_pem(self) -> bytes:
        """Retourne la clé publique du serveur en format PEM"""
        return self.server_public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
    
    def create_session(self, client_mac: str) -> 'SessionManager':
        """Crée une nouvelle session de chiffrement pour un client"""
        # Supprimer l'ancienne session si elle existe
        if client_mac in self.active_sessions:
            del self.active_sessions[client_mac]
        
        # Créer une nouvelle session
        session = SessionManager(client_mac, self)
        self.active_sessions[client_mac] = session
        
        self.logger.info(f"Session de chiffrement créée pour {client_mac}")
        return session
    
    def get_session(self, client_mac: str) -> Optional['SessionManager']:
        """Récupère la session d'un client"""
        return self.active_sessions.get(client_mac)
    
    def close_session(self, client_mac: str):
        """Ferme la session d'un client"""
        if client_mac in self.active_sessions:
            del self.active_sessions[client_mac]
            self.logger.info(f"Session fermée pour {client_mac}")
    
    def decrypt_with_private_key(self, encrypted_data: bytes) -> bytes:
        """Déchiffre des données avec la clé privée RSA du serveur"""
        try:
            decrypted_data = self.server_private_key.decrypt(
                encrypted_data,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            return decrypted_data
            
        except Exception as e:
            self.logger.error(f"Erreur déchiffrement RSA: {e}")
            raise

class SessionManager:
    """Gestionnaire de session de chiffrement pour un client"""
    
    def __init__(self, client_mac: str, encryption_manager: EncryptionManager):
        self.client_mac = client_mac
        self.encryption_manager = encryption_manager
        self.logger = logging.getLogger(f"{__name__}.{client_mac}")
        
        # Clés de session
        self.aes_key = os.urandom(32)  # AES-256
        self.hmac_key = os.urandom(32)  # HMAC-SHA256
        
        # Compteurs pour prévenir les attaques de replay
        self.send_counter = 0
        self.receive_counter = 0
        
        # Timestamp de création
        self.created_at = time.time()
        self.last_used = self.created_at
        
        self.logger.debug("Session de chiffrement créée")
    
    def get_session_keys_encrypted(self, client_public_key_pem: bytes) -> bytes:
        """Retourne les clés de session chiffrées avec la clé publique du client"""
        try:
            # Charger la clé publique du client
            client_public_key = load_pem_public_key(
                client_public_key_pem, backend=default_backend()
            )
            
            # Créer le package de clés
            keys_package = {
                'aes_key': self.aes_key.hex(),
                'hmac_key': self.hmac_key.hex(),
                'timestamp': self.created_at
            }
            
            keys_json = json.dumps(keys_package).encode('utf-8')
            
            # Chiffrer avec la clé publique du client
            encrypted_keys = client_public_key.encrypt(
                keys_json,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            
            return encrypted_keys
            
        except Exception as e:
            self.logger.error(f"Erreur chiffrement clés de session: {e}")
            raise
    
    def encrypt_data(self, data: bytes) -> bytes:
        """Chiffre des données avec AES-256-CBC + HMAC"""
        try:
            # Génération d'un IV aléatoire
            iv = os.urandom(16)
            
            # Chiffrement AES
            cipher = Cipher(
                algorithms.AES(self.aes_key),
                modes.CBC(iv),
                backend=default_backend()
            )
            encryptor = cipher.encryptor()
            
            # Padding PKCS7
            padder = crypto_padding.PKCS7(128).padder()
            padded_data = padder.update(data) + padder.finalize()
            
            # Chiffrement
            ciphertext = encryptor.update(padded_data) + encryptor.finalize()
            
            # Création du message avec compteur et IV
            message = {
                'counter': self.send_counter,
                'iv': iv.hex(),
                'ciphertext': ciphertext.hex(),
                'timestamp': time.time()
            }
            
            message_bytes = json.dumps(message).encode('utf-8')
            
            # HMAC pour l'intégrité
            hmac_digest = hmac.new(
                self.hmac_key,
                message_bytes,
                hashlib.sha256
            ).hexdigest()
            
            # Package final
            final_package = {
                'message': message,
                'hmac': hmac_digest
            }
            
            # Incrémenter le compteur
            self.send_counter += 1
            self.last_used = time.time()
            
            return json.dumps(final_package).encode('utf-8')
            
        except Exception as e:
            self.logger.error(f"Erreur chiffrement données: {e}")
            raise
    
    def decrypt_data(self, encrypted_package: bytes) -> bytes:
        """Déchiffre des données AES-256-CBC + validation HMAC"""
        try:
            # Parse du package
            package_data = json.loads(encrypted_package.decode('utf-8'))
            message = package_data['message']
            received_hmac = package_data['hmac']
            
            # Validation HMAC
            message_bytes = json.dumps(message).encode('utf-8')
            calculated_hmac = hmac.new(
                self.hmac_key,
                message_bytes,
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(received_hmac, calculated_hmac):
                raise ValueError("HMAC invalide - intégrité compromise")
            
            # Validation du compteur (protection contre replay)
            counter = message['counter']
            if counter <= self.receive_counter:
                raise ValueError("Compteur invalide - possible attaque de replay")
            
            # Validation du timestamp (protection contre les anciens messages)
            timestamp = message['timestamp']
            if time.time() - timestamp > 300:  # 5 minutes
                raise ValueError("Message trop ancien")
            
            # Extraction des données
            iv = bytes.fromhex(message['iv'])
            ciphertext = bytes.fromhex(message['ciphertext'])
            
            # Déchiffrement AES
            cipher = Cipher(
                algorithms.AES(self.aes_key),
                modes.CBC(iv),
                backend=default_backend()
            )
            decryptor = cipher.decryptor()
            
            padded_data = decryptor.update(ciphertext) + decryptor.finalize()
            
            # Suppression du padding
            unpadder = crypto_padding.PKCS7(128).unpadder()
            data = unpadder.update(padded_data) + unpadder.finalize()
            
            # Mise à jour du compteur
            self.receive_counter = counter
            self.last_used = time.time()
            
            return data
            
        except Exception as e:
            self.logger.error(f"Erreur déchiffrement données: {e}")
            raise
    
    def encrypt_file(self, file_path: Path) -> bytes:
        """Chiffre un fichier complet"""
        try:
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            return self.encrypt_data(file_data)
            
        except Exception as e:
            self.logger.error(f"Erreur chiffrement fichier {file_path}: {e}")
            raise
    
    def decrypt_to_file(self, encrypted_data: bytes, output_path: Path):
        """Déchiffre des données vers un fichier"""
        try:
            decrypted_data = self.decrypt_data(encrypted_data)
            
            with open(output_path, 'wb') as f:
                f.write(decrypted_data)
                
        except Exception as e:
            self.logger.error(f"Erreur déchiffrement vers fichier {output_path}: {e}")
            raise
    
    def is_expired(self, max_age_seconds: int = 3600) -> bool:
        """Vérifie si la session a expiré"""
        return (time.time() - self.last_used) > max_age_seconds
    
    def get_session_info(self) -> dict:
        """Retourne les informations de la session"""
        return {
            'client_mac': self.client_mac,
            'created_at': self.created_at,
            'last_used': self.last_used,
            'send_counter': self.send_counter,
            'receive_counter': self.receive_counter,
            'age_seconds': time.time() - self.created_at
        }

class BatchEncryptor:
    """Utilitaire pour chiffrer/déchiffrer des lots d'images"""
    
    def __init__(self, session: SessionManager):
        self.session = session
        self.logger = logging.getLogger(__name__)
    
    def create_encrypted_batch(self, batch_dir: Path, batch_id: str) -> bytes:
        """Crée un lot chiffré à partir d'un dossier d'images"""
        import zipfile
        import tempfile
        
        try:
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_zip:
                temp_zip_path = Path(temp_zip.name)
            
            # Création du ZIP sans compression (images peu compressibles)
            with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_STORED) as zipf:
                # Métadonnées du lot
                batch_info = {
                    'batch_id': batch_id,
                    'created_at': time.time(),
                    'image_count': 0
                }
                
                # Ajout des images
                for image_path in sorted(batch_dir.glob('*.png')):
                    zipf.write(image_path, image_path.name)
                    batch_info['image_count'] += 1
                
                # Ajout des métadonnées
                zipf.writestr('batch_info.json', json.dumps(batch_info))
            
            # Chiffrement du ZIP
            encrypted_data = self.session.encrypt_file(temp_zip_path)
            
            # Nettoyage
            temp_zip_path.unlink()
            
            self.logger.info(f"Lot {batch_id} chiffré ({batch_info['image_count']} images)")
            return encrypted_data
            
        except Exception as e:
            self.logger.error(f"Erreur création lot chiffré {batch_id}: {e}")
            raise
    
    def extract_encrypted_batch(self, encrypted_data: bytes, output_dir: Path) -> dict:
        """Extrait un lot chiffré vers un dossier"""
        import zipfile
        import tempfile
        
        try:
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_zip:
                temp_zip_path = Path(temp_zip.name)
            
            # Déchiffrement vers fichier temporaire
            self.session.decrypt_to_file(encrypted_data, temp_zip_path)
            
            # Extraction du ZIP
            with zipfile.ZipFile(temp_zip_path, 'r') as zipf:
                zipf.extractall(output_dir)
                
                # Lecture des métadonnées
                batch_info_path = output_dir / 'batch_info.json'
                if batch_info_path.exists():
                    with open(batch_info_path, 'r') as f:
                        batch_info = json.load(f)
                    batch_info_path.unlink()  # Supprimer après lecture
                else:
                    batch_info = {'batch_id': 'unknown', 'image_count': 0}
            
            # Nettoyage
            temp_zip_path.unlink()
            
            self.logger.info(f"Lot {batch_info['batch_id']} extrait ({batch_info['image_count']} images)")
            return batch_info
            
        except Exception as e:
            self.logger.error(f"Erreur extraction lot chiffré: {e}")
            raise

def generate_secure_token(length: int = 32) -> str:
    """Génère un token sécurisé"""
    return os.urandom(length).hex()

def hash_mac_address(mac_address: str) -> str:
    """Hash sécurisé d'une adresse MAC pour l'identification"""
    return hashlib.sha256(mac_address.encode()).hexdigest()[:16]

def verify_file_integrity(file_path: Path, expected_hash: str) -> bool:
    """Vérifie l'intégrité d'un fichier"""
    try:
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        
        return hasher.hexdigest() == expected_hash
        
    except Exception:
        return False