# core/batch_manager.py
import os
import subprocess
import asyncio
import shutil
from pathlib import Path
from typing import List, Optional, Tuple
import re

from models.job import Job, JobStatus
from models.batch import Batch, BatchStatus
from models.client import ClientStatus
from config.settings import config
from utils.logger import get_logger
from utils.file_utils import ensure_dir, get_video_info

class BatchManager:
    """Gestionnaire des lots d'images"""
    
    def __init__(self, server):
        self.server = server
        self.logger = get_logger(__name__)
    
    async def assign_pending_batches(self):
        """Assigne les lots en attente aux clients disponibles"""
        # Récupération des clients disponibles
        available_clients = [
            mac for mac, client in self.server.clients.items()
            if client.is_online and client.status == ClientStatus.CONNECTED
        ]
        
        if not available_clients:
            return
        
        # Récupération des lots en attente
        pending_batches = [
            batch for batch in self.server.batches.values()
            if batch.status == BatchStatus.PENDING
        ]
        
        if not pending_batches:
            return
        
        # Tri des lots par priorité (les plus anciens en premier)
        pending_batches.sort(key=lambda b: b.created_at)
        
        # Gestion des doublons si nécessaire
        should_duplicate = (len(pending_batches) < config.DUPLICATE_THRESHOLD and 
                          len(available_clients) > len(pending_batches))
        
        assignments = []
        
        # Attribution normale
        for i, batch in enumerate(pending_batches):
            if i < len(available_clients):
                client_mac = available_clients[i]
                assignments.append((client_mac, batch))
        
        # Attribution des doublons si nécessaire
        if should_duplicate and len(assignments) < len(available_clients):
            remaining_clients = available_clients[len(assignments):]
            for client_mac in remaining_clients:
                # Sélection du lot le plus ancien non dupliqué
                for batch in pending_batches:
                    duplicate_count = sum(1 for b in self.server.batches.values()
                                        if b.frame_start == batch.frame_start and 
                                           b.status in [BatchStatus.ASSIGNED, BatchStatus.PROCESSING])
                    
                    if duplicate_count < 2:  # Maximum 2 copies par lot
                        # Création d'un lot dupliqué
                        duplicate_batch = Batch(
                            job_id=batch.job_id,
                            frame_start=batch.frame_start,
                            frame_end=batch.frame_end,
                            frame_paths=batch.frame_paths.copy(),
                            status=BatchStatus.DUPLICATE
                        )
                        self.server.batches[duplicate_batch.id] = duplicate_batch
                        assignments.append((client_mac, duplicate_batch))
                        break
        
        # Envoi des assignations
        for client_mac, batch in assignments:
            success = await self.server.send_batch_to_client(client_mac, batch)
            if success:
                self.logger.debug(f"Lot {batch.id} assigné au client {client_mac}")
    
    def create_batches_from_frames(self, job: Job, frame_paths: List[str]) -> List[Batch]:
        """Crée des lots à partir d'une liste de frames"""
        batches = []
        
        for i in range(0, len(frame_paths), config.BATCH_SIZE):
            batch_frames = frame_paths[i:i + config.BATCH_SIZE]
            
            batch = Batch(
                job_id=job.id,
                frame_start=i,
                frame_end=min(i + config.BATCH_SIZE - 1, len(frame_paths) - 1),
                frame_paths=batch_frames
            )
            
            batches.append(batch)
            self.server.batches[batch.id] = batch
        
        self.logger.info(f"Créé {len(batches)} lots pour le job {job.id}")
        return batches