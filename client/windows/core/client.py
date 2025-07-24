# client/windows/core/client.py
"""
Client principal pour l'upscaling distribué
Gère la connexion au serveur et la coordination des traitements
"""

import asyncio
import logging
import json
import time
from typing import Optional, Dict, Any, Callable
from pathlib import Path
import websockets
from websockets.client import WebSocketClientProtocol

# Imports locaux
from ..security.client_security import ClientSecurity
from ..utils.config import config
from ..utils.system_info import SystemInfo
from .processor import ClientProcessor

class ConnectionState:
    """États de connexion du client"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATING = "authenticating"
    READY = "ready"
    ERROR = "error"

class DistributedUpscalingClient:
    """
    Client principal d'upscaling distribué
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Configuration
        self.config = config
        self.system_info = SystemInfo()
        self.security = ClientSecurity()
        self.processor = ClientProcessor(self)
        
        # État de connexion
        self.connection_state = ConnectionState.DISCONNECTED
        self.websocket: Optional[WebSocketClientProtocol] = None
        self.server_host = ""
        self.server_port = 0
        
        # Identification client
        self.client_id = self.security.generate_client_id()
        self.mac_address = self.system_info.get_mac_address()
        
        # Gestion des messages
        self.message_handlers = {
            'batch_assignment': self._handle_batch_assignment,
            'batch_request': self._handle_batch_request,
            'configuration_update': self._handle_configuration_update,
            'server_info': self._handle_server_info,
            'ping': self._handle_ping,
            'disconnect': self._handle_disconnect,
            'error': self._handle_error
        }
        
        # Statistiques
        self.connection_stats = {
            'connect_time': None,
            'last_heartbeat': None,
            'messages_sent': 0,
            'messages_received': 0,
            'reconnection_attempts': 0,
            'bytes_transferred': 0
        }
        
        # Tâches asynchrones
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.message_handler_task: Optional[asyncio.Task] = None
        self.auto_reconnect_task: Optional[asyncio.Task] = None
        
        # Callbacks pour les événements
        self.event_callbacks: Dict[str, Callable] = {}
        
        # Configuration de reconnexion automatique
        self.auto_reconnect_enabled = True
        self.reconnect_delay = 10  # secondes
        self.max_reconnection_attempts = 0  # 0 = illimité
        
        self.logger.info(f"Client initialisé - ID: {self.client_id}, MAC: {self.mac_address}")
    
    @property
    def is_connected(self) -> bool:
        """Vérifie si le client est connecté"""
        return (self.connection_state in [ConnectionState.CONNECTED, ConnectionState.READY] and
                self.websocket is not None and
                not self.websocket.closed)
    
    @property
    def is_ready(self) -> bool:
        """Vérifie si le client est prêt à traiter des lots"""
        return (self.connection_state == ConnectionState.READY and
                self.security.is_ready() and
                not self.processor.is_processing)
    
    async def connect(self, host: str, port: int) -> bool:
        """
        Se connecte au serveur
        
        Args:
            host: Adresse du serveur
            port: Port du serveur
            
        Returns:
            True si connecté avec succès
        """
        if self.is_connected:
            self.logger.warning("Déjà connecté au serveur")
            return True
        
        self.server_host = host
        self.server_port = port
        self.connection_state = ConnectionState.CONNECTING
        
        try:
            # Construction de l'URL WebSocket
            uri = f"ws://{host}:{port}"
            if self.config.get("server.use_ssl", False):
                uri = f"wss://{host}:{port}"
            
            self.logger.info(f"Connexion au serveur: {uri}")
            
            # Connexion WebSocket avec timeout
            self.websocket = await asyncio.wait_for(
                websockets.connect(uri, ping_interval=30, ping_timeout=10),
                timeout=30
            )
            
            self.connection_state = ConnectionState.CONNECTED
            self.connection_stats['connect_time'] = time.time()
            self._emit_event('connected', {'host': host, 'port': port})
            
            # Démarrage des tâches de gestion
            self.message_handler_task = asyncio.create_task(self._message_handler_loop())
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
            # Authentification et échange de clés
            if await self._authenticate():
                self.connection_state = ConnectionState.READY
                self._emit_event('ready', {})
                self.logger.info("Connexion établie et client prêt")
                return True
            else:
                await self.disconnect()
                return False
                
        except asyncio.TimeoutError:
            self.logger.error("Timeout lors de la connexion")
            self.connection_state = ConnectionState.ERROR
            self._emit_event('connection_error', {'error': 'Timeout'})
            return False
        except Exception as e:
            self.logger.error(f"Erreur de connexion: {e}")
            self.connection_state = ConnectionState.ERROR
            self._emit_event('connection_error', {'error': str(e)})
            return False
    
    async def disconnect(self):
        """Déconnecte le client du serveur"""
        if not self.websocket:
            return
        
        self.logger.info("Déconnexion du serveur")
        
        # Arrêt de la reconnexion automatique
        self.auto_reconnect_enabled = False
        
        # Annulation des tâches
        for task in [self.heartbeat_task, self.message_handler_task, self.auto_reconnect_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Fermeture de la connexion WebSocket
        if not self.websocket.closed:
            try:
                await self.websocket.close()
            except Exception as e:
                self.logger.error(f"Erreur fermeture WebSocket: {e}")
        
        # Remise à zéro de l'état
        self.websocket = None
        self.connection_state = ConnectionState.DISCONNECTED
        self.security.reset_session()
        
        self._emit_event('disconnected', {})
        self.logger.info("Déconnecté du serveur")
    
    async def _authenticate(self) -> bool:
        """
        Effectue l'authentification et l'échange de clés
        
        Returns:
            True si l'authentification a réussi
        """
        try:
            self.connection_state = ConnectionState.AUTHENTICATING
            
            # Collecte des informations système
            system_info = self.system_info.get_system_info()
            capabilities = self.processor.get_processing_capabilities()
            
            # Message d'authentification
            auth_message = {
                'type': 'client_hello',
                'client_id': self.client_id,
                'mac_address': self.mac_address,
                'public_key': self.security.get_public_key_pem(),
                'system_info': {
                    'platform': system_info['basic']['platform'],
                    'hostname': system_info['basic']['hostname'],
                    'cpu_cores': system_info['hardware']['cpu'].get('logical_cores', 1),
                    'ram_gb': system_info['hardware']['memory'].get('total_ram_gb', 0),
                    'gpu_available': self.system_info.is_gpu_available(),
                    'performance_score': self.system_info.get_performance_score()
                },
                'capabilities': capabilities,
                'version': '1.0.0'
            }
            
            # Envoi du message d'authentification
            await self._send_message(auth_message)
            
            # Attente de la réponse du serveur
            response = await self._wait_for_message('server_hello', timeout=30)
            if not response:
                raise Exception("Pas de réponse du serveur pour l'authentification")
            
            # Traitement de la réponse
            if response.get('status') != 'accepted':
                raise Exception(f"Authentification refusée: {response.get('message', 'Raison inconnue')}")
            
            # Configuration de la clé publique du serveur
            server_public_key = response.get('server_public_key')
            if server_public_key:
                self.security.set_server_public_key(server_public_key)
            
            # Déchiffrement de la clé de session si fournie
            encrypted_session_key = response.get('session_key')
            if encrypted_session_key:
                import base64
                encrypted_key_bytes = base64.b64decode(encrypted_session_key)
                if not self.security.decrypt_session_key(encrypted_key_bytes):
                    raise Exception("Échec du déchiffrement de la clé de session")
            
            self.logger.info("Authentification réussie")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur d'authentification: {e}")
            return False
    
    async def _send_message(self, message: Dict[str, Any]) -> bool:
        """
        Envoie un message au serveur
        
        Args:
            message: Message à envoyer
            
        Returns:
            True si envoyé avec succès
        """
        if not self.websocket or self.websocket.closed:
            return False
        
        try:
            message_json = json.dumps(message)
            await self.websocket.send(message_json)
            
            self.connection_stats['messages_sent'] += 1
            self.connection_stats['bytes_transferred'] += len(message_json)
            
            self.logger.debug(f"Message envoyé: {message.get('type', 'unknown')}")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur envoi message: {e}")
            return False
    
    async def _wait_for_message(self, message_type: str, timeout: float = 10) -> Optional[Dict[str, Any]]:
        """
        Attend un message spécifique du serveur
        
        Args:
            message_type: Type de message attendu
            timeout: Timeout en secondes
            
        Returns:
            Message reçu ou None si timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                if not self.websocket:
                    break
                
                message_raw = await asyncio.wait_for(self.websocket.recv(), timeout=1)
                message = json.loads(message_raw)
                
                if message.get('type') == message_type:
                    return message
                else:
                    # Traitement des autres messages reçus en attendant
                    asyncio.create_task(self._handle_message(message))
                    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error(f"Erreur attente message: {e}")
                break
        
        return None
    
    async def _message_handler_loop(self):
        """Boucle de gestion des messages"""
        try:
            while self.is_connected:
                try:
                    message_raw = await self.websocket.recv()
                    message = json.loads(message_raw)
                    
                    self.connection_stats['messages_received'] += 1
                    self.connection_stats['bytes_transferred'] += len(message_raw)
                    
                    await self._handle_message(message)
                    
                except websockets.exceptions.ConnectionClosed:
                    self.logger.info("Connexion fermée par le serveur")
                    break
                except json.JSONDecodeError as e:
                    self.logger.error(f"Message JSON invalide: {e}")
                except Exception as e:
                    self.logger.error(f"Erreur traitement message: {e}")
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"Erreur boucle messages: {e}")
        finally:
            if self.auto_reconnect_enabled:
                self.auto_reconnect_task = asyncio.create_task(self._auto_reconnect())
    
    async def _handle_message(self, message: Dict[str, Any]):
        """
        Traite un message reçu du serveur
        
        Args:
            message: Message à traiter
        """
        message_type = message.get('type', 'unknown')
        
        self.logger.debug(f"Message reçu: {message_type}")
        
        # Recherche du gestionnaire approprié
        handler = self.message_handlers.get(message_type)
        if handler:
            try:
                await handler(message)
            except Exception as e:
                self.logger.error(f"Erreur traitement message {message_type}: {e}")
        else:
            self.logger.warning(f"Type de message non géré: {message_type}")
    
    async def _handle_batch_assignment(self, message: Dict[str, Any]):
        """Traite l'assignation d'un lot"""
        batch_id = message.get('batch_id')
        batch_data = message.get('batch_data')
        batch_config = message.get('batch_config', {})
        
        if not batch_id or not batch_data:
            self.logger.error("Message d'assignation de lot invalide")
            return
        
        self.logger.info(f"Lot assigné: {batch_id}")
        
        # Décodage des données
        import base64
        try:
            encrypted_data = base64.b64decode(batch_data)
        except Exception as e:
            self.logger.error(f"Erreur décodage données lot: {e}")
            return
        
        # Traitement du lot
        result = await self.processor.process_batch(encrypted_data, batch_id, batch_config)
        
        # Envoi du résultat
        if result:
            result_b64 = base64.b64encode(result).decode('utf-8')
            
            response_message = {
                'type': 'batch_result',
                'batch_id': batch_id,
                'status': 'completed',
                'result_data': result_b64,
                'processing_stats': {
                    'processing_time': self.processor.processing_start_time,
                    'frames_processed': batch_config.get('frames_count', 0)
                }
            }
        else:
            response_message = {
                'type': 'batch_result',
                'batch_id': batch_id,
                'status': 'failed',
                'error_message': self.processor.stats.get('last_error', 'Erreur inconnue')
            }
        
        await self._send_message(response_message)
        self._emit_event('batch_completed', {'batch_id': batch_id, 'success': result is not None})
    
    async def _handle_batch_request(self, message: Dict[str, Any]):
        """Traite une demande de disponibilité pour un lot"""
        batch_id = message.get('batch_id')
        
        # Vérification de la disponibilité
        available = self.is_ready and not self.processor.is_processing
        
        response = {
            'type': 'batch_availability',
            'batch_id': batch_id,
            'available': available,
            'client_stats': {
                'performance_score': self.system_info.get_performance_score(),
                'batches_completed': self.processor.stats['batches_processed'],
                'current_load': self._get_current_load()
            }
        }
        
        await self._send_message(response)
    
    async def _handle_configuration_update(self, message: Dict[str, Any]):
        """Traite une mise à jour de configuration"""
        new_config = message.get('configuration', {})
        
        if new_config:
            # Mise à jour de la configuration locale
            for key, value in new_config.items():
                self.config.set(key, value)
            
            self.logger.info("Configuration mise à jour par le serveur")
            self._emit_event('configuration_updated', new_config)
    
    async def _handle_server_info(self, message: Dict[str, Any]):
        """Traite les informations du serveur"""
        server_info = message.get('server_info', {})
        self._emit_event('server_info_received', server_info)
    
    async def _handle_ping(self, message: Dict[str, Any]):
        """Traite un ping du serveur"""
        pong_message = {
            'type': 'pong',
            'timestamp': message.get('timestamp', time.time()),
            'client_stats': self._get_client_status()
        }
        await self._send_message(pong_message)
    
    async def _handle_disconnect(self, message: Dict[str, Any]):
        """Traite une demande de déconnexion du serveur"""
        reason = message.get('reason', 'Demande du serveur')
        self.logger.info(f"Déconnexion demandée par le serveur: {reason}")
        
        self.auto_reconnect_enabled = False
        await self.disconnect()
    
    async def _handle_error(self, message: Dict[str, Any]):
        """Traite un message d'erreur du serveur"""
        error_message = message.get('message', 'Erreur inconnue')
        error_code = message.get('code', 'UNKNOWN')
        
        self.logger.error(f"Erreur serveur [{error_code}]: {error_message}")
        self._emit_event('server_error', {'code': error_code, 'message': error_message})
    
    async def _heartbeat_loop(self):
        """Boucle d'envoi de heartbeat"""
        try:
            heartbeat_interval = self.config.get("server.heartbeat_interval", 30)
            
            while self.is_connected:
                try:
                    heartbeat_message = {
                        'type': 'heartbeat',
                        'timestamp': time.time(),
                        'client_status': self._get_client_status()
                    }
                    
                    if await self._send_message(heartbeat_message):
                        self.connection_stats['last_heartbeat'] = time.time()
                    
                    await asyncio.sleep(heartbeat_interval)
                    
                except Exception as e:
                    self.logger.error(f"Erreur heartbeat: {e}")
                    await asyncio.sleep(heartbeat_interval)
                    
        except asyncio.CancelledError:
            pass
    
    async def _auto_reconnect(self):
        """Reconnexion automatique en cas de déconnexion"""
        if not self.auto_reconnect_enabled:
            return
        
        self.connection_stats['reconnection_attempts'] += 1
        
        try:
            # Attente avant tentative de reconnexion
            await asyncio.sleep(self.reconnect_delay)
            
            # Vérification si on doit encore tenter
            if (self.max_reconnection_attempts > 0 and 
                self.connection_stats['reconnection_attempts'] > self.max_reconnection_attempts):
                self.logger.error("Nombre maximum de tentatives de reconnexion atteint")
                self._emit_event('reconnection_failed', {})
                return
            
            self.logger.info(f"Tentative de reconnexion {self.connection_stats['reconnection_attempts']}")
            
            # Tentative de reconnexion
            if await self.connect(self.server_host, self.server_port):
                self.logger.info("Reconnexion réussie")
                self.connection_stats['reconnection_attempts'] = 0  # Reset du compteur
                self._emit_event('reconnected', {})
            else:
                # Échec, on programme une nouvelle tentative
                self.auto_reconnect_task = asyncio.create_task(self._auto_reconnect())
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"Erreur reconnexion automatique: {e}")
    
    def _get_client_status(self) -> Dict[str, Any]:
        """Retourne le statut actuel du client"""
        processor_stats = self.processor.get_stats()
        
        return {
            'client_id': self.client_id,
            'mac_address': self.mac_address,
            'connection_state': self.connection_state,
            'is_processing': self.processor.is_processing,
            'current_batch': self.processor.current_batch_id,
            'performance_score': self.system_info.get_performance_score(),
            'system_load': self._get_current_load(),
            'processing_stats': processor_stats['performance_stats'],
            'uptime': time.time() - self.connection_stats.get('connect_time', time.time())
        }
    
    def _get_current_load(self) -> Dict[str, float]:
        """Retourne la charge système actuelle"""
        try:
            perf_info = self.system_info._get_performance_info()
            return {
                'cpu_percent': perf_info.get('cpu_percent_total', 0),
                'memory_percent': perf_info.get('memory_percent', 0),
                'disk_percent': perf_info.get('disk_percent', 0)
            }
        except:
            return {'cpu_percent': 0, 'memory_percent': 0, 'disk_percent': 0}
    
    def _emit_event(self, event_type: str, data: Dict[str, Any] = None):
        """Émet un événement vers les callbacks enregistrés"""
        if event_type in self.event_callbacks:
            try:
                callback = self.event_callbacks[event_type]
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(data or {}))
                else:
                    callback(data or {})
            except Exception as e:
                self.logger.error(f"Erreur callback événement {event_type}: {e}")
    
    def register_event_callback(self, event_type: str, callback: Callable):
        """
        Enregistre un callback pour un type d'événement
        
        Args:
            event_type: Type d'événement
            callback: Fonction de callback
        """
        self.event_callbacks[event_type] = callback
    
    def unregister_event_callback(self, event_type: str):
        """
        Désenregistre un callback d'événement
        
        Args:
            event_type: Type d'événement
        """
        if event_type in self.event_callbacks:
            del self.event_callbacks[event_type]
    
    async def request_server_info(self) -> Optional[Dict[str, Any]]:
        """
        Demande les informations du serveur
        
        Returns:
            Informations du serveur ou None
        """
        if not self.is_connected:
            return None
        
        message = {'type': 'get_server_info'}
        await self._send_message(message)
        
        # Attente de la réponse
        response = await self._wait_for_message('server_info', timeout=10)
        return response.get('server_info') if response else None
    
    async def update_preferences(self, preferences: Dict[str, Any]) -> bool:
        """
        Met à jour les préférences du client sur le serveur
        
        Args:
            preferences: Nouvelles préférences
            
        Returns:
            True si mis à jour avec succès
        """
        if not self.is_connected:
            return False
        
        message = {
            'type': 'update_preferences',
            'preferences': preferences
        }
        
        return await self._send_message(message)
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """
        Retourne les statistiques de connexion
        
        Returns:
            Statistiques de connexion
        """
        stats = self.connection_stats.copy()
        
        # Calculs supplémentaires
        if stats['connect_time']:
            stats['uptime_seconds'] = time.time() - stats['connect_time']
        else:
            stats['uptime_seconds'] = 0
        
        if stats['last_heartbeat']:
            stats['time_since_last_heartbeat'] = time.time() - stats['last_heartbeat']
        else:
            stats['time_since_last_heartbeat'] = 0
        
        stats['connection_state'] = self.connection_state
        stats['server_address'] = f"{self.server_host}:{self.server_port}"
        
        return stats
    
    def get_detailed_status(self) -> Dict[str, Any]:
        """
        Retourne un statut détaillé du client
        
        Returns:
            Statut détaillé
        """
        return {
            'client_info': {
                'client_id': self.client_id,
                'mac_address': self.mac_address,
                'version': '1.0.0'
            },
            'connection': self.get_connection_stats(),
            'system': self.system_info.get_system_info(),
            'processor': self.processor.get_stats(),
            'security': {
                'session_established': self.security.is_ready(),
                'encryption_enabled': True
            },
            'configuration': {
                'auto_reconnect': self.auto_reconnect_enabled,
                'heartbeat_interval': self.config.get("server.heartbeat_interval", 30),
                'work_directory': str(self.config.get_work_directory())
            }
        }
    
    async def cleanup(self):
        """Nettoie les ressources du client"""
        try:
            # Arrêt de la reconnexion automatique
            self.auto_reconnect_enabled = False
            
            # Déconnexion
            await self.disconnect()
            
            # Nettoyage du processeur
            if hasattr(self.processor, 'cleanup_old_files'):
                self.processor.cleanup_old_files()
            
            # Sauvegarde de la configuration
            self.config.save_config()
            
            self.logger.info("Nettoyage du client terminé")
            
        except Exception as e:
            self.logger.error(f"Erreur nettoyage client: {e}")
    
    def __del__(self):
        """Destructeur pour nettoyage automatique"""
        if hasattr(self, 'websocket') and self.websocket:
            try:
                asyncio.create_task(self.cleanup())
            except:
                pass