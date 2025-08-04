"""
Client distribué pour l'upscaling - Version Windows
UpscalingByNetwork/client/windows/core/distributed_client.py
"""

import asyncio
import websockets
import json
import time
import uuid
import shutil
import zipfile
from pathlib import Path
from typing import Optional, Dict, List
import logging
import subprocess
import platform
import psutil

from ..utils.upscaler import RealESRGANUpscaler
from ..utils.system_info import SystemInfo
from ....shared.protocol.messages import NetworkMessage, MessageType
from ....shared.utils.mac_address import get_primary_mac_address


class DistributedClient:
    """Client distribué pour Windows"""
    
    def __init__(self):
        self.mac_address = get_primary_mac_address()
        self.client_id = str(uuid.uuid4())
        
        # État de connexion
        self.connected = False
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.server_host = ""
        self.server_port = 8888
        
        # État de traitement
        self.current_batch_id: Optional[str] = None
        self.processing = False
        self.current_progress = 0.0
        
        # Statistiques
        self.batches_completed = 0
        self.total_processing_time = 0.0
        self.images_processed = 0
        
        # Configuration
        self.work_dir = Path("client_work")
        self.temp_dir = self.work_dir / "temp"
        self.received_dir = self.temp_dir / "received_batches"
        self.processed_dir = self.temp_dir / "processed_batches"
        self.logs_dir = self.work_dir / "logs"
        
        # Gestionnaires
        self.upscaler = RealESRGANUpscaler()
        self.system_info = SystemInfo()
        
        # Clés de sécurité
        self.session_keys: Dict[str, bytes] = {}  # batch_id -> session_key
        
        # Configuration Real-ESRGAN
        self.realesrgan_model = "realesr-animevideov3"
        self.realesrgan_scale = 4
        self.tile_size = 256
        self.gpu_id = 0
        
        self.setup_directories()
        self.setup_logging()
        
        # Callbacks pour l'interface graphique
        self.on_connection_changed = None
        self.on_batch_received = None
        self.on_progress_update = None
        self.on_batch_completed = None
        self.on_error = None
    
    def setup_directories(self):
        """Crée les dossiers de travail"""
        for directory in [self.work_dir, self.temp_dir, self.received_dir, 
                         self.processed_dir, self.logs_dir]:
            directory.mkdir(parents=True, exist_ok=True)
    
    def setup_logging(self):
        """Configure le logging"""
        log_file = self.logs_dir / f"client_{time.strftime('%Y%m%d')}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Log des informations système au démarrage
        self.logger.info(f"Client démarré - MAC: {self.mac_address}")
        self.logger.info(f"Système: {platform.system()} {platform.release()}")
        self.logger.info(f"CPU: {psutil.cpu_count()} cœurs")
        self.logger.info(f"RAM: {psutil.virtual_memory().total // (1024**3)} GB")
    
    async def connect_to_server(self, host: str, port: int) -> bool:
        """Se connecte au serveur"""
        try:
            self.server_host = host
            self.server_port = port
            
            self.logger.info(f"Connexion au serveur {host}:{port}...")
            
            # Connexion WebSocket
            uri = f"ws://{host}:{port}"
            self.websocket = await websockets.connect(uri)
            
            # Authentification
            auth_success = await self.authenticate()
            if not auth_success:
                await self.websocket.close()
                return False
            
            self.connected = True
            
            # Démarrage des tâches
            asyncio.create_task(self.message_handler())
            asyncio.create_task(self.heartbeat_sender())
            
            self.logger.info("Connexion établie avec succès")
            
            if self.on_connection_changed:
                self.on_connection_changed(True, f"Connecté à {host}:{port}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur connexion: {e}")
            if self.on_error:
                self.on_error(f"Connexion échouée: {e}")
            return False
    
    async def authenticate(self) -> bool:
        """S'authentifie auprès du serveur"""
        try:
            # Envoi du message de connexion
            connect_message = NetworkMessage(
                type=MessageType.CLIENT_CONNECT,
                client_mac=self.mac_address,
                timestamp=time.time(),
                data={
                    'client_id': self.client_id,
                    'mac_address': self.mac_address,
                    'system_info': self.system_info.get_system_info(),
                    'capabilities': {
                        'real_esrgan': self.upscaler.is_available(),
                        'gpu_count': self.system_info.get_gpu_count(),
                        'cpu_cores': psutil.cpu_count(),
                        'ram_gb': psutil.virtual_memory().total // (1024**3)
                    }
                }
            )
            
            await self.websocket.send(connect_message.to_json())
            
            # Attente de la réponse
            response = await asyncio.wait_for(self.websocket.recv(), timeout=30)
            response_data = json.loads(response)
            
            if response_data.get('type') == 'handshake_init':
                # Handshake sécurisé
                return await self.complete_handshake(response_data)
            
            return False
            
        except Exception as e:
            self.logger.error(f"Erreur authentification: {e}")
            return False
    
    async def complete_handshake(self, handshake_data: dict) -> bool:
        """Complète le handshake sécurisé"""
        try:
            # Pour simplifier, on accepte la connexion
            # Dans une implémentation complète, il faudrait gérer RSA ici
            
            handshake_response = NetworkMessage(
                type=MessageType.HANDSHAKE_RESPONSE,
                client_mac=self.mac_address,
                timestamp=time.time(),
                data={'status': 'accepted'}
            )
            
            await self.websocket.send(handshake_response.to_json())
            
            # Attente de confirmation
            confirmation = await asyncio.wait_for(self.websocket.recv(), timeout=10)
            conf_data = json.loads(confirmation)
            
            return conf_data.get('type') == 'status_update' and conf_data.get('data', {}).get('status') == 'connected'
            
        except Exception as e:
            self.logger.error(f"Erreur handshake: {e}")
            return False
    
    async def disconnect(self):
        """Se déconnecte du serveur"""
        if self.connected and self.websocket:
            try:
                # Message de déconnexion
                disconnect_message = NetworkMessage(
                    type=MessageType.CLIENT_DISCONNECT,
                    client_mac=self.mac_address,
                    timestamp=time.time(),
                    data={'reason': 'user_disconnect'}
                )
                
                await self.websocket.send(disconnect_message.to_json())
                await self.websocket.close()
                
            except Exception as e:
                self.logger.error(f"Erreur déconnexion: {e}")
        
        self.connected = False
        self.websocket = None
        
        if self.on_connection_changed:
            self.on_connection_changed(False, "Déconnecté")
        
        self.logger.info("Déconnecté du serveur")
    
    async def message_handler(self):
        """Gestionnaire des messages reçus"""
        try:
            async for message_str in self.websocket:
                await self.handle_message(message_str)
        except websockets.exceptions.ConnectionClosed:
            self.logger.info("Connexion fermée par le serveur")
            self.connected = False
            if self.on_connection_changed:
                self.on_connection_changed(False, "Connexion fermée")
        except Exception as e:
            self.logger.error(f"Erreur handler messages: {e}")
            self.connected = False
            if self.on_error:
                self.on_error(f"Erreur communication: {e}")
    
    async def handle_message(self, message_str: str):
        """Traite un message reçu"""
        try:
            message = NetworkMessage.from_json(message_str)
            
            if message.type == MessageType.BATCH_ASSIGNMENT:
                await self.handle_batch_assignment(message)
            elif message.type == MessageType.STATUS_UPDATE:
                await self.handle_status_update(message)
            elif message.type == MessageType.ERROR:
                await self.handle_error(message)
            else:
                self.logger.warning(f"Message non géré: {message.type}")
                
        except Exception as e:
            self.logger.error(f"Erreur traitement message: {e}")
    
    async def handle_batch_assignment(self, message: NetworkMessage):
        """Traite l'assignation d'un lot"""
        try:
            data = message.data
            batch_id = data['batch_id']
            encrypted_data_hex = data['encrypted_data']
            frame_count = data['frame_count']
            job_id = data['job_id']
            
            self.logger.info(f"Lot reçu: {batch_id} ({frame_count} images)")
            
            # Conversion hex vers bytes
            encrypted_data = bytes.fromhex(encrypted_data_hex)
            
            # Acceptation du lot
            accept_message = NetworkMessage(
                type=MessageType.BATCH_ACCEPTED,
                client_mac=self.mac_address,
                timestamp=time.time(),
                data={'batch_id': batch_id}
            )
            
            await self.websocket.send(accept_message.to_json())
            
            # Traitement du lot
            self.current_batch_id = batch_id
            self.processing = True
            
            if self.on_batch_received:
                self.on_batch_received(batch_id, frame_count)
            
            # Traitement asynchrone
            asyncio.create_task(self.process_batch(batch_id, encrypted_data, frame_count))
            
        except Exception as e:
            self.logger.error(f"Erreur traitement assignation lot: {e}")
            if self.on_error:
                self.on_error(f"Erreur réception lot: {e}")
    
    async def process_batch(self, batch_id: str, encrypted_data: bytes, frame_count: int):
        """Traite un lot d'images"""
        start_time = time.time()
        
        try:
            self.logger.info(f"Début traitement lot {batch_id}")
            
            # Création du dossier de traitement
            batch_dir = self.received_dir / batch_id
            input_dir = batch_dir / "input"
            output_dir = batch_dir / "output"
            
            for directory in [batch_dir, input_dir, output_dir]:
                directory.mkdir(parents=True, exist_ok=True)
            
            # Déchiffrement (simplifié pour l'exemple)
            # Dans la réalité, il faudrait utiliser la clé de session
            await self.decrypt_and_extract_batch(encrypted_data, input_dir)
            
            # Vérification des fichiers reçus
            input_files = list(input_dir.glob("*.png"))
            if len(input_files) != frame_count:
                raise Exception(f"Nombre de fichiers incorrect: {len(input_files)}/{frame_count}")
            
            # Traitement avec Real-ESRGAN
            await self.run_upscaling(input_dir, output_dir, batch_id)
            
            # Vérification des résultats
            output_files = list(output_dir.glob("*.png"))
            if len(output_files) != len(input_files):
                raise Exception(f"Traitement incomplet: {len(output_files)}/{len(input_files)}")
            
            # Compression et chiffrement des résultats
            result_data = await self.compress_and_encrypt_results(output_dir)
            
            # Envoi des résultats
            processing_time = time.time() - start_time
            
            completion_message = NetworkMessage(
                type=MessageType.BATCH_COMPLETED,
                client_mac=self.mac_address,
                timestamp=time.time(),
                data={
                    'batch_id': batch_id,
                    'encrypted_result': result_data.hex(),
                    'processing_time': processing_time,
                    'frames_processed': len(output_files)
                }
            )
            
            await self.websocket.send(completion_message.to_json())
            
            # Mise à jour des statistiques
            self.batches_completed += 1
            self.total_processing_time += processing_time
            self.images_processed += len(output_files)
            
            self.logger.info(f"Lot {batch_id} terminé en {processing_time:.1f}s")
            
            if self.on_batch_completed:
                self.on_batch_completed(batch_id, processing_time, len(output_files))
            
            # Nettoyage
            await self.cleanup_batch_files(batch_dir)
            
        except Exception as e:
            self.logger.error(f"Erreur traitement lot {batch_id}: {e}")
            
            # Signaler l'échec
            failure_message = NetworkMessage(
                type=MessageType.BATCH_FAILED,
                client_mac=self.mac_address,
                timestamp=time.time(),
                data={
                    'batch_id': batch_id,
                    'error': str(e),
                    'processing_time': time.time() - start_time
                }
            )
            
            await self.websocket.send(failure_message.to_json())
            
            if self.on_error:
                self.on_error(f"Échec traitement lot {batch_id}: {e}")
        
        finally:
            self.current_batch_id = None
            self.processing = False
            self.current_progress = 0.0
    
    async def decrypt_and_extract_batch(self, encrypted_data: bytes, output_dir: Path):
        """Déchiffre et extrait un lot"""
        try:
            # Déchiffrement simplifié (à implémenter avec la vraie clé)
            # Pour l'instant, on suppose que les données ne sont pas chiffrées
            zip_data = encrypted_data
            
            # Extraction du ZIP
            zip_path = output_dir.parent / "batch.zip"
            with open(zip_path, 'wb') as f:
                f.write(zip_data)
            
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(output_dir)
            
            # Suppression du ZIP temporaire
            zip_path.unlink()
            
        except Exception as e:
            raise Exception(f"Erreur déchiffrement/extraction: {e}")
    
    async def run_upscaling(self, input_dir: Path, output_dir: Path, batch_id: str):
        """Exécute l'upscaling avec Real-ESRGAN"""
        try:
            # Vérification de Real-ESRGAN
            if not self.upscaler.is_available():
                raise Exception("Real-ESRGAN non disponible")
            
            # Construction de la commande
            realesrgan_path = Path("realesrgan-ncnn-vulkan") / "realesrgan-ncnn-vulkan.exe"
            
            if not realesrgan_path.exists():
                raise Exception(f"Real-ESRGAN non trouvé: {realesrgan_path}")
            
            cmd = [
                str(realesrgan_path),
                "-i", str(input_dir),
                "-o", str(output_dir),
                "-n", self.realesrgan_model,
                "-s", str(self.realesrgan_scale),
                "-t", str(self.tile_size),
                "-g", str(self.gpu_id)
            ]
            
            self.logger.info(f"Commande upscaling: {' '.join(cmd)}")
            
            # Exécution avec suivi de progression
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Suivi de la progression (basique)
            input_files = list(input_dir.glob("*.png"))
            total_files = len(input_files)
            
            while process.returncode is None:
                await asyncio.sleep(1)
                
                # Estimation de la progression
                output_files = list(output_dir.glob("*.png"))
                progress = (len(output_files) / total_files) * 100 if total_files > 0 else 0
                
                if progress != self.current_progress:
                    self.current_progress = progress
                    
                    # Envoi de la progression
                    progress_message = NetworkMessage(
                        type=MessageType.BATCH_PROGRESS,
                        client_mac=self.mac_address,
                        timestamp=time.time(),
                        data={
                            'batch_id': batch_id,
                            'progress': progress,
                            'current_frame': len(output_files)
                        }
                    )
                    
                    await self.websocket.send(progress_message.to_json())
                    
                    if self.on_progress_update:
                        self.on_progress_update(batch_id, progress, len(output_files))
            
            # Attente de la fin du processus
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore')
                raise Exception(f"Erreur Real-ESRGAN (code {process.returncode}): {error_msg}")
            
            self.logger.info(f"Upscaling terminé pour le lot {batch_id}")
            
        except Exception as e:
            raise Exception(f"Erreur upscaling: {e}")
    
    async def compress_and_encrypt_results(self, output_dir: Path) -> bytes:
        """Compresse et chiffre les résultats"""
        try:
            # Création du ZIP des résultats
            zip_path = self.processed_dir / f"result_{int(time.time())}.zip"
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zf:
                for png_file in output_dir.glob("*.png"):
                    zf.write(png_file, png_file.name)
            
            # Lecture du fichier ZIP
            with open(zip_path, 'rb') as f:
                zip_data = f.read()
            
            # Chiffrement (simplifié)
            # Dans la réalité, utiliser la clé de session
            encrypted_data = zip_data
            
            # Suppression du ZIP temporaire
            zip_path.unlink()
            
            return encrypted_data
            
        except Exception as e:
            raise Exception(f"Erreur compression/chiffrement: {e}")
    
    async def cleanup_batch_files(self, batch_dir: Path):
        """Nettoie les fichiers temporaires d'un lot"""
        try:
            if batch_dir.exists():
                shutil.rmtree(batch_dir)
            self.logger.debug(f"Nettoyage terminé: {batch_dir}")
        except Exception as e:
            self.logger.warning(f"Erreur nettoyage {batch_dir}: {e}")
    
    async def heartbeat_sender(self):
        """Envoie des heartbeats au serveur"""
        while self.connected:
            try:
                heartbeat = NetworkMessage(
                    type=MessageType.HEARTBEAT,
                    client_mac=self.mac_address,
                    timestamp=time.time(),
                    data={
                        'status': 'processing' if self.processing else 'idle',
                        'current_batch': self.current_batch_id,
                        'progress': self.current_progress,
                        'system_load': {
                            'cpu_percent': psutil.cpu_percent(),
                            'memory_percent': psutil.virtual_memory().percent,
                            'disk_usage': psutil.disk_usage('.').percent
                        }
                    }
                )
                
                await self.websocket.send(heartbeat.to_json())
                await asyncio.sleep(30)  # Heartbeat toutes les 30 secondes
                
            except Exception as e:
                self.logger.error(f"Erreur heartbeat: {e}")
                break
    
    async def handle_status_update(self, message: NetworkMessage):
        """Traite une mise à jour de statut"""
        status = message.data.get('status')
        self.logger.info(f"Statut serveur: {status}")
    
    async def handle_error(self, message: NetworkMessage):
        """Traite un message d'erreur"""
        error = message.data.get('error', 'Erreur inconnue')
        self.logger.error(f"Erreur serveur: {error}")
        if self.on_error:
            self.on_error(f"Serveur: {error}")
    
    def get_stats(self) -> dict:
        """Retourne les statistiques du client"""
        return {
            'connected': self.connected,
            'mac_address': self.mac_address,
            'batches_completed': self.batches_completed,
            'images_processed': self.images_processed,
            'total_processing_time': self.total_processing_time,
            'current_batch': self.current_batch_id,
            'processing': self.processing,
            'current_progress': self.current_progress,
            'avg_processing_time': (self.total_processing_time / self.batches_completed) if self.batches_completed > 0 else 0,
            'system_info': self.system_info.get_system_info(),
            'upscaler_available': self.upscaler.is_available()
        }
    
    def get_connection_info(self) -> dict:
        """Retourne les informations de connexion"""
        return {
            'connected': self.connected,
            'server_host': self.server_host,
            'server_port': self.server_port,
            'mac_address': self.mac_address
        }

# Test du client
if __name__ == "__main__":
    async def test_client():
        client = DistributedClient()
        
        # Test de connexion
        success = await client.connect_to_server("localhost", 8888)
        if success:
            print("Connexion réussie")
            await asyncio.sleep(60)  # Attendre 1 minute
            await client.disconnect()
        else:
            print("Connexion échouée")
    
    asyncio.run(test_client())