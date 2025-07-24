# server/core/batch_manager.py
"""
Gestionnaire de lots pour la distribution sécurisée avec dossiers - Version corrigée
Gère la création, compression, chiffrement et distribution des lots
"""

import asyncio
import logging
import shutil
import zipfile
import hashlib
import time
import subprocess
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path

# Imports corrigés avec chemins absolus
import sys
sys.path.append(str(Path(__file__).parent.parent))

from models.batch import Batch, BatchStatus
from models.client import Client, ClientStatus
from utils.config import config

class BatchManager:
    """
    Gestionnaire de lots pour la distribution sécurisée avec dossiers
    Gère la création, compression, chiffrement et distribution des lots
    """
    
    def __init__(self, server_instance):
        self.server = server_instance
        self.logger = logging.getLogger(__name__)
        self.config = config
        
        # Dossiers de travail
        directories = self.config.get_work_directories()
        self.work_dir = directories['work']
        self.temp_dir = directories['temp']
        self.output_dir = directories['output']
        
        # Dossiers spécifiques aux lots
        self.batches_dir = self.work_dir / "batches"
        self.frames_dir = self.work_dir / "frames"
        self.results_dir = self.work_dir / "results"
        
        # Création des dossiers
        for directory in [self.batches_dir, self.frames_dir, self.results_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Statistiques et monitoring
        self.stats = {
            'total_batches_created': 0,
            'total_batches_completed': 0,
            'total_batches_failed': 0,
            'average_batch_time': 0,
            'total_data_transferred_mb': 0,
            'frames_per_batch': self.config.get("processing.batch_size", 50),
            'current_job_progress': 0
        }
        
        # Configuration adaptative
        self.adaptive_config = {
            'current_batch_size': self.config.get("processing.batch_size", 50),
            'duplicate_threshold': self.config.get("processing.duplicate_threshold", 5),
            'optimization_enabled': True
        }
        
        # Tâche de monitoring
        self.monitoring_task = None
        self.running = False
        
        self.logger.info("Gestionnaire de lots initialisé")
    
    async def start(self):
        """Démarre le gestionnaire de lots"""
        if self.running:
            return
            
        self.running = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        self.logger.info("Gestionnaire de lots démarré")
    
    async def stop(self):
        """Arrête le gestionnaire de lots"""
        self.running = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        self.logger.info("Gestionnaire de lots arrêté")
    
    async def create_batches_from_job(self, job_id: str, video_path: str) -> List[Batch]:
        """
        Crée des lots à partir d'une vidéo
        
        Args:
            job_id: Identifiant unique du job
            video_path: Chemin vers la vidéo source
            
        Returns:
            Liste des lots créés
        """
        try:
            self.logger.info(f"Création des lots pour le job {job_id} - vidéo: {video_path}")
            
            # 1. Extraction des frames de la vidéo
            frames_dir = await self._extract_video_frames(job_id, video_path)
            
            # 2. Listage des images extraites
            frame_files = sorted(list(frames_dir.glob("*.png")))
            
            if not frame_files:
                raise Exception("Aucune image extraite de la vidéo")
            
            self.logger.info(f"Job {job_id}: {len(frame_files)} frames extraites")
            
            # 3. Création des lots
            batches = await self._create_batches_from_frames(job_id, frame_files)
            
            # 4. Mise à jour des statistiques
            self.stats['total_batches_created'] += len(batches)
            
            self.logger.info(f"Job {job_id}: {len(batches)} lots créés")
            return batches
            
        except Exception as e:
            self.logger.error(f"Erreur création lots pour job {job_id}: {e}")
            raise
    
    async def _extract_video_frames(self, job_id: str, video_path: str) -> Path:
        """
        Extrait les frames d'une vidéo avec FFmpeg
        
        Args:
            job_id: Identifiant du job
            video_path: Chemin vers la vidéo
            
        Returns:
            Dossier contenant les frames extraites
        """
        frames_output_dir = self.frames_dir / job_id
        
        # Nettoyage du dossier précédent
        if frames_output_dir.exists():
            shutil.rmtree(frames_output_dir)
        frames_output_dir.mkdir(parents=True)
        
        # Construction de la commande FFmpeg
        output_pattern = frames_output_dir / "frame_%08d.png"
        
        cmd = [
            'ffmpeg',
            '-i', str(video_path),
            '-vf', 'fps=fps=30',  # Extraction à 30 FPS (ajustable)
            '-pix_fmt', 'rgb24',
            '-q:v', '1',  # Qualité maximale
            str(output_pattern),
            '-y'  # Overwrite
        ]
        
        try:
            self.logger.info(f"Extraction frames: {' '.join(cmd)}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore')
                raise Exception(f"FFmpeg a échoué (code {process.returncode}): {error_msg}")
            
            # Vérification des fichiers extraits
            frame_files = list(frames_output_dir.glob("*.png"))
            if not frame_files:
                raise Exception("Aucune frame extraite par FFmpeg")
            
            self.logger.info(f"Extraction terminée: {len(frame_files)} frames")
            return frames_output_dir
            
        except Exception as e:
            self.logger.error(f"Erreur extraction frames: {e}")
            raise
    
    async def _create_batches_from_frames(self, job_id: str, frame_files: List[Path]) -> List[Batch]:
        """
        Crée des lots à partir d'une liste de frames
        
        Args:
            job_id: Identifiant du job
            frame_files: Liste des fichiers frames
            
        Returns:
            Liste des lots créés
        """
        batches = []
        batch_size = self.adaptive_config['current_batch_size']
        
        # Division en lots
        for i in range(0, len(frame_files), batch_size):
            batch_frames = frame_files[i:i + batch_size]
            batch_id = f"{job_id}_batch_{i // batch_size + 1:04d}"
            
            # Création du dossier de lot
            batch_dir = self.batches_dir / batch_id
            batch_dir.mkdir(exist_ok=True)
            
            # Copie des frames dans le dossier de lot
            for frame_file in batch_frames:
                dest_file = batch_dir / frame_file.name
                shutil.copy2(frame_file, dest_file)
            
            # Création de l'objet Batch
            batch = Batch(
                id=batch_id,
                job_id=job_id,
                frames_count=len(batch_frames),
                input_directory=str(batch_dir),
                status=BatchStatus.PENDING
            )
            
            batches.append(batch)
            
            # Enregistrement dans le serveur
            if hasattr(self.server, 'batches'):
                self.server.batches[batch_id] = batch
        
        return batches
    
    async def prepare_batch_for_client(self, batch_id: str) -> Optional[bytes]:
        """
        Prépare un lot pour envoi à un client (compression + chiffrement)
        
        Args:
            batch_id: Identifiant du lot
            
        Returns:
            Données du lot chiffrées ou None en cas d'erreur
        """
        try:
            if not hasattr(self.server, 'batches') or batch_id not in self.server.batches:
                raise Exception(f"Lot {batch_id} non trouvé")
            
            batch = self.server.batches[batch_id]
            batch_dir = Path(batch.input_directory)
            
            if not batch_dir.exists():
                raise Exception(f"Dossier du lot {batch_id} non trouvé: {batch_dir}")
            
            # 1. Création du fichier ZIP
            zip_path = self.temp_dir / f"{batch_id}.zip"
            self._create_batch_zip(batch_dir, zip_path)
            
            # 2. Lecture des données
            with open(zip_path, 'rb') as f:
                zip_data = f.read()
            
            # 3. Calcul du hash pour vérification d'intégrité
            data_hash = hashlib.sha256(zip_data).hexdigest()
            batch.data_hash = data_hash
            
            # 4. Chiffrement (sera fait côté serveur principal avec la clé de session)
            # Pour l'instant, on retourne les données non chiffrées
            # Le chiffrement se fera au moment de l'envoi au client
            
            # 5. Nettoyage du fichier temporaire
            zip_path.unlink()
            
            self.logger.info(f"Lot {batch_id} préparé: {len(zip_data)} bytes")
            return zip_data
            
        except Exception as e:
            self.logger.error(f"Erreur préparation lot {batch_id}: {e}")
            return None
    
    def _create_batch_zip(self, batch_dir: Path, zip_path: Path):
        """
        Crée un fichier ZIP à partir d'un dossier de lot
        
        Args:
            batch_dir: Dossier contenant les frames
            zip_path: Chemin du fichier ZIP à créer
        """
        try:
            compression_level = self.config.get("processing.compression_level", 0)
            compression_type = zipfile.ZIP_STORED if compression_level == 0 else zipfile.ZIP_DEFLATED
            
            with zipfile.ZipFile(zip_path, 'w', compression_type) as zip_file:
                for file_path in batch_dir.glob('*'):
                    if file_path.is_file():
                        zip_file.write(file_path, file_path.name)
            
            self.logger.debug(f"ZIP créé: {zip_path}")
            
        except Exception as e:
            self.logger.error(f"Erreur création ZIP {zip_path}: {e}")
            raise
    
    async def process_batch_result(self, batch_id: str, result_data: bytes) -> bool:
        """
        Traite le résultat d'un lot retourné par un client
        
        Args:
            batch_id: Identifiant du lot
            result_data: Données du résultat (déjà déchiffrées)
            
        Returns:
            True si le traitement a réussi
        """
        try:
            if not hasattr(self.server, 'batches') or batch_id not in self.server.batches:
                raise Exception(f"Lot {batch_id} non trouvé")
            
            batch = self.server.batches[batch_id]
            
            # 1. Sauvegarde des données résultat
            result_zip_path = self.temp_dir / f"{batch_id}_result.zip"
            with open(result_zip_path, 'wb') as f:
                f.write(result_data)
            
            # 2. Extraction dans le dossier de résultats
            result_dir = self.results_dir / batch_id
            if result_dir.exists():
                shutil.rmtree(result_dir)
            result_dir.mkdir(parents=True)
            
            extracted_files = self._extract_result_zip(result_zip_path, result_dir)
            
            # 3. Vérification du nombre de fichiers
            expected_count = batch.frames_count
            actual_count = len(extracted_files)
            
            if actual_count != expected_count:
                self.logger.warning(f"Lot {batch_id}: {actual_count} fichiers reçus, {expected_count} attendus")
                
                # Si moins de 80% des fichiers, considérer comme échec
                if actual_count < expected_count * 0.8:
                    raise Exception(f"Lot incomplet: {actual_count}/{expected_count} fichiers")
            
            # 4. Déplacement vers le dossier final de sortie
            final_output_dir = self.output_dir / batch.job_id
            final_output_dir.mkdir(exist_ok=True)
            
            for file_path in result_dir.glob('*'):
                if file_path.is_file():
                    dest_path = final_output_dir / file_path.name
                    shutil.move(str(file_path), str(dest_path))
            
            # 5. Mise à jour du statut du lot
            batch.status = BatchStatus.COMPLETED
            batch.completed_at = datetime.now()
            batch.output_directory = str(final_output_dir)
            
            # 6. Nettoyage
            result_zip_path.unlink()
            shutil.rmtree(result_dir)
            
            # 7. Mise à jour des statistiques
            self.stats['total_batches_completed'] += 1
            
            self.logger.info(f"Lot {batch_id} traité avec succès: {actual_count} fichiers")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur traitement résultat lot {batch_id}: {e}")
            
            # Marquer le lot comme échoué
            if hasattr(self.server, 'batches') and batch_id in self.server.batches:
                batch = self.server.batches[batch_id]
                batch.status = BatchStatus.FAILED
                batch.error_message = str(e)
            
            self.stats['total_batches_failed'] += 1
    
    async def _recompose_video(self, job_id: str, frames_dir: Path) -> bool:
        """
        Recompose la vidéo à partir des frames upscalées
        
        Args:
            job_id: Identifiant du job
            frames_dir: Dossier contenant les frames upscalées
            
        Returns:
            True si la recomposition a réussi
        """
        try:
            # Récupération des informations du job original
            original_video_path = None
            if hasattr(self.server, 'jobs') and job_id in self.server.jobs:
                job = self.server.jobs[job_id]
                original_video_path = job.input_file
            
            # Tri des frames par nom pour assurer l'ordre correct
            frame_files = sorted(list(frames_dir.glob('*.png')))
            if not frame_files:
                raise Exception("Aucune frame à recomposer")
            
            # Création du pattern d'entrée pour FFmpeg
            # Renommage temporaire des fichiers pour avoir une séquence continue
            temp_frames_dir = self.temp_dir / f"{job_id}_recompose"
            temp_frames_dir.mkdir(exist_ok=True)
            
            for i, frame_file in enumerate(frame_files):
                temp_name = f"frame_{i+1:08d}.png"
                temp_path = temp_frames_dir / temp_name
                shutil.copy2(frame_file, temp_path)
            
            # Fichier de sortie
            output_video_path = self.output_dir / f"{job_id}_upscaled.mp4"
            
            # Construction de la commande FFmpeg
            input_pattern = temp_frames_dir / "frame_%08d.png"
            
            cmd = [
                'ffmpeg',
                '-framerate', '30',  # Framerate (ajustable selon l'original)
                '-i', str(input_pattern),
                '-c:v', 'libx264',
                '-pix_fmt', 'yuv420p',
                '-crf', '18',  # Qualité élevée
                str(output_video_path),
                '-y'  # Overwrite
            ]
            
            # Ajout de l'audio si vidéo originale disponible
            if original_video_path and Path(original_video_path).exists():
                # Commande avec audio
                cmd = [
                    'ffmpeg',
                    '-framerate', '30',
                    '-i', str(input_pattern),
                    '-i', str(original_video_path),
                    '-c:v', 'libx264',
                    '-c:a', 'copy',  # Copie de l'audio sans réencodage
                    '-pix_fmt', 'yuv420p',
                    '-crf', '18',
                    '-map', '0:v:0',  # Vidéo depuis la première entrée
                    '-map', '1:a:0?',  # Audio depuis la seconde entrée (optionnel)
                    '-shortest',  # Durée de la sortie = plus courte des entrées
                    str(output_video_path),
                    '-y'
                ]
            
            self.logger.info(f"Recomposition vidéo: {' '.join(cmd)}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore')
                raise Exception(f"FFmpeg a échoué (code {process.returncode}): {error_msg}")
            
            # Vérification du fichier de sortie
            if not output_video_path.exists() or output_video_path.stat().st_size == 0:
                raise Exception("Fichier vidéo de sortie invalide")
            
            # Nettoyage du dossier temporaire
            shutil.rmtree(temp_frames_dir)
            
            self.logger.info(f"Vidéo recomposée: {output_video_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur recomposition vidéo job {job_id}: {e}")
            return False
    
    async def _cleanup_job_files(self, job_id: str):
        """
        Nettoie les fichiers intermédiaires d'un job
        
        Args:
            job_id: Identifiant du job
        """
        try:
            cleanup_count = 0
            
            # Nettoyage des dossiers de frames originales
            frames_job_dir = self.frames_dir / job_id
            if frames_job_dir.exists():
                shutil.rmtree(frames_job_dir)
                cleanup_count += 1
            
            # Nettoyage des dossiers de lots
            for batch_dir in self.batches_dir.glob(f"{job_id}_batch_*"):
                if batch_dir.is_dir():
                    shutil.rmtree(batch_dir)
                    cleanup_count += 1
            
            # Nettoyage des résultats intermédiaires (garder seulement la vidéo finale)
            results_job_dir = self.output_dir / job_id
            if results_job_dir.exists():
                shutil.rmtree(results_job_dir)
                cleanup_count += 1
            
            if cleanup_count > 0:
                self.logger.info(f"Nettoyage job {job_id}: {cleanup_count} éléments supprimés")
                
        except Exception as e:
            self.logger.error(f"Erreur nettoyage job {job_id}: {e}")
    
    async def _monitoring_loop(self):
        """Boucle de monitoring du gestionnaire de lots"""
        while self.running:
            try:
                await self._update_batch_statistics()
                await self._check_stalled_batches()
                
                if self.adaptive_config['optimization_enabled']:
                    await self._optimize_batch_parameters()
                
                await asyncio.sleep(30)  # Monitoring toutes les 30 secondes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Erreur monitoring lots: {e}")
                await asyncio.sleep(60)  # Attente plus longue en cas d'erreur
    
    async def _update_batch_statistics(self):
        """Met à jour les statistiques des lots"""
        if not hasattr(self.server, 'batches'):
            return
        
        try:
            total_batches = len(self.server.batches)
            completed_batches = sum(1 for b in self.server.batches.values() 
                                  if b.status == BatchStatus.COMPLETED)
            failed_batches = sum(1 for b in self.server.batches.values() 
                               if b.status == BatchStatus.FAILED)
            processing_batches = sum(1 for b in self.server.batches.values() 
                                   if b.status == BatchStatus.PROCESSING)
            
            # Calcul du temps moyen de traitement
            completed_times = []
            for batch in self.server.batches.values():
                if (batch.status == BatchStatus.COMPLETED and 
                    batch.assigned_at and batch.completed_at):
                    duration = (batch.completed_at - batch.assigned_at).total_seconds()
                    completed_times.append(duration)
            
            if completed_times:
                self.stats['average_batch_time'] = sum(completed_times) / len(completed_times)
            
            # Mise à jour des statistiques
            self.stats['total_batches_completed'] = completed_batches
            self.stats['total_batches_failed'] = failed_batches
            
            # Calcul du progrès si on a un job courant
            if hasattr(self.server, 'current_job') and self.server.current_job:
                job_batches = [b for b in self.server.batches.values() 
                             if b.job_id == self.server.current_job]
                if job_batches:
                    job_completed = sum(1 for b in job_batches 
                                      if b.status == BatchStatus.COMPLETED)
                    self.stats['current_job_progress'] = (job_completed / len(job_batches)) * 100
            
        except Exception as e:
            self.logger.error(f"Erreur mise à jour statistiques lots: {e}")
    
    async def _check_stalled_batches(self):
        """Vérifie les lots bloqués et les relance si nécessaire"""
        if not hasattr(self.server, 'batches'):
            return
        
        try:
            current_time = datetime.now()
            stall_timeout = timedelta(minutes=10)  # Timeout de 10 minutes
            
            stalled_batches = []
            
            for batch_id, batch in self.server.batches.items():
                if (batch.status == BatchStatus.PROCESSING and 
                    batch.assigned_at and 
                    current_time - batch.assigned_at > stall_timeout):
                    stalled_batches.append(batch)
            
            for batch in stalled_batches:
                self.logger.warning(f"Lot bloqué détecté: {batch.id}")
                
                # Remettre le lot en attente
                batch.status = BatchStatus.PENDING
                batch.assigned_to = None
                batch.assigned_at = None
                batch.retry_count = getattr(batch, 'retry_count', 0) + 1
                
                # Si trop de tentatives, marquer comme échoué
                if batch.retry_count > 3:
                    batch.status = BatchStatus.FAILED
                    batch.error_message = "Trop de tentatives échouées"
                    self.logger.error(f"Lot {batch.id} marqué comme échoué après {batch.retry_count} tentatives")
                
        except Exception as e:
            self.logger.error(f"Erreur vérification lots bloqués: {e}")
    
    async def _optimize_batch_parameters(self):
        """Optimise les paramètres de lot selon les performances"""
        try:
            if not hasattr(self.server, 'clients') or not self.server.clients:
                return
            
            # Analyse des performances des clients
            active_clients = [c for c in self.server.clients.values() if c.is_online]
            if not active_clients:
                return
            
            # Calcul de la performance moyenne
            avg_batch_times = []
            for client in active_clients:
                if client.average_batch_time > 0:
                    avg_batch_times.append(client.average_batch_time)
            
            if not avg_batch_times:
                return
            
            avg_time = sum(avg_batch_times) / len(avg_batch_times)
            
            # Ajustement de la taille des lots
            current_size = self.adaptive_config['current_batch_size']
            target_time = 120  # 2 minutes cible par lot
            
            if avg_time > target_time * 1.5:  # Trop lent
                new_size = max(10, int(current_size * 0.8))
                if new_size != current_size:
                    self.adaptive_config['current_batch_size'] = new_size
                    self.logger.info(f"Taille des lots réduite: {current_size} -> {new_size}")
            
            elif avg_time < target_time * 0.5:  # Trop rapide
                new_size = min(100, int(current_size * 1.2))
                if new_size != current_size:
                    self.adaptive_config['current_batch_size'] = new_size
                    self.logger.info(f"Taille des lots augmentée: {current_size} -> {new_size}")
            
        except Exception as e:
            self.logger.error(f"Erreur optimisation paramètres lots: {e}")
    
    def get_batch_status(self, batch_id: str) -> Optional[Dict]:
        """
        Retourne le statut d'un lot
        
        Args:
            batch_id: Identifiant du lot
            
        Returns:
            Dictionnaire avec le statut ou None si non trouvé
        """
        if not hasattr(self.server, 'batches') or batch_id not in self.server.batches:
            return None
        
        batch = self.server.batches[batch_id]
        
        return {
            'id': batch.id,
            'job_id': batch.job_id,
            'status': batch.status.value,
            'frames_count': batch.frames_count,
            'assigned_to': batch.assigned_to,
            'assigned_at': batch.assigned_at.isoformat() if batch.assigned_at else None,
            'completed_at': batch.completed_at.isoformat() if batch.completed_at else None,
            'retry_count': getattr(batch, 'retry_count', 0),
            'error_message': getattr(batch, 'error_message', None)
        }
    
    def get_job_progress(self, job_id: str) -> Dict:
        """
        Retourne le progrès d'un job
        
        Args:
            job_id: Identifiant du job
            
        Returns:
            Dictionnaire avec le progrès
        """
        if not hasattr(self.server, 'batches'):
            return {'total': 0, 'completed': 0, 'failed': 0, 'processing': 0, 'pending': 0}
        
        job_batches = [b for b in self.server.batches.values() if b.job_id == job_id]
        
        total = len(job_batches)
        completed = sum(1 for b in job_batches if b.status == BatchStatus.COMPLETED)
        failed = sum(1 for b in job_batches if b.status == BatchStatus.FAILED)
        processing = sum(1 for b in job_batches if b.status == BatchStatus.PROCESSING)
        pending = sum(1 for b in job_batches if b.status == BatchStatus.PENDING)
        
        return {
            'total': total,
            'completed': completed,
            'failed': failed,
            'processing': processing,
            'pending': pending,
            'progress_percent': (completed / total * 100) if total > 0 else 0
        }
    
    def get_stats(self) -> Dict:
        """Retourne les statistiques du gestionnaire"""
        return self.stats.copy()
    
    def reset_stats(self):
        """Remet à zéro les statistiques"""
        self.stats = {
            'total_batches_created': 0,
            'total_batches_completed': 0,
            'total_batches_failed': 0,
            'average_batch_time': 0,
            'total_data_transferred_mb': 0,
            'frames_per_batch': self.config.get("processing.batch_size", 50),
            'current_job_progress': 0
        }
        self.logger.info("Statistiques du gestionnaire de lots remises à zéro")
    
    def optimize_batch_distribution(self) -> Optional[Dict]:
        """
        Optimise la distribution des lots
        
        Returns:
            Dictionnaire avec les optimisations appliquées ou None
        """
        try:
            if not hasattr(self.server, 'clients'):
                return None
            
            active_clients = [c for c in self.server.clients.values() if c.is_online]
            if len(active_clients) < 2:
                return None
            
            # Analyse des performances
            performance_scores = []
            for client in active_clients:
                if client.batches_completed > 0:
                    score = client.success_rate * (1 / max(client.average_batch_time, 1))
                    performance_scores.append(score)
            
            if not performance_scores:
                return None
            
            # Détection de déséquilibre
            max_score = max(performance_scores)
            min_score = min(performance_scores)
            
            if max_score > min_score * 2:  # Déséquilibre significatif
                # Réduction du seuil de duplication pour permettre plus de parallélisme
                self.adaptive_config['duplicate_threshold'] = max(2, 
                    self.adaptive_config['duplicate_threshold'] - 1)
                
                return {
                    'reason': 'Déséquilibre de performance détecté',
                    'duplicate_threshold': self.adaptive_config['duplicate_threshold'],
                    'performance_ratio': max_score / min_score
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Erreur optimisation distribution: {e}")
            return None
    
    def _extract_result_zip(self, zip_path: Path, extract_dir: Path) -> List[str]:
        """
        Extrait un fichier ZIP de résultat
        
        Args:
            zip_path: Chemin du fichier ZIP
            extract_dir: Dossier d'extraction
            
        Returns:
            Liste des fichiers extraits
        """
        extracted_files = []
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_file:
                # Vérification de sécurité
                for name in zip_file.namelist():
                    if os.path.isabs(name) or ".." in name:
                        raise Exception(f"Nom de fichier dangereux: {name}")
                
                # Extraction
                zip_file.extractall(extract_dir)
                extracted_files = [
                    name for name in zip_file.namelist()
                    if not name.endswith('/')  # Exclure les dossiers
                ]
            
            return extracted_files
            
        except Exception as e:
            self.logger.error(f"Erreur extraction ZIP résultat {zip_path}: {e}")
            return []
    
    async def finalize_job(self, job_id: str) -> bool:
        """
        Finalise un job en recomposant la vidéo
        
        Args:
            job_id: Identifiant du job
            
        Returns:
            True si la finalisation a réussi
        """
        try:
            self.logger.info(f"Finalisation du job {job_id}")
            
            # Vérification que tous les lots sont terminés
            if hasattr(self.server, 'jobs') and job_id in self.server.jobs:
                job = self.server.jobs[job_id]
                
                # Compter les lots terminés
                completed_batches = 0
                total_batches = 0
                
                for batch_id, batch in self.server.batches.items():
                    if batch.job_id == job_id:
                        total_batches += 1
                        if batch.status == BatchStatus.COMPLETED:
                            completed_batches += 1
                
                if completed_batches < total_batches:
                    self.logger.warning(f"Job {job_id}: {completed_batches}/{total_batches} lots terminés")
            
            # Recomposition de la vidéo
            frames_dir = self.output_dir / job_id
            if not frames_dir.exists() or not list(frames_dir.glob('*.png')):
                raise Exception(f"Aucune frame upscalée trouvée pour le job {job_id}")
            
            success = await self._recompose_video(job_id, frames_dir)
            
            if success:
                self.logger.info(f"Job {job_id} finalisé avec succès")
                
                # Nettoyage optionnel des fichiers intermédiaires
                if not self.config.get("processing.keep_intermediate_files", False):
                    await self._cleanup_job_files(job_id)
            
            return success
            
        except Exception as e:
            self.logger.error(f"Erreur finalisation job {job_id}: {e}")
            return False