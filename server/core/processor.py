# server/core/processor.py
"""
Processeur serveur pour l'upscaling distribué
Gère la distribution des lots aux clients et la coordination
"""

import os
import sys
import asyncio
import logging
import time
import zipfile
import shutil
import io
from pathlib import Path
from typing import Optional, Dict, List, Any
import json

# Imports serveur (corrigés)
from security.server_security import ServerSecurity
from utils.config import config
from utils.system_info import SystemInfo

class ServerProcessor:
    """
    Processeur serveur pour l'upscaling distribué
    Gère la coordination des traitements et la distribution des tâches
    """
    
    def __init__(self, server_instance):
        self.server = server_instance
        self.logger = logging.getLogger(__name__)
        self.config = config
        self.security = ServerSecurity()
        self.system_info = SystemInfo()
        
        # État du processeur serveur
        self.is_processing = False
        self.current_job_id = None
        self.processing_start_time = None
        
        # Dossiers de travail
        self.work_directories = self.config.get_work_directories()
        self.input_dir = self.work_directories['input']
        self.output_dir = self.work_directories['output']
        self.temp_dir = self.work_directories['temp']
        self.batches_dir = self.work_directories['batches']
        
        # Jobs en cours
        self.active_jobs: Dict[str, Dict] = {}
        self.completed_jobs: Dict[str, Dict] = {}
        self.failed_jobs: Dict[str, Dict] = {}
        
        # Clients connectés
        self.connected_clients: Dict[str, Dict] = {}
        self.client_capabilities: Dict[str, Dict] = {}
        
        # Statistiques du serveur
        self.stats = {
            'jobs_processed': 0,
            'total_batches_created': 0,
            'total_batches_completed': 0,
            'total_processing_time': 0,
            'clients_served': 0,
            'data_processed_gb': 0,
            'server_start_time': time.time()
        }
        
        self.logger.info("Processeur serveur initialisé")
    
    def register_client(self, client_id: str, client_info: Dict[str, Any]):
        """Enregistre un nouveau client"""
        try:
            self.connected_clients[client_id] = {
                'id': client_id,
                'connected_at': time.time(),
                'last_seen': time.time(),
                'info': client_info,
                'status': 'connected',
                'current_batch': None,
                'batches_completed': 0,
                'total_processing_time': 0
            }
            
            # Enregistrement des capacités du client
            if 'capabilities' in client_info:
                self.client_capabilities[client_id] = client_info['capabilities']
            
            # Génération de la clé de session
            session_key = self.security.generate_session_key(client_id)
            
            self.logger.info(f"Client {client_id} enregistré avec succès")
            return session_key
            
        except Exception as e:
            self.logger.error(f"Erreur enregistrement client {client_id}: {e}")
            return None
    
    def unregister_client(self, client_id: str):
        """Désenregistre un client"""
        try:
            if client_id in self.connected_clients:
                client_info = self.connected_clients[client_id]
                
                # Si le client traitait un lot, le remettre en attente
                if client_info.get('current_batch'):
                    self._reassign_batch(client_info['current_batch'])
                
                # Suppression des informations client
                del self.connected_clients[client_id]
                self.client_capabilities.pop(client_id, None)
                
                # Nettoyage de la sécurité
                self.security.remove_client_session(client_id)
                
                self.logger.info(f"Client {client_id} désenregistré")
                
        except Exception as e:
            self.logger.error(f"Erreur désenregistrement client {client_id}: {e}")
    
    def update_client_status(self, client_id: str, status: str, additional_info: Dict = None):
        """Met à jour le statut d'un client"""
        try:
            if client_id in self.connected_clients:
                self.connected_clients[client_id]['status'] = status
                self.connected_clients[client_id]['last_seen'] = time.time()
                
                if additional_info:
                    self.connected_clients[client_id].update(additional_info)
                
                self.logger.debug(f"Statut client {client_id} mis à jour: {status}")
                
        except Exception as e:
            self.logger.error(f"Erreur mise à jour statut client {client_id}: {e}")
    
    def create_job_from_video(self, video_path: str, job_id: str = None) -> Optional[str]:
        """Crée un nouveau job d'upscaling à partir d'une vidéo"""
        try:
            if job_id is None:
                job_id = f"job_{int(time.time())}"
            
            video_file = Path(video_path)
            if not video_file.exists():
                raise Exception(f"Fichier vidéo non trouvé: {video_path}")
            
            # Création du job
            job_info = {
                'id': job_id,
                'source_video': str(video_file),
                'created_at': time.time(),
                'status': 'created',
                'batches': [],
                'total_frames': 0,
                'frames_processed': 0,
                'progress_percent': 0,
                'estimated_completion_time': None
            }
            
            self.active_jobs[job_id] = job_info
            self.logger.info(f"Job {job_id} créé pour la vidéo {video_file.name}")
            
            return job_id
            
        except Exception as e:
            self.logger.error(f"Erreur création job: {e}")
            return None
    
    async def extract_frames_from_video(self, job_id: str) -> bool:
        """Extrait les frames d'une vidéo pour un job"""
        try:
            if job_id not in self.active_jobs:
                raise Exception(f"Job {job_id} non trouvé")
            
            job = self.active_jobs[job_id]
            video_path = job['source_video']
            
            # Dossier pour les frames
            frames_dir = self.temp_dir / job_id / "frames"
            frames_dir.mkdir(parents=True, exist_ok=True)
            
            # Utilisation de FFmpeg pour extraire les frames
            ffmpeg_path = self.config.get_executable_path('ffmpeg')
            if not ffmpeg_path or not Path(ffmpeg_path).exists():
                raise Exception("FFmpeg non trouvé")
            
            # Commande FFmpeg
            cmd = [
                ffmpeg_path,
                '-i', video_path,
                '-q:v', '1',  # Qualité maximale
                str(frames_dir / "frame_%06d.png")
            ]
            
            self.logger.info(f"Extraction des frames pour le job {job_id}...")
            
            # Exécution de FFmpeg
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore')
                raise Exception(f"Erreur FFmpeg: {error_msg}")
            
            # Comptage des frames extraites
            frame_files = list(frames_dir.glob("frame_*.png"))
            job['total_frames'] = len(frame_files)
            job['status'] = 'frames_extracted'
            
            self.logger.info(f"Job {job_id}: {len(frame_files)} frames extraites")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur extraction frames job {job_id}: {e}")
            if job_id in self.active_jobs:
                self.active_jobs[job_id]['status'] = 'error'
                self.active_jobs[job_id]['error'] = str(e)
            return False
    
    async def create_batches_for_job(self, job_id: str, batch_size: int = None) -> bool:
        """Crée les lots pour un job"""
        try:
            if job_id not in self.active_jobs:
                raise Exception(f"Job {job_id} non trouvé")
            
            job = self.active_jobs[job_id]
            
            if job['status'] != 'frames_extracted':
                raise Exception(f"Job {job_id} n'est pas prêt pour la création de lots")
            
            batch_size = batch_size or self.config.BATCH_SIZE
            
            # Dossier des frames
            frames_dir = self.temp_dir / job_id / "frames"
            frame_files = sorted(list(frames_dir.glob("frame_*.png")))
            
            if not frame_files:
                raise Exception("Aucune frame trouvée")
            
            # Création des lots
            batches = []
            for i in range(0, len(frame_files), batch_size):
                batch_frames = frame_files[i:i + batch_size]
                
                batch_id = f"{job_id}_batch_{len(batches):04d}"
                batch_dir = self.batches_dir / batch_id
                batch_dir.mkdir(parents=True, exist_ok=True)
                
                # Copie des frames dans le dossier du lot
                for frame_file in batch_frames:
                    shutil.copy2(frame_file, batch_dir / frame_file.name)
                
                # Création du ZIP du lot
                batch_zip = batch_dir / f"{batch_id}.zip"
                with zipfile.ZipFile(batch_zip, 'w', zipfile.ZIP_STORED) as zf:
                    for frame_file in batch_dir.glob("*.png"):
                        zf.write(frame_file, frame_file.name)
                
                batch_info = {
                    'id': batch_id,
                    'job_id': job_id,
                    'frame_count': len(batch_frames),
                    'status': 'pending',
                    'created_at': time.time(),
                    'assigned_client': None,
                    'zip_path': str(batch_zip),
                    'attempts': 0,
                    'max_attempts': self.config.MAX_RETRIES
                }
                
                batches.append(batch_info)
            
            job['batches'] = batches
            job['status'] = 'ready_for_processing'
            
            self.stats['total_batches_created'] += len(batches)
            
            self.logger.info(f"Job {job_id}: {len(batches)} lots créés")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur création lots job {job_id}: {e}")
            if job_id in self.active_jobs:
                self.active_jobs[job_id]['status'] = 'error'
                self.active_jobs[job_id]['error'] = str(e)
            return False
    
    def get_next_batch_for_client(self, client_id: str) -> Optional[Dict]:
        """Récupère le prochain lot disponible pour un client"""
        try:
            if client_id not in self.connected_clients:
                return None
            
            # Recherche d'un lot en attente
            for job_id, job in self.active_jobs.items():
                if job['status'] != 'ready_for_processing':
                    continue
                
                for batch in job['batches']:
                    if batch['status'] == 'pending':
                        # Attribution du lot au client
                        batch['status'] = 'assigned'
                        batch['assigned_client'] = client_id
                        batch['assigned_at'] = time.time()
                        
                        # Mise à jour du client
                        self.connected_clients[client_id]['current_batch'] = batch['id']
                        self.connected_clients[client_id]['status'] = 'processing'
                        
                        self.logger.info(f"Lot {batch['id']} attribué au client {client_id}")
                        return batch
            
            return None
            
        except Exception as e:
            self.logger.error(f"Erreur attribution lot client {client_id}: {e}")
            return None
    
    def complete_batch(self, batch_id: str, client_id: str, result_data: bytes) -> bool:
        """Marque un lot comme terminé et traite le résultat"""
        try:
            # Recherche du lot
            batch = None
            job = None
            
            for job_id, job_info in self.active_jobs.items():
                for b in job_info['batches']:
                    if b['id'] == batch_id:
                        batch = b
                        job = job_info
                        break
                if batch:
                    break
            
            if not batch or not job:
                raise Exception(f"Lot {batch_id} non trouvé")
            
            if batch['assigned_client'] != client_id:
                raise Exception(f"Lot {batch_id} non attribué au client {client_id}")
            
            # Sauvegarde du résultat
            result_dir = self.output_dir / job['id'] / batch_id
            result_dir.mkdir(parents=True, exist_ok=True)
            
            # Décompression du résultat
            with zipfile.ZipFile(io.BytesIO(result_data), 'r') as zf:
                zf.extractall(result_dir)
            
            # Mise à jour du lot
            batch['status'] = 'completed'
            batch['completed_at'] = time.time()
            batch['processing_time'] = batch['completed_at'] - batch.get('assigned_at', batch['completed_at'])
            
            # Mise à jour du client
            if client_id in self.connected_clients:
                self.connected_clients[client_id]['current_batch'] = None
                self.connected_clients[client_id]['status'] = 'idle'
                self.connected_clients[client_id]['batches_completed'] += 1
                self.connected_clients[client_id]['total_processing_time'] += batch['processing_time']
            
            # Mise à jour du job
            job['frames_processed'] += batch['frame_count']
            job['progress_percent'] = (job['frames_processed'] / job['total_frames']) * 100
            
            self.stats['total_batches_completed'] += 1
            
            self.logger.info(f"Lot {batch_id} terminé par le client {client_id}")
            
            # Vérification si le job est terminé
            if all(b['status'] == 'completed' for b in job['batches']):
                self._complete_job(job['id'])
            
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur finalisation lot {batch_id}: {e}")
            return False
    
    def _complete_job(self, job_id: str):
        """Finalise un job terminé"""
        try:
            if job_id not in self.active_jobs:
                return
            
            job = self.active_jobs[job_id]
            
            # Assemblage final avec FFmpeg (si disponible)
            # TODO: Implémenter l'assemblage des frames en vidéo
            
            job['status'] = 'completed'
            job['completed_at'] = time.time()
            job['total_processing_time'] = job['completed_at'] - job['created_at']
            
            # Déplacement vers les jobs terminés
            self.completed_jobs[job_id] = self.active_jobs.pop(job_id)
            
            self.stats['jobs_processed'] += 1
            self.stats['total_processing_time'] += job['total_processing_time']
            
            self.logger.info(f"Job {job_id} terminé avec succès")
            
        except Exception as e:
            self.logger.error(f"Erreur finalisation job {job_id}: {e}")
    
    def _reassign_batch(self, batch_id: str):
        """Remet un lot en attente pour réattribution"""
        try:
            for job in self.active_jobs.values():
                for batch in job['batches']:
                    if batch['id'] == batch_id:
                        batch['status'] = 'pending'
                        batch['assigned_client'] = None
                        batch['attempts'] += 1
                        
                        if batch['attempts'] >= batch['max_attempts']:
                            batch['status'] = 'failed'
                            self.logger.warning(f"Lot {batch_id} échoué après {batch['attempts']} tentatives")
                        else:
                            self.logger.info(f"Lot {batch_id} remis en attente (tentative {batch['attempts']})")
                        
                        return
            
        except Exception as e:
            self.logger.error(f"Erreur réattribution lot {batch_id}: {e}")
    
    def get_server_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du serveur"""
        current_time = time.time()
        uptime = current_time - self.stats['server_start_time']
        
        # Calcul des lots en cours
        pending_batches = 0
        assigned_batches = 0
        completed_batches = 0
        
        for job in self.active_jobs.values():
            for batch in job['batches']:
                if batch['status'] == 'pending':
                    pending_batches += 1
                elif batch['status'] == 'assigned':
                    assigned_batches += 1
                elif batch['status'] == 'completed':
                    completed_batches += 1
        
        return {
            'uptime_seconds': uptime,
            'uptime_formatted': self._format_uptime(uptime),
            'jobs': {
                'active': len(self.active_jobs),
                'completed': len(self.completed_jobs),
                'failed': len(self.failed_jobs)
            },
            'batches': {
                'pending': pending_batches,
                'assigned': assigned_batches,
                'completed': completed_batches,
                'total_created': self.stats['total_batches_created'],
                'total_completed': self.stats['total_batches_completed']
            },
            'clients': {
                'connected': len(self.connected_clients),
                'active': len([c for c in self.connected_clients.values() if c['status'] == 'processing'])
            },
            'performance': {
                'jobs_processed': self.stats['jobs_processed'],
                'total_processing_time': self.stats['total_processing_time'],
                'average_job_time': self.stats['total_processing_time'] / max(1, self.stats['jobs_processed'])
            }
        }
    
    def _format_uptime(self, seconds: float) -> str:
        """Formate le temps de fonctionnement"""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}j")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if secs > 0 or not parts:
            parts.append(f"{secs}s")
        
        return " ".join(parts)
    
    def cleanup_old_files(self, max_age_hours: int = 24):
        """Nettoie les anciens fichiers temporaires"""
        try:
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600
            
            # Nettoyage des dossiers temporaires
            for temp_dir in [self.temp_dir, self.batches_dir]:
                if not temp_dir.exists():
                    continue
                
                for item in temp_dir.iterdir():
                    try:
                        if item.stat().st_mtime < current_time - max_age_seconds:
                            if item.is_file():
                                item.unlink()
                            elif item.is_dir():
                                shutil.rmtree(item)
                            self.logger.debug(f"Fichier ancien supprimé: {item}")
                    except Exception as e:
                        self.logger.warning(f"Erreur suppression {item}: {e}")
            
            self.logger.info("Nettoyage des anciens fichiers terminé")
            
        except Exception as e:
            self.logger.error(f"Erreur nettoyage: {e}")
    
    async def process_video_complete(self, video_path: str, job_id: str = None) -> Optional[str]:
        """Traite une vidéo de A à Z (méthode tout-en-un)"""
        try:
            # 1. Création du job
            job_id = self.create_job_from_video(video_path, job_id)
            if not job_id:
                return None
            
            # 2. Extraction des frames
            if not await self.extract_frames_from_video(job_id):
                return None
            
            # 3. Création des lots
            if not await self.create_batches_for_job(job_id):
                return None
            
            self.logger.info(f"Job {job_id} prêt pour traitement distribué")
            return job_id
            
        except Exception as e:
            self.logger.error(f"Erreur traitement complet vidéo: {e}")
            return None
    
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retourne le statut détaillé d'un job"""
        try:
            # Recherche dans les jobs actifs
            if job_id in self.active_jobs:
                job = self.active_jobs[job_id]
            elif job_id in self.completed_jobs:
                job = self.completed_jobs[job_id]
            elif job_id in self.failed_jobs:
                job = self.failed_jobs[job_id]
            else:
                return None
            
            # Calcul des statistiques
            total_batches = len(job.get('batches', []))
            completed_batches = len([b for b in job.get('batches', []) if b['status'] == 'completed'])
            pending_batches = len([b for b in job.get('batches', []) if b['status'] == 'pending'])
            assigned_batches = len([b for b in job.get('batches', []) if b['status'] == 'assigned'])
            failed_batches = len([b for b in job.get('batches', []) if b['status'] == 'failed'])
            
            # Estimation du temps restant
            estimated_completion = None
            if completed_batches > 0 and pending_batches + assigned_batches > 0:
                avg_time_per_batch = sum(b.get('processing_time', 0) for b in job.get('batches', [])) / completed_batches
                remaining_batches = pending_batches + assigned_batches
                estimated_completion = time.time() + (avg_time_per_batch * remaining_batches)
            
            return {
                'job_id': job_id,
                'status': job['status'],
                'created_at': job['created_at'],
                'source_video': job['source_video'],
                'total_frames': job.get('total_frames', 0),
                'frames_processed': job.get('frames_processed', 0),
                'progress_percent': job.get('progress_percent', 0),
                'batches': {
                    'total': total_batches,
                    'completed': completed_batches,
                    'pending': pending_batches,
                    'assigned': assigned_batches,
                    'failed': failed_batches
                },
                'estimated_completion': estimated_completion,
                'error': job.get('error')
            }
            
        except Exception as e:
            self.logger.error(f"Erreur récupération statut job {job_id}: {e}")
            return None
    
    def get_client_info(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Retourne les informations détaillées d'un client"""
        if client_id not in self.connected_clients:
            return None
        
        client = self.connected_clients[client_id]
        current_time = time.time()
        
        return {
            'client_id': client_id,
            'status': client['status'],
            'connected_at': client['connected_at'],
            'last_seen': client['last_seen'],
            'connection_duration': current_time - client['connected_at'],
            'current_batch': client.get('current_batch'),
            'batches_completed': client.get('batches_completed', 0),
            'total_processing_time': client.get('total_processing_time', 0),
            'average_batch_time': (
                client.get('total_processing_time', 0) / max(1, client.get('batches_completed', 1))
            ),
            'info': client.get('info', {}),
            'capabilities': self.client_capabilities.get(client_id, {})
        }
    
    def get_all_jobs_summary(self) -> Dict[str, Any]:
        """Retourne un résumé de tous les jobs"""
        try:
            jobs_summary = {
                'active': [],
                'completed': [],
                'failed': []
            }
            
            # Jobs actifs
            for job_id, job in self.active_jobs.items():
                status = self.get_job_status(job_id)
                if status:
                    jobs_summary['active'].append(status)
            
            # Jobs terminés (derniers 10)
            completed_jobs = list(self.completed_jobs.items())[-10:]
            for job_id, job in completed_jobs:
                status = self.get_job_status(job_id)
                if status:
                    jobs_summary['completed'].append(status)
            
            # Jobs échoués (derniers 10)
            failed_jobs = list(self.failed_jobs.items())[-10:]
            for job_id, job in failed_jobs:
                status = self.get_job_status(job_id)
                if status:
                    jobs_summary['failed'].append(status)
            
            return jobs_summary
            
        except Exception as e:
            self.logger.error(f"Erreur résumé jobs: {e}")
            return {'active': [], 'completed': [], 'failed': []}
    
    def cancel_job(self, job_id: str) -> bool:
        """Annule un job en cours"""
        try:
            if job_id not in self.active_jobs:
                return False
            
            job = self.active_jobs[job_id]
            
            # Libération des lots assignés
            for batch in job.get('batches', []):
                if batch['status'] == 'assigned' and batch.get('assigned_client'):
                    client_id = batch['assigned_client']
                    if client_id in self.connected_clients:
                        self.connected_clients[client_id]['current_batch'] = None
                        self.connected_clients[client_id]['status'] = 'idle'
            
            # Déplacement vers les jobs échoués
            job['status'] = 'cancelled'
            job['cancelled_at'] = time.time()
            job['error'] = 'Job annulé par l\'utilisateur'
            
            self.failed_jobs[job_id] = self.active_jobs.pop(job_id)
            
            self.logger.info(f"Job {job_id} annulé")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur annulation job {job_id}: {e}")
            return False