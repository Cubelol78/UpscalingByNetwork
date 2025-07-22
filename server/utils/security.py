# utils/security.py
import secrets
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from utils.logger import get_logger

class SecurityManager:
    """Gestionnaire de sécurité pour le chiffrement des données"""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        self._fernet = None
        self._key = None
    
    def generate_key(self) -> bytes:
        """Génère une nouvelle clé de chiffrement"""
        return Fernet.generate_key()
    
    def set_key(self, key: bytes):
        """Définit la clé de chiffrement"""
        self._key = key
        self._fernet = Fernet(key)
    
    def derive_key_from_password(self, password: str, salt: bytes = None) -> bytes:
        """Dérive une clé à partir d'un mot de passe"""
        if salt is None:
            salt = secrets.token_bytes(16)
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key
    
    def encrypt_data(self, data: bytes) -> bytes:
        """Chiffre des données"""
        if not self._fernet:
            raise ValueError("Clé de chiffrement non définie")
        return self._fernet.encrypt(data)
    
    def decrypt_data(self, encrypted_data: bytes) -> bytes:
        """Déchiffre des données"""
        if not self._fernet:
            raise ValueError("Clé de chiffrement non définie")
        return self._fernet.decrypt(encrypted_data)
    
    def encrypt_json(self, data: dict) -> str:
        """Chiffre un objet JSON"""
        import json
        json_str = json.dumps(data)
        encrypted = self.encrypt_data(json_str.encode())
        return base64.urlsafe_b64encode(encrypted).decode()
    
    def decrypt_json(self, encrypted_str: str) -> dict:
        """Déchiffre un objet JSON"""
        import json
        encrypted_data = base64.urlsafe_b64decode(encrypted_str.encode())
        decrypted = self.decrypt_data(encrypted_data)
        return json.loads(decrypted.decode())
    
    def generate_token(self, length: int = 32) -> str:
        """Génère un token aléatoire"""
        return secrets.token_urlsafe(length)
    
    def hash_password(self, password: str) -> str:
        """Hash un mot de passe avec salt"""
        import bcrypt
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    def verify_password(self, password: str, hashed: str) -> bool:
        """Vérifie un mot de passe contre son hash"""
        import bcrypt
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

# Gestionnaire de sécurité global
security_manager = SecurityManager()