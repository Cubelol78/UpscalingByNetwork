# UpscalingByNetwork/server/core/distributed_server.py
"""
Serveur distribué pour l'upscaling de vidéos
Gère les clients, les lots, le chiffrement et la distribution du travail
"""

import asyncio
import logging
import json
import time
import hashlib
import zipfile
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import uuid

# Imports pour le réseau et le chiffrement
import socket
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend
import os

# Import conditionnel pour FFmpeg et utils
try:
    from ..utils.ffmpeg_handler import FFmpegHandler
    from ..utils.realesrgan_handler import RealESRGANHandler
    from ..utils.encryption_manager import EncryptionManager
except ImportError:
    # Fallback pour les tests
    FFmpegHandler = None
    RealESRGANHandler = None
    EncryptionManager = None

@dataclass
class ClientInfo:
    """Informations sur un client connecté"""
    mac_address: str
    hostname: str
    ip_address: str
    port: int
    connected_at: datetime
    last_seen: datetime
    status: str  # "idle", "processing", "disconnected"
    current_batch: Optional[str] = None
    batches_processed: int = 0
    total_images_processed: int = 0
    session_key: Optional[bytes] = None
    
    def to_dict(self):
        """Convertit en dictionnaire pour JSON"""
        data = asdict(self)
        data['connected_at'] = self.connected_at.isoformat()
        data['last_seen'] = self.last_seen.isoformat()
        if self.session_key:
            data['session_key'] = self.session_key.hex()
        return data

@dataclass  
class BatchInfo:
    """Informations sur un lot d'images"""
    batch_id: str
    job_id: str
    start_frame: int
    end_frame: int
    total_images: int
    status: str  # "pending", "assigned", "processing", "completed", "error"
    assigned_client: Optional[str] = None
    assigned_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    input_path: Optional[Path] = None
    output_path: Optional[Path] = None
    
    def to_dict(self):
        """Convertit en dictionnaire pour JSON"""
        data = asdict(self)
        if self.assigned_at:
            data['assigned_at'] = self.assigned_at.isoformat()
        if self.completed_at:
            data['completed_at'] = self.completed_at.isoformat()
        if self.input_path:
            data['input_path'] = str(self.input_path)
        if self.output_path:
            data['output_path'] = str(self.output_path)
        return data

@dataclass
class JobInfo:
    """Informations sur un job d'upscaling"""
    job_id: str
    video_path: Path
    output_path: Path
    scale_factor: int
    model: str
    batch_size: int
    total_frames: int
    total_batches: int
    completed_batches: int
    status: str  # "preparing", "processing", "assembling", "completed", "error"
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    
    def to_dict(self):
        """Convertit en dictionnaire pour JSON"""
        data = asdict(self)
        data['video_path'] = str(self.video_path)
        data['output_path'] = str(self.output_path)
        data['created_at'] = self.created_at.isoformat()
        if self.started_at:
            data['started_at'] = self.started_at.isoformat()
        if self.completed_at:
            data['completed_at'] = self.completed_at.isoformat()
        return data

