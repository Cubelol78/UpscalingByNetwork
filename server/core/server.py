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

# Imports pour les optimisations
from core.optimized_real_esrgan import optimized_realesrgan
from utils.hardware_detector import hardware_detector

class UpscalingServer:
    """Serveur principal d'upscaling distribué avec optimisations"""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        self.clients: Dict[str, Client] = {}  # MAC -> Client
        self.websockets: Dict[str, WebSocketServerProtocol] = {}  # MAC -> WebSocket
        self.jobs: Dict[str, Job] = {}  # Job ID -> Job
        self.batches: Dict[str, Batch] = {}  # Batch ID -> Batch
        self.current_job: Optional[str] = None
        self.running = False  # Le serveur démarre à l'arrêt
        self.server = None
        self._start_time = time.time()
        
        # Métriques de performance en temps réel
        self.performance_metrics = {
            'total_frames_processed': 0,
            'total_processing_time': 0,
            'average_fps': 0,
            'gpu_utilization_history': [],
            'client_performance_scores': {}
        }
        
        # Configuration adaptative
        self.adaptive_config = {
            'current_batch_size': config.BATCH_SIZE,
            'current_concurrent_limit': 2,
            'last_optimization': time.time()
        }
        
        # Historiques pour optimisation
        self.assignment_history = []
        self.failure_analyses = []
        
        # Managers
        from core.batch_manager import BatchManager
        from core.client_manager import ClientManager
        from core.video_processor import VideoProcessor
        
        self.batch_manager = BatchManager(self)
        self.client_manager = ClientManager(self)
        self.video_processor = VideoProcessor(self)
        
        self.logger.info("Serveur d'upscaling initialisé (arrêté)")
    
    async def start(self):
        """Démarre le serveur"""
        if self.running:
            self.logger.warning("Le serveur est déjà en cours d'exécution")
            return
            
        self.running = True
        self._start_time = time.time()
        self.logger.info(f"Démarrage du serveur sur {config.HOST}:{config.PORT}")
        
        try:
            # Démarrage des tâches de maintenance
            asyncio.create_task(self._heartbeat_monitor())
            asyncio.create_task(self._batch_assignment_loop())
            
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
                
        except Exception as e:
            self.logger.error(f"Erreur lors du démarrage du serveur: {e}")
            self.running = False
            raise
    
    async def stop(self):
        """Arrête le serveur"""
        if not self.running:
            self.logger.warning("Le serveur est déjà arrêté")
            return
            
        self.running = False
        
        # Fermeture de toutes les connexions clients
        for websocket in list(self.websockets.values()):
            try:
                await websocket.close()
            except:
                pass
        
        # Arrêt du serveur WebSocket
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            
        # Nettoyage des données
        self.clients.clear()
        self.websockets.clear()
        
        self.logger.info("Serveur arrêté")
    
    async def _batch_assignment_loop(self):
        """Boucle d'assignation des lots"""
        while self.running:
            try:
                await self.batch_manager.assign_pending_batches()
                await asyncio.sleep(1)  # Vérification chaque seconde
                
            except Exception as e:
                self.logger.error(f"Erreur dans batch_assignment_loop: {e}")
                await asyncio.sleep(5)
    
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
                    await self._handle_batch_result_optimized(data)
                
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
    
    async def _handle_batch_result_optimized(self, data: dict):
        """Version optimisée du traitement des résultats de lot"""
        batch_id = data.get("batch_id")
        success = data.get("success", False)
        performance_data = data.get("performance", {})
        
        if batch_id not in self.batches:
            return
        
        batch = self.batches[batch_id]
        client = self.clients.get(batch.assigned_client)
        
        # Enregistrement des métriques de performance
        processing_time = performance_data.get('processing_time', batch.processing_time or 0)
        gpu_utilization = performance_data.get('gpu_utilization', 0)
        memory_usage = performance_data.get('memory_usage', 0)
        
        if success:
            batch.complete()
            if client:
                client.complete_batch(processing_time)
            
            # Mise à jour des métriques globales
            self._update_performance_metrics(batch, processing_time, performance_data)
            
            # Enregistrement pour le batch manager
            was_duplicated = batch.status == BatchStatus.DUPLICATE
            self.batch_manager.record_batch_completion(batch, processing_time, was_duplicated)
            
            self.logger.info(f"Lot {batch_id} terminé avec succès "
                           f"({processing_time:.1f}s, {gpu_utilization:.1f}% GPU)")
            
            # Mise à jour du job
            await self._update_job_progress(batch.job_id)
            
            # Optimisation adaptative
            await self._adaptive_optimization()
            
        else:
            error_msg = data.get("error", "Erreur inconnue")
            batch.fail(error_msg)
            if client:
                client.fail_batch()
            
            # Analyse de l'erreur pour optimisation
            self._analyze_batch_failure(batch, error_msg, performance_data)
            
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
                self.logger.error(f"Erreur dans heartbeat_monitor: {e}")
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
    
    async def send_batch_to_client(self, client_mac: str, batch: Batch, adaptations: dict = None) -> bool:
        """Version optimisée de l'envoi de lot avec adaptations"""
        if client_mac not in self.websockets:
            return False
        
        try:
            websocket = self.websockets[client_mac]
            
            # Configuration de base
            base_config = optimized_realesrgan.optimal_config.copy()
            
            # Application des adaptations en temps réel
            if adaptations:
                base_config.update(adaptations)
            
            # Adaptation spécifique au client
            client = self.clients.get(client_mac)
            if client:
                client_config = self._get_client_specific_config(client, base_config)
                base_config.update(client_config)
            
            message = {
                "type": "batch_assignment",
                "batch_id": batch.id,
                "frame_paths": batch.frame_paths,
                "config": {
                    "model": base_config.get('model', config.REALESRGAN_MODEL),
                    "scale": config.REALESRGAN_SCALE,
                    "tile_size": base_config.get('tile_size', config.TILE_SIZE),
                    "threads": base_config.get('threads', "2:4:2"),
                    "gpu_id": base_config.get('gpu_id', 0),
                    "use_fp16": base_config.get('use_fp16', True),
                    "tta_mode": base_config.get('tta_mode', False)
                },
                "optimization_info": {
                    "hardware_detected": True,
                    "performance_tier": self._get_client_performance_tier(client_mac),
                    "recommended_monitoring": True
                }
            }
            
            await websocket.send(json.dumps(message))
            
            # Mise à jour du statut
            batch.assign_to_client(client_mac)
            self.clients[client_mac].assign_batch(batch.id)
            
            # Enregistrement de l'assignation pour optimisation future
            self._record_batch_assignment(client_mac, batch, base_config)
            
            self.logger.info(f"Lot {batch.id} envoyé au client {client_mac} avec optimisations")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur envoi lot optimisé au client {client_mac}: {e}")
            return False
    
    def _get_client_specific_config(self, client: Client, base_config: dict) -> dict:
        """Génère une configuration spécifique à un client"""
        adaptations = {}
        
        # Adaptation selon l'historique de performance du client
        if client.average_batch_time > 0:
            if client.average_batch_time > 300:  # > 5 minutes par lot
                # Client lent, configuration conservative
                adaptations['tile_size'] = min(128, base_config.get('tile_size', 256))
                adaptations['threads'] = "1:2:1"
                
            elif client.average_batch_time < 60:  # < 1 minute par lot
                # Client rapide, configuration agressive
                adaptations['tile_size'] = max(384, base_config.get('tile_size', 256))
                adaptations['tta_mode'] = True
        
        # Adaptation selon le taux de succès
        if client.success_rate < 80:
            # Client instable, configuration sûre
            adaptations['tile_size'] = min(128, base_config.get('tile_size', 256))
            adaptations['use_fp16'] = False  # Plus stable
            adaptations['tta_mode'] = False
        
        # Adaptation selon les informations GPU du client
        if hasattr(client, 'gpu_info') and client.gpu_info:
            gpu_memory = client.gpu_info.get('memory_total', 0)
            
            if gpu_memory > 0:
                if gpu_memory < 4096:  # < 4GB
                    adaptations['tile_size'] = min(128, base_config.get('tile_size', 256))
                elif gpu_memory > 16384:  # > 16GB
                    adaptations['tile_size'] = max(512, base_config.get('tile_size', 256))
        
        return adaptations
    
    def _get_client_performance_tier(self, client_mac: str) -> str:
        """Détermine le niveau de performance d'un client"""
        if client_mac not in self.clients:
            return "unknown"
        
        client = self.clients[client_mac]
        
        # Calcul du score de performance
        score = 0
        
        if client.average_batch_time > 0:
            # Plus rapide = meilleur score
            score += 1000 / client.average_batch_time
        
        # Taux de succès
        score *= (client.success_rate / 100) if client.success_rate > 0 else 0.5
        
        # Nombre de lots traités (expérience)
        score += min(client.batches_completed * 0.1, 10)
        
        # Classification
        if score > 100:
            return "extreme"
        elif score > 50:
            return "high"
        elif score > 20:
            return "medium"
        elif score > 5:
            return "low"
        else:
            return "unknown"
    
    def _record_batch_assignment(self, client_mac: str, batch: Batch, config_used: dict):
        """Enregistre une assignation pour analyse future"""
        assignment_record = {
            'timestamp': time.time(),
            'client_mac': client_mac,
            'batch_id': batch.id,
            'frame_count': len(batch.frame_paths),
            'config_used': config_used.copy(),
            'estimated_time': batch.estimated_time
        }
        
        self.assignment_history.append(assignment_record)
        
        # Limitation de l'historique
        if len(self.assignment_history) > 1000:
            self.assignment_history.pop(0)
    
    def _update_performance_metrics(self, batch: Batch, processing_time: float, performance_data: dict):
        """Met à jour les métriques de performance globales"""
        frame_count = len(batch.frame_paths)
        
        # Mise à jour des totaux
        self.performance_metrics['total_frames_processed'] += frame_count
        self.performance_metrics['total_processing_time'] += processing_time
        
        # Calcul de la moyenne FPS
        if self.performance_metrics['total_processing_time'] > 0:
            self.performance_metrics['average_fps'] = (
                self.performance_metrics['total_frames_processed'] / 
                self.performance_metrics['total_processing_time']
            )
        
        # Historique d'utilisation GPU
        gpu_util = performance_data.get('gpu_utilization', 0)
        if gpu_util > 0:
            self.performance_metrics['gpu_utilization_history'].append({
                'timestamp': time.time(),
                'utilization': gpu_util,
                'memory_usage': performance_data.get('memory_usage', 0)
            })
            
            # Limitation de l'historique
            if len(self.performance_metrics['gpu_utilization_history']) > 100:
                self.performance_metrics['gpu_utilization_history'].pop(0)
    
    def _analyze_batch_failure(self, batch: Batch, error_msg: str, performance_data: dict):
        """Analyse les échecs de lots pour optimisation"""
        failure_analysis = {
            'batch_id': batch.id,
            'client_mac': batch.assigned_client,
            'error_type': self._classify_error(error_msg),
            'retry_count': batch.retry_count,
            'frame_count': len(batch.frame_paths),
            'performance_data': performance_data,
            'timestamp': time.time()
        }
        
        self.failure_analyses.append(failure_analysis)
        
        # Limitation de l'historique
        if len(self.failure_analyses) > 200:
            self.failure_analyses.pop(0)
        
        # Recommandations d'optimisation basées sur l'erreur
        recommendations = self._get_failure_recommendations(failure_analysis)
        for rec in recommendations:
            self.logger.warning(f"Recommandation: {rec}")
    
    def _classify_error(self, error_msg: str) -> str:
        """Classifie le type d'erreur"""
        error_lower = error_msg.lower()
        
        if 'out of memory' in error_lower or 'cuda' in error_lower:
            return 'memory_error'
        elif 'timeout' in error_lower:
            return 'timeout_error'
        elif 'network' in error_lower or 'connection' in error_lower:
            return 'network_error'
        elif 'file' in error_lower or 'permission' in error_lower:
            return 'file_error'
        else:
            return 'unknown_error'
    
    def _get_failure_recommendations(self, failure_analysis: dict) -> List[str]:
        """Génère des recommandations basées sur l'analyse d'échec"""
        recommendations = []
        error_type = failure_analysis['error_type']
        client_mac = failure_analysis['client_mac']
        
        if error_type == 'memory_error':
            recommendations.append(f"Client {client_mac}: Réduire tile_size ou utiliser FP16")
            recommendations.append("Considérer la réduction de la taille des lots")
            
        elif error_type == 'timeout_error':
            recommendations.append(f"Client {client_mac}: Augmenter le timeout ou réduire la charge")
            recommendations.append("Vérifier la performance du client")
            
        elif error_type == 'network_error':
            recommendations.append(f"Client {client_mac}: Problème de connectivité réseau")
            recommendations.append("Vérifier la stabilité de la connexion")
            
        elif error_type == 'file_error':
            recommendations.append(f"Client {client_mac}: Problème d'accès aux fichiers")
            recommendations.append("Vérifier les permissions et l'espace disque")
        
        return recommendations
    
    async def _adaptive_optimization(self):
        """Optimisation adaptative basée sur les performances en temps réel"""
        current_time = time.time()
        
        # Optimisation toutes les 5 minutes minimum
        if current_time - self.adaptive_config['last_optimization'] < 300:
            return
        
        self.adaptive_config['last_optimization'] = current_time
        
        try:
            # Optimisations batch manager
            batch_optimizations = self.batch_manager.optimize_batch_distribution()
            
            if batch_optimizations:
                self.logger.info(f"Optimisation adaptative: {batch_optimizations.get('reason', '')}")
                
                # Application des optimisations
                if 'batch_size' in batch_optimizations:
                    self.adaptive_config['current_batch_size'] = batch_optimizations['batch_size']
                
                if 'increase_duplication' in batch_optimizations:
                    # Augmentation temporaire du seuil de duplication
                    config.DUPLICATE_THRESHOLD = min(config.DUPLICATE_THRESHOLD + 2, 10)
            
            # Optimisation des clients sous-performants
            await self._optimize_underperforming_clients()
            
            # Optimisation de la charge système
            system_optimizations = optimized_realesrgan.adapt_to_system_load()
            if system_optimizations:
                self.logger.info(f"Optimisation système: {system_optimizations.get('reason', '')}")
            
        except Exception as e:
            self.logger.error(f"Erreur optimisation adaptative: {e}")
    
    async def _optimize_underperforming_clients(self):
        """Optimise les clients sous-performants"""
        for mac, client in self.clients.items():
            if not client.is_online:
                continue
            
            # Identification des clients sous-performants
            is_underperforming = (
                client.success_rate < 70 or  # Taux de succès < 70%
                (client.average_batch_time > 0 and client.average_batch_time > 600) or  # > 10 min par lot
                client.batches_failed > client.batches_completed
            )
            
            if is_underperforming and client.batches_completed > 5:  # Au moins 5 lots pour juger
                self.logger.warning(f"Client sous-performant détecté: {mac} "
                                  f"(succès: {client.success_rate:.1f}%, "
                                  f"temps moyen: {client.average_batch_time:.1f}s)")
                
                # Actions d'optimisation
                await self._apply_client_optimizations(mac, client)
    
    async def _apply_client_optimizations(self, mac: str, client: Client):
        """Applique des optimisations spécifiques à un client"""
        try:
            if mac in self.websockets:
                optimization_message = {
                    "type": "optimization_update",
                    "optimizations": {
                        "reduce_tile_size": True,
                        "use_conservative_settings": True,
                        "enable_monitoring": True,
                        "suggested_tile_size": 128,
                        "suggested_threads": "1:2:1"
                    },
                    "reason": "Performance optimization based on history"
                }
                
                await self.websockets[mac].send(json.dumps(optimization_message))
                self.logger.info(f"Optimisations envoyées au client {mac}")
                
        except Exception as e:
            self.logger.error(f"Erreur envoi optimisations au client {mac}: {e}")
    
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
                "uptime": int(time.time() - self._start_time)
            }
        }
    
    def get_optimization_statistics(self) -> dict:
        """Retourne les statistiques d'optimisation"""
        # Statistiques hardware
        system_status = optimized_realesrgan.get_system_status()
        
        # Statistiques de performance
        performance_stats = {
            'total_frames_processed': self.performance_metrics['total_frames_processed'],
            'average_fps': self.performance_metrics['average_fps'],
            'total_processing_time_hours': self.performance_metrics['total_processing_time'] / 3600,
        }
        
        # Statistiques GPU récentes
        gpu_stats = {}
        if self.performance_metrics['gpu_utilization_history']:
            recent_gpu = self.performance_metrics['gpu_utilization_history'][-10:]
            gpu_stats = {
                'average_gpu_utilization': sum(g['utilization'] for g in recent_gpu) / len(recent_gpu),
                'average_memory_usage': sum(g['memory_usage'] for g in recent_gpu) / len(recent_gpu),
                'samples_count': len(recent_gpu)
            }
        
        # Statistiques des lots
        batch_stats = self.batch_manager.get_batch_statistics()
        
        # Statistiques des échecs
        failure_stats = {}
        if hasattr(self, 'failure_analyses'):
            recent_failures = [f for f in self.failure_analyses 
                             if time.time() - f['timestamp'] < 3600]  # Dernière heure
            
            if recent_failures:
                error_types = {}
                for failure in recent_failures:
                    error_type = failure['error_type']
                    error_types[error_type] = error_types.get(error_type, 0) + 1
                
                failure_stats = {
                    'recent_failures_count': len(recent_failures),
                    'error_types_distribution': error_types,
                    'failure_rate_percent': (len(recent_failures) / max(batch_stats.get('total_batches_processed', 1), 1)) * 100
                }
        
        # Configuration adaptative actuelle
        adaptive_stats = {
            'current_batch_size': self.adaptive_config['current_batch_size'],
            'current_concurrent_limit': self.adaptive_config['current_concurrent_limit'],
            'last_optimization': self.adaptive_config['last_optimization'],
            'optimization_frequency_minutes': (time.time() - self.adaptive_config['last_optimization']) / 60
        }
        
        return {
            'hardware_status': system_status,
            'performance_metrics': performance_stats,
            'gpu_utilization': gpu_stats,
            'batch_statistics': batch_stats,
            'failure_analysis': failure_stats,
            'adaptive_configuration': adaptive_stats,
            'optimization_recommendations': self._get_current_recommendations()
        }
    
    def _get_current_recommendations(self) -> List[str]:
        """Génère des recommandations d'optimisation actuelles"""
        recommendations = []
        
        # Analyse des performances
        avg_fps = self.performance_metrics['average_fps']
        
        if avg_fps < 0.5:
            recommendations.append("Performance très faible - Vérifier la configuration GPU et réduire la charge")
        elif avg_fps < 1.0:
            recommendations.append("Performance faible - Considérer l'optimisation des paramètres")
        elif avg_fps > 3.0:
            recommendations.append("Excellente performance - Possibilité d'augmenter la charge ou la qualité")
        
        # Analyse de l'utilisation GPU
        if self.performance_metrics['gpu_utilization_history']:
            recent_gpu = self.performance_metrics['gpu_utilization_history'][-5:]
            avg_gpu_util = sum(g['utilization'] for g in recent_gpu) / len(recent_gpu)
            
            if avg_gpu_util < 50:
                recommendations.append("Utilisation GPU faible - Augmenter tile_size ou charge de travail")
            elif avg_gpu_util > 95:
                recommendations.append("GPU saturé - Réduire tile_size ou charge de travail")
        
        # Analyse des clients
        active_clients = sum(1 for c in self.clients.values() if c.is_online)
        processing_clients = sum(1 for c in self.clients.values() 
                               if c.status == ClientStatus.PROCESSING)
        
        if active_clients > processing_clients and processing_clients < 3:
            recommendations.append("Clients disponibles sous-utilisés - Augmenter la distribution de lots")
        
        # Analyse des échecs
        if hasattr(self, 'failure_analyses'):
            recent_failures = [f for f in self.failure_analyses 
                             if time.time() - f['timestamp'] < 1800]  # 30 minutes
            
            if len(recent_failures) > 5:
                recommendations.append("Taux d'échec élevé récent - Vérifier la stabilité des clients")
        
        return recommendations
    
    async def auto_benchmark_system(self) -> dict:
        """Lance un benchmark automatique du système"""
        self.logger.info("Démarrage du benchmark automatique du système")
        
        try:
            # Benchmark hardware
            system_info = hardware_detector.detect_system_info()
            
            # Benchmark Real-ESRGAN avec différentes configurations
            test_frames = []  # Frames de test (à implémenter)
            
            if test_frames:
                benchmark_results = optimized_realesrgan.benchmark_configuration(test_frames)
            else:
                # Benchmark simulé basé sur les spécifications hardware
                benchmark_results = self._simulate_benchmark(system_info)
            
            # Recommandations basées sur le benchmark
            recommendations = self._generate_benchmark_recommendations(benchmark_results)
            
            benchmark_report = {
                'system_info': {
                    'gpu_count': len(system_info.gpus),
                    'primary_gpu': system_info.gpus[0].name if system_info.gpus else "None",
                    'cpu_cores': system_info.cpu.cores_logical,
                    'ram_gb': system_info.ram_total_gb,
                    'is_laptop': system_info.is_laptop
                },
                'benchmark_results': benchmark_results,
                'recommendations': recommendations,
                'optimal_settings': {
                    'batch_size': optimized_realesrgan.get_optimal_batch_size(),
                    'concurrent_batches': optimized_realesrgan.get_recommended_concurrent_batches(),
                    'realesrgan_config': optimized_realesrgan.optimal_config
                }
            }
            
            self.logger.info("Benchmark automatique terminé")
            return benchmark_report
            
        except Exception as e:
            self.logger.error(f"Erreur benchmark automatique: {e}")
            return {'error': str(e)}
    
    def _simulate_benchmark(self, system_info) -> dict:
        """Simule un benchmark basé sur les spécifications hardware"""
        # Estimation des performances basée sur le hardware
        base_fps = 1.0
        
        if system_info.gpus:
            gpu = system_info.gpus[0]
            
            if gpu.performance_tier == 'extreme':
                base_fps = 4.0
            elif gpu.performance_tier == 'high':
                base_fps = 2.5
            elif gpu.performance_tier == 'medium':
                base_fps = 1.5
            else:
                base_fps = 0.8
            
            # Ajustement selon la VRAM
            if gpu.memory_total_mb >= 16384:
                base_fps *= 1.3
            elif gpu.memory_total_mb <= 4096:
                base_fps *= 0.7
        else:
            base_fps = 0.3  # CPU seulement
        
        # Ajustement laptop
        if system_info.is_laptop:
            base_fps *= 0.8
        
        return {
            'estimated_fps': base_fps,
            'estimated_processing_time_per_frame': 1.0 / base_fps,
            'configuration_used': optimized_realesrgan.optimal_config,
            'confidence': 'estimated'
        }
    
    def _generate_benchmark_recommendations(self, benchmark_results: dict) -> List[str]:
        """Génère des recommandations basées sur le benchmark"""
        recommendations = []
        
        fps = benchmark_results.get('estimated_fps', 0)
        
        if fps > 3.0:
            recommendations.append("Excellent performance - Configuration optimale détectée")
            recommendations.append("Possibilité d'activer le mode TTA pour une qualité supérieure")
            
        elif fps > 1.5:
            recommendations.append("Bonne performance - Configuration équilibrée recommandée")
            recommendations.append("Peut traiter des lots de taille standard efficacement")
            
        elif fps > 0.8:
            recommendations.append("Performance modérée - Optimisations recommandées")
            recommendations.append("Considérer la réduction de tile_size ou l'usage de FP16")
            
        else:
            recommendations.append("Performance faible - Configuration conservative nécessaire")
            recommendations.append("Réduire significativement tile_size et utiliser des lots plus petits")
            recommendations.append("Considérer l'upgrade du matériel pour de meilleures performances")
        
        return recommendations