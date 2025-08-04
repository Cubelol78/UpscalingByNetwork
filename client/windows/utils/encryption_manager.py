# UpscalingByNetwork/client/windows/utils/encryption_manager.py
"""
Gestionnaire de chiffrement côté client
Gère les clés, le handshake RSA et le chiffrement AES des communications
"""

import os
import hashlib
import hmac
import logging
import json
import time
from pathlib import Path
from typing import Optional, Tuple

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes, serialization, padding as crypto_padding
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key
from cryptography.hazmat.backends import default_backend

class ClientEncryptionManager:
    """Gestionnaire de chiffrement pour le client"""
    
    def __init__(self, keys_dir: Path = None):
        self.logger = logging.getLogger(__name__)
        
        # Dossier des clés (optionnel pour le client)
        self.keys_dir = keys_dir or Path("client_work/keys")
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        
        # Clés RSA du client
        self.client_private_key = None
        self.client_public_key = None
        
        # Clé de session reçue du serveur
        self.session_key = None
        self.hmac_key = None
        
        # Compteurs pour anti-replay
        self.send_counter = 0
        self.receive_counter = 0
        self.session_start_time = None
        
        # Configuration
        self.rsa_key_size = 2048
        self.session_timeout = 3600  # 1 heure
        
        # Générer les clés RSA du client
        self.generate_client_keys()
        
        self.logger.info("Gestionnaire de chiffrement client initialisé")
    
    def generate_client_keys(self):
        """Génère les clés RSA du client"""
        try:
            # Générer une nouvelle paire de clés à chaque session
            self.client_private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=self.rsa_key_size,
                backend=default_backend()
            )
            
            self.client_public_key = self.client_private_key.public_key()
            
            self.logger.debug("Clés RSA client générées")
            
        except Exception as e:
            self.logger.error(f"Erreur génération clés client: {e}")
            raise
    
    def get_public_key_pem(self) -> bytes:
        """Retourne la clé publique du client en format PEM"""
        return self.client_public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
    
    def set_session_key(self, session_key: bytes):
        """Configure la clé de session reçue du serveur"""
        try:
            # La clé de session contient AES + HMAC
            if len(session_key) == 64:  # 32 bytes AES + 32 bytes HMAC
                self.session_key = session_key[:32]  # AES-256
                self.hmac_key = session_key[32:]     # HMAC-SHA256
            else:
                # Fallback : utiliser la clé complète pour AES et dériver HMAC
                self.session_key = session_key[:32] if len(session_key) >= 32 else session_key
                self.hmac_key = hashlib.sha256(session_key + b"hmac").digest()[:32]
            
            # Réinitialiser les compteurs
            self.send_counter = 0
            self.receive_counter = 0
            self.session_start_time = time.time()
            
            self.logger.info("Clé de session configurée")
            
        except Exception as e:
            self.logger.error(f"Erreur configuration clé de session: {e}")
            raise
    
    def has_session_key(self) -> bool:
        """Vérifie si une clé de session est configurée"""
        return self.session_key is not None and self.hmac_key is not None
    
    def is_session_expired(self) -> bool:
        """Vérifie si la session a expiré"""
        if not self.session_start_time:
            return True
        
        return (time.time() - self.session_start_time) > self.session_timeout
    
    def encrypt_data(self, data: bytes) -> bytes:
        """Chiffre des données avec AES-256-CBC + HMAC"""
        if not self.has_session_key():
            raise ValueError("Aucune clé de session configurée")
        
        if self.is_session_expired():
            raise ValueError("Session expirée")
        
        try:
            # Génération d'un IV aléatoire
            iv = os.urandom(16)
            
            # Chiffrement AES
            cipher = Cipher(
                algorithms.AES(self.session_key),
                modes.CBC(iv),
                backend=default_backend()
            )
            encryptor = cipher.encryptor()
            
            # Padding PKCS7
            padder = crypto_padding.PKCS7(128).padder()
            padded_data = padder.update(data) + padder.finalize()
            
            # Chiffrement
            ciphertext = encryptor.update(padded_data) + encryptor.finalize()
            
            # Création du message avec métadonnées
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
            
            return json.dumps(final_package).encode('utf-8')
            
        except Exception as e:
            self.logger.error(f"Erreur chiffrement données: {e}")
            raise
    
    def decrypt_data(self, encrypted_package: bytes) -> bytes:
        """Déchiffre des données AES-256-CBC + validation HMAC"""
        if not self.has_session_key():
            raise ValueError("Aucune clé de session configurée")
        
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
            
            # Validation du timestamp
            timestamp = message['timestamp']
            if time.time() - timestamp > 300:  # 5 minutes max
                raise ValueError("Message trop ancien")
            
            # Extraction des données
            iv = bytes.fromhex(message['iv'])
            ciphertext = bytes.fromhex(message['ciphertext'])
            
            # Déchiffrement AES
            cipher = Cipher(
                algorithms.AES(self.session_key),
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
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'wb') as f:
                f.write(decrypted_data)
                
        except Exception as e:
            self.logger.error(f"Erreur déchiffrement vers fichier {output_path}: {e}")
            raise
    
    def create_handshake_data(self, client_info: dict) -> dict:
        """Crée les données de handshake avec la clé publique"""
        handshake_data = client_info.copy()
        handshake_data['public_key'] = self.get_public_key_pem().decode('utf-8')
        handshake_data['encryption_supported'] = True
        
        return handshake_data
    
    def process_server_handshake(self, server_response: dict) -> bool:
        """Traite la réponse de handshake du serveur"""
        try:
            if 'session_key' not in server_response:
                self.logger.warning("Pas de clé de session dans la réponse du serveur")
                return False
            
            # Décoder la clé de session
            session_key_hex = server_response['session_key']
            session_key = bytes.fromhex(session_key_hex)
            
            # Configurer la clé de session
            self.set_session_key(session_key)
            
            self.logger.info("Handshake de chiffrement réussi")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur traitement handshake serveur: {e}")
            return False
    
    def get_encryption_stats(self) -> dict:
        """Retourne les statistiques de chiffrement"""
        return {
            'session_active': self.has_session_key(),
            'session_expired': self.is_session_expired(),
            'send_counter': self.send_counter,
            'receive_counter': self.receive_counter,
            'session_age': time.time() - self.session_start_time if self.session_start_time else 0,
            'rsa_key_size': self.rsa_key_size
        }
    
    def clear_session(self):
        """Nettoie la session de chiffrement"""
        self.session_key = None
        self.hmac_key = None
        self.send_counter = 0
        self.receive_counter = 0
        self.session_start_time = None
        
        self.logger.info("Session de chiffrement nettoyée")

