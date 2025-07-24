# server/src/core/batch_manager.py
import asyncio
import logging
import shutil
import zipfile
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path

from ..models.batch import Batch, BatchStatus, BatchUtils
from ..models.client import Client, ClientStatus
from ..security.encryption import EncryptionManager
from ..utils.config import Config

class BatchManager:
    """
    Gestionnaire de lots pour la distribution sécurisée avec dossiers
    Gère la création, compression, chiffrement et distribution des lots
    """
    
    def __init__(self, server_instance):
        self.server = server_instance
        self.logger = logging.getLogger(__name__)
        self.config = Config()
        self.encryption = EncryptionManager()
        
        # Statistiques et monitoring
        self.stats = {
            'total_batches_created': 0,
            'total_batches_completed': 0,
            'total_batches_failed': 0,
            'average_batch_time': 0,
            'total_data_transferred_mb': 0
        }
        
        # Tâche de monitoring
        self.monitoring_task = None
        self.running = False
    
    async def start(self):
        """Démarre le gestionnaire de lots"""
        self.running = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        self.logger.info("Gestionnaire de lots démarré")
    
    async def stop(self):
        """Arrête le gestionnaire de lots"""
        self.running = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
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
            # 1. Extraction des frames de la vidéo
            frames_dir = await self._extract_video_frames(job_id, video_path)
            
            # 2. Listage des images extraites
            frame_files = sorted(list(frames_dir.glob("*.png")))
            
            if not frame_files:
                raise Exception("Aucune image extraite de la vidéo")
            
            # 3. Création des dossiers de lots
            batches = await self._create_batch_folders(job_id, frame_files)
            
            self.logger.info(f"Job {job_id}: {len(batches)} lots créés à partir de {len(frame_files)} images")
            self.stats['total_batches_created'] += len(batches)
            
            return batches
            
        except Exception as e:
            self.logger.error(f"Erreur création lots pour job {job_id}: {e}")
            raise
    
    async def _extract_video_frames(self, job_id: str, video_path: str) -> Path:
        """Extrait les frames d'une vidéo avec FFmpeg"""
        job_dir = Path(self.config.TEMP_DIR) / f"job_{job_id}"
        frames_dir = job_dir / "original_frames"
        
        # Création des dossiers
        frames_dir.mkdir(parents=True, exist_ok=True)
        
        # Commande FFmpeg pour extraction
        ffmpeg_cmd = [
            "ffmpeg", "-i", str(video_path),
            "-vf", "fps=fps=30",  # 30 FPS par défaut
            "-q:v", "1",  # Qualité maximale
            str(frames_dir / "frame_%06d.png")
        ]
        
        self.logger.info(f"Extraction frames de {video_path}")
        
        process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise Exception(f"Erreur FFmpeg: {stderr.decode()}")
        
        self.logger.info(f"Frames extraites dans {frames_dir}")
        return frames_dir
    
    async def _create_batch_folders(self, job_id: str, frame_files: List[Path]) -> List[Batch]:
        """Crée les dossiers de lots avec les images"""
        job_dir = Path(self.config.TEMP_DIR) / f"job_{job_id}"
        batches_dir = job_dir / "batches"
        batches_dir.mkdir(exist_ok=True)
        
        batches = []
        batch_size = self.config.BATCH_SIZE  # 50 par défaut
        
        for i in range(0, len(frame_files), batch_size):
            batch_number = (i // batch_size) + 1
            batch_frames = frame_files[i:i + batch_size]
            
            # Création du lot
            batch = Batch(
                job_id=job_id,
                frame_start=i,
                frame_end=min(i + batch_size - 1, len(frame_files) - 1),
                frame_paths=[str(f.name) for f in batch_frames]  # Noms relatifs
            )
            
            # Création du dossier du lot
            batch_dir = batches_dir / f"batch_{batch_number:03d}"
            batch_dir.mkdir(exist_ok=True)
            
            # Copie des images dans le dossier du lot
            for frame_file in batch_frames:
                dst_path = batch_dir / frame_file.name
                shutil.copy2(frame_file, dst_path)
            
            batch.batch_folder = str(batch_dir)
            batches.append(batch)
            
            self.logger.debug(f"Lot {batch.id} créé: {len(batch_frames)} images dans {batch_dir}")
        
        return batches
    
    async def prepare_batch_for_client(self, batch: Batch, client_mac: str) -> bytes:
        """
        Prépare un lot pour envoi au client (zip + chiffrement)
        
        Args:
            batch: Le lot à préparer
            client_mac: Adresse MAC du client destinataire
            
        Returns:
            Données chiffrées prêtes à envoyer
        """
        try:
            # 1. Compression du dossier du lot
            zip_data = await self._compress_batch_folder(batch)
            
            # 2. Chiffrement avec la clé de session du client
            session_key = self.server.get_client_session_key(client_mac)
            encrypted_data = self.encryption.encrypt_data(zip_data, session_key)
            
            self.logger.debug(f"Lot {batch.id} préparé pour client {client_mac}: {len(encrypted_data)} bytes")
            
            # Mise à jour des statistiques
            self.stats['total_data_transferred_mb'] += len(encrypted_data) / (1024 * 1024)
            
            return encrypted_data
            
        except Exception as e:
            self.logger.error(f"Erreur préparation lot {batch.id} pour {client_mac}: {e}")
            raise
    
    async def _compress_batch_folder(self, batch: Batch) -> bytes:
        """Compresse le dossier d'un lot en ZIP (compression 0)"""
        batch_folder = Path(batch.batch_folder)
        
        if not batch_folder.exists():
            raise Exception(f"Dossier du lot non trouvé: {batch_folder}")
        
        # Compression en mémoire
        import io
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_STORED) as zip_file:  # ZIP_STORED = pas de compression
            for image_file in batch_folder.glob("*.png"):
                zip_file.write(image_file, image_file.name)
        
        zip_data = zip_buffer.getvalue()
        self.logger.debug(f"Lot {batch.id} compressé: {len(zip_data)} bytes")
        
        return zip_data
    
    async def process_batch_result(self, batch_id: str, client_mac: str, encrypted_data: bytes) -> bool:
        """
        Traite le résultat d'un lot reçu du client
        
        Args:
            batch_id: ID du lot traité
            client_mac: MAC du client qui a traité
            encrypted_data: Données chiffrées reçues
            
        Returns:
            True si le traitement a réussi, False sinon
        """
        try:
            if batch_id not in self.server.batches:
                self.logger.warning(f"Lot {batch_id} non trouvé pour traitement résultat")
                return False
            
            batch = self.server.batches[batch_id]
            
            # 1. Déchiffrement des données
            session_key = self.server.get_client_session_key(client_mac)
            zip_data = self.encryption.decrypt_data(encrypted_data, session_key)
            
            # 2. Décompression et validation
            upscaled_images = await self._extract_upscaled_images(zip_data, batch)
            
            # 3. Vérification de la complétude
            expected_count = len(batch.frame_paths)
            received_count = len(upscaled_images)
            
            if received_count != expected_count:
                self.logger.warning(f"Lot {batch_id} incomplet: {received_count}/{expected_count} images")
                batch.fail(f"Images incomplètes: {received_count}/{expected_count}")
                return False
            
            # 4. Copie vers le dossier final
            success = await self._copy_to_final_directory(batch, upscaled_images)
            
            if success:
                batch.complete()
                self.stats['total_batches_completed'] += 1
                self.logger.info(f"Lot {batch_id} traité avec succès par {client_mac}")
                
                # Nettoyage du dossier temporaire du lot
                await self._cleanup_batch_folder(batch)
                
                return True
            else:
                batch.fail("Erreur lors de la copie finale")
                return False
                
        except Exception as e:
            self.logger.error(f"Erreur traitement résultat lot {batch_id}: {e}")
            if batch_id in self.server.batches:
                self.server.batches[batch_id].fail(str(e))
            return False
    
    async def _extract_upscaled_images(self, zip_data: bytes, batch: Batch) -> List[Path]:
        """Extrait les images upscalées du ZIP reçu"""
        import io
        import tempfile
        
        upscaled_images = []
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Extraction du ZIP
            with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zip_file:
                zip_file.extractall(temp_path)
            
            # Validation des images extraites
            for expected_frame in batch.frame_paths:
                upscaled_name = expected_frame  # Même nom que l'original
                upscaled_path = temp_path / upscaled_name
                
                if upscaled_path.exists():
                    upscaled_images.append(upscaled_path)
                else:
                    self.logger.warning(f"Image upscalée manquante: {upscaled_name}")
        
        return upscaled_images
    
    async def _copy_to_final_directory(self, batch: Batch, upscaled_images: List[Path]) -> bool:
        """Copie les images upscalées vers le dossier final"""
        try:
            job_dir = Path(self.config.TEMP_DIR) / f"job_{batch.job_id}"
            final_dir = job_dir / "upscaled_final"
            final_dir.mkdir(exist_ok=True)
            
            for image_path in upscaled_images:
                dst_path = final_dir / image_path.name
                shutil.copy2(image_path, dst_path)
            
            self.logger.debug(f"Lot {batch.id}: {len(upscaled_images)} images copiées vers {final_dir}")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur copie finale lot {batch.id}: {e}")
            return False
    
    async def _cleanup_batch_folder(self, batch: Batch):
        """Nettoie le dossier temporaire d'un lot terminé"""
        try:
            batch_folder = Path(batch.batch_folder)
            if batch_folder.exists():
                shutil.rmtree(batch_folder)
                self.logger.debug(f"Dossier lot {batch.id} nettoyé: {batch_folder}")
        except Exception as e:
            self.logger.warning(f"Erreur nettoyage lot {batch.id}: {e}")
    
    async def assign_batches_to_clients(self) -> List[Tuple[str, Batch]]:
        """Assigne les lots aux clients disponibles"""
        pending_batches = self._get_pending_batches()
        available_clients = self._get_available_clients()
        
        if not pending_batches or not available_clients:
            return []
        
        assignments = []
        
        # Assignation normale (1 lot par client disponible)
        max_assignments = min(len(pending_batches), len(available_clients))
        
        for i in range(max_assignments):
            client_mac = available_clients[i]
            batch = pending_batches[i]
            
            batch.assign_to_client(client_mac)
            assignments.append((client_mac, batch))
            
            self.logger.debug(f"Lot {batch.id} assigné au client {client_mac}")
        
        # Gestion des doublons si nécessaire
        remaining_clients = available_clients[max_assignments:]
        if remaining_clients and len(pending_batches) < self.config.DUPLICATE_THRESHOLD:
            duplicate_assignments = await self._create_duplicate_assignments(
                pending_batches, remaining_clients
            )
            assignments.extend(duplicate_assignments)
        
        return assignments
    
    async def _create_duplicate_assignments(self, batches: List[Batch], clients: List[str]) -> List[Tuple[str, Batch]]:
        """Crée des assignations dupliquées pour accélération"""
        assignments = []
        
        for client_mac in clients:
            if not batches:
                break
            
            # Sélection du lot le plus ancien pour duplication
            oldest_batch = min(batches, key=lambda b: b.created_at)
            
            # Création d'un lot dupliqué
            duplicate_batch = oldest_batch.create_duplicate()
            duplicate_batch.batch_folder = oldest_batch.batch_folder  # Même dossier source
            
            duplicate_batch.assign_to_client(client_mac)
            self.server.batches[duplicate_batch.id] = duplicate_batch
            
            assignments.append((client_mac, duplicate_batch))
            
            self.logger.debug(f"Lot dupliqué {duplicate_batch.id} créé pour client {client_mac}")
        
        return assignments
    
    def _get_pending_batches(self) -> List[Batch]:
        """Récupère les lots en attente"""
        pending = [batch for batch in self.server.batches.values() 
                  if batch.status == BatchStatus.PENDING]
        
        # Tri par âge (plus ancien en premier)
        return sorted(pending, key=lambda b: b.created_at)
    
    def _get_available_clients(self) -> List[str]:
        """Récupère les clients disponibles"""
        available = []
        
        for mac, client in self.server.clients.items():
            if (client.status == ClientStatus.CONNECTED and 
                client.current_batch is None and
                client.is_online):
                available.append(mac)
        
        return available
    
    async def _monitoring_loop(self):
        """Boucle de monitoring pour timeouts et reprises"""
        while self.running:
            try:
                await self._check_batch_timeouts()
                await self._retry_failed_batches()
                await asyncio.sleep(30)  # Vérification toutes les 30 secondes
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Erreur monitoring: {e}")
                await asyncio.sleep(5)
    
    async def _check_batch_timeouts(self):
        """Vérifie les timeouts des lots en traitement"""
        timeout_duration = timedelta(minutes=self.config.BATCH_TIMEOUT_MINUTES)
        now = datetime.now()
        
        for batch in self.server.batches.values():
            if (batch.status == BatchStatus.PROCESSING and 
                batch.started_at and 
                now - batch.started_at > timeout_duration):
                
                batch.timeout()
                self.logger.warning(f"Timeout lot {batch.id} (client: {batch.assigned_client})")
                
                # Libérer le client
                if batch.assigned_client in self.server.clients:
                    self.server.clients[batch.assigned_client].current_batch = None
    
    async def _retry_failed_batches(self):
        """Remet en attente les lots échoués qui peuvent être réessayés"""
        for batch in self.server.batches.values():
            if batch.status == BatchStatus.FAILED and batch.can_retry:
                batch.reset_for_retry()
                self.logger.info(f"Lot {batch.id} remis en attente (tentative {batch.retry_count + 1})")
    
    def get_stats(self) -> dict:
        """Retourne les statistiques du gestionnaire"""
        return {
            **self.stats,
            'pending_batches': len(self._get_pending_batches()),
            'available_clients': len(self._get_available_clients())
        }