"""
Serveur principal pour l'upscaling distribué
UpscalingByNetwork/server/core/distributed_server.py
"""

import asyncio
import websockets
import json
import time
import uuid
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Set
import logging
from dataclasses import asdict

from ..models.distributed_job import DistributedJob, JobStatus
from ..models.network_batch import NetworkBatch, BatchStatus  
from ..models.remote_client import RemoteClient, ClientStatus
from ..utils.encryption import SecurityManager
from ..utils.compression import BatchCompressor
from ..utils.wan_protocol import WANProtocol
from ...shared.protocol.messages import NetworkMessage, MessageType
from ...shared.utils.mac_address import get_mac_from_connection

class DistributedServer:
    """Serveur principal pour la distribution d'upscaling"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8888):
        self.host = host
        self.port = port
        self.running = False
        
        # Collections principales
        self.jobs: Dict[str, DistributedJob] = {}
        self.batches: Dict[str, NetworkBatch] = {}
        self.clients: Dict[str, RemoteClient] = {}  # MAC -> Client
        self.websockets: Dict[str, websockets.WebSocketServerProtocol] = {}  # MAC -> WebSocket
        
        # Gestionnaires
        self.security_manager = SecurityManager()
        self.compressor = BatchCompressor()
        self.wan_protocol = WANProtocol()
        
        # Configuration
        self.batch_size = 50
        self.max_retries = 3
        self.duplicate_threshold = 5
        self.heartbeat_interval = 30
        self.client_timeout = 120
        
        # Statistiques
        self.stats = {
            'total_jobs': 0,
            'total_batches': 0,
            'completed_batches': 0,
            'failed_batches': 0,
            'active_clients': 0,
            'uptime': 0
        }
        
        # Dossiers de travail
        self.work_dir = Path("server_work")
        self.jobs_dir = self.work_dir / "jobs"
        self.temp_dir = self.work_dir / "temp"
        
        self.setup_directories()
        self.setup_logging()
        
        # Job actuel (pour traitement local si nécessaire)
        self.current_job_id: Optional[str] = None
        
        # Flag pour traitement local du serveur
        self.server_can_process = True
    
    def setup_directories(self):
        """Crée les dossiers de travail"""
        for directory in [self.work_dir, self.jobs_dir, self.temp_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Dossiers pour sécurité
        (self.temp_dir / "encryption_keys").mkdir(exist_ok=True)
        (self.temp_dir / "client_sessions").mkdir(exist_ok=True)
    
    def setup_logging(self):
        """Configure le logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
    
    async def start_server(self):
        """Démarre le serveur WebSocket"""
        self.logger.info(f"Démarrage du serveur sur {self.host}:{self.port}")
        self.running = True
        self.stats['uptime'] = time.time()
        
        # Démarrage des tâches de background
        asyncio.create_task(self.heartbeat_monitor())
        asyncio.create_task(self.batch_distributor())
        asyncio.create_task(self.cleanup_task())
        
        # Serveur WebSocket
        async with websockets.serve(self.handle_client, self.host, self.port):
            self.logger.info("Serveur démarré, en attente de connexions...")
            await asyncio.Future()  # Run forever
    
    async def handle_client(self, websocket, path):
        """Gère une connexion client"""
        client_mac = None
        try:
            # Authentification et identification du client
            client_mac = await self.authenticate_client(websocket)
            if not client_mac:
                await websocket.close(1000, "Authentification échouée")
                return
            
            # Enregistrement du client
            await self.register_client(client_mac, websocket)
            
            # Boucle de traitement des messages
            async for message in websocket:
                await self.handle_message(client_mac, message)
                
        except websockets.exceptions.ConnectionClosed:
            self.logger.info(f"Client {client_mac} déconnecté")
        except Exception as e:
            self.logger.error(f"Erreur connexion client {client_mac}: {e}")
        finally:
            if client_mac:
                await self.disconnect_client(client_mac)
    
    async def authenticate_client(self, websocket) -> Optional[str]:
        """Authentifie un client et retourne son adresse MAC"""
        try:
            # Réception du message de connexion
            message_str = await asyncio.wait_for(websocket.recv(), timeout=30)
            message_data = json.loads(message_str)
            
            if message_data.get('type') != 'client_connect':
                return None
            
            client_mac = message_data.get('mac_address')
            if not client_mac:
                return None
            
            # Handshake sécurisé
            session_key = await self.security_manager.handshake_with_client(client_mac, websocket)
            if not session_key:
                return None
            
            self.logger.info(f"Client authentifié: {client_mac}")
            return client_mac
            
        except Exception as e:
            self.logger.error(f"Erreur authentification: {e}")
            return None
    
    async def register_client(self, client_mac: str, websocket):
        """Enregistre un nouveau client"""
        # Création/mise à jour du client
        if client_mac in self.clients:
            client = self.clients[client_mac]
            client.reconnect()
        else:
            client = RemoteClient(mac_address=client_mac)
            self.clients[client_mac] = client
        
        # Stockage de la WebSocket
        self.websockets[client_mac] = websocket
        
        # Notification de connexion
        await self.send_message(client_mac, NetworkMessage(
            type=MessageType.STATUS_UPDATE,
            client_mac=client_mac,
            timestamp=time.time(),
            data={'status': 'connected', 'server_version': '1.0'}
        ))
        
        self.stats['active_clients'] = len([c for c in self.clients.values() if c.is_online])
        self.logger.info(f"Client {client_mac} enregistré. Total: {self.stats['active_clients']}")
    
    async def disconnect_client(self, client_mac: str):
        """Déconnecte un client"""
        if client_mac in self.clients:
            client = self.clients[client_mac]
            
            # Libération du lot en cours
            if client.current_batch_id:
                await self.release_batch(client.current_batch_id, "Client déconnecté")
            
            client.disconnect()
        
        # Suppression de la WebSocket
        if client_mac in self.websockets:
            del self.websockets[client_mac]
        
        self.stats['active_clients'] = len([c for c in self.clients.values() if c.is_online])
        self.logger.info(f"Client {client_mac} déconnecté")
    
    async def handle_message(self, client_mac: str, message_str: str):
        """Traite un message reçu d'un client"""
        try:
            message = NetworkMessage.from_json(message_str)
            client = self.clients.get(client_mac)
            
            if not client:
                return
            
            client.last_activity = time.time()
            
            # Dispatch selon le type de message
            if message.type == MessageType.HEARTBEAT:
                await self.handle_heartbeat(client_mac, message)
            elif message.type == MessageType.BATCH_ACCEPTED:
                await self.handle_batch_accepted(client_mac, message)
            elif message.type == MessageType.BATCH_PROGRESS:
                await self.handle_batch_progress(client_mac, message)
            elif message.type == MessageType.BATCH_COMPLETED:
                await self.handle_batch_completed(client_mac, message)
            elif message.type == MessageType.BATCH_FAILED:
                await self.handle_batch_failed(client_mac, message)
            else:
                self.logger.warning(f"Message non géré: {message.type}")
                
        except Exception as e:
            self.logger.error(f"Erreur traitement message de {client_mac}: {e}")
    
    async def create_distributed_job(self, video_path: str):
        """Crée un job pour traitement distribué"""
        
        # 1. Extraction des frames
        job_id = str(uuid.uuid4())
        frames_dir = f"jobs/{job_id}/frames"
        
        # FFmpeg : extraction frames
        await self.extract_frames(video_path, frames_dir)
        
        # 2. Découpage en lots de 50 images
        frame_files = sorted(Path(frames_dir).glob("*.png"))
        
        batches = []
        for i in range(0, len(frame_files), 50):
            batch_frames = frame_files[i:i+50]
            batch_id = f"batch_{i//50 + 1:03d}"
            
            # Création du dossier batch
            batch_dir = f"jobs/{job_id}/batches/{batch_id}"
            
            # Copie des images dans le batch
            for frame in batch_frames:
                shutil.copy(frame, f"{batch_dir}/input/")
            
            # Création du ZIP (compression 0)
            zip_path = f"{batch_dir}/{batch_id}.zip"
            self.create_batch_zip(f"{batch_dir}/input", zip_path)
            
            batches.append({
                'id': batch_id,
                'status': 'pending',
                'zip_path': zip_path,
                'frame_count': len(batch_frames)
            })
        
        return job_id, batches
    
    async def extract_frames_and_create_batches(self, job_id: str) -> bool:
        """Extrait les frames et crée les lots"""
        try:
            if job_id not in self.jobs:
                raise ValueError(f"Job {job_id} non trouvé")
            
            job = self.jobs[job_id]
            job.status = JobStatus.EXTRACTING
            
            job_dir = self.jobs_dir / job_id
            frames_dir = job_dir / 'frames'
            
            # Extraction des frames avec FFmpeg
            ffmpeg_cmd = [
                "ffmpeg/ffmpeg.exe",
                "-i", str(job_dir / 'input' / Path(job.input_video_path).name),
                "-q:v", "1",
                str(frames_dir / "frame_%06d.png"),
                "-loglevel", "quiet"
            ]
            
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise Exception(f"Erreur FFmpeg: {stderr.decode()}")
            
            # Comptage des frames
            frame_files = sorted(list(frames_dir.glob("frame_*.png")))
            job.total_frames = len(frame_files)
            
            if job.total_frames == 0:
                raise Exception("Aucune frame extraite")
            
            # Extraction de l'audio
            await self.extract_audio(job_id)
            
            # Création des lots
            await self.create_batches_from_frames(job_id, frame_files)
            
            job.status = JobStatus.PROCESSING
            job.start_time = time.time()
            
            self.logger.info(f"Job {job_id}: {job.total_frames} frames, {len(job.batch_ids)} lots")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur extraction/création lots: {e}")
            if job_id in self.jobs:
                self.jobs[job_id].fail(str(e))
            return False
    
    async def create_batches_from_frames(self, job_id: str, frame_files: List[Path]):
        """Crée les lots à partir des frames"""
        job = self.jobs[job_id]
        job_dir = self.jobs_dir / job_id
        batches_dir = job_dir / 'batches'
        
        batch_ids = []
        
        for i in range(0, len(frame_files), self.batch_size):
            batch_frames = frame_files[i:i + self.batch_size]
            batch_id = f"{job_id}_batch_{len(batch_ids):03d}"
            
            # Création du lot
            batch = NetworkBatch(
                id=batch_id,
                job_id=job_id,
                frame_start=i,
                frame_end=min(i + self.batch_size - 1, len(frame_files) - 1),
                frame_paths=[str(f) for f in batch_frames]
            )
            
            # Dossiers du lot
            batch_dir = batches_dir / batch_id
            input_dir = batch_dir / 'input'
            output_dir = batch_dir / 'output'
            
            for directory in [input_dir, output_dir]:
                directory.mkdir(parents=True, exist_ok=True)
            
            # Copie des frames dans le lot
            for frame_file in batch_frames:
                shutil.copy2(frame_file, input_dir / frame_file.name)
            
            # Création du ZIP (compression 0 pour les images)
            zip_path = batch_dir / f"{batch_id}.zip"
            await self.compressor.create_batch_zip(input_dir, zip_path)
            
            batch.zip_path = str(zip_path)
            
            self.batches[batch_id] = batch
            batch_ids.append(batch_id)
        
        job.batch_ids = batch_ids
        self.stats['total_batches'] += len(batch_ids)
    
    async def extract_audio(self, job_id: str):
        """Extrait l'audio de la vidéo"""
        job = self.jobs[job_id]
        job_dir = self.jobs_dir / job_id
        
        input_video = job_dir / 'input' / Path(job.input_video_path).name
        audio_output = job_dir / 'audio' / 'audio.aac'
        
        ffmpeg_cmd = [
            "ffmpeg/ffmpeg.exe",
            "-i", str(input_video),
            "-vn", "-acodec", "aac", "-b:a", "192k",
            str(audio_output),
            "-loglevel", "error"
        ]
        
        process = await asyncio.create_subprocess_exec(*ffmpeg_cmd)
        await process.communicate()
        
        if audio_output.exists():
            job.has_audio = True
            job.audio_path = str(audio_output)
    
    async def batch_distributor(self):
        """Distribue les lots aux clients disponibles"""
        while self.running:
            try:
                await self.distribute_pending_batches()
                await asyncio.sleep(2)  # Vérification toutes les 2 secondes
            except Exception as e:
                self.logger.error(f"Erreur distributeur de lots: {e}")
                await asyncio.sleep(5)
    
    async def distribute_pending_batches(self):
        """Distribue les lots en attente"""
        # Clients disponibles
        available_clients = [
            mac for mac, client in self.clients.items()
            if client.is_online and client.status == ClientStatus.IDLE
        ]
        
        if not available_clients:
            return
        
        # Lots en attente
        pending_batches = [
            batch for batch in self.batches.values()
            if batch.status == BatchStatus.PENDING
        ]
        
        if not pending_batches:
            # Si le serveur peut traiter et qu'il n'y a pas de lots en attente
            if self.server_can_process:
                await self.process_local_batches()
            return
        
        # Tri par priorité (plus anciens en premier)
        pending_batches.sort(key=lambda b: b.created_at)
        
        # Gestion des doublons si nécessaire
        if (len(pending_batches) < self.duplicate_threshold and 
            len(available_clients) > len(pending_batches)):
            
            for client_mac in available_clients[len(pending_batches):]:
                # Création de doublons des lots les plus anciens
                original_batch = pending_batches[0]
                duplicate_batch = await self.create_duplicate_batch(original_batch)
                if duplicate_batch:
                    pending_batches.append(duplicate_batch)
                    if len(pending_batches) >= len(available_clients):
                        break
        
        # Attribution des lots
        assignments = list(zip(available_clients, pending_batches[:len(available_clients)]))
        
        for client_mac, batch in assignments:
            await self.assign_batch_to_client(client_mac, batch)
    
    async def assign_batch_to_client(self, client_mac: str, batch: NetworkBatch):
        """Assigne un lot à un client"""
        try:
            client = self.clients[client_mac]
            
            # Génération de la clé de session pour ce lot
            session_key = self.security_manager.generate_session_key()
            
            # Chiffrement du lot
            with open(batch.zip_path, 'rb') as f:
                zip_data = f.read()
            
            encrypted_data = self.security_manager.encrypt_batch(zip_data, session_key)
            
            # Stockage de la clé pour ce client/lot
            self.security_manager.store_session_key(client_mac, batch.id, session_key)
            
            # Mise à jour des statuts
            batch.assign_to_client(client_mac)
            client.assign_batch(batch.id)
            
            # Envoi du lot
            message = NetworkMessage(
                type=MessageType.BATCH_ASSIGNMENT,
                client_mac=client_mac,
                timestamp=time.time(),
                data={
                    'batch_id': batch.id,
                    'encrypted_data': encrypted_data.hex(),
                    'frame_count': len(batch.frame_paths),
                    'job_id': batch.job_id
                }
            )
            
            await self.send_message(client_mac, message)
            self.logger.info(f"Lot {batch.id} assigné au client {client_mac}")
            
        except Exception as e:
            self.logger.error(f"Erreur assignation lot {batch.id} à {client_mac}: {e}")
            # Libération du lot en cas d'erreur
            await self.release_batch(batch.id, f"Erreur assignation: {e}")
    
    async def process_local_batches(self):
        """Traite les lots localement si le serveur peut traiter"""
        if not self.current_job_id or self.current_job_id not in self.jobs:
            return
        
        job = self.jobs[self.current_job_id]
        
        # Recherche d'un lot à traiter localement
        pending_batch = None
        for batch_id in job.batch_ids:
            batch = self.batches.get(batch_id)
            if batch and batch.status == BatchStatus.PENDING:
                pending_batch = batch
                break
        
        if not pending_batch:
            return
        
        # Traitement local du lot
        await self.process_batch_locally(pending_batch)
    
    async def process_batch_locally(self, batch: NetworkBatch):
        """Traite un lot localement sur le serveur"""
        try:
            self.logger.info(f"Traitement local du lot {batch.id}")
            
            batch.status = BatchStatus.PROCESSING
            batch.assigned_client = "SERVER"
            batch.start_time = time.time()
            
            job_dir = self.jobs_dir / batch.job_id
            batch_dir = job_dir / 'batches' / batch.id
            
            input_dir = batch_dir / 'input'
            output_dir = batch_dir / 'output'
            
            # Traitement avec Real-ESRGAN
            realesrgan_cmd = [
                "realesrgan-ncnn-vulkan/realesrgan-ncnn-vulkan.exe",
                "-i", str(input_dir),
                "-o", str(output_dir),
                "-n", "realesr-animevideov3",
                "-s", "4",
                "-t", "256",
                "-g", "0"
            ]
            
            process = await asyncio.create_subprocess_exec(
                *realesrgan_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise Exception(f"Erreur Real-ESRGAN: {stderr.decode()}")
            
            # Vérification des résultats
            input_files = list(input_dir.glob("*.png"))
            output_files = list(output_dir.glob("*.png"))
            
            if len(output_files) != len(input_files):
                raise Exception(f"Traitement incomplet: {len(output_files)}/{len(input_files)}")
            
            # Succès
            await self.complete_batch_processing(batch.id, "SERVER", output_dir)
            
        except Exception as e:
            self.logger.error(f"Erreur traitement local lot {batch.id}: {e}")
            await self.handle_batch_failure(batch.id, "SERVER", str(e))
    
    async def send_message(self, client_mac: str, message: NetworkMessage):
        """Envoie un message à un client"""
        if client_mac not in self.websockets:
            return False
        
        try:
            websocket = self.websockets[client_mac]
            await websocket.send(message.to_json())
            return True
        except Exception as e:
            self.logger.error(f"Erreur envoi message à {client_mac}: {e}")
            return False
    
    # Autres méthodes pour le heartbeat, cleanup, etc.
    async def heartbeat_monitor(self):
        """Surveille les heartbeats des clients"""
        while self.running:
            try:
                current_time = time.time()
                
                for mac, client in list(self.clients.items()):
                    if client.is_online and (current_time - client.last_activity) > self.client_timeout:
                        self.logger.warning(f"Client {mac} timeout")
                        await self.disconnect_client(mac)
                
                await asyncio.sleep(self.heartbeat_interval)
                
            except Exception as e:
                self.logger.error(f"Erreur monitor heartbeat: {e}")
                await asyncio.sleep(10)
    
    async def cleanup_task(self):
        """Tâche de nettoyage périodique"""
        while self.running:
            try:
                # Nettoyage des lots échoués, etc.
                await asyncio.sleep(300)  # Toutes les 5 minutes
            except Exception as e:
                self.logger.error(f"Erreur cleanup: {e}")
    
    def get_stats(self) -> dict:
        """Retourne les statistiques du serveur"""
        self.stats['active_clients'] = len([c for c in self.clients.values() if c.is_online])
        self.stats['uptime'] = time.time() - self.stats['uptime'] if self.running else 0
        
        return self.stats.copy()
    
    def get_clients_status(self) -> Dict[str, dict]:
        """Retourne le statut de tous les clients"""
        return {
            mac: {
                'status': client.status.value,
                'is_online': client.is_online,
                'current_batch': client.current_batch_id,
                'batches_completed': client.batches_completed,
                'current_progress': client.current_progress,
                'last_activity': client.last_activity,
                'total_processing_time': client.total_processing_time
            }
            for mac, client in self.clients.items()
        }
    
    async def stop_server(self):
        """Arrête le serveur"""
        self.logger.info("Arrêt du serveur...")
        self.running = False
        
        # Déconnexion de tous les clients
        for client_mac in list(self.clients.keys()):
            await self.disconnect_client(client_mac)
        
        self.logger.info("Serveur arrêté")

# Point d'entrée pour test
if __name__ == "__main__":
    server = DistributedServer()
    asyncio.run(server.start_server())