class DistributedServer:
    """Serveur principal pour l'upscaling distribué"""
    
    def __init__(self, work_dir: Path = None):
        self.logger = logging.getLogger(__name__)
        
        # Configuration
        self.host = "0.0.0.0"
        self.port = 8888
        self.max_clients = 50
        self.batch_size = 50
        self.max_retry_attempts = 3
        self.client_timeout = 300  # 5 minutes
        
        # Dossiers de travail
        self.work_dir = work_dir or Path("server_work")
        self.jobs_dir = self.work_dir / "jobs"
        self.temp_dir = self.work_dir / "temp"
        self.encryption_keys_dir = self.temp_dir / "encryption_keys"
        self.output_dir = Path("output")
        
        # État du serveur
        self.running = False
        self.server_socket = None
        self.start_time = None
        
        # Données d'état
        self.connected_clients: Dict[str, ClientInfo] = {}
        self.active_jobs: Dict[str, JobInfo] = {}
        self.active_batches: Dict[str, BatchInfo] = {}
        self.pending_batches: List[str] = []  # Liste des IDs de lots en attente
        
        # Gestionnaires
        self.encryption_manager = None
        self.ffmpeg_handler = None
        self.realesrgan_handler = None
        
        # Tâches asynchrones
        self.server_task = None
        self.client_monitor_task = None
        self.batch_manager_task = None
        
        # Créer les dossiers nécessaires
        self.create_directories()
        
        self.logger.info("Serveur distribué initialisé")
    
    def create_directories(self):
        """Crée les dossiers nécessaires"""
        directories = [
            self.work_dir,
            self.jobs_dir,
            self.temp_dir,
            self.encryption_keys_dir,
            self.output_dir
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
        
        self.logger.debug("Dossiers de travail créés")
    
    def initialize_handlers(self):
        """Initialise les gestionnaires d'outils"""
        try:
            # Gestionnaire de chiffrement
            if EncryptionManager:
                self.encryption_manager = EncryptionManager(self.encryption_keys_dir)
            
            # Gestionnaire FFmpeg
            if FFmpegHandler:
                self.ffmpeg_handler = FFmpegHandler()
            
            # Gestionnaire Real-ESRGAN
            if RealESRGANHandler:
                self.realesrgan_handler = RealESRGANHandler()
            
            self.logger.info("Gestionnaires initialisés")
            
        except Exception as e:
            self.logger.error(f"Erreur initialisation gestionnaires: {e}")
    
    async def start(self, host: str = "0.0.0.0", port: int = 8888):
        """Démarre le serveur"""
        if self.running:
            self.logger.warning("Le serveur est déjà démarré")
            return
        
        self.host = host
        self.port = port
        self.start_time = datetime.now()
        
        try:
            # Initialisation des gestionnaires
            self.initialize_handlers()
            
            # Création du socket serveur
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((host, port))
            self.server_socket.listen(self.max_clients)
            self.server_socket.setblocking(False)
            
            self.running = True
            
            # Démarrage des tâches de gestion
            self.server_task = asyncio.create_task(self.accept_clients())
            self.client_monitor_task = asyncio.create_task(self.monitor_clients())
            self.batch_manager_task = asyncio.create_task(self.manage_batches())
            
            self.logger.info(f"Serveur démarré sur {host}:{port}")
            
        except Exception as e:
            self.logger.error(f"Erreur démarrage serveur: {e}")
            await self.stop()
            raise
    
    async def stop(self):
        """Arrête le serveur"""
        if not self.running:
            return
        
        self.running = False
        
        try:
            # Arrêt des tâches
            if self.server_task:
                self.server_task.cancel()
            if self.client_monitor_task:
                self.client_monitor_task.cancel()
            if self.batch_manager_task:
                self.batch_manager_task.cancel()
            
            # Déconnexion des clients
            for client_mac in list(self.connected_clients.keys()):
                await self.disconnect_client(client_mac)
            
            # Fermeture du socket
            if self.server_socket:
                self.server_socket.close()
            
            self.logger.info("Serveur arrêté")
            
        except Exception as e:
            self.logger.error(f"Erreur arrêt serveur: {e}")
    
    async def accept_clients(self):
        """Accepte les connexions des clients"""
        while self.running:
            try:
                client_socket, address = await asyncio.get_event_loop().sock_accept(self.server_socket)
                client_socket.setblocking(False)
                
                # Traitement de la connexion client dans une tâche séparée
                asyncio.create_task(self.handle_client(client_socket, address))
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Erreur acceptation client: {e}")
                await asyncio.sleep(1)
    
    async def handle_client(self, client_socket, address):
        """Gère la communication avec un client"""
        client_mac = None
        
        try:
            # Handshake initial et authentification
            client_info = await self.perform_handshake(client_socket, address)
            if not client_info:
                return
            
            client_mac = client_info.mac_address
            self.connected_clients[client_mac] = client_info
            
            self.logger.info(f"Client connecté: {client_mac} ({client_info.hostname})")
            
            # Boucle de communication
            while self.running and client_mac in self.connected_clients:
                try:
                    # Réception des messages
                    data = await asyncio.wait_for(
                        asyncio.get_event_loop().sock_recv(client_socket, 4096),
                        timeout=60
                    )
                    
                    if not data:
                        break
                    
                    # Traitement du message
                    await self.process_client_message(client_mac, data)
                    
                    # Mise à jour de l'heure de dernière activité
                    self.connected_clients[client_mac].last_seen = datetime.now()
                    
                except asyncio.TimeoutError:
                    # Vérification de la connexion
                    await self.send_ping(client_socket)
                    
                except Exception as e:
                    self.logger.error(f"Erreur communication client {client_mac}: {e}")
                    break
            
        except Exception as e:
            self.logger.error(f"Erreur gestion client {address}: {e}")
            
        finally:
            # Nettoyage de la connexion
            if client_mac:
                await self.disconnect_client(client_mac)
            
            try:
                client_socket.close()
            except:
                pass
    
    async def perform_handshake(self, client_socket, address) -> Optional[ClientInfo]:
        """Effectue le handshake avec un client"""
        try:
            # Réception des informations client
            data = await asyncio.wait_for(
                asyncio.get_event_loop().sock_recv(client_socket, 1024),
                timeout=30
            )
            
            client_hello = json.loads(data.decode('utf-8'))
            
            # Validation des informations
            if not all(key in client_hello for key in ['mac_address', 'hostname', 'version']):
                self.logger.warning(f"Handshake invalide de {address}")
                return None
            
            # Génération de la clé de session
            session_key = os.urandom(32)  # AES-256
            
            # Création des informations client
            client_info = ClientInfo(
                mac_address=client_hello['mac_address'],
                hostname=client_hello['hostname'],
                ip_address=address[0],
                port=address[1],
                connected_at=datetime.now(),
                last_seen=datetime.now(),
                status="idle",
                session_key=session_key
            )
            
            # Réponse du serveur avec la clé de session
            server_hello = {
                'status': 'accepted',
                'server_version': '1.0.0',
                'session_key': session_key.hex(),
                'batch_size': self.batch_size,
                'supported_models': [
                    'realesr-animevideov3',
                    'realesrgan-x4plus',
                    'realesrgan-x4plus-anime'
                ]
            }
            
            response = json.dumps(server_hello).encode('utf-8')
            await asyncio.get_event_loop().sock_sendall(client_socket, response)
            
            return client_info
            
        except Exception as e:
            self.logger.error(f"Erreur handshake avec {address}: {e}")
            return None
    
    async def process_client_message(self, client_mac: str, data: bytes):
        """Traite un message reçu d'un client"""
        try:
            # Déchiffrement du message si nécessaire
            client_info = self.connected_clients[client_mac]
            if client_info.session_key:
                # TODO: Implémenter le déchiffrement
                pass
            
            message = json.loads(data.decode('utf-8'))
            message_type = message.get('type')
            
            if message_type == 'ping':
                await self.handle_ping(client_mac)
                
            elif message_type == 'batch_request':
                await self.handle_batch_request(client_mac)
                
            elif message_type == 'batch_progress':
                await self.handle_batch_progress(client_mac, message)
                
            elif message_type == 'batch_completed':
                await self.handle_batch_completed(client_mac, message)
                
            elif message_type == 'batch_error':
                await self.handle_batch_error(client_mac, message)
                
            else:
                self.logger.warning(f"Type de message inconnu de {client_mac}: {message_type}")
                
        except Exception as e:
            self.logger.error(f"Erreur traitement message de {client_mac}: {e}")
    
    async def send_ping(self, client_socket):
        """Envoie un ping au client"""
        try:
            ping_message = json.dumps({'type': 'ping'}).encode('utf-8')
            await asyncio.get_event_loop().sock_sendall(client_socket, ping_message)
        except Exception as e:
            self.logger.error(f"Erreur envoi ping: {e}")
    
    async def handle_ping(self, client_mac: str):
        """Gère un ping reçu d'un client"""
        # Mise à jour de l'heure de dernière activité
        if client_mac in self.connected_clients:
            self.connected_clients[client_mac].last_seen = datetime.now()
    
    async def handle_batch_request(self, client_mac: str):
        """Gère une demande de lot d'un client"""
        if client_mac not in self.connected_clients:
            return
        
        client_info = self.connected_clients[client_mac]
        
        # Vérifier si le client n'est pas déjà occupé
        if client_info.status == "processing":
            self.logger.warning(f"Client {client_mac} demande un lot mais en traite déjà un")
            return
        
        # Assigner un lot si disponible
        batch_id = await self.assign_batch_to_client(client_mac)
        if batch_id:
            self.logger.info(f"Lot {batch_id} assigné au client {client_mac}")
        else:
            self.logger.debug(f"Aucun lot disponible pour le client {client_mac}")
    
    async def assign_batch_to_client(self, client_mac: str) -> Optional[str]:
        """Assigne un lot à un client"""
        if not self.pending_batches:
            return None
        
        # Prendre le premier lot en attente
        batch_id = self.pending_batches.pop(0)
        batch_info = self.active_batches[batch_id]
        
        # Mise à jour du lot
        batch_info.status = "assigned"
        batch_info.assigned_client = client_mac
        batch_info.assigned_at = datetime.now()
        
        # Mise à jour du client
        client_info = self.connected_clients[client_mac]
        client_info.status = "processing"
        client_info.current_batch = batch_id
        
        # Préparation et envoi du lot au client
        await self.send_batch_to_client(client_mac, batch_id)
        
        return batch_id
    
    async def send_batch_to_client(self, client_mac: str, batch_id: str):
        """Envoie un lot à un client"""
        try:
            batch_info = self.active_batches[batch_id]
            
            # Création du package de lot (ZIP + chiffrement)
            batch_package = await self.create_batch_package(batch_info)
            
            # TODO: Envoyer le package au client via socket
            self.logger.info(f"Package de lot {batch_id} créé pour {client_mac}")
            
        except Exception as e:
            self.logger.error(f"Erreur envoi lot {batch_id} à {client_mac}: {e}")
            # Remettre le lot en attente
            await self.reassign_batch(batch_id)
    
    async def create_batch_package(self, batch_info: BatchInfo) -> bytes:
        """Crée un package chiffré pour un lot"""
        try:
            # Création du fichier ZIP avec les images
            zip_path = self.temp_dir / f"{batch_info.batch_id}.zip"
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zipf:
                # Ajout des images du lot
                for i in range(batch_info.start_frame, batch_info.end_frame + 1):
                    image_path = batch_info.input_path / f"frame_{i:06d}.png"
                    if image_path.exists():
                        zipf.write(image_path, image_path.name)
            
            # Lecture et chiffrement du ZIP
            with open(zip_path, 'rb') as f:
                zip_data = f.read()
            
            # TODO: Chiffrer les données avec la clé de session du client
            encrypted_data = zip_data  # Placeholder
            
            # Nettoyage
            zip_path.unlink()
            
            return encrypted_data
            
        except Exception as e:
            self.logger.error(f"Erreur création package lot {batch_info.batch_id}: {e}")
            raise
    
    async def handle_batch_progress(self, client_mac: str, message: dict):
        """Gère la progression d'un lot"""
        batch_id = message.get('batch_id')
        processed_count = message.get('processed_count', 0)
        
        if batch_id in self.active_batches:
            batch_info = self.active_batches[batch_id]
            batch_info.status = "processing"
            
            self.logger.debug(f"Progression lot {batch_id}: {processed_count}/{batch_info.total_images}")
    
    async def handle_batch_completed(self, client_mac: str, message: dict):
        """Gère la completion d'un lot"""
        batch_id = message.get('batch_id')
        
        if batch_id not in self.active_batches:
            return
        
        batch_info = self.active_batches[batch_id]
        
        try:
            # Réception du lot traité
            processed_data = message.get('processed_data')  # En base64 ou référence
            
            # Déchiffrement et extraction
            success = await self.process_completed_batch(batch_info, processed_data)
            
            if success:
                batch_info.status = "completed"
                batch_info.completed_at = datetime.now()
                
                # Mise à jour des statistiques client
                client_info = self.connected_clients[client_mac]
                client_info.batches_processed += 1
                client_info.total_images_processed += batch_info.total_images
                client_info.status = "idle"
                client_info.current_batch = None
                
                self.logger.info(f"Lot {batch_id} complété par {client_mac}")
                
                # Vérifier si le job est terminé
                await self.check_job_completion(batch_info.job_id)
                
            else:
                await self.reassign_batch(batch_id)
                
        except Exception as e:
            self.logger.error(f"Erreur traitement lot complété {batch_id}: {e}")
            await self.reassign_batch(batch_id)
    
    async def process_completed_batch(self, batch_info: BatchInfo, processed_data: Any) -> bool:
        """Traite un lot complété reçu d'un client"""
        try:
            # TODO: Déchiffrer et extraire les images traitées
            # TODO: Valider le nombre d'images
            # TODO: Déplacer vers le dossier de sortie
            
            self.logger.info(f"Lot {batch_info.batch_id} traité avec succès")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur traitement lot {batch_info.batch_id}: {e}")
            return False
    
    async def handle_batch_error(self, client_mac: str, message: dict):
        """Gère une erreur de traitement de lot"""
        batch_id = message.get('batch_id')
        error_message = message.get('error', 'Erreur inconnue')
        
        self.logger.warning(f"Erreur lot {batch_id} par {client_mac}: {error_message}")
        
        await self.reassign_batch(batch_id)
    
    async def reassign_batch(self, batch_id: str):
        """Remet un lot en attente pour réassignation"""
        if batch_id not in self.active_batches:
            return
        
        batch_info = self.active_batches[batch_id]
        batch_info.retry_count += 1
        
        if batch_info.retry_count >= self.max_retry_attempts:
            batch_info.status = "error"
            self.logger.error(f"Lot {batch_id} abandonné après {self.max_retry_attempts} tentatives")
            return
        
        # Remettre en attente
        batch_info.status = "pending"
        batch_info.assigned_client = None
        batch_info.assigned_at = None
        self.pending_batches.append(batch_id)
        
        # Libérer le client si nécessaire
        if batch_info.assigned_client and batch_info.assigned_client in self.connected_clients:
            client_info = self.connected_clients[batch_info.assigned_client]
            client_info.status = "idle"
            client_info.current_batch = None
        
        self.logger.info(f"Lot {batch_id} remis en attente (tentative {batch_info.retry_count})")
    
    async def disconnect_client(self, client_mac: str):
        """Déconnecte un client"""
        if client_mac not in self.connected_clients:
            return
        
        client_info = self.connected_clients[client_mac]
        
        # Réassigner le lot en cours si nécessaire
        if client_info.current_batch:
            await self.reassign_batch(client_info.current_batch)
        
        # Supprimer le client
        del self.connected_clients[client_mac]
        
        self.logger.info(f"Client déconnecté: {client_mac}")
    
    async def monitor_clients(self):
        """Surveille les clients connectés"""
        while self.running:
            try:
                current_time = datetime.now()
                clients_to_disconnect = []
                
                for client_mac, client_info in self.connected_clients.items():
                    # Vérifier le timeout
                    if (current_time - client_info.last_seen).total_seconds() > self.client_timeout:
                        clients_to_disconnect.append(client_mac)
                
                # Déconnecter les clients expirés
                for client_mac in clients_to_disconnect:
                    await self.disconnect_client(client_mac)
                
                await asyncio.sleep(60)  # Vérification toutes les minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Erreur surveillance clients: {e}")
                await asyncio.sleep(60)
    
    async def manage_batches(self):
        """Gère la distribution des lots"""
        while self.running:
            try:
                # Vérifier s'il y a des lots en attente et des clients disponibles
                idle_clients = [
                    mac for mac, client in self.connected_clients.items()
                    if client.status == "idle"
                ]
                
                if self.pending_batches and idle_clients:
                    # Assigner des lots aux clients disponibles
                    for client_mac in idle_clients[:len(self.pending_batches)]:
                        await self.assign_batch_to_client(client_mac)
                
                await asyncio.sleep(5)  # Vérification toutes les 5 secondes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Erreur gestion lots: {e}")
                await asyncio.sleep(5)
    
    # === API publique pour la création de jobs ===
    
    async def create_job(self, video_path: Path, scale_factor: int = 4, 
                        model: str = "realesr-animevideov3") -> str:
        """Crée un nouveau job d'upscaling"""
        try:
            # Génération de l'ID du job
            job_id = f"job_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            
            # Création des dossiers du job
            job_dir = self.jobs_dir / job_id
            frames_dir = job_dir / "frames"
            output_dir = job_dir / "output"
            
            for directory in [job_dir, frames_dir, output_dir]:
                directory.mkdir(parents=True, exist_ok=True)
            
            # Extraction des frames avec FFmpeg
            if self.ffmpeg_handler:
                total_frames = await self.ffmpeg_handler.extract_frames(
                    video_path, frames_dir
                )
            else:
                # Fallback: estimation
                total_frames = 1000  # Placeholder
            
            # Calcul du nombre de lots
            total_batches = (total_frames + self.batch_size - 1) // self.batch_size
            
            # Création des informations du job
            job_info = JobInfo(
                job_id=job_id,
                video_path=video_path,
                output_path=self.output_dir / f"{video_path.stem}_upscaled.mp4",
                scale_factor=scale_factor,
                model=model,
                batch_size=self.batch_size,
                total_frames=total_frames,
                total_batches=total_batches,
                completed_batches=0,
                status="preparing",
                created_at=datetime.now()
            )
            
            self.active_jobs[job_id] = job_info
            
            # Création des lots
            await self.create_batches_for_job(job_info, frames_dir)
            
            # Démarrage du job
            job_info.status = "processing"
            job_info.started_at = datetime.now()
            
            self.logger.info(f"Job {job_id} créé: {total_batches} lots, {total_frames} frames")
            
            return job_id
            
        except Exception as e:
            self.logger.error(f"Erreur création job: {e}")
            raise
    
    async def create_batches_for_job(self, job_info: JobInfo, frames_dir: Path):
        """Crée les lots pour un job"""
        for batch_num in range(job_info.total_batches):
            start_frame = batch_num * self.batch_size
            end_frame = min(start_frame + self.batch_size - 1, job_info.total_frames - 1)
            
            batch_id = f"{job_info.job_id}_batch_{batch_num:04d}"
            
            batch_info = BatchInfo(
                batch_id=batch_id,
                job_id=job_info.job_id,
                start_frame=start_frame,
                end_frame=end_frame,
                total_images=end_frame - start_frame + 1,
                status="pending",
                input_path=frames_dir,
                output_path=self.jobs_dir / job_info.job_id / "output"
            )
            
            self.active_batches[batch_id] = batch_info
            self.pending_batches.append(batch_id)
    
    async def check_job_completion(self, job_id: str):
        """Vérifie si un job est terminé"""
        if job_id not in self.active_jobs:
            return
        
        job_info = self.active_jobs[job_id]
        
        # Compter les lots complétés
        completed_batches = sum(
            1 for batch in self.active_batches.values()
            if batch.job_id == job_id and batch.status == "completed"
        )
        
        job_info.completed_batches = completed_batches
        
        if completed_batches >= job_info.total_batches:
            # Job terminé, assembler la vidéo finale
            await self.assemble_final_video(job_info)
    
    async def assemble_final_video(self, job_info: JobInfo):
        """Assemble la vidéo finale"""
        try:
            job_info.status = "assembling"
            
            output_frames_dir = self.jobs_dir / job_info.job_id / "output"
            
            # Assemblage avec FFmpeg
            if self.ffmpeg_handler:
                await self.ffmpeg_handler.assemble_video(
                    output_frames_dir,
                    job_info.video_path,  # Pour l'audio
                    job_info.output_path
                )
            
            job_info.status = "completed"
            job_info.completed_at = datetime.now()
            
            self.logger.info(f"Job {job_info.job_id} terminé: {job_info.output_path}")
            
        except Exception as e:
            job_info.status = "error"
            job_info.error_message = str(e)
            self.logger.error(f"Erreur assemblage job {job_info.job_id}: {e}")
    
    # === Méthodes d'état et statistiques ===
    
    def get_server_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du serveur"""
        uptime = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        
        return {
            'running': self.running,
            'uptime': uptime,
            'clients_connected': len(self.connected_clients),
            'active_jobs': len(self.active_jobs),
            'active_batches': len(self.active_batches),
            'pending_batches': len(self.pending_batches),
            'total_images_processed': sum(
                client.total_images_processed for client in self.connected_clients.values()
            )
        }
    
    def get_client_stats(self) -> List[Dict[str, Any]]:
        """Retourne les statistiques des clients"""
        return [client.to_dict() for client in self.connected_clients.values()]
    
    def get_job_stats(self) -> List[Dict[str, Any]]:
        """Retourne les statistiques des jobs"""
        return [job.to_dict() for job in self.active_jobs.values()]
    
    def get_batch_stats(self) -> List[Dict[str, Any]]:
        """Retourne les statistiques des lots"""
        return [batch.to_dict() for batch in self.active_batches.values()]