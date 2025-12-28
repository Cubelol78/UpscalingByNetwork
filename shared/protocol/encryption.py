"""
Système de chiffrement et de handshake sécurisé
Utilise Diffie-Hellman pour l'échange de clés et AES pour le chiffrement
"""

import os
import base64
import hashlib
from typing import Tuple, Optional
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import dh
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

# Paramètres DH pré-générés (RFC 3526 - Group 14, 2048 bits)
# Ceci évite les problèmes de permission sur Windows et accélère l'initialisation
RFC3526_PRIME_2048 = int(
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD1"
    "29024E088A67CC74020BBEA63B139B22514A08798E3404DD"
    "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245"
    "E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3D"
    "C2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
    "83655D23DCA3AD961C62F356208552BB9ED529077096966D"
    "670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
    "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9"
    "DE2BCBF6955817183995497CEA956AE515D2261898FA0510"
    "15728E5A8AACAA68FFFFFFFFFFFFFFFF", 16
)
RFC3526_GENERATOR = 2


class EncryptionHandler:
    """Gestionnaire de chiffrement avec échange de clés Diffie-Hellman"""

    # Paramètres DH standards (RFC 3526 - 2048 bits)
    DH_PARAMETERS = None

    def __init__(self):
        """Initialise le gestionnaire de chiffrement"""
        self.PrivateKey = None
        self.PublicKey = None
        self.SharedKey = None
        self.AesKey = None

        # Utilise les paramètres DH pré-générés (RFC 3526)
        if EncryptionHandler.DH_PARAMETERS is None:
            ParameterNumbers = dh.DHParameterNumbers(
                p=RFC3526_PRIME_2048,
                g=RFC3526_GENERATOR
            )
            EncryptionHandler.DH_PARAMETERS = ParameterNumbers.parameters(default_backend())

    def GenerateKeyPair(self) -> bytes:
        """
        Génère une paire de clés DH (privée + publique)

        Returns:
            Clé publique en bytes
        """
        # Génère la clé privée
        self.PrivateKey = EncryptionHandler.DH_PARAMETERS.generate_private_key()

        # Extrait la clé publique
        self.PublicKey = self.PrivateKey.public_key()

        # Sérialise la clé publique pour l'envoi
        PublicKeyBytes = self.PublicKey.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        return PublicKeyBytes

    def ComputeSharedKey(self, PeerPublicKeyBytes: bytes) -> bool:
        """
        Calcule la clé partagée à partir de la clé publique du pair

        Args:
            PeerPublicKeyBytes: Clé publique du pair en bytes

        Returns:
            True si succès, False sinon
        """
        try:
            # Désérialise la clé publique du pair
            PeerPublicKey = serialization.load_pem_public_key(
                PeerPublicKeyBytes,
                backend=default_backend()
            )

            # Calcule la clé partagée
            self.SharedKey = self.PrivateKey.exchange(PeerPublicKey)

            # Dérive une clé AES de 256 bits depuis la clé partagée
            self.AesKey = HKDF(
                algorithm=hashes.SHA256(),
                length=32,  # 256 bits
                salt=None,
                info=b'upscaling-network',
                backend=default_backend()
            ).derive(self.SharedKey)

            return True

        except Exception as e:
            print(f"Erreur lors du calcul de la clé partagée: {e}")
            return False

    def Encrypt(self, PlainText: bytes) -> bytes:
        """
        Chiffre des données avec AES-256-GCM

        Args:
            PlainText: Données à chiffrer

        Returns:
            Données chiffrées (IV + ciphertext + tag)
        """
        if self.AesKey is None:
            raise ValueError("Clé AES non initialisée. Effectuez d'abord le handshake.")

        # Génère un IV aléatoire (12 bytes pour GCM)
        Iv = os.urandom(12)

        # Crée le cipher AES-GCM
        Cipher_obj = Cipher(
            algorithms.AES(self.AesKey),
            modes.GCM(Iv),
            backend=default_backend()
        )

        # Chiffre
        Encryptor = Cipher_obj.encryptor()
        CipherText = Encryptor.update(PlainText) + Encryptor.finalize()

        # Récupère le tag d'authentification
        Tag = Encryptor.tag

        # Retourne IV + CipherText + Tag
        return Iv + CipherText + Tag

    def Decrypt(self, EncryptedData: bytes) -> Optional[bytes]:
        """
        Déchiffre des données avec AES-256-GCM

        Args:
            EncryptedData: Données chiffrées (IV + ciphertext + tag)

        Returns:
            Données déchiffrées ou None si erreur
        """
        if self.AesKey is None:
            raise ValueError("Clé AES non initialisée. Effectuez d'abord le handshake.")

        try:
            # Extrait IV (12 bytes), tag (16 bytes) et ciphertext
            Iv = EncryptedData[:12]
            Tag = EncryptedData[-16:]
            CipherText = EncryptedData[12:-16]

            # Crée le cipher AES-GCM
            Cipher_obj = Cipher(
                algorithms.AES(self.AesKey),
                modes.GCM(Iv, Tag),
                backend=default_backend()
            )

            # Déchiffre
            Decryptor = Cipher_obj.decryptor()
            PlainText = Decryptor.update(CipherText) + Decryptor.finalize()

            return PlainText

        except Exception as e:
            print(f"Erreur lors du déchiffrement: {e}")
            return None

    def EncryptMessage(self, Message: str) -> str:
        """
        Chiffre un message texte

        Args:
            Message: Message en texte clair

        Returns:
            Message chiffré encodé en base64
        """
        PlainBytes = Message.encode('utf-8')
        EncryptedBytes = self.Encrypt(PlainBytes)
        return base64.b64encode(EncryptedBytes).decode('utf-8')

    def DecryptMessage(self, EncryptedMessage: str) -> Optional[str]:
        """
        Déchiffre un message texte

        Args:
            EncryptedMessage: Message chiffré encodé en base64

        Returns:
            Message en texte clair ou None si erreur
        """
        try:
            EncryptedBytes = base64.b64decode(EncryptedMessage)
            PlainBytes = self.Decrypt(EncryptedBytes)

            if PlainBytes is None:
                return None

            return PlainBytes.decode('utf-8')

        except Exception as e:
            print(f"Erreur lors du déchiffrement du message: {e}")
            return None

    def GetPublicKeyBytes(self) -> Optional[bytes]:
        """
        Récupère la clé publique en bytes

        Returns:
            Clé publique ou None si non générée
        """
        if self.PublicKey is None:
            return None

        return self.PublicKey.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

    def IsReady(self) -> bool:
        """
        Vérifie si le chiffrement est prêt à être utilisé

        Returns:
            True si la clé AES est initialisée
        """
        return self.AesKey is not None


class PasswordHasher:
    """Gestionnaire de hashage de mots de passe"""

    @staticmethod
    def HashPassword(Password: str, Salt: Optional[bytes] = None) -> Tuple[str, str]:
        """
        Hash un mot de passe avec SHA-256 et un salt

        Args:
            Password: Mot de passe en clair
            Salt: Salt optionnel (généré si None)

        Returns:
            Tuple (hash_base64, salt_base64)
        """
        if Salt is None:
            Salt = os.urandom(32)

        # Hash avec SHA-256
        Hasher = hashlib.pbkdf2_hmac(
            'sha256',
            Password.encode('utf-8'),
            Salt,
            100000  # 100k itérations
        )

        HashB64 = base64.b64encode(Hasher).decode('utf-8')
        SaltB64 = base64.b64encode(Salt).decode('utf-8')

        return HashB64, SaltB64

    @staticmethod
    def VerifyPassword(Password: str, HashB64: str, SaltB64: str) -> bool:
        """
        Vérifie un mot de passe contre son hash

        Args:
            Password: Mot de passe à vérifier
            HashB64: Hash attendu (base64)
            SaltB64: Salt (base64)

        Returns:
            True si le mot de passe correspond
        """
        try:
            Salt = base64.b64decode(SaltB64)
            ExpectedHash = base64.b64decode(HashB64)

            # Recalcule le hash
            ComputedHash = hashlib.pbkdf2_hmac(
                'sha256',
                Password.encode('utf-8'),
                Salt,
                100000
            )

            # Compare de manière sécurisée (timing attack resistant)
            return hmac.compare_digest(ComputedHash, ExpectedHash)

        except Exception as e:
            print(f"Erreur lors de la vérification du mot de passe: {e}")
            return False


# Import pour compare_digest
import hmac


# ============================================================================
# HELPERS DE HANDSHAKE
# ============================================================================

def PerformHandshakeClient(EncHandler: EncryptionHandler,
                          ServerPublicKeyBytes: bytes) -> bool:
    """
    Effectue le handshake côté client

    Args:
        EncHandler: Handler de chiffrement du client
        ServerPublicKeyBytes: Clé publique reçue du serveur

    Returns:
        True si succès
    """
    # Génère la paire de clés du client
    EncHandler.GenerateKeyPair()

    # Calcule la clé partagée
    return EncHandler.ComputeSharedKey(ServerPublicKeyBytes)


def PerformHandshakeServer(EncHandler: EncryptionHandler,
                          ClientPublicKeyBytes: bytes) -> bool:
    """
    Effectue le handshake côté serveur

    Args:
        EncHandler: Handler de chiffrement du serveur
        ClientPublicKeyBytes: Clé publique reçue du client

    Returns:
        True si succès
    """
    # Génère la paire de clés du serveur
    EncHandler.GenerateKeyPair()

    # Calcule la clé partagée
    return EncHandler.ComputeSharedKey(ClientPublicKeyBytes)


# ============================================================================
# EXEMPLE D'UTILISATION
# ============================================================================

if __name__ == "__main__":
    print("=== Test du système de chiffrement ===\n")

    # Simulation d'un handshake client-serveur
    print("1. Création des handlers")
    ClientHandler = EncryptionHandler()
    ServerHandler = EncryptionHandler()

    print("2. Génération des clés publiques")
    ClientPublicKey = ClientHandler.GenerateKeyPair()
    ServerPublicKey = ServerHandler.GenerateKeyPair()

    print("3. Échange de clés et calcul des clés partagées")
    ClientSuccess = ClientHandler.ComputeSharedKey(ServerPublicKey)
    ServerSuccess = ServerHandler.ComputeSharedKey(ClientPublicKey)

    print(f"   Client handshake: {'✓' if ClientSuccess else '✗'}")
    print(f"   Server handshake: {'✓' if ServerSuccess else '✗'}")

    # Vérification que les clés partagées sont identiques
    if ClientHandler.SharedKey == ServerHandler.SharedKey:
        print("   ✓ Clés partagées identiques\n")
    else:
        print("   ✗ Erreur: clés partagées différentes\n")

    # Test de chiffrement/déchiffrement
    print("4. Test de chiffrement")
    OriginalMessage = "Ceci est un message secret de test!"
    print(f"   Message original: {OriginalMessage}")

    # Client chiffre
    EncryptedMessage = ClientHandler.EncryptMessage(OriginalMessage)
    print(f"   Message chiffré: {EncryptedMessage[:50]}...")

    # Serveur déchiffre
    DecryptedMessage = ServerHandler.DecryptMessage(EncryptedMessage)
    print(f"   Message déchiffré: {DecryptedMessage}")

    if DecryptedMessage == OriginalMessage:
        print("   ✓ Chiffrement/déchiffrement réussi\n")
    else:
        print("   ✗ Erreur de chiffrement/déchiffrement\n")

    # Test de hashage de mot de passe
    print("5. Test de hashage de mot de passe")
    Password = "MonMotDePasseSecret123"
    HashValue, SaltValue = PasswordHasher.HashPassword(Password)
    print(f"   Hash: {HashValue[:50]}...")
    print(f"   Salt: {SaltValue[:50]}...")

    # Vérification
    IsValid = PasswordHasher.VerifyPassword(Password, HashValue, SaltValue)
    print(f"   Vérification correct password: {'✓' if IsValid else '✗'}")

    IsInvalid = PasswordHasher.VerifyPassword("MauvaisMotDePasse", HashValue, SaltValue)
    print(f"   Vérification wrong password: {'✓' if not IsInvalid else '✗'}")
