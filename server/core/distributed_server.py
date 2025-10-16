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
import base64
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import uuid

# Imports pour le réseau et le chiffrement
import websockets
from websockets.server import WebSocketServerProtocol
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
        self.websocket_server = None
        self.start_time = None

        # Données d'état
        self.connected_clients: Dict[str, ClientInfo] = {}
        self.client_websockets: Dict[str, WebSocketServerProtocol] = {}  # WebSocket par MAC
        self.active_jobs: Dict[str, JobInfo] = {}
        self.active_batches: Dict[str, BatchInfo] = {}
        self.pending_batches: List[str] = []  # Liste des IDs de lots en attente

        # Locks for thread-safe access to shared state
        # Lock acquisition order (to prevent deadlocks):
        # 1. clients_lock (protects connected_clients and client_websockets)
        # 2. batches_lock (protects pending_batches and active_batches)
        # 3. jobs_lock (protects active_jobs)
        # Always acquire locks in this order when multiple locks are needed
        self.clients_lock = asyncio.Lock()  # Protects: connected_clients, client_websockets
        self.batches_lock = asyncio.Lock()  # Protects: pending_batches, active_batches
        self.jobs_lock = asyncio.Lock()     # Protects: active_jobs

        # Gestionnaires
        self.encryption_manager = None
        self.ffmpeg_handler = None
        self.realesrgan_handler = None

        # Tâches asynchrones
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

            # Démarrage du serveur WebSocket
            self.running = True

            # Création du serveur WebSocket avec ping_interval=30 et ping_timeout=10
            self.websocket_server = await websockets.serve(
                self.handle_client,
                host,
                port,
                ping_interval=30,
                ping_timeout=10,
                max_size=100 * 1024 * 1024  # 100 MB max message size for batch transfers
            )

            # Démarrage des tâches de gestion
            self.client_monitor_task = asyncio.create_task(self.monitor_clients())
            self.batch_manager_task = asyncio.create_task(self.manage_batches())

            self.logger.info(f"Serveur WebSocket démarré sur {host}:{port}")

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
            if self.client_monitor_task:
                self.client_monitor_task.cancel()
            if self.batch_manager_task:
                self.batch_manager_task.cancel()

            # Déconnexion des clients
            for client_mac in list(self.connected_clients.keys()):
                await self.disconnect_client(client_mac)

            # Fermeture du serveur WebSocket
            if self.websocket_server:
                self.websocket_server.close()
                await self.websocket_server.wait_closed()

            self.logger.info("Serveur arrêté")

        except Exception as e:
            self.logger.error(f"Erreur arrêt serveur: {e}")
    
    async def handle_client(self, websocket: WebSocketServerProtocol, path: str = None):
        """Gère la communication avec un client via WebSocket de manière thread-safe

        Cette méthode gère le cycle de vie complet d'une connexion client,
        du handshake initial à la déconnexion finale.

        Args:
            websocket: La connexion WebSocket du client
            path: Le chemin de la requête WebSocket (optionnel)
        """
        client_mac = None
        address = websocket.remote_address

        try:
            # Handshake initial et authentification
            client_info = await self.perform_handshake(websocket, address)
            if not client_info:
                await websocket.close(1008, "Authentication failed")
                return

            client_mac = client_info.mac_address

            # Register client atomically
            async with self.clients_lock:
                self.connected_clients[client_mac] = client_info
                self.client_websockets[client_mac] = websocket

            self.logger.info(f"Client connecté: {client_mac} ({client_info.hostname}) depuis {address}")

            # Boucle de communication
            async for message_raw in websocket:
                try:
                    # Traitement du message
                    await self.process_client_message(client_mac, message_raw.encode('utf-8') if isinstance(message_raw, str) else message_raw)

                    # Mise à jour de l'heure de dernière activité
                    async with self.clients_lock:
                        if client_mac in self.connected_clients:
                            self.connected_clients[client_mac].last_seen = datetime.now()

                except Exception as e:
                    self.logger.error(f"Erreur traitement message du client {client_mac}: {e}")

        except websockets.exceptions.ConnectionClosedOK:
            self.logger.info(f"Client {client_mac or address} déconnecté normalement")
        except websockets.exceptions.ConnectionClosedError as e:
            self.logger.warning(f"Client {client_mac or address} déconnecté avec erreur: {e}")
        except Exception as e:
            self.logger.error(f"Erreur gestion client {address}: {e}")

        finally:
            # Nettoyage de la connexion
            if client_mac:
                await self.disconnect_client(client_mac)
    
    async def perform_handshake(self, websocket: WebSocketServerProtocol, address) -> Optional[ClientInfo]:
        """Effectue le handshake avec un client via WebSocket"""
        try:
            # Réception des informations client
            message_raw = await asyncio.wait_for(websocket.recv(), timeout=30)
            client_hello = json.loads(message_raw)

            # Validation des informations - le client envoie 'client_hello' comme type
            if client_hello.get('type') != 'client_hello':
                self.logger.warning(f"Type de message incorrect lors du handshake de {address}")
                return None

            # Extraction des informations requises
            mac_address = client_hello.get('mac_address')
            hostname = client_hello.get('system_info', {}).get('hostname', 'unknown')

            if not mac_address:
                self.logger.warning(f"Handshake invalide de {address}: MAC address manquante")
                return None

            # Génération de la clé de session
            session_key = os.urandom(32)  # AES-256

            # Création des informations client
            client_info = ClientInfo(
                mac_address=mac_address,
                hostname=hostname,
                ip_address=address[0] if address else "unknown",
                port=address[1] if address and len(address) > 1 else 0,
                connected_at=datetime.now(),
                last_seen=datetime.now(),
                status="idle",
                session_key=session_key
            )

            # Réponse du serveur avec la clé de session
            server_hello = {
                'type': 'server_hello',
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

            response = json.dumps(server_hello)
            await websocket.send(response)

            return client_info

        except asyncio.TimeoutError:
            self.logger.error(f"Timeout handshake avec {address}")
            return None
        except json.JSONDecodeError as e:
            self.logger.error(f"Message JSON invalide lors du handshake avec {address}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Erreur handshake avec {address}: {e}")
            return None
    
    async def process_client_message(self, client_mac: str, data: bytes):
        """Traite un message reçu d'un client"""
        try:
            # Déchiffrement du message si nécessaire
            client_info = self.connected_clients.get(client_mac)
            if not client_info:
                self.logger.warning(f"Message reçu d'un client inconnu: {client_mac}")
                return

            # Déchiffrement du message avec la clé de session
            if client_info.session_key and self.encryption_manager:
                try:
                    # Récupération ou création de la session de chiffrement
                    session = self.encryption_manager.get_session(client_mac)
                    if not session:
                        # Créer une session avec la clé existante
                        session = self.encryption_manager.create_session(client_mac)
                        # Utiliser la clé de session stockée
                        session.aes_key = client_info.session_key

                    # Déchiffrement des données
                    data = session.decrypt_data(data)
                    self.logger.debug(f"Message déchiffré du client {client_mac}")
                except Exception as e:
                    self.logger.error(f"Erreur déchiffrement message de {client_mac}: {e}")
                    # En cas d'erreur de déchiffrement, on essaie de traiter le message en clair
                    # pour maintenir la compatibilité avec les anciens clients
                    self.logger.warning(f"Tentative de traitement du message en clair pour {client_mac}")

            message = json.loads(data.decode('utf-8'))
            message_type = message.get('type')

            # Gestionnaire de messages
            if message_type == 'ping' or message_type == 'heartbeat':
                await self.handle_ping(client_mac)

            elif message_type == 'pong':
                # Mise à jour de l'activité
                client_info.last_seen = datetime.now()

            elif message_type == 'batch_request':
                await self.handle_batch_request(client_mac)

            elif message_type == 'batch_progress':
                await self.handle_batch_progress(client_mac, message)

            elif message_type == 'batch_result':
                # Le client envoie 'batch_result' au lieu de 'batch_completed'
                if message.get('status') == 'completed':
                    await self.handle_batch_completed(client_mac, message)
                elif message.get('status') == 'failed':
                    await self.handle_batch_error(client_mac, message)

            elif message_type == 'batch_completed':
                await self.handle_batch_completed(client_mac, message)

            elif message_type == 'batch_error':
                await self.handle_batch_error(client_mac, message)

            elif message_type == 'batch_availability':
                # Réponse à une demande de disponibilité - enregistrer l'info
                self.logger.debug(f"Client {client_mac} disponibilité: {message.get('available')}")

            elif message_type == 'get_server_info':
                # Envoyer les informations du serveur
                server_info = {
                    'type': 'server_info',
                    'server_info': self.get_server_stats()
                }
                await self.send_message_to_client(client_mac, server_info)

            elif message_type == 'update_preferences':
                # Mise à jour des préférences client (à implémenter si nécessaire)
                self.logger.debug(f"Préférences reçues du client {client_mac}")

            else:
                self.logger.warning(f"Type de message inconnu de {client_mac}: {message_type}")

        except json.JSONDecodeError as e:
            self.logger.error(f"Message JSON invalide de {client_mac}: {e}")
        except Exception as e:
            self.logger.error(f"Erreur traitement message de {client_mac}: {e}")
    
    async def send_message_to_client(self, client_mac: str, message: dict) -> bool:
        """Envoie un message à un client via WebSocket"""
        if client_mac not in self.client_websockets:
            self.logger.warning(f"Client {client_mac} non trouvé pour envoi de message")
            return False

        websocket = self.client_websockets[client_mac]
        try:
            message_json = json.dumps(message)
            message_bytes = message_json.encode('utf-8')

            # Chiffrement du message si une clé de session existe
            if client_mac in self.connected_clients:
                client_info = self.connected_clients[client_mac]
                if client_info.session_key and self.encryption_manager:
                    try:
                        # Récupération ou création de la session de chiffrement
                        session = self.encryption_manager.get_session(client_mac)
                        if not session:
                            # Créer une session avec la clé existante
                            session = self.encryption_manager.create_session(client_mac)
                            # Utiliser la clé de session stockée
                            session.aes_key = client_info.session_key

                        # Chiffrement du message
                        message_bytes = session.encrypt_data(message_bytes)
                        self.logger.debug(f"Message chiffré pour le client {client_mac}")
                    except Exception as e:
                        self.logger.error(f"Erreur chiffrement message pour {client_mac}: {e}")
                        # En cas d'erreur, envoyer en clair
                        self.logger.warning(f"Envoi du message en clair pour {client_mac}")

            await websocket.send(message_bytes)
            return True
        except websockets.exceptions.ConnectionClosed:
            self.logger.warning(f"Connexion fermée pour le client {client_mac}")
            return False
        except Exception as e:
            self.logger.error(f"Erreur envoi message au client {client_mac}: {e}")
            return False
    
    async def handle_ping(self, client_mac: str):
        """Gère un ping/heartbeat reçu d'un client de manière thread-safe

        Met à jour l'horodatage de dernière activité du client et répond avec un pong.

        Args:
            client_mac: Adresse MAC du client
        """
        # Mise à jour de l'heure de dernière activité
        async with self.clients_lock:
            if client_mac in self.connected_clients:
                self.connected_clients[client_mac].last_seen = datetime.now()

        # Réponse pong au client
        pong_message = {'type': 'pong', 'timestamp': time.time()}
        await self.send_message_to_client(client_mac, pong_message)
    
    async def handle_batch_request(self, client_mac: str):
        """Gère une demande de lot d'un client de manière thread-safe

        Un client demande un nouveau lot à traiter. Cette méthode vérifie
        que le client n'est pas déjà occupé avant d'assigner un lot.

        Args:
            client_mac: Adresse MAC du client demandeur
        """
        # Check client status before assignment
        async with self.clients_lock:
            if client_mac not in self.connected_clients:
                return

            client_info = self.connected_clients[client_mac]

            # Vérifier si le client n'est pas déjà occupé
            if client_info.status == "processing":
                self.logger.warning(f"Client {client_mac} demande un lot mais en traite déjà un")
                return

        # Assigner un lot si disponible (handles its own locking)
        batch_id = await self.assign_batch_to_client(client_mac)
        if batch_id:
            self.logger.info(f"Lot {batch_id} assigné au client {client_mac}")
        else:
            self.logger.debug(f"Aucun lot disponible pour le client {client_mac}")
    
    async def assign_batch_to_client(self, client_mac: str) -> Optional[str]:
        """Assigne un lot à un client de manière thread-safe

        Cette méthode utilise des locks pour garantir qu'un seul batch est assigné
        à la fois et éviter les conditions de course lors de l'accès concurrent
        aux structures de données partagées.

        Args:
            client_mac: Adresse MAC du client

        Returns:
            L'ID du batch assigné, ou None si aucun batch n'est disponible
        """
        # Acquire locks in the correct order to prevent deadlocks:
        # 1. clients_lock (for client state)
        # 2. batches_lock (for batch queues)
        async with self.clients_lock:
            # Vérifier que le client existe et est disponible
            if client_mac not in self.connected_clients:
                self.logger.warning(f"Tentative d'assignation à un client inexistant: {client_mac}")
                return None

            client_info = self.connected_clients[client_mac]
            if client_info.status != "idle":
                self.logger.warning(
                    f"Tentative d'assignation à un client occupé: {client_mac} "
                    f"(statut: {client_info.status})"
                )
                return None

            # Now acquire batches_lock for atomic batch assignment
            async with self.batches_lock:
                # Double-check pending_batches inside the lock
                if not self.pending_batches:
                    return None

                # Atomically pop the first pending batch
                batch_id = self.pending_batches.pop(0)
                batch_info = self.active_batches[batch_id]

                # Mise à jour du lot (statut initial "assigned")
                batch_info.status = "assigned"
                batch_info.assigned_client = client_mac
                batch_info.assigned_at = datetime.now()

                # Mise à jour du client
                client_info.status = "processing"
                client_info.current_batch = batch_id

                self.logger.info(
                    f"Assignation du lot {batch_id} au client {client_mac} "
                    f"({batch_info.total_images} images)"
                )

        # Préparation et envoi du lot au client
        # Note: send_batch_to_client() mettra à jour le statut à "processing" après envoi réussi
        # This is done OUTSIDE the lock to avoid holding locks during I/O operations
        await self.send_batch_to_client(client_mac, batch_id)

        return batch_id
    
    async def send_batch_to_client(self, client_mac: str, batch_id: str):
        """Envoie un lot à un client via WebSocket

        Note: Cette méthode doit être appelée SANS tenir de locks, car elle effectue
        des opérations I/O (création de ZIP, envoi réseau). Les locks sont acquis
        uniquement pour les mises à jour critiques de l'état partagé.
        """
        try:
            # Read batch and job info (quick read, no modification)
            async with self.batches_lock:
                if batch_id not in self.active_batches:
                    raise Exception(f"Batch {batch_id} introuvable")
                batch_info = self.active_batches[batch_id]

            async with self.jobs_lock:
                job_info = self.active_jobs.get(batch_info.job_id)
                if not job_info:
                    raise Exception(f"Job {batch_info.job_id} introuvable pour le lot {batch_id}")

            # Vérification que le client est toujours connecté
            async with self.clients_lock:
                if client_mac not in self.connected_clients:
                    raise Exception(f"Client {client_mac} non connecté")

            # Création du package de lot (ZIP + chiffrement)
            # This is I/O intensive - done WITHOUT holding locks
            self.logger.debug(f"Création du package pour le lot {batch_id}")
            batch_package = await self.create_batch_package(batch_info)

            # Vérification que le package n'est pas vide
            if not batch_package:
                raise Exception("Package de lot vide")

            # Encodage en base64 pour transmission JSON
            batch_data_b64 = base64.b64encode(batch_package).decode('utf-8')
            self.logger.debug(
                f"Lot {batch_id} encodé: {len(batch_package)} bytes -> "
                f"{len(batch_data_b64)} chars base64"
            )

            # Message d'assignation de lot avec configuration complète
            batch_message = {
                'type': 'batch_assignment',
                'batch_id': batch_id,
                'batch_data': batch_data_b64,
                'batch_config': {
                    'job_id': batch_info.job_id,
                    'start_frame': batch_info.start_frame,
                    'end_frame': batch_info.end_frame,
                    'total_images': batch_info.total_images,
                    'frames_count': batch_info.total_images,
                    'model': job_info.model,
                    'scale_factor': job_info.scale_factor
                }
            }

            # Envoi du message au client
            self.logger.info(
                f"Envoi du lot {batch_id} au client {client_mac} "
                f"({batch_info.total_images} images, modèle: {job_info.model})"
            )

            # Network I/O - done WITHOUT holding locks
            send_success = await self.send_message_to_client(client_mac, batch_message)

            if send_success:
                # Mise à jour du statut après envoi réussi - lock required
                async with self.batches_lock:
                    if batch_id in self.active_batches:
                        self.active_batches[batch_id].status = "processing"
                self.logger.info(
                    f"Lot {batch_id} envoyé avec succès au client {client_mac} "
                    f"(tentative {batch_info.retry_count + 1}/{self.max_retry_attempts})"
                )
            else:
                raise Exception("Échec de l'envoi du message au client")

        except Exception as e:
            self.logger.error(f"Erreur envoi lot {batch_id} à {client_mac}: {e}")

            # Remettre le lot en attente et libérer le client - locks required
            async with self.clients_lock:
                if client_mac in self.connected_clients:
                    self.connected_clients[client_mac].status = "idle"
                    self.connected_clients[client_mac].current_batch = None

            await self.reassign_batch(batch_id)
    
    async def create_batch_package(self, batch_info: BatchInfo) -> bytes:
        """Crée un package chiffré pour un lot"""
        zip_path = None
        try:
            # Vérification du dossier d'entrée
            if not batch_info.input_path or not batch_info.input_path.exists():
                raise Exception(
                    f"Dossier d'entrée invalide ou inexistant: {batch_info.input_path}"
                )

            # Création du fichier ZIP avec les images
            zip_path = self.temp_dir / f"{batch_info.batch_id}.zip"

            images_added = 0
            missing_images = []

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zipf:
                # Ajout des images du lot
                for i in range(batch_info.start_frame, batch_info.end_frame + 1):
                    image_path = batch_info.input_path / f"frame_{i:06d}.png"
                    if image_path.exists():
                        zipf.write(image_path, image_path.name)
                        images_added += 1
                    else:
                        missing_images.append(i)

            # Vérification du nombre d'images
            if images_added == 0:
                raise Exception(
                    f"Aucune image trouvée pour le lot {batch_info.batch_id} "
                    f"dans {batch_info.input_path}"
                )

            if missing_images:
                self.logger.warning(
                    f"Lot {batch_info.batch_id}: {len(missing_images)} images manquantes "
                    f"sur {batch_info.total_images} (frames: {missing_images[:5]}...)"
                )

            # Lecture du ZIP
            with open(zip_path, 'rb') as f:
                zip_data = f.read()

            # Vérification de la taille
            if len(zip_data) == 0:
                raise Exception(f"Fichier ZIP vide pour le lot {batch_info.batch_id}")

            self.logger.debug(
                f"Lot {batch_info.batch_id}: {images_added} images dans le ZIP "
                f"({len(zip_data)} bytes)"
            )

            # Chiffrement des données avec la clé de session du client
            encrypted_data = zip_data  # Par défaut, données non chiffrées

            if batch_info.assigned_client and self.encryption_manager:
                client_info = self.connected_clients.get(batch_info.assigned_client)
                if client_info and client_info.session_key:
                    try:
                        # Récupération ou création de la session de chiffrement
                        session = self.encryption_manager.get_session(batch_info.assigned_client)
                        if not session:
                            # Créer une session avec la clé existante
                            session = self.encryption_manager.create_session(batch_info.assigned_client)
                            # Utiliser la clé de session stockée
                            session.aes_key = client_info.session_key

                        # Chiffrement des données
                        encrypted_data = session.encrypt_data(zip_data)
                        self.logger.debug(
                            f"Lot {batch_info.batch_id} chiffré: "
                            f"{len(zip_data)} -> {len(encrypted_data)} bytes"
                        )
                    except Exception as e:
                        self.logger.error(f"Erreur chiffrement lot {batch_info.batch_id}: {e}")
                        # En cas d'erreur, envoyer en clair pour maintenir la compatibilité
                        self.logger.warning(f"Envoi du lot {batch_info.batch_id} en clair")
                        encrypted_data = zip_data
                else:
                    # Pas de clé de session, envoyer en clair
                    self.logger.warning(
                        f"Pas de clé de session pour {batch_info.assigned_client}, "
                        f"envoi du lot {batch_info.batch_id} en clair"
                    )
            else:
                # Pas de gestionnaire de chiffrement, envoyer en clair
                self.logger.debug(f"Envoi du lot {batch_info.batch_id} sans chiffrement")

            return encrypted_data

        except Exception as e:
            self.logger.error(f"Erreur création package lot {batch_info.batch_id}: {e}")
            raise
        finally:
            # Nettoyage du fichier ZIP temporaire
            if zip_path and zip_path.exists():
                try:
                    zip_path.unlink()
                    self.logger.debug(f"Fichier ZIP temporaire supprimé: {zip_path}")
                except Exception as e:
                    self.logger.warning(f"Erreur suppression ZIP temporaire {zip_path}: {e}")
    
    async def handle_batch_progress(self, client_mac: str, message: dict):
        """Gère la progression d'un lot de manière thread-safe

        Met à jour le statut de progression d'un lot en cours de traitement.

        Args:
            client_mac: Adresse MAC du client
            message: Message contenant l'ID du lot et le nombre d'images traitées
        """
        batch_id = message.get('batch_id')
        processed_count = message.get('processed_count', 0)

        async with self.batches_lock:
            if batch_id in self.active_batches:
                batch_info = self.active_batches[batch_id]
                batch_info.status = "processing"

                self.logger.debug(f"Progression lot {batch_id}: {processed_count}/{batch_info.total_images}")
    
    async def handle_batch_completed(self, client_mac: str, message: dict):
        """Gère la completion d'un lot de manière thread-safe

        Cette méthode traite la réception d'un lot complété par un client,
        incluant la validation, le déchiffrement et la mise à jour des statistiques.

        Args:
            client_mac: Adresse MAC du client
            message: Message contenant les données du lot complété
        """
        batch_id = message.get('batch_id')

        # Quick check for batch existence
        async with self.batches_lock:
            if batch_id not in self.active_batches:
                self.logger.warning(f"Lot inconnu reçu: {batch_id}")
                return
            batch_info = self.active_batches[batch_id]

        try:
            # Réception du lot traité (en base64)
            result_data = message.get('result_data') or message.get('processed_data')

            if not result_data:
                raise Exception("Aucune donnée de résultat reçue")

            # Décodage des données base64
            processed_bytes = base64.b64decode(result_data)

            # Déchiffrement et extraction (I/O intensive, done without locks)
            success = await self.process_completed_batch(batch_info, processed_bytes)

            if success:
                # Update batch and client state atomically
                async with self.clients_lock:
                    async with self.batches_lock:
                        if batch_id in self.active_batches:
                            self.active_batches[batch_id].status = "completed"
                            self.active_batches[batch_id].completed_at = datetime.now()

                        # Mise à jour des statistiques client
                        if client_mac in self.connected_clients:
                            client_info = self.connected_clients[client_mac]
                            client_info.batches_processed += 1
                            client_info.total_images_processed += batch_info.total_images
                            client_info.status = "idle"
                            client_info.current_batch = None

                self.logger.info(f"Lot {batch_id} complété par {client_mac}")

                # Vérifier si le job est terminé (handles its own locking)
                await self.check_job_completion(batch_info.job_id)

            else:
                await self.reassign_batch(batch_id)

        except Exception as e:
            self.logger.error(f"Erreur traitement lot complété {batch_id}: {e}")
            await self.reassign_batch(batch_id)
    
    async def process_completed_batch(self, batch_info: BatchInfo, processed_data: bytes) -> bool:
        """Traite un lot complété reçu d'un client

        Déchiffre, extrait et valide les images traitées reçues du client.
        Vérifie l'intégrité des données et la validité des images avant de les
        sauvegarder dans le dossier de sortie du job.

        Args:
            batch_info: Informations sur le lot à traiter
            processed_data: Données chiffrées reçues du client (ZIP)

        Returns:
            True si le traitement a réussi, False sinon
        """
        temp_zip_path = None
        extracted_files = []

        try:
            # Validation des données d'entrée
            if not processed_data or len(processed_data) == 0:
                self.logger.error(f"Lot {batch_info.batch_id}: données vides reçues")
                return False

            if not batch_info.output_path:
                self.logger.error(f"Lot {batch_info.batch_id}: chemin de sortie non défini")
                return False

            # Création du dossier de sortie si nécessaire
            batch_info.output_path.mkdir(parents=True, exist_ok=True)

            self.logger.info(
                f"Traitement du lot {batch_info.batch_id}: "
                f"{len(processed_data)} bytes reçus, {batch_info.total_images} images attendues"
            )

            # Déchiffrement des données avec la clé de session si nécessaire
            if batch_info.assigned_client and self.encryption_manager:
                client_info = self.connected_clients.get(batch_info.assigned_client)
                if client_info and client_info.session_key:
                    try:
                        # Récupération de la session de chiffrement
                        session = self.encryption_manager.get_session(batch_info.assigned_client)
                        if not session:
                            # Créer une session avec la clé existante
                            session = self.encryption_manager.create_session(batch_info.assigned_client)
                            # Utiliser la clé de session stockée
                            session.aes_key = client_info.session_key

                        # Déchiffrement des données
                        decrypted_data = session.decrypt_data(processed_data)
                        self.logger.debug(
                            f"Lot {batch_info.batch_id} déchiffré: "
                            f"{len(processed_data)} -> {len(decrypted_data)} bytes"
                        )
                        processed_data = decrypted_data
                    except Exception as e:
                        self.logger.error(f"Erreur déchiffrement lot {batch_info.batch_id}: {e}")
                        # En cas d'erreur, on essaie de traiter les données en clair
                        self.logger.warning(f"Tentative de traitement du lot {batch_info.batch_id} en clair")

            # Sauvegarder le ZIP temporaire
            temp_zip_path = self.temp_dir / f"{batch_info.batch_id}_result.zip"
            try:
                with open(temp_zip_path, 'wb') as f:
                    f.write(processed_data)
                self.logger.debug(f"ZIP temporaire créé: {temp_zip_path} ({temp_zip_path.stat().st_size} bytes)")
            except Exception as e:
                self.logger.error(f"Erreur écriture ZIP temporaire {temp_zip_path}: {e}")
                return False

            # Validation et extraction du fichier ZIP
            try:
                # Vérifier que c'est un ZIP valide
                if not zipfile.is_zipfile(temp_zip_path):
                    self.logger.error(
                        f"Lot {batch_info.batch_id}: fichier ZIP invalide ou corrompu"
                    )
                    return False

                # Ouvrir et analyser le ZIP
                with zipfile.ZipFile(temp_zip_path, 'r') as zipf:
                    # Tester l'intégrité du ZIP
                    bad_file = zipf.testzip()
                    if bad_file:
                        self.logger.error(
                            f"Lot {batch_info.batch_id}: fichier corrompu dans le ZIP: {bad_file}"
                        )
                        return False

                    # Liste des fichiers dans le ZIP
                    file_list = zipf.namelist()
                    file_count = len(file_list)

                    self.logger.debug(
                        f"Lot {batch_info.batch_id}: {file_count} fichiers dans le ZIP"
                    )

                    # Vérification du nombre d'images
                    if file_count == 0:
                        self.logger.error(f"Lot {batch_info.batch_id}: ZIP vide")
                        return False

                    if file_count != batch_info.total_images:
                        self.logger.warning(
                            f"Lot {batch_info.batch_id}: nombre d'images incorrect "
                            f"({file_count} reçues, {batch_info.total_images} attendues)"
                        )
                        # Ne pas échouer si on a au moins quelques images
                        if file_count < batch_info.total_images * 0.5:  # Moins de 50%
                            self.logger.error(
                                f"Lot {batch_info.batch_id}: trop peu d'images reçues "
                                f"({file_count}/{batch_info.total_images})"
                            )
                            return False

                    # Validation des noms de fichiers et types
                    expected_frames = set()
                    for i in range(batch_info.start_frame, batch_info.end_frame + 1):
                        expected_frames.add(f"frame_{i:06d}.png")

                    received_frames = set()
                    invalid_files = []

                    for filename in file_list:
                        # Vérifier l'extension
                        if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                            invalid_files.append(filename)
                            self.logger.warning(
                                f"Lot {batch_info.batch_id}: fichier avec extension invalide: {filename}"
                            )
                            continue

                        # Vérifier le format du nom
                        if filename.startswith('frame_') and filename.endswith('.png'):
                            received_frames.add(filename)

                    # Identifier les frames manquantes
                    missing_frames = expected_frames - received_frames
                    if missing_frames:
                        self.logger.warning(
                            f"Lot {batch_info.batch_id}: {len(missing_frames)} frames manquantes: "
                            f"{sorted(list(missing_frames))[:5]}{'...' if len(missing_frames) > 5 else ''}"
                        )

                    # Identifier les frames supplémentaires (ne devrait pas arriver)
                    extra_frames = received_frames - expected_frames
                    if extra_frames:
                        self.logger.warning(
                            f"Lot {batch_info.batch_id}: {len(extra_frames)} frames supplémentaires: "
                            f"{sorted(list(extra_frames))[:5]}{'...' if len(extra_frames) > 5 else ''}"
                        )

                    # Extraire vers le dossier de sortie
                    self.logger.debug(
                        f"Extraction vers {batch_info.output_path}"
                    )
                    zipf.extractall(batch_info.output_path)
                    extracted_files = file_list.copy()

            except zipfile.BadZipFile as e:
                self.logger.error(
                    f"Lot {batch_info.batch_id}: fichier ZIP corrompu: {e}"
                )
                return False
            except Exception as e:
                self.logger.error(
                    f"Lot {batch_info.batch_id}: erreur lors de l'extraction du ZIP: {e}"
                )
                return False

            # Validation des images extraites
            valid_images = 0
            invalid_images = []

            for filename in extracted_files:
                if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    continue

                image_path = batch_info.output_path / filename

                if not image_path.exists():
                    invalid_images.append((filename, "fichier non extrait"))
                    continue

                # Vérifier que le fichier n'est pas vide
                try:
                    file_size = image_path.stat().st_size
                    if file_size == 0:
                        invalid_images.append((filename, "fichier vide"))
                        self.logger.warning(
                            f"Lot {batch_info.batch_id}: image vide: {filename}"
                        )
                        # Supprimer le fichier vide
                        image_path.unlink()
                        continue

                    # Vérifier la signature du fichier (magic bytes)
                    with open(image_path, 'rb') as f:
                        header = f.read(8)
                        # PNG signature
                        is_png = header[:8] == b'\x89PNG\r\n\x1a\n'
                        # JPEG signature
                        is_jpeg = header[:2] == b'\xff\xd8'

                        if not (is_png or is_jpeg):
                            invalid_images.append((filename, "format invalide"))
                            self.logger.warning(
                                f"Lot {batch_info.batch_id}: image corrompue ou format invalide: {filename}"
                            )
                            # Ne pas supprimer, laisser pour investigation
                            continue

                    valid_images += 1

                except Exception as e:
                    invalid_images.append((filename, str(e)))
                    self.logger.warning(
                        f"Lot {batch_info.batch_id}: erreur validation image {filename}: {e}"
                    )

            # Rapport de validation
            if invalid_images:
                self.logger.warning(
                    f"Lot {batch_info.batch_id}: {len(invalid_images)} images invalides détectées"
                )
                for filename, reason in invalid_images[:5]:  # Afficher max 5
                    self.logger.debug(f"  - {filename}: {reason}")

            # Vérifier qu'on a un nombre suffisant d'images valides
            min_required_images = max(1, int(batch_info.total_images * 0.8))  # Au moins 80%
            if valid_images < min_required_images:
                self.logger.error(
                    f"Lot {batch_info.batch_id}: nombre d'images valides insuffisant "
                    f"({valid_images}/{batch_info.total_images}, minimum requis: {min_required_images})"
                )
                return False

            # Nettoyage du fichier temporaire
            if temp_zip_path and temp_zip_path.exists():
                try:
                    temp_zip_path.unlink()
                    self.logger.debug(f"ZIP temporaire supprimé: {temp_zip_path}")
                except Exception as e:
                    self.logger.warning(f"Erreur suppression ZIP temporaire {temp_zip_path}: {e}")

            # Succès
            self.logger.info(
                f"Lot {batch_info.batch_id} traité avec succès: "
                f"{valid_images}/{batch_info.total_images} images valides extraites vers {batch_info.output_path}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Erreur inattendue lors du traitement du lot {batch_info.batch_id}: {e}")
            import traceback
            self.logger.debug(f"Traceback: {traceback.format_exc()}")

            # Tentative de nettoyage en cas d'erreur
            if temp_zip_path and temp_zip_path.exists():
                try:
                    temp_zip_path.unlink()
                    self.logger.debug(f"ZIP temporaire nettoyé après erreur: {temp_zip_path}")
                except Exception as cleanup_error:
                    self.logger.warning(f"Erreur nettoyage ZIP temporaire: {cleanup_error}")

            return False
    
    async def handle_batch_error(self, client_mac: str, message: dict):
        """Gère une erreur de traitement de lot de manière thread-safe

        Cette méthode est appelée lorsqu'un client signale une erreur lors du
        traitement d'un lot. Elle libère le client et réassigne le lot.

        Args:
            client_mac: Adresse MAC du client
            message: Message contenant les détails de l'erreur
        """
        batch_id = message.get('batch_id')
        error_message = message.get('error_message') or message.get('error', 'Erreur inconnue')

        self.logger.warning(f"Erreur lot {batch_id} par {client_mac}: {error_message}")

        # Réinitialiser le statut du client
        async with self.clients_lock:
            if client_mac in self.connected_clients:
                client_info = self.connected_clients[client_mac]
                client_info.status = "idle"
                client_info.current_batch = None

        # reassign_batch() handles its own locking
        await self.reassign_batch(batch_id)
    
    async def reassign_batch(self, batch_id: str):
        """Remet un lot en attente pour réassignation de manière thread-safe

        Cette méthode est appelée lorsqu'un batch échoue ou qu'un client se déconnecte.
        Elle utilise les locks appropriés pour garantir la cohérence des données.

        Args:
            batch_id: ID du batch à réassigner
        """
        # Acquire locks in the correct order: clients_lock, then batches_lock
        async with self.clients_lock:
            async with self.batches_lock:
                if batch_id not in self.active_batches:
                    return

                batch_info = self.active_batches[batch_id]
                assigned_client = batch_info.assigned_client

                batch_info.retry_count += 1

                if batch_info.retry_count >= self.max_retry_attempts:
                    batch_info.status = "error"
                    batch_info.assigned_client = None
                    batch_info.assigned_at = None
                    self.logger.error(f"Lot {batch_id} abandonné après {self.max_retry_attempts} tentatives")
                    return

                # Remettre en attente
                batch_info.status = "pending"
                batch_info.assigned_client = None
                batch_info.assigned_at = None
                self.pending_batches.append(batch_id)

                # Libérer le client si nécessaire
                if assigned_client and assigned_client in self.connected_clients:
                    client_info = self.connected_clients[assigned_client]
                    client_info.status = "idle"
                    client_info.current_batch = None

                self.logger.info(f"Lot {batch_id} remis en attente (tentative {batch_info.retry_count})")
    
    async def disconnect_client(self, client_mac: str):
        """Déconnecte un client de manière thread-safe

        Cette méthode gère la déconnexion propre d'un client, incluant la réassignation
        de son batch en cours et le nettoyage de toutes les ressources associées.

        Args:
            client_mac: Adresse MAC du client à déconnecter
        """
        # First check if client exists and get current batch (quick check with lock)
        current_batch = None
        async with self.clients_lock:
            if client_mac not in self.connected_clients:
                return

            client_info = self.connected_clients[client_mac]
            current_batch = client_info.current_batch

        # Réassigner le lot en cours si nécessaire (BEFORE removing client)
        # This is done outside the lock to avoid holding it during reassign_batch
        if current_batch:
            await self.reassign_batch(current_batch)

        # Fermer la session de chiffrement si elle existe
        # This is I/O and doesn't need locks
        if self.encryption_manager:
            try:
                self.encryption_manager.close_session(client_mac)
                self.logger.debug(f"Session de chiffrement fermée pour {client_mac}")
            except Exception as e:
                self.logger.debug(f"Erreur fermeture session de chiffrement pour {client_mac}: {e}")

        # Now remove client from all data structures atomically
        async with self.clients_lock:
            # Fermer la connexion WebSocket si elle existe
            if client_mac in self.client_websockets:
                websocket = self.client_websockets[client_mac]
                try:
                    if not websocket.closed:
                        await websocket.close(1000, "Server disconnect")
                except Exception as e:
                    self.logger.debug(f"Erreur lors de la fermeture du websocket pour {client_mac}: {e}")
                del self.client_websockets[client_mac]

            # Supprimer le client
            if client_mac in self.connected_clients:
                del self.connected_clients[client_mac]

        self.logger.info(f"Client déconnecté: {client_mac}")
    
    async def monitor_clients(self):
        """Surveille les clients connectés et déconnecte ceux qui ont timeout

        Cette tâche background vérifie périodiquement l'activité des clients et
        déconnecte ceux qui n'ont pas envoyé de heartbeat dans le délai imparti.
        """
        while self.running:
            try:
                current_time = datetime.now()
                clients_to_disconnect = []

                # Create a snapshot of clients to check (avoid holding lock during iteration)
                async with self.clients_lock:
                    # Copy the items to avoid "dictionary changed size during iteration" errors
                    clients_snapshot = list(self.connected_clients.items())

                # Check timeouts without holding the lock
                for client_mac, client_info in clients_snapshot:
                    # Vérifier le timeout
                    if (current_time - client_info.last_seen).total_seconds() > self.client_timeout:
                        clients_to_disconnect.append(client_mac)

                # Déconnecter les clients expirés
                # disconnect_client() handles its own locking
                for client_mac in clients_to_disconnect:
                    await self.disconnect_client(client_mac)

                await asyncio.sleep(60)  # Vérification toutes les minutes

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Erreur surveillance clients: {e}")
                await asyncio.sleep(60)
    
    async def manage_batches(self):
        """Gère la distribution des lots de manière thread-safe

        Cette tâche background distribue automatiquement les lots en attente
        aux clients disponibles. Elle vérifie périodiquement l'état des clients
        et des lots pour effectuer des assignations.
        """
        while self.running:
            try:
                # Get snapshot of idle clients and pending batches count
                # Use separate locks to minimize lock contention
                idle_clients = []
                async with self.clients_lock:
                    # Create list of idle clients
                    idle_clients = [
                        mac for mac, client in self.connected_clients.items()
                        if client.status == "idle"
                    ]

                has_pending_batches = False
                async with self.batches_lock:
                    has_pending_batches = len(self.pending_batches) > 0

                # Only attempt assignments if both conditions are met
                if has_pending_batches and idle_clients:
                    # Assigner des lots aux clients disponibles
                    # assign_batch_to_client() handles its own locking
                    # Limit to avoid overwhelming the system
                    for client_mac in idle_clients[:10]:  # Process max 10 at a time
                        try:
                            await self.assign_batch_to_client(client_mac)
                        except Exception as e:
                            self.logger.error(f"Erreur assignation lot à {client_mac}: {e}")

                await asyncio.sleep(5)  # Vérification toutes les 5 secondes

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Erreur gestion lots: {e}")
                await asyncio.sleep(5)
    
    # === API publique pour la création de jobs ===
    
    async def create_job(self, video_path: Path, scale_factor: int = 4,
                        model: str = "realesr-animevideov3") -> str:
        """Crée un nouveau job d'upscaling de manière thread-safe

        Cette méthode crée un nouveau job d'upscaling, extrait les frames de la vidéo,
        et crée tous les lots nécessaires pour le traitement distribué.

        Args:
            video_path: Chemin vers la vidéo à traiter
            scale_factor: Facteur d'agrandissement (2 ou 4)
            model: Modèle d'upscaling à utiliser

        Returns:
            L'ID du job créé
        """
        try:
            # Génération de l'ID du job
            job_id = f"job_{int(time.time())}_{uuid.uuid4().hex[:8]}"

            # Création des dossiers du job
            job_dir = self.jobs_dir / job_id
            frames_dir = job_dir / "frames"
            output_dir = job_dir / "output"

            for directory in [job_dir, frames_dir, output_dir]:
                directory.mkdir(parents=True, exist_ok=True)

            # Extraction des frames avec FFmpeg (I/O intensive, done without locks)
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

            # Add job atomically
            async with self.jobs_lock:
                self.active_jobs[job_id] = job_info

            # Création des lots (handles its own locking)
            await self.create_batches_for_job(job_info, frames_dir)

            # Démarrage du job
            async with self.jobs_lock:
                if job_id in self.active_jobs:
                    self.active_jobs[job_id].status = "processing"
                    self.active_jobs[job_id].started_at = datetime.now()

            self.logger.info(f"Job {job_id} créé: {total_batches} lots, {total_frames} frames")

            return job_id

        except Exception as e:
            self.logger.error(f"Erreur création job: {e}")
            raise
    
    async def create_batches_for_job(self, job_info: JobInfo, frames_dir: Path):
        """Crée les lots pour un job de manière thread-safe

        Cette méthode crée tous les lots nécessaires pour traiter un job et les
        ajoute à la file d'attente pour distribution aux clients.

        Args:
            job_info: Informations sur le job
            frames_dir: Répertoire contenant les frames extraites
        """
        batches_to_add = []

        # Prepare all batches without holding locks
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

            batches_to_add.append((batch_id, batch_info))

        # Add all batches atomically
        async with self.batches_lock:
            for batch_id, batch_info in batches_to_add:
                self.active_batches[batch_id] = batch_info
                self.pending_batches.append(batch_id)
    
    async def check_job_completion(self, job_id: str):
        """Vérifie si un job est terminé de manière thread-safe

        Cette méthode compte les lots complétés pour un job et déclenche
        l'assemblage de la vidéo finale si tous les lots sont terminés.

        Args:
            job_id: ID du job à vérifier
        """
        # Check job existence and count completed batches
        async with self.jobs_lock:
            if job_id not in self.active_jobs:
                return
            job_info = self.active_jobs[job_id]

        # Count completed batches
        async with self.batches_lock:
            completed_batches = sum(
                1 for batch in self.active_batches.values()
                if batch.job_id == job_id and batch.status == "completed"
            )

        # Update job info
        async with self.jobs_lock:
            if job_id in self.active_jobs:
                self.active_jobs[job_id].completed_batches = completed_batches

                if completed_batches >= job_info.total_batches:
                    # Job terminé, assembler la vidéo finale
                    # This is done outside the lock since it's I/O intensive
                    pass

        # Assemble video outside of locks
        if completed_batches >= job_info.total_batches:
            await self.assemble_final_video(job_info)
    
    async def assemble_final_video(self, job_info: JobInfo):
        """Assemble la vidéo finale de manière thread-safe

        Cette méthode assemble tous les frames traités en une vidéo finale.
        Les mises à jour du statut du job sont protégées par des locks.

        Args:
            job_info: Informations sur le job à assembler
        """
        try:
            # Update status to assembling
            async with self.jobs_lock:
                if job_info.job_id in self.active_jobs:
                    self.active_jobs[job_info.job_id].status = "assembling"

            output_frames_dir = self.jobs_dir / job_info.job_id / "output"

            # Assemblage avec FFmpeg (I/O intensive, done without locks)
            if self.ffmpeg_handler:
                await self.ffmpeg_handler.assemble_video(
                    output_frames_dir,
                    job_info.video_path,  # Pour l'audio
                    job_info.output_path
                )

            # Update status to completed
            async with self.jobs_lock:
                if job_info.job_id in self.active_jobs:
                    self.active_jobs[job_info.job_id].status = "completed"
                    self.active_jobs[job_info.job_id].completed_at = datetime.now()

            self.logger.info(f"Job {job_info.job_id} terminé: {job_info.output_path}")

        except Exception as e:
            # Update status to error
            async with self.jobs_lock:
                if job_info.job_id in self.active_jobs:
                    self.active_jobs[job_info.job_id].status = "error"
                    self.active_jobs[job_info.job_id].error_message = str(e)
            self.logger.error(f"Erreur assemblage job {job_info.job_id}: {e}")
    
    # === Méthodes d'état et statistiques ===
    
    def get_server_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du serveur de manière thread-safe

        Note: This is a synchronous method that needs to be called from async context.
        Consider using asyncio.create_task() if calling from async code.

        Returns:
            Dictionnaire contenant les statistiques du serveur
        """
        uptime = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0

        # Note: Since this is a sync method and we need locks, we use a workaround
        # In production, this should be made async or use proper synchronization
        # For now, we accept potential race conditions in stats reading
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
        """Retourne les statistiques des clients

        Note: This is a synchronous method. Stats reading may have minor race conditions.
        Consider making this async in production for full thread-safety.

        Returns:
            Liste des statistiques de chaque client connecté
        """
        return [client.to_dict() for client in self.connected_clients.values()]

    def get_job_stats(self) -> List[Dict[str, Any]]:
        """Retourne les statistiques des jobs

        Note: This is a synchronous method. Stats reading may have minor race conditions.
        Consider making this async in production for full thread-safety.

        Returns:
            Liste des statistiques de chaque job actif
        """
        return [job.to_dict() for job in self.active_jobs.values()]

    def get_batch_stats(self) -> List[Dict[str, Any]]:
        """Retourne les statistiques des lots

        Note: This is a synchronous method. Stats reading may have minor race conditions.
        Consider making this async in production for full thread-safety.

        Returns:
            Liste des statistiques de chaque batch actif
        """
        return [batch.to_dict() for batch in self.active_batches.values()]