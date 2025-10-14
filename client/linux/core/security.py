"""
Security module for client-server communication
Handles encryption/decryption and session management
"""

import logging
import base64
from typing import Optional

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, padding

    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


class ClientSecurity:
    """Handle encryption and security"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        if not CRYPTO_AVAILABLE:
            self.logger.warning("Cryptography not available - insecure mode")

        # Keys
        self.session_key: Optional[bytes] = None
        self.private_key = None
        self.public_key = None
        self.server_public_key = None

        # State
        self.session_established = False

        if CRYPTO_AVAILABLE:
            self._generate_key_pair()

    def _generate_key_pair(self):
        """Generate RSA key pair"""
        try:
            self.private_key = rsa.generate_private_key(
                public_exponent=65537, key_size=2048
            )
            self.public_key = self.private_key.public_key()
            self.logger.info("Generated RSA key pair")
        except Exception as e:
            self.logger.error(f"Error generating key pair: {e}")

    def get_public_key_pem(self) -> str:
        """Get public key as PEM string"""
        if not CRYPTO_AVAILABLE or not self.public_key:
            return ""

        try:
            pem = self.public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            return pem.decode("utf-8")
        except Exception as e:
            self.logger.error(f"Error exporting public key: {e}")
            return ""

    def set_server_public_key(self, pem_data: str):
        """Set server's public key"""
        if not CRYPTO_AVAILABLE:
            return

        try:
            self.server_public_key = serialization.load_pem_public_key(
                pem_data.encode("utf-8")
            )
            self.logger.info("Server public key set")
        except Exception as e:
            self.logger.error(f"Error setting server public key: {e}")

    def decrypt_session_key(self, encrypted_key: bytes) -> bool:
        """Decrypt session key from server"""
        if not CRYPTO_AVAILABLE or not self.private_key:
            return False

        try:
            self.session_key = self.private_key.decrypt(
                encrypted_key,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )
            self.session_established = True
            self.logger.info("Session key decrypted")
            return True
        except Exception as e:
            self.logger.error(f"Error decrypting session key: {e}")
            return False

    def set_session_key(self, key: bytes):
        """Set session key directly"""
        try:
            if CRYPTO_AVAILABLE:
                Fernet(key)  # Validate key
            self.session_key = key
            self.session_established = True
            self.logger.info("Session key set")
        except Exception as e:
            self.logger.error(f"Invalid session key: {e}")
            self.session_established = False

    def encrypt_data(self, data: bytes) -> Optional[bytes]:
        """Encrypt data with session key"""
        if not self.session_established or not self.session_key:
            self.logger.error("No session key")
            return None

        if not CRYPTO_AVAILABLE:
            return data  # Insecure mode

        try:
            fernet = Fernet(self.session_key)
            return fernet.encrypt(data)
        except Exception as e:
            self.logger.error(f"Encryption error: {e}")
            return None

    def decrypt_data(self, encrypted_data: bytes) -> Optional[bytes]:
        """Decrypt data with session key"""
        if not self.session_established or not self.session_key:
            self.logger.error("No session key")
            return None

        if not CRYPTO_AVAILABLE:
            return encrypted_data  # Insecure mode

        try:
            fernet = Fernet(self.session_key)
            return fernet.decrypt(encrypted_data)
        except Exception as e:
            self.logger.error(f"Decryption error: {e}")
            return None

    def is_ready(self) -> bool:
        """Check if security is ready"""
        return self.session_established and self.session_key is not None

    def reset_session(self):
        """Reset session"""
        self.session_key = None
        self.session_established = False
        self.logger.info("Session reset")
