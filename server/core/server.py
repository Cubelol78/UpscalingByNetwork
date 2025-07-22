import asyncio
import logging
import json
import time
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import websockets
from websockets.server import WebSocketServerProtocol

from models.batch import Batch, BatchStatus
from models.client import Client, ClientStatus
from models.job import Job, JobStatus
from config.settings import config
from utils.logger import get_logger

# core/server.py
class UpscalingServer:
    """Serveur principal d'upscaling distribué"""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        self.clients: Dict[str, Client] = {}  # MAC -> Client
        self.websockets: Dict[str, WebSocketServerProtocol] = {}  # MAC -> WebSocket
        self.jobs: Dict[str, Job] = {}  # Job ID -> Job
        self.batches: Dict[str, Batch] = {}  # Batch ID -> Batch
        self.current_job: Optional[str] = None
        self.running = False
        self.server = None
        
        # Managers
        from core.batch_manager import BatchManager
        from core.client_manager import ClientManager
        from core.video_processor import VideoProcessor
        
        self.batch_manager = BatchManager(self)
        self.client_manager = ClientManager(self)
        self.video_processor = VideoProcessor(self)
    
    async def start(self):
        """Démarre le serveur"""
        self.running = True
        self.logger.info(f"Démarrage du serveur sur {config.HOST}:{config.PORT}")
        
        # Démarrage des tâches de maintenance
        asyncio.create_task(self._heartbeat_monitor())
        
        # Démarrage du serveur WebSocket
        self.server = await websockets.serve(
            self._handle_client,
            config.HOST,
            config.PORT,
            max_size=10 * 1024 * 1024  # 10MB pour les images
        )
        
        self.logger.info("Serveur démarré et en attente de connexions")
        
        # Boucle principale
        try:
            await self.server.wait_closed()
        except asyncio.CancelledError:
            pass
    
    async def stop(self):
        """Arrête le serveur"""
        self.running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        self.logger.info("Serveur arrêté")
    
    async def _handle_client(self, websocket: WebSocketServerProtocol, path: str):
        """Gère une connexion client"""
        client_ip = websocket.remote_address[0]
        self.logger.info(f"Nouvelle connexion depuis {client_ip}")
        
        client_mac = None
        try:
            async for message in websocket:
                data = json.loads(message)
                
                if data["type"] == "register":
                    client_mac = await self._register_client(websocket, data)
                    if client_mac:
                        self.websockets[client_mac] = websocket
                
                elif data["type"] == "heartbeat":
                    await self._handle_heartbeat(data)
                
                elif data["type"] == "batch_result":
                    await self._handle_batch_result(data)
                
                elif data["type"] == "batch_progress":
                    await self._handle_batch_progress(data)
                
                elif data["type"] == "client_status":
                    await self._handle_client_status(data)
        
        except websockets.exceptions.ConnectionClosed:
            self.logger.info(f"Client {client_ip} déconnecté")
        except Exception as e:
            self.logger.error(f"Erreur avec le client {client_ip}: {e}")
        finally:
            if client_mac and client_mac in self.clients:
                self.clients[client_mac].disconnect()
                if client_mac in self.websockets:
                    del self.websockets[client_mac]
    
    async def _register_client(self, websocket: WebSocketServerProtocol, data: dict) -> Optional[str]:
        """Enregistre un nouveau client"""
        try:
            client_info = data["client_info"]
            mac_address = client_info["mac_address"]
            
            # Vérification de la limite de clients
            if len(self.clients) >= config.MAX_CLIENTS and mac_address not in self.clients:
                await websocket.send(json.dumps({
                    "type": "registration_rejected",
                    "reason": "Server full"
                }))
                return None
            
            # Création ou mise à jour du client
            if mac_address in self.clients:
                client = self.clients[mac_address]
                client.ip_address = websocket.remote_address[0]
                client.update_heartbeat()
            else:
                client = Client(
                    mac_address=mac_address,
                    ip_address=websocket.remote_address[0],
                    hostname=client_info.get("hostname", ""),
                    platform=client_info.get("platform", ""),
                    gpu_info=client_info.get("gpu_info", {}),
                    cpu_info=client_info.get("cpu_info", {}),
                    capabilities=client_info.get("capabilities", {})
                )
                self.clients[mac_address] = client
            
            client.status = ClientStatus.CONNECTED
            
            # Confirmation d'enregistrement
            await websocket.send(json.dumps({
                "type": "registration_accepted",
                "client_id": mac_address,
                "server_info": {
                    "batch_size": config.BATCH_SIZE,
                    "model": config.REALESRGAN_MODEL,
                    "tile_size": config.TILE_SIZE
                }
            }))
            
            self.logger.info(f"Client enregistré: {mac_address} ({client.hostname})")
            return mac_address
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'enregistrement du client: {e}")
            return None
    
    async def _handle_heartbeat(self, data: dict):
        """Traite un heartbeat client"""
        mac_address = data.get("client_id")
        if mac_address in self.clients:
            self.clients[mac_address].update_heartbeat()
    
    async def _handle_batch_result(self, data: dict):
        """Traite le résultat d'un lot"""
        batch_id = data.get("batch_id")
        success = data.get("success", False)
        
        if batch_id not in self.batches:
            return
        
        batch = self.batches[batch_id]
        client = self.clients.get(batch.assigned_client)
        
        if success:
            batch.complete()
            if client:
                processing_time = batch.processing_time or 0
                client.complete_batch(processing_time)
            self.logger.info(f"Lot {batch_id} terminé avec succès")
            
            # Mise à jour du job
            await self._update_job_progress(batch.job_id)
            
        else:
            error_msg = data.get("error", "Erreur inconnue")
            batch.fail(error_msg)
            if client:
                client.fail_batch()
            self.logger.warning(f"Lot {batch_id} échoué: {error_msg}")
            
            # Remettre le lot en attente si sous le seuil de tentatives
            if batch.retry_count < config.MAX_RETRIES:
                batch.reset()
                self.logger.info(f"Lot {batch_id} remis en attente (tentative {batch.retry_count + 1})")
    
    async def _handle_batch_progress(self, data: dict):
        """Traite la progression d'un lot"""
        batch_id = data.get("batch_id")
        progress = data.get("progress", 0)
        
        if batch_id in self.batches:
            self.batches[batch_id].progress = progress
    
    async def _handle_client_status(self, data: dict):
        """Traite le statut d'un client"""
        mac_address = data.get("client_id")
        status_info = data.get("status", {})
        
        if mac_address in self.clients:
            client = self.clients[mac_address]
            # Mise à jour des informations du client
            if "gpu_usage" in status_info:
                client.gpu_info["usage"] = status_info["gpu_usage"]
            if "cpu_usage" in status_info:
                client.cpu_info["usage"] = status_info["cpu_usage"]
    
    async def _heartbeat_monitor(self):
        """Surveille les heartbeats des clients"""
        while self.running:
            try:
                current_time = time.time()
                disconnected_clients = []
                
                for mac_address, client in self.clients.items():
                    if not client.is_online:
                        disconnected_clients.append(mac_address)
                        self.logger.warning(f"Client {mac_address} timeout")
                
                # Traitement des clients déconnectés
                for mac_address in disconnected_clients:
                    client = self.clients[mac_address]
                    client.disconnect()
                    
                    # Libération du lot en cours
                    if client.current_batch:
                        batch = self.batches.get(client.current_batch)
                        if batch:
                            batch.reset()
                            self.logger.info(f"Lot {batch.id} libéré suite à déconnexion client")
                
                await asyncio.sleep(config.HEARTBEAT_INTERVAL)
                
            except Exception as e:
                self.logger.error(f"Erreur dans batch_monitor: {e}")
                await asyncio.sleep(5)
    
    async def _update_job_progress(self, job_id: str):
        """Met à jour la progression d'un job"""
        if job_id not in self.jobs:
            return
        
        job = self.jobs[job_id]
        completed_count = sum(1 for batch_id in job.batches 
                             if self.batches[batch_id].status == BatchStatus.COMPLETED)
        
        job.completed_batches = completed_count
        
        # Vérification si le job est terminé
        if completed_count == len(job.batches):
            self.logger.info(f"Job {job_id} - tous les lots terminés, assemblage de la vidéo")
            job.status = JobStatus.ASSEMBLING
            
            # Lancement de l'assemblage en arrière-plan
            asyncio.create_task(self._assemble_video(job_id))
    
    async def _assemble_video(self, job_id: str):
        """Assemble la vidéo finale"""
        try:
            job = self.jobs[job_id]
            success = await self.video_processor.assemble_video(job)
            
            if success:
                job.complete()
                self.logger.info(f"Job {job_id} terminé avec succès")
            else:
                job.fail("Erreur lors de l'assemblage de la vidéo")
                self.logger.error(f"Job {job_id} échoué lors de l'assemblage")
                
        except Exception as e:
            job.fail(f"Erreur d'assemblage: {str(e)}")
            self.logger.error(f"Erreur lors de l'assemblage du job {job_id}: {e}")
    
    async def send_batch_to_client(self, client_mac: str, batch: Batch) -> bool:
        """Envoie un lot à un client"""
        if client_mac not in self.websockets:
            return False
        
        try:
            websocket = self.websockets[client_mac]
            
            message = {
                "type": "batch_assignment",
                "batch_id": batch.id,
                "frame_paths": batch.frame_paths,
                "model": config.REALESRGAN_MODEL,
                "scale": config.REALESRGAN_SCALE,
                "tile_size": config.TILE_SIZE
            }
            
            await websocket.send(json.dumps(message))
            
            # Mise à jour du statut
            batch.assign_to_client(client_mac)
            self.clients[client_mac].assign_batch(batch.id)
            
            self.logger.info(f"Lot {batch.id} envoyé au client {client_mac}")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur envoi lot au client {client_mac}: {e}")
            return False
    
    def get_statistics(self) -> dict:
        """Retourne les statistiques du serveur"""
        total_clients = len(self.clients)
        online_clients = sum(1 for client in self.clients.values() if client.is_online)
        processing_clients = sum(1 for client in self.clients.values() 
                               if client.status == ClientStatus.PROCESSING)
        
        total_batches = len(self.batches)
        pending_batches = sum(1 for batch in self.batches.values() 
                            if batch.status == BatchStatus.PENDING)
        processing_batches = sum(1 for batch in self.batches.values() 
                               if batch.status == BatchStatus.PROCESSING)
        completed_batches = sum(1 for batch in self.batches.values() 
                              if batch.status == BatchStatus.COMPLETED)
        
        current_job_info = {}
        if self.current_job and self.current_job in self.jobs:
            job = self.jobs[self.current_job]
            current_job_info = {
                "id": job.id,
                "status": job.status.value,
                "progress": job.progress,
                "input_file": Path(job.input_video_path).name,
                "total_frames": job.total_frames,
                "estimated_remaining": job.estimated_remaining_time
            }
        
        return {
            "clients": {
                "total": total_clients,
                "online": online_clients,
                "processing": processing_clients
            },
            "batches": {
                "total": total_batches,
                "pending": pending_batches,
                "processing": processing_batches,
                "completed": completed_batches
            },
            "current_job": current_job_info,
            "server": {
                "running": self.running,
                "uptime": int(time.time() - getattr(self, '_start_time', time.time()))
            }
        }