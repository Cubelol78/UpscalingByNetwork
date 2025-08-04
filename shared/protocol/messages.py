"""
Protocoles de communication partagés
UpscalingByNetwork/shared/protocol/messages.py
"""

import json
import time
from enum import Enum
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, Union
import uuid

class MessageType(Enum):
    """Types de messages réseau"""
    
    # Connexion et authentification
    CLIENT_CONNECT = "client_connect"
    CLIENT_DISCONNECT = "client_disconnect"
    HANDSHAKE_INIT = "handshake_init"
    HANDSHAKE_RESPONSE = "handshake_response"
    HANDSHAKE_COMPLETE = "handshake_complete"
    
    # Surveillance
    HEARTBEAT = "heartbeat"
    STATUS_UPDATE = "status_update"
    CLIENT_STATUS = "client_status"
    
    # Gestion des lots
    BATCH_ASSIGNMENT = "batch_assignment"
    BATCH_ACCEPTED = "batch_accepted"
    BATCH_REJECTED = "batch_rejected"
    BATCH_PROGRESS = "batch_progress"
    BATCH_COMPLETED = "batch_completed"
    BATCH_FAILED = "batch_failed"
    BATCH_TIMEOUT = "batch_timeout"
    BATCH_CANCEL = "batch_cancel"
    
    # Contrôle et configuration
    SERVER_SHUTDOWN = "server_shutdown"
    CLIENT_PAUSE = "client_pause"
    CLIENT_RESUME = "client_resume"
    CONFIG_UPDATE = "config_update"
    
    # Erreurs et notifications
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    
    # Administration
    ADMIN_COMMAND = "admin_command"
    ADMIN_RESPONSE = "admin_response"