class BatchCrypto:
    """Utilitaires de chiffrement pour les lots"""
    
    def __init__(self, encryption_manager: ClientEncryptionManager):
        self.encryption_manager = encryption_manager
        self.logger = logging.getLogger(__name__)
    
    def decrypt_batch_package(self, encrypted_data: str, output_dir: Path) -> dict:
        """Déchiffre un package de lot reçu du serveur"""
        import base64
        import zipfile
        import tempfile
        
        try:
            # Décodage base64
            encrypted_bytes = base64.b64decode(encrypted_data)
            
            # Déchiffrement
            decrypted_data = self.encryption_manager.decrypt_data(encrypted_bytes)
            
            # Écriture vers fichier temporaire
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_file:
                temp_file.write(decrypted_data)
                temp_zip_path = Path(temp_file.name)
            
            # Extraction du ZIP
            output_dir.mkdir(parents=True, exist_ok=True)
            
            with zipfile.ZipFile(temp_zip_path, 'r') as zipf:
                zipf.extractall(output_dir)
                
                # Lecture des métadonnées si présentes
                batch_info = {}
                if 'batch_info.json' in zipf.namelist():
                    with zipf.open('batch_info.json') as f:
                        batch_info = json.loads(f.read().decode('utf-8'))
            
            # Nettoyage
            temp_zip_path.unlink()
            
            self.logger.info(f"Lot déchiffré vers {output_dir}")
            return batch_info
            
        except Exception as e:
            self.logger.error(f"Erreur déchiffrement lot: {e}")
            raise
    
    def encrypt_result_package(self, results_dir: Path, batch_id: str) -> str:
        """Chiffre un package de résultats pour envoi au serveur"""
        import base64
        import zipfile
        import tempfile
        
        try:
            # Création du ZIP avec les résultats
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_file:
                temp_zip_path = Path(temp_file.name)
            
            with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_STORED) as zipf:
                # Ajout des images traitées
                image_count = 0
                for image_path in results_dir.glob("*.png"):
                    zipf.write(image_path, image_path.name)
                    image_count += 1
                
                # Métadonnées
                metadata = {
                    'batch_id': batch_id,
                    'image_count': image_count,
                    'processed_at': time.time(),
                    'client_version': '1.0.0'
                }
                zipf.writestr('result_info.json', json.dumps(metadata))
            
            # Lecture et chiffrement
            with open(temp_zip_path, 'rb') as f:
                zip_data = f.read()
            
            encrypted_data = self.encryption_manager.encrypt_data(zip_data)
            
            # Encodage base64 pour transport
            result_package = base64.b64encode(encrypted_data).decode('utf-8')
            
            # Nettoyage
            temp_zip_path.unlink()
            
            self.logger.info(f"Résultats chiffrés pour le lot {batch_id}")
            return result_package
            
        except Exception as e:
            self.logger.error(f"Erreur chiffrement résultats: {e}")
            raise

def generate_client_id() -> str:
    """Génère un identifiant unique pour le client"""
    import uuid
    import platform
    
    # Utiliser MAC address + hostname pour un ID stable
    mac = hex(uuid.getnode())[2:]
    hostname = platform.node()
    
    # Hash pour anonymiser
    client_string = f"{mac}_{hostname}_{time.time()}"
    client_hash = hashlib.sha256(client_string.encode()).hexdigest()[:16]
    
    return f"client_{client_hash}"

def verify_message_integrity(message: dict, expected_fields: list) -> bool:
    """Vérifie l'intégrité d'un message"""
    try:
        # Vérifier la présence des champs requis
        for field in expected_fields:
            if field not in message:
                return False
        
        # Vérifier les types de base
        if 'timestamp' in message:
            timestamp = message['timestamp']
            if not isinstance(timestamp, (int, float)):
                return False
            
            # Vérifier que le timestamp n'est pas trop ancien ou futur
            now = time.time()
            if abs(now - timestamp) > 3600:  # 1 heure de tolérance
                return False
        
        return True
        
    except Exception:
        return False