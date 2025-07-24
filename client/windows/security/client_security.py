# client-windows/src/security/client_security.py
import os
import base64
import logging
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding

class ClientSecurity:
    """
    Gestionnaire de sécurité côté client
    Gère le handshake sécurisé et le chiffrement des données
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Clés du client
        self.rsa_private_key, self.rsa_public_key = self._generate_rsa_keys()
        
        # Clé de session reçue du serveur
        self.session_key: Optional[bytes] = None
        self.server_public_key: Optional[rsa.RSAPublicKey] = None
        
        self.logger.info("Sécurité client initialisée")
    
    def _generate_rsa_keys(self):
        """Génère les clés RSA du client pour l'échange initial"""
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        public_key = private_key.public_key()
        
        self.logger.debug("Clés RSA client générées")
        return private_key, public_key
    
    def get_public_key_pem(self) -> str:
        """Retourne la clé publique du client au format PEM"""
        pem = self.rsa_public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return pem.decode('utf-8')
    
    def set_server_public_key(self, server_public_key_pem: str) -> bool:
        """
        Définit la clé publique du serveur
        
        Args:
            server_public_key_pem: Clé publique du serveur au format PEM
            
        Returns:
            True si la clé a été chargée avec succès
        """
        try:
            self.server_public_key = serialization.load_pem_public_key(
                server_public_key_pem.encode('utf-8')
            )
            self.logger.debug("Clé publique serveur chargée")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur chargement clé publique serveur: {e}")
            return False
    
    def decrypt_session_key(self, encrypted_session_key_b64: str) -> bool:
        """
        Déchiffre la clé de session reçue du serveur
        
        Args:
            encrypted_session_key_b64: Clé de session chiffrée en base64
            
        Returns:
            True si le déchiffrement a réussi
        """
        try:
            # Décodage base64
            encrypted_session_key = base64.b64decode(encrypted_session_key_b64)
            
            # Déchiffrement avec la clé privée du client
            session_key = self.rsa_private_key.decrypt(
                encrypted_session_key,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            
            self.session_key = session_key
            self.logger.info("Clé de session déchiffrée et stockée")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur déchiffrement clé de session: {e}")
            return False
    
    def get_session_key(self) -> Optional[bytes]:
        """Retourne la clé de session actuelle"""
        return self.session_key
    
    def has_session_key(self) -> bool:
        """Vérifie si une clé de session est disponible"""
        return self.session_key is not None
    
    def encrypt_data(self, data: bytes, session_key: Optional[bytes] = None) -> bytes:
        """
        Chiffre des données avec la clé de session
        
        Args:
            data: Données à chiffrer
            session_key: Clé de session (utilise la clé stockée si None)
            
        Returns:
            Données chiffrées
        """
        key_to_use = session_key or self.session_key
        
        if not key_to_use:
            raise Exception("Aucune clé de session disponible pour chiffrement")
        
        try:
            # Création de l'objet Fernet
            fernet_key = base64.urlsafe_b64encode(key_to_use)
            fernet = Fernet(fernet_key)
            
            # Chiffrement
            encrypted_data = fernet.encrypt(data)
            
            self.logger.debug(f"Données chiffrées: {len(data)} -> {len(encrypted_data)} bytes")
            return encrypted_data
            
        except Exception as e:
            self.logger.error(f"Erreur chiffrement données: {e}")
            raise
    
    def decrypt_data(self, encrypted_data: bytes, session_key: Optional[bytes] = None) -> bytes:
        """
        Déchiffre des données avec la clé de session
        
        Args:
            encrypted_data: Données chiffrées
            session_key: Clé de session (utilise la clé stockée si None)
            
        Returns:
            Données déchiffrées
        """
        key_to_use = session_key or self.session_key
        
        if not key_to_use:
            raise Exception("Aucune clé de session disponible pour déchiffrement")
        
        try:
            # Création de l'objet Fernet
            fernet_key = base64.urlsafe_b64encode(key_to_use)
            fernet = Fernet(fernet_key)
            
            # Déchiffrement
            decrypted_data = fernet.decrypt(encrypted_data)
            
            self.logger.debug(f"Données déchiffrées: {len(encrypted_data)} -> {len(decrypted_data)} bytes")
            return decrypted_data
            
        except Exception as e:
            self.logger.error(f"Erreur déchiffrement données: {e}")
            raise
    
    def clear_session(self):
        """Efface la session actuelle"""
        self.session_key = None
        self.server_public_key = None
        self.logger.info("Session sécurisée effacée")
    
    def get_security_status(self) -> dict:
        """Retourne l'état de la sécurité"""
        return {
            'has_rsa_keys': self.rsa_private_key is not None,
            'has_server_public_key': self.server_public_key is not None,
            'has_session_key': self.session_key is not None,
            'ready_for_secure_communication': (
                self.session_key is not None and 
                self.server_public_key is not None
            )
        }

class HandshakeManager:
    """Gestionnaire du handshake sécurisé avec le serveur"""
    
    def __init__(self, client_security: ClientSecurity):
        self.security = client_security
        self.logger = logging.getLogger(__name__)
        
        # État du handshake
        self.handshake_completed = False
        self.auth_token: Optional[str] = None
    
    async def perform_handshake(self, websocket, client_mac: str) -> bool:
        """
        Effectue le handshake sécurisé avec le serveur
        
        Args:
            websocket: Connexion WebSocket avec le serveur
            client_mac: Adresse MAC du client
            
        Returns:
            True si le handshake a réussi
        """
        try:
            self.logger.info("Début du handshake sécurisé")
            
            # Étape 1: Demande de clé publique serveur
            await self._request_server_public_key(websocket)
            
            # Étape 2: Envoi de la clé publique client et demande d'autorisation
            await self._send_client_public_key(websocket, client_mac)
            
            # Étape 3: Réception et déchiffrement de la clé de session
            session_success = await self._receive_session_key(websocket)
            
            if session_success:
                self.handshake_completed = True
                self.logger.info("Handshake sécurisé terminé avec succès")
                return True
            else:
                self.logger.error("Échec du handshake sécurisé")
                return False
                
        except Exception as e:
            self.logger.error(f"Erreur handshake: {e}")
            return False
    
    async def _request_server_public_key(self, websocket):
        """Demande la clé publique du serveur"""
        message = {
            'type': 'request_public_key'
        }
        
        await websocket.send(str(message).replace("'", '"'))
        
        # Attente de la réponse
        response = await websocket.recv()
        response_data = eval(response)  # TODO: Utiliser json.loads en production
        
        if response_data.get('type') == 'public_key':
            server_public_key = response_data.get('public_key')
            if not self.security.set_server_public_key(server_public_key):
                raise Exception("Impossible de charger la clé publique serveur")
        else:
            raise Exception("Réponse invalide pour demande clé publique")
    
    async def _send_client_public_key(self, websocket, client_mac: str):
        """Envoie la clé publique du client et demande l'autorisation"""
        message = {
            'type': 'client_auth',
            'client_mac': client_mac,
            'public_key': self.security.get_public_key_pem(),
            'capabilities': self._get_client_capabilities()
        }
        
        await websocket.send(str(message).replace("'", '"'))
    
    async def _receive_session_key(self, websocket) -> bool:
        """Reçoit et déchiffre la clé de session"""
        response = await websocket.recv()
        response_data = eval(response)  # TODO: Utiliser json.loads en production
        
        if response_data.get('type') == 'session_key':
            encrypted_session_key = response_data.get('encrypted_session_key')
            auth_token = response_data.get('auth_token')
            
            if self.security.decrypt_session_key(encrypted_session_key):
                self.auth_token = auth_token
                return True
        
        return False
    
    def _get_client_capabilities(self) -> dict:
        """Retourne les capacités du client pour le serveur"""
        # Import local pour éviter les dépendances circulaires
        from ..utils.system_info import SystemInfo
        
        system_info = SystemInfo()
        gpu_info = system_info.get_gpu_info()
        memory_info = system_info.get_memory_info()
        
        return {
            'os': system_info.get_os_info(),
            'gpu_name': gpu_info.get('name', '') if gpu_info else '',
            'gpu_memory_mb': gpu_info.get('memory_mb', 0) if gpu_info else 0,
            'system_memory_gb': memory_info.get('total_gb', 0),
            'cpu_cores': system_info.get_cpu_info().get('cores', 1),
            'realesrgan_available': self._check_realesrgan_availability(),
            'max_batch_size': self._calculate_max_batch_size(gpu_info, memory_info)
        }
    
    def _check_realesrgan_availability(self) -> bool:
        """Vérifie si Real-ESRGAN est disponible"""
        import shutil
        import sys
        
        executable_name = "realesrgan-ncnn-vulkan.exe" if sys.platform == "win32" else "realesrgan-ncnn-vulkan"
        return shutil.which(executable_name) is not None
    
    def _calculate_max_batch_size(self, gpu_info: dict, memory_info: dict) -> int:
        """Calcule la taille maximale de lot recommandée"""
        base_size = 25
        
        if gpu_info:
            gpu_memory = gpu_info.get('memory_mb', 0)
            
            if gpu_memory >= 8192:  # 8GB+
                return 60
            elif gpu_memory >= 6144:  # 6GB+
                return 45
            elif gpu_memory >= 4096:  # 4GB+
                return 35
        
        return base_size
    
    def get_auth_token(self) -> Optional[str]:
        """Retourne le token d'authentification actuel"""
        return self.auth_token
    
    def is_handshake_completed(self) -> bool:
        """Vérifie si le handshake est terminé"""
        return self.handshake_completed
    
    def reset_handshake(self):
        """Remet à zéro l'état du handshake"""
        self.handshake_completed = False
        self.auth_token = None
        self.security.clear_session()
        self.logger.info("Handshake réinitialisé")

class MessageValidator:
    """Validateur de messages pour vérifier l'intégrité et l'authenticité"""
    
    def __init__(self, client_security: ClientSecurity):
        self.security = client_security
        self.logger = logging.getLogger(__name__)
    
    def validate_server_message(self, message_data: dict) -> bool:
        """
        Valide un message reçu du serveur
        
        Args:
            message_data: Données du message à valider
            
        Returns:
            True si le message est valide
        """
        try:
            # Vérification des champs requis
            required_fields = ['type', 'timestamp']
            for field in required_fields:
                if field not in message_data:
                    self.logger.warning(f"Champ requis manquant: {field}")
                    return False
            
            # Vérification du timestamp (pas trop ancien)
            message_timestamp = message_data.get('timestamp')
            import time
            current_time = time.time()
            
            if abs(current_time - message_timestamp) > 300:  # 5 minutes max
                self.logger.warning("Message trop ancien ou futur")
                return False
            
            # Validation spécifique selon le type de message
            message_type = message_data.get('type')
            return self._validate_by_type(message_type, message_data)
            
        except Exception as e:
            self.logger.error(f"Erreur validation message: {e}")
            return False
    
    def _validate_by_type(self, message_type: str, message_data: dict) -> bool:
        """Valide selon le type de message"""
        
        if message_type == 'batch_assignment':
            required = ['batch_id', 'batch_data', 'encrypted_data']
            return all(field in message_data for field in required)
        
        elif message_type == 'ping':
            return True  # Ping simple, pas de validation spéciale
        
        elif message_type == 'server_status':
            return 'status' in message_data
        
        elif message_type == 'error':
            return 'error_message' in message_data
        
        else:
            self.logger.warning(f"Type de message inconnu: {message_type}")
            return False
    
    def create_signed_message(self, message_data: dict) -> dict:
        """
        Crée un message signé pour envoi au serveur
        
        Args:
            message_data: Données du message
            
        Returns:
            Message avec signature et métadonnées
        """
        import time
        import json
        import hashlib
        
        # Ajout des métadonnées
        message_data['timestamp'] = time.time()
        message_data['client_version'] = "1.0.0"  # TODO: Version dynamique
        
        # Calcul de la signature (hash du contenu)
        message_json = json.dumps(message_data, sort_keys=True)
        message_hash = hashlib.sha256(message_json.encode()).hexdigest()
        message_data['signature'] = message_hash
        
        return message_data

class SecurityAudit:
    """Auditeur de sécurité pour logging et monitoring"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.security_events = []
        self.max_events = 1000
    
    def log_security_event(self, event_type: str, details: dict):
        """Enregistre un événement de sécurité"""
        import time
        
        event = {
            'timestamp': time.time(),
            'type': event_type,
            'details': details
        }
        
        self.security_events.append(event)
        
        # Limitation de la taille de l'historique
        if len(self.security_events) > self.max_events:
            self.security_events = self.security_events[-self.max_events:]
        
        # Log selon la criticité
        if event_type in ['handshake_failed', 'decryption_failed', 'invalid_message']:
            self.logger.warning(f"Événement sécurité: {event_type} - {details}")
        else:
            self.logger.debug(f"Événement sécurité: {event_type}")
    
    def get_security_summary(self) -> dict:
        """Retourne un résumé des événements de sécurité"""
        if not self.security_events:
            return {
                'total_events': 0,
                'event_types': {},
                'recent_events': []
            }
        
        # Comptage par type
        event_types = {}
        for event in self.security_events:
            event_type = event['type']
            event_types[event_type] = event_types.get(event_type, 0) + 1
        
        # Événements récents (dernière heure)
        import time
        recent_threshold = time.time() - 3600  # 1 heure
        recent_events = [
            event for event in self.security_events 
            if event['timestamp'] > recent_threshold
        ]
        
        return {
            'total_events': len(self.security_events),
            'event_types': event_types,
            'recent_events': len(recent_events),
            'last_event': self.security_events[-1] if self.security_events else None
        }
    
    def check_security_health(self) -> dict:
        """Vérifie la santé sécuritaire du système"""
        issues = []
        warnings = []
        
        # Vérification des événements récents
        summary = self.get_security_summary()
        
        if summary['recent_events'] > 10:
            warnings.append("Nombre élevé d'événements sécuritaires récents")
        
        # Vérification des types d'événements problématiques
        problematic_types = ['handshake_failed', 'decryption_failed', 'invalid_message']
        for event_type in problematic_types:
            count = summary['event_types'].get(event_type, 0)
            if count > 5:
                issues.append(f"Trop d'événements '{event_type}': {count}")
        
        health_status = "healthy"
        if issues:
            health_status = "critical"
        elif warnings:
            health_status = "warning"
        
        return {
            'status': health_status,
            'issues': issues,
            'warnings': warnings,
            'summary': summary
        }