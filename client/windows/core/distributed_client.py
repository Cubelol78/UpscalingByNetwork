# UpscalingByNetwork/client/windows/core/distributed_client.py
"""
Client distribué pour l'upscaling de vidéos
Se connecte au serveur, reçoit les lots, les traite et renvoie les résultats
"""

import asyncio
import logging
import json
import time
import socket
import uuid
import platform
import psutil
from pathlib import Path
from typing import Dict, Optional, Any, Callable
from datetime import datetime
import tempfile
import zipfile
import hashlib

# Import conditionnel des gestionnaires
try:
    from ..utils.realesrgan_handler import RealESRGANHandler
    from ..utils.encryption_manager import ClientEncryptionManager  
    from ..utils.system_monitor import SystemMonitor
except ImportError:
    # Fallback pour les tests
    RealESRGANHandler = None
    ClientEncryptionManager = None
    SystemMonitor = None

class DistributedClient:
    """Client principal pour l'upscaling distribué"""
    
    def __init__(self, work_dir: Path = None):
        self.logger = logging.getLogger(__name__)
        
        # Configuration
        self.client_version = "1.0.0"
        self.mac_address = self._get_mac_address()
        self.hostname = platform.node()
        
        # Dossiers de travail
        self.work_dir = work_dir or Path("client_work")
        self.temp_dir = self.work_dir / "temp"
        self.received_batches_dir = self.temp_dir / "received_batches"
        self.processed_batches_dir = self.temp_dir / "processed_batches"
        self.logs_dir = self.work_dir / "logs"
        
        # État de connexion
        self.connected = False
        self.server_socket = None
        self.server_host = None
        self.server_port = None
        self.connection_start_time = None
        
        # État de traitement
        self.current_batch = None
        self.processing = False
        self.total_batches_processed = 0
        self.total_images_processed = 0
        
        # Gestionnaires
        self.realesrgan_handler = None
        self.encryption_manager = None
        self.system_monitor = None
        
        # Configuration du traitement
        self.max_concurrent_batches = 1
        self.auto_request_batches = True
        self.processing_settings = {
            'model': 'realesr-animevideov3',
            'scale': 4,
            'tile_size': 0  # Auto
        }
        
        # Callbacks pour l'interface
        self.on_connected = None
        self.on_disconnected = None
        self.on_batch_received = None
        self.on_batch_progress = None
        self.on_batch_completed = None
        self.on_error = None
        
        # Tâches asynchrones
        self.connection_task = None
        self.heartbeat_task = None
        self.batch_processor_task = None
        
        # Créer les dossiers nécessaires
        self.create_directories()
        
        self.logger.info(f"Client distribué initialisé - MAC: {self.mac_address}")
    
    def _get_mac_address(self) -> str:
        """Récupère l'adresse MAC de la machine"""
        try:
            mac = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff)
                           for elements in range(0, 2*6, 2)][::-1])
            return mac
        except Exception:
            # Fallback avec une MAC générée
            return f"00:00:00:{uuid.uuid4().hex[:6]}"
    
    def create_directories(self):
        """Crée les dossiers nécessaires"""
        directories = [
            self.work_dir,
            self.temp_dir,
            self.received_batches_dir,
            self.processed_batches_dir,
            self.logs_dir
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
        
        self.logger.debug("Dossiers de travail créés")
    
    def initialize_handlers(self):
        """Initialise les gestionnaires d'outils"""
        try:
            # Gestionnaire Real-ESRGAN
            if RealESRGANHandler:
                realesrgan_path = self._find_realesrgan_path()
                self.realesrgan_handler = RealESRGANHandler(realesrgan_path)
                self.logger.info("Gestionnaire Real-ESRGAN initialisé")
            
            # Gestionnaire de chiffrement
            if ClientEncryptionManager:
                self.encryption_manager = ClientEncryptionManager()
                self.logger.info("Gestionnaire de chiffrement initialisé")
            
            # Moniteur système
            if SystemMonitor:
                self.system_monitor = SystemMonitor()
                self.logger.info("Moniteur système initialisé")
            
        except Exception as e:
            self.logger.error(f"Erreur initialisation gestionnaires: {e}")
            raise
    
    def _find_realesrgan_path(self) -> Path:
        """Trouve le chemin vers Real-ESRGAN"""
        # Chercher dans le dossier du client
        client_dir = Path(__file__).parent.parent
        realesrgan_dir = client_dir / "realesrgan-ncnn-vulkan"
        
        if (realesrgan_dir / "realesrgan-ncnn-vulkan.exe").exists():
            return realesrgan_dir / "realesrgan-ncnn-vulkan.exe"
        elif (realesrgan_dir / "realesrgan-ncnn-vulkan").exists():
            return realesrgan_dir / "realesrgan-ncnn-vulkan"
        
        return Path("realesrgan-ncnn-vulkan.exe")
    
    async def connect_to_server(self, host: str, port: int = 8888) -> bool:
        """Se connecte au serveur"""
        if self.connected:
            self.logger.warning("Déjà connecté au serveur")
            return True
        
        self.server_host = host
        self.server_port = port
        
        try:
            self.logger.info(f"Connexion au serveur {host}:{port}...")
            
            # Initialisation des gestionnaires
            self.initialize_handlers()
            
            # Création du socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.settimeout(30)
            
            # Connexion
            await asyncio.get_event_loop().sock_connect(
                self.server_socket, (host, port)
            )
            self.server_socket.setblocking(False)
            
            # Handshake
            if not await self.perform_handshake():
                await self.disconnect()
                return False
            
            # État connecté
            self.connected = True
            self.connection_start_time = datetime.now()
            
            # Démarrage des tâches de maintenance
            self.connection_task = asyncio.create_task(self.handle_server_communication())
            self.heartbeat_task = asyncio.create_task(self.send_heartbeat())
            
            if self.auto_request_batches:
                self.batch_processor_task = asyncio.create_task(self.batch_processor())
            
            self.logger.info("Connexion établie avec le serveur")
            
            # Callback
            if self.on_connected:
                await self.on_connected(host, port)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur connexion serveur: {e}")
            await self.disconnect()
            
            if self.on_error:
                await self.on_error(f"Connexion échouée: {e}")
            
            return False
    
    async def perform_handshake(self) -> bool:
        """Effectue le handshake avec le serveur"""
        try:
            # Préparation des informations client
            client_hello = {
                'mac_address': self.mac_address,
                'hostname': self.hostname,
                'version': self.client_version,
                'platform': platform.system(),
                'capabilities': {
                    'realesrgan': self.realesrgan_handler is not None,
                    'encryption': self.encryption_manager is not None,
                    'max_concurrent_batches': self.max_concurrent_batches
                }
            }
            
            if self.encryption_manager:
                # Ajouter la clé publique pour le chiffrement
                client_hello['public_key'] = self.encryption_manager.get_public_key_pem().decode()
            
            # Envoi au serveur
            message = json.dumps(client_hello).encode('utf-8')
            await asyncio.get_event_loop().sock_sendall(self.server_socket, message)
            
            # Réception de la réponse
            response = await asyncio.wait_for(
                asyncio.get_event_loop().sock_recv(self.server_socket, 4096),
                timeout=30
            )
            
            server_hello = json.loads(response.decode('utf-8'))
            
            # Validation de la réponse
            if server_hello.get('status') != 'accepted':
                raise RuntimeError(f"Connexion refusée: {server_hello.get('reason', 'Raison inconnue')}")
            
            # Configuration selon la réponse du serveur
            if 'session_key' in server_hello and self.encryption_manager:
                session_key = bytes.fromhex(server_hello['session_key'])
                self.encryption_manager.set_session_key(session_key)
            
            if 'batch_size' in server_hello:
                self.server_batch_size = server_hello['batch_size']
            
            self.logger.info("Handshake réussi")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur handshake: {e}")
            return False
    
    async def disconnect(self):
        """Se déconnecte du serveur"""
        if not self.connected:
            return
        
        self.connected = False
        
        try:
            # Arrêt des tâches
            if self.connection_task:
                self.connection_task.cancel()
            if self.heartbeat_task:
                self.heartbeat_task.cancel()
            if self.batch_processor_task:
                self.batch_processor_task.cancel()
            
            # Fermeture du socket
            if self.server_socket:
                self.server_socket.close()
                self.server_socket = None
            
            self.logger.info("Déconnecté du serveur")
            
            # Callback
            if self.on_disconnected:
                await self.on_disconnected()
                
        except Exception as e:
            self.logger.error(f"Erreur déconnexion: {e}")
    
    async def handle_server_communication(self):
        """Gère la communication avec le serveur"""
        while self.connected:
            try:
                # Réception des messages
                data = await asyncio.wait_for(
                    asyncio.get_event_loop().sock_recv(self.server_socket, 8192),
                    timeout=60
                )
                
                if not data:
                    self.logger.warning("Connexion fermée par le serveur")
                    break
                
                # Traitement du message
                await self.process_server_message(data)
                
            except asyncio.TimeoutError:
                self.logger.debug("Timeout réception - connexion OK")
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Erreur communication serveur: {e}")
                break
        
        # Déconnexion automatique en cas d'erreur
        if self.connected:
            await self.disconnect()
    
    async def process_server_message(self, data: bytes):
        """Traite un message reçu du serveur"""
        try:
            # Déchiffrement si nécessaire
            if self.encryption_manager and self.encryption_manager.has_session_key():
                data = self.encryption_manager.decrypt_data(data)
            
            message = json.loads(data.decode('utf-8'))
            message_type = message.get('type')
            
            if message_type == 'ping':
                await self.handle_ping()
                
            elif message_type == 'batch_assignment':
                await self.handle_batch_assignment(message)
                
            elif message_type == 'batch_data':
                await self.handle_batch_data(message)
                
            elif message_type == 'job_cancelled':
                await self.handle_job_cancelled(message)
                
            elif message_type == 'server_shutdown':
                await self.handle_server_shutdown(message)
                
            else:
                self.logger.warning(f"Type de message inconnu: {message_type}")
                
        except Exception as e:
            self.logger.error(f"Erreur traitement message serveur: {e}")
    
    async def send_heartbeat(self):
        """Envoie des signaux de vie au serveur"""
        while self.connected:
            try:
                # Informations système actuelles
                system_info = {}
                if self.system_monitor:
                    system_info = self.system_monitor.get_current_stats()
                
                heartbeat = {
                    'type': 'heartbeat',
                    'timestamp': time.time(),
                    'status': 'processing' if self.processing else 'idle',
                    'current_batch': self.current_batch,
                    'batches_processed': self.total_batches_processed,
                    'images_processed': self.total_images_processed,
                    'system_info': system_info
                }
                
                await self.send_message(heartbeat)
                await asyncio.sleep(30)  # Heartbeat toutes les 30 secondes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Erreur heartbeat: {e}")
                await asyncio.sleep(30)
    
    async def send_message(self, message: dict):
        """Envoie un message au serveur"""
        try:
            data = json.dumps(message).encode('utf-8')
            
            # Chiffrement si configuré
            if self.encryption_manager and self.encryption_manager.has_session_key():
                data = self.encryption_manager.encrypt_data(data)
            
            await asyncio.get_event_loop().sock_sendall(self.server_socket, data)
            
        except Exception as e:
            self.logger.error(f"Erreur envoi message: {e}")
            raise
    
    async def handle_ping(self):
        """Répond à un ping du serveur"""
        pong = {
            'type': 'pong',
            'timestamp': time.time()
        }
        await self.send_message(pong)
    
    async def handle_batch_assignment(self, message: dict):
        """Gère l'assignation d'un nouveau lot"""
        try:
            batch_id = message['batch_id']
            batch_info = message['batch_info']
            
            self.logger.info(f"Lot assigné: {batch_id}")
            
            # Stockage des informations du lot
            self.current_batch = {
                'batch_id': batch_id,
                'info': batch_info,
                'start_time': time.time(),
                'progress': 0
            }
            
            # Callback
            if self.on_batch_received:
                await self.on_batch_received(batch_id, batch_info)
            
            # Demander les données du lot
            await self.request_batch_data(batch_id)
            
        except Exception as e:
            self.logger.error(f"Erreur assignation lot: {e}")
    
    async def handle_batch_data(self, message: dict):
        """Gère la réception des données d'un lot"""
        try:
            batch_id = message['batch_id']
            encrypted_data = message['data']
            
            if not self.current_batch or self.current_batch['batch_id'] != batch_id:
                self.logger.warning(f"Lot non attendu: {batch_id}")
                return
            
            self.logger.info(f"Données reçues pour le lot {batch_id}")
            
            # Démarrage du traitement
            asyncio.create_task(self.process_batch(batch_id, encrypted_data))
            
        except Exception as e:
            self.logger.error(f"Erreur réception données lot: {e}")
    
    async def request_batch_data(self, batch_id: str):
        """Demande les données d'un lot"""
        request = {
            'type': 'batch_data_request',
            'batch_id': batch_id
        }
        await self.send_message(request)
    
    async def process_batch(self, batch_id: str, encrypted_data: str):
        """Traite un lot d'images"""
        start_time = time.time()
        self.processing = True
        
        try:
            # Préparation des dossiers
            batch_input_dir = self.received_batches_dir / batch_id
            batch_output_dir = self.processed_batches_dir / batch_id
            
            batch_input_dir.mkdir(parents=True, exist_ok=True)
            batch_output_dir.mkdir(parents=True, exist_ok=True)
            
            # Déchiffrement et extraction des images
            await self.extract_batch_data(encrypted_data, batch_input_dir)
            
            # Comptage des images
            image_files = list(batch_input_dir.glob("*.png")) + list(batch_input_dir.glob("*.jpg"))
            total_images = len(image_files)
            
            if total_images == 0:
                raise ValueError("Aucune image trouvée dans le lot")
            
            self.logger.info(f"Traitement de {total_images} images pour le lot {batch_id}")
            
            # Traitement avec Real-ESRGAN
            results = await self.realesrgan_handler.upscale_batch(
                batch_input_dir,
                batch_output_dir,
                model=self.processing_settings['model'],
                scale=self.processing_settings['scale'],
                tile_size=self.processing_settings['tile_size'],
                progress_callback=lambda p, c, t: self.report_batch_progress(batch_id, p, c, t)
            )
            
            if not results['success']:
                raise RuntimeError(f"Échec traitement: {results.get('error', 'Erreur inconnue')}")
            
            # Création du package de résultats
            result_data = await self.create_result_package(batch_output_dir, batch_id)
            
            # Envoi des résultats
            await self.send_batch_results(batch_id, result_data, results)
            
            # Mise à jour des statistiques
            self.total_batches_processed += 1
            self.total_images_processed += results['processed_images']
            
            processing_time = time.time() - start_time
            self.logger.info(
                f"Lot {batch_id} terminé en {processing_time:.1f}s "
                f"({results['processed_images']} images)"
            )
            
            # Callback
            if self.on_batch_completed:
                await self.on_batch_completed(batch_id, True, processing_time)
            
        except Exception as e:
            processing_time = time.time() - start_time
            self.logger.error(f"Erreur traitement lot {batch_id}: {e}")
            
            # Signaler l'erreur au serveur
            await self.send_batch_error(batch_id, str(e))
            
            # Callback
            if self.on_batch_completed:
                await self.on_batch_completed(batch_id, False, processing_time)
                
        finally:
            self.processing = False
            self.current_batch = None
            
            # Nettoyage des dossiers temporaires
            await self.cleanup_batch_files(batch_id)
    
    async def extract_batch_data(self, encrypted_data: str, output_dir: Path):
        """Extrait les données chiffrées d'un lot"""
        try:
            # Décodage base64 si nécessaire
            import base64
            data_bytes = base64.b64decode(encrypted_data)
            
            # Déchiffrement
            if self.encryption_manager:
                decrypted_data = self.encryption_manager.decrypt_data(data_bytes)
            else:
                decrypted_data = data_bytes
            
            # Extraction du ZIP
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_file:
                temp_file.write(decrypted_data)
                temp_zip_path = Path(temp_file.name)
            
            with zipfile.ZipFile(temp_zip_path, 'r') as zipf:
                zipf.extractall(output_dir)
            
            # Nettoyage
            temp_zip_path.unlink()
            
        except Exception as e:
            self.logger.error(f"Erreur extraction données lot: {e}")
            raise
    
    async def create_result_package(self, processed_dir: Path, batch_id: str) -> str:
        """Crée un package des résultats traités"""
        try:
            # Création du ZIP des résultats
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_file:
                temp_zip_path = Path(temp_file.name)
            
            with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_STORED) as zipf:
                # Ajout des images traitées
                for image_path in processed_dir.glob("*.png"):
                    zipf.write(image_path, image_path.name)
                
                # Métadonnées
                metadata = {
                    'batch_id': batch_id,
                    'processed_at': time.time(),
                    'client_mac': self.mac_address,
                    'processing_settings': self.processing_settings,
                    'image_count': len(list(processed_dir.glob("*.png")))
                }
                zipf.writestr('metadata.json', json.dumps(metadata))
            
            # Lecture et chiffrement
            with open(temp_zip_path, 'rb') as f:
                zip_data = f.read()
            
            if self.encryption_manager:
                encrypted_data = self.encryption_manager.encrypt_data(zip_data)
            else:
                encrypted_data = zip_data
            
            # Encodage base64 pour transport
            import base64
            result_data = base64.b64encode(encrypted_data).decode('utf-8')
            
            # Nettoyage
            temp_zip_path.unlink()
            
            return result_data
            
        except Exception as e:
            self.logger.error(f"Erreur création package résultats: {e}")
            raise
    
    async def send_batch_results(self, batch_id: str, result_data: str, processing_info: dict):
        """Envoie les résultats d'un lot au serveur"""
        message = {
            'type': 'batch_completed',
            'batch_id': batch_id,
            'result_data': result_data,
            'processing_info': processing_info,
            'client_stats': {
                'batches_processed': self.total_batches_processed,
                'images_processed': self.total_images_processed
            }
        }
        
        await self.send_message(message)
    
    async def send_batch_error(self, batch_id: str, error_message: str):
        """Signale une erreur de traitement au serveur"""
        message = {
            'type': 'batch_error',
            'batch_id': batch_id,
            'error': error_message,
            'timestamp': time.time()
        }
        
        await self.send_message(message)
    
    async def report_batch_progress(self, batch_id: str, progress: float, 
                                  current: int, total: int):
        """Rapporte la progression d'un lot"""
        if self.current_batch:
            self.current_batch['progress'] = progress
        
        # Callback
        if self.on_batch_progress:
            await self.on_batch_progress(batch_id, progress, current, total)
        
        # Rapport au serveur (pas trop fréquent)
        if current % 10 == 0 or current == total:
            message = {
                'type': 'batch_progress',
                'batch_id': batch_id,
                'progress': progress,
                'processed_count': current,
                'total_count': total
            }
            
            try:
                await self.send_message(message)
            except Exception as e:
                self.logger.debug(f"Erreur rapport progression: {e}")
    
    async def cleanup_batch_files(self, batch_id: str):
        """Nettoie les fichiers temporaires d'un lot"""
        try:
            import shutil
            
            batch_input_dir = self.received_batches_dir / batch_id
            batch_output_dir = self.processed_batches_dir / batch_id
            
            if batch_input_dir.exists():
                shutil.rmtree(batch_input_dir)
            if batch_output_dir.exists():
                shutil.rmtree(batch_output_dir)
                
        except Exception as e:
            self.logger.warning(f"Erreur nettoyage lot {batch_id}: {e}")
    
    async def batch_processor(self):
        """Processeur automatique de lots"""
        while self.connected:
            try:
                if not self.processing and self.auto_request_batches:
                    # Demander un nouveau lot
                    request = {
                        'type': 'batch_request',
                        'timestamp': time.time()
                    }
                    await self.send_message(request)
                
                await asyncio.sleep(5)  # Vérification toutes les 5 secondes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Erreur processeur lots: {e}")
                await asyncio.sleep(5)
    
    # === Méthodes d'état et configuration ===
    
    def get_client_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du client"""
        uptime = (datetime.now() - self.connection_start_time).total_seconds() if self.connection_start_time else 0
        
        stats = {
            'connected': self.connected,
            'uptime': uptime,
            'server_host': self.server_host,
            'server_port': self.server_port,
            'mac_address': self.mac_address,
            'hostname': self.hostname,
            'processing': self.processing,
            'current_batch': self.current_batch,
            'total_batches_processed': self.total_batches_processed,
            'total_images_processed': self.total_images_processed,
            'processing_settings': self.processing_settings
        }
        
        # Ajout des stats système si disponibles
        if self.system_monitor:
            stats['system_info'] = self.system_monitor.get_current_stats()
        
        return stats
    
    def set_processing_settings(self, model: str = None, scale: int = None, 
                              tile_size: int = None):
        """Configure les paramètres de traitement"""
        if model:
            self.processing_settings['model'] = model
        if scale:
            self.processing_settings['scale'] = scale
        if tile_size is not None:
            self.processing_settings['tile_size'] = tile_size
        
        self.logger.info(f"Paramètres de traitement mis à jour: {self.processing_settings}")
    
    def set_auto_request_batches(self, enabled: bool):
        """Active/désactive la demande automatique de lots"""
        self.auto_request_batches = enabled
        
        if enabled and self.connected and not self.batch_processor_task:
            self.batch_processor_task = asyncio.create_task(self.batch_processor())
        elif not enabled and self.batch_processor_task:
            self.batch_processor_task.cancel()
            self.batch_processor_task = None