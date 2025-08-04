# UpscalingByNetwork/shared/protocol/encryption_protocol.py

import json
import secrets


class SecurityManager:
    """Gestionnaire de sécurité pour les communications WAN"""
    
    def __init__(self):
        self.session_keys = {}  # MAC -> clé de session
        self.master_key = self.generate_master_key()
    
    async def handshake_with_client(self, client_mac: str, websocket):
        """Établit une session sécurisée avec un client"""
        
        # 1. Génération clé de session
        session_key = secrets.token_bytes(32)
        
        # 2. Chiffrement de la clé avec RSA temporaire
        public_key, private_key = self.generate_rsa_keypair()
        
        # 3. Envoi de la clé publique
        await websocket.send(json.dumps({
            'type': 'handshake_init',
            'public_key': public_key.export_key().decode()
        }))
        
        # 4. Réception de la clé de session chiffrée
        response = await websocket.recv()
        encrypted_session_key = json.loads(response)['encrypted_key']
        
        # 5. Stockage de la clé de session
        self.session_keys[client_mac] = session_key
        
        return session_key
    
    def encrypt_batch(self, zip_path: str, session_key: bytes) -> bytes:
        """Chiffre un lot avec AES-256"""
        
        # Lecture du fichier ZIP
        with open(zip_path, 'rb') as f:
            data = f.read()
        
        # Chiffrement AES-256-CBC
        cipher = AES.new(session_key, AES.MODE_CBC)
        iv = cipher.iv
        
        # Padding PKCS7
        padded_data = self.pad_data(data)
        encrypted_data = cipher.encrypt(padded_data)
        
        # IV + données chiffrées
        return iv + encrypted_data
    
    def decrypt_batch(self, encrypted_data: bytes, session_key: bytes) -> bytes:
        """Déchiffre un lot"""
        
        # Extraction IV et données
        iv = encrypted_data[:16]
        encrypted = encrypted_data[16:]
        
        # Déchiffrement
        cipher = AES.new(session_key, AES.MODE_CBC, iv)
        padded_data = cipher.decrypt(encrypted)
        
        # Suppression du padding
        return self.unpad_data(padded_data)