@dataclass
class NetworkMessage:
    """Message réseau standardisé"""
    type: MessageType
    client_mac: str
    timestamp: float
    data: Dict[str, Any]
    session_id: str = ""
    message_id: str = ""
    correlation_id: str = ""
    
    def __post_init__(self):
        if not self.message_id:
            self.message_id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = time.time()
    
    def to_json(self) -> str:
        """Convertit le message en JSON"""
        return json.dumps({
            'type': self.type.value,
            'client_mac': self.client_mac,
            'timestamp': self.timestamp,
            'data': self.data,
            'session_id': self.session_id,
            'message_id': self.message_id,
            'correlation_id': self.correlation_id
        })
    
    @classmethod
    def from_json(cls, json_str: str) -> 'NetworkMessage':
        """Crée un message depuis JSON"""
        try:
            data = json.loads(json_str)
            return cls(
                type=MessageType(data['type']),
                client_mac=data['client_mac'],
                timestamp=data['timestamp'],
                data=data['data'],
                session_id=data.get('session_id', ''),
                message_id=data.get('message_id', ''),
                correlation_id=data.get('correlation_id', '')
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise ValueError(f"Message JSON invalide: {e}")
    
    def create_response(self, response_type: MessageType, 
                       response_data: Dict[str, Any]) -> 'NetworkMessage':
        """Crée un message de réponse"""
        return NetworkMessage(
            type=response_type,
            client_mac=self.client_mac,
            timestamp=time.time(),
            data=response_data,
            session_id=self.session_id,
            correlation_id=self.message_id  # La réponse corrèle avec l'ID du message original
        )

# Messages spécialisés pour différents types d'opérations

@dataclass
class ClientConnectData:
    """Données de connexion client"""
    client_id: str
    mac_address: str
    client_version: str
    system_info: Dict[str, Any]
    capabilities: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class BatchAssignmentData:
    """Données d'assignation de lot"""
    batch_id: str
    job_id: str
    encrypted_data: str  # Données chiffrées en hexadécimal
    frame_count: int
    estimated_time: float
    model_config: Dict[str, Any]
    priority: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class BatchProgressData:
    """Données de progression de lot"""
    batch_id: str
    progress: float  # Pourcentage 0-100
    current_frame: int
    frames_processed: int
    elapsed_time: float
    estimated_remaining: float
    current_speed: float  # images/seconde
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class BatchCompletedData:
    """Données de lot terminé"""
    batch_id: str
    encrypted_result: str  # Résultats chiffrés en hexadécimal
    processing_time: float
    frames_processed: int
    success: bool
    statistics: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class BatchFailedData:
    """Données de lot échoué"""
    batch_id: str
    error_code: str
    error_message: str
    partial_results: bool
    retry_possible: bool
    elapsed_time: float
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class HeartbeatData:
    """Données de heartbeat"""
    status: str  # idle, processing, error
    current_batch: Optional[str]
    progress: float
    system_load: Dict[str, Any]
    uptime: float
    last_activity: float
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class StatusUpdateData:
    """Données de mise à jour de statut"""
    status: str
    message: str
    server_info: Dict[str, Any]
    capabilities: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

# Factory pour créer des messages typés

class MessageFactory:
    """Factory pour créer des messages standardisés"""
    
    @staticmethod
    def create_client_connect(client_mac: str, client_data: ClientConnectData) -> NetworkMessage:
        """Crée un message de connexion client"""
        return NetworkMessage(
            type=MessageType.CLIENT_CONNECT,
            client_mac=client_mac,
            timestamp=time.time(),
            data=client_data.to_dict()
        )
    
    @staticmethod
    def create_handshake_init(client_mac: str, public_key: str) -> NetworkMessage:
        """Crée un message d'initialisation handshake"""
        return NetworkMessage(
            type=MessageType.HANDSHAKE_INIT,
            client_mac=client_mac,
            timestamp=time.time(),
            data={'public_key': public_key}
        )
    
    @staticmethod
    def create_batch_assignment(client_mac: str, batch_data: BatchAssignmentData) -> NetworkMessage:
        """Crée un message d'assignation de lot"""
        return NetworkMessage(
            type=MessageType.BATCH_ASSIGNMENT,
            client_mac=client_mac,
            timestamp=time.time(),
            data=batch_data.to_dict()
        )
    
    @staticmethod
    def create_batch_progress(client_mac: str, progress_data: BatchProgressData) -> NetworkMessage:
        """Crée un message de progression"""
        return NetworkMessage(
            type=MessageType.BATCH_PROGRESS,
            client_mac=client_mac,
            timestamp=time.time(),
            data=progress_data.to_dict()
        )
    
    @staticmethod
    def create_batch_completed(client_mac: str, completed_data: BatchCompletedData) -> NetworkMessage:
        """Crée un message de lot terminé"""
        return NetworkMessage(
            type=MessageType.BATCH_COMPLETED,
            client_mac=client_mac,
            timestamp=time.time(),
            data=completed_data.to_dict()
        )
    
    @staticmethod
    def create_batch_failed(client_mac: str, failed_data: BatchFailedData) -> NetworkMessage:
        """Crée un message de lot échoué"""
        return NetworkMessage(
            type=MessageType.BATCH_FAILED,
            client_mac=client_mac,
            timestamp=time.time(),
            data=failed_data.to_dict()
        )
    
    @staticmethod
    def create_heartbeat(client_mac: str, heartbeat_data: HeartbeatData) -> NetworkMessage:
        """Crée un message de heartbeat"""
        return NetworkMessage(
            type=MessageType.HEARTBEAT,
            client_mac=client_mac,
            timestamp=time.time(),
            data=heartbeat_data.to_dict()
        )
    
    @staticmethod
    def create_status_update(client_mac: str, status_data: StatusUpdateData) -> NetworkMessage:
        """Crée un message de mise à jour de statut"""
        return NetworkMessage(
            type=MessageType.STATUS_UPDATE,
            client_mac=client_mac,
            timestamp=time.time(),
            data=status_data.to_dict()
        )
    
    @staticmethod
    def create_error(client_mac: str, error_code: str, error_message: str, 
                    details: Dict[str, Any] = None) -> NetworkMessage:
        """Crée un message d'erreur"""
        data = {
            'error_code': error_code,
            'error_message': error_message,
            'details': details or {}
        }
        
        return NetworkMessage(
            type=MessageType.ERROR,
            client_mac=client_mac,
            timestamp=time.time(),
            data=data
        )

# Validateurs de messages

class MessageValidator:
    """Validateur pour les messages réseau"""
    
    @staticmethod
    def validate_message(message: NetworkMessage) -> bool:
        """Valide la structure d'un message"""
        try:
            # Vérifications de base
            if not message.type or not isinstance(message.type, MessageType):
                return False
            
            if not message.client_mac or not isinstance(message.client_mac, str):
                return False
            
            if not message.timestamp or not isinstance(message.timestamp, (int, float)):
                return False
            
            if not isinstance(message.data, dict):
                return False
            
            # Validation spécifique par type
            return MessageValidator._validate_by_type(message)
            
        except Exception:
            return False
    
    @staticmethod
    def _validate_by_type(message: NetworkMessage) -> bool:
        """Validation spécifique selon le type de message"""
        validators = {
            MessageType.CLIENT_CONNECT: MessageValidator._validate_client_connect,
            MessageType.BATCH_ASSIGNMENT: MessageValidator._validate_batch_assignment,
            MessageType.BATCH_PROGRESS: MessageValidator._validate_batch_progress,
            MessageType.BATCH_COMPLETED: MessageValidator._validate_batch_completed,
            MessageType.BATCH_FAILED: MessageValidator._validate_batch_failed,
            MessageType.HEARTBEAT: MessageValidator._validate_heartbeat
        }
        
        validator = validators.get(message.type)
        if validator:
            return validator(message.data)
        
        return True  # Pas de validation spécifique
    
    @staticmethod
    def _validate_client_connect(data: Dict[str, Any]) -> bool:
        """Valide les données de connexion client"""
        required_fields = ['client_id', 'mac_address', 'system_info', 'capabilities']
        return all(field in data for field in required_fields)
    
    @staticmethod
    def _validate_batch_assignment(data: Dict[str, Any]) -> bool:
        """Valide les données d'assignation de lot"""
        required_fields = ['batch_id', 'job_id', 'encrypted_data', 'frame_count']
        return all(field in data for field in required_fields)
    
    @staticmethod
    def _validate_batch_progress(data: Dict[str, Any]) -> bool:
        """Valide les données de progression"""
        required_fields = ['batch_id', 'progress', 'current_frame']
        if not all(field in data for field in required_fields):
            return False
        
        # Vérification des valeurs
        progress = data.get('progress', -1)
        return 0 <= progress <= 100
    
    @staticmethod
    def _validate_batch_completed(data: Dict[str, Any]) -> bool:
        """Valide les données de lot terminé"""
        required_fields = ['batch_id', 'processing_time', 'frames_processed', 'success']
        return all(field in data for field in required_fields)
    
    @staticmethod
    def _validate_batch_failed(data: Dict[str, Any]) -> bool:
        """Valide les données de lot échoué"""
        required_fields = ['batch_id', 'error_code', 'error_message']
        return all(field in data for field in required_fields)
    
    @staticmethod
    def _validate_heartbeat(data: Dict[str, Any]) -> bool:
        """Valide les données de heartbeat"""
        required_fields = ['status', 'system_load']
        return all(field in data for field in required_fields)