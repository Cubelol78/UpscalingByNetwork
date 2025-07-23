# core/batch_manager.py (Fixed)
import os
import subprocess
import asyncio
import shutil
import time
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime
import re

from models.job import Job, JobStatus
from models.batch import Batch, BatchStatus
from models.client import ClientStatus
from config.settings import config
from utils.logger import get_logger
from utils.file_utils import ensure_dir, get_video_info
from core.optimized_real_esrgan import optimized_realesrgan

class BatchManager:
    """Gestionnaire des lots d'images avec optimisations"""
    
    def __init__(self, server):
        self.server = server
        self.logger = get_logger(__name__)
        
        # Statistiques pour optimisation dynamique
        self.batch_performance_history = []
        
    async def assign_pending_batches(self):
        """Assigne les lots en attente aux clients disponibles avec optimisations"""
        # Récupération des clients disponibles triés par performance
        available_clients = self._get_sorted_available_clients()
        
        if not available_clients:
            return
        
        # Récupération des lots en attente
        pending_batches = [
            batch for batch in self.server.batches.values()
            if batch.status == BatchStatus.PENDING
        ]
        
        if not pending_batches:
            return
        
        # Tri des lots par priorité (avec logique de performance)
        pending_batches = self._prioritize_batches(pending_batches)
        
        # Adaptation dynamique du nombre de lots simultanés
        max_concurrent = optimized_realesrgan.get_recommended_concurrent_batches()
        currently_processing = sum(1 for batch in self.server.batches.values() 
                                 if batch.status == BatchStatus.PROCESSING)
        
        available_slots = max_concurrent - currently_processing
        if available_slots <= 0:
            return
        
        # Gestion intelligente des doublons
        should_duplicate = self._should_create_duplicates(pending_batches, available_clients)
        
        assignments = []
        
        # Attribution normale optimisée
        for i, batch in enumerate(pending_batches):
            if i < len(available_clients) and len(assignments) < available_slots:
                client_mac = available_clients[i]
                assignments.append((client_mac, batch))
        
        # Attribution des doublons si nécessaire et bénéfique
        if should_duplicate and len(assignments) < available_slots:
            duplicate_assignments = self._create_duplicate_assignments(
                pending_batches, available_clients[len(assignments):], 
                available_slots - len(assignments)
            )
            assignments.extend(duplicate_assignments)
        
        # Envoi des assignations avec adaptation en temps réel
        successful_assignments = 0
        for client_mac, batch in assignments:
            # Adaptation de la configuration selon la charge système
            adaptations = optimized_realesrgan.adapt_to_system_load()
            if adaptations:
                self.logger.info(f"Adaptation configuration pour {client_mac}: {adaptations.get('reason', '')}")
            
            success = await self.server.send_batch_to_client(client_mac, batch, adaptations)
            if success:
                successful_assignments += 1
                self.logger.debug(f"Lot {batch.id} assigné au client {client_mac}")
        
        if successful_assignments > 0:
            self.logger.info(f"{successful_assignments} lots assignés avec optimisations")
    
    def _get_sorted_available_clients(self) -> List[str]:
        """Récupère les clients disponibles triés par performance"""
        available_clients = [
            (mac, client) for mac, client in self.server.clients.items()
            if client.is_online and client.status == ClientStatus.CONNECTED
        ]
        
        # Tri par performance (vitesse moyenne de traitement)
        def client_performance_score(client_data):
            mac, client = client_data
            
            # Score basé sur plusieurs facteurs
            score = 0
            
            # Temps moyen de traitement (plus bas = mieux)
            if client.average_batch_time > 0:
                score += 1000 / client.average_batch_time  # Inversé pour favoriser la rapidité
            else:
                score += 100  # Score par défaut pour nouveaux clients
            
            # Taux de succès
            score *= (client.success_rate / 100) if client.success_rate > 0 else 0.5
            
            # Pénalité pour échecs récents
            if client.batches_failed > 0:
                failure_penalty = client.batches_failed / max(client.batches_completed + client.batches_failed, 1)
                score *= (1 - failure_penalty * 0.5)  # Réduction max 50%
            
            # Bonus pour matériel performant
            if hasattr(client, 'gpu_info') and client.gpu_info:
                gpu_memory = client.gpu_info.get('memory_total', 0)
                if gpu_memory > 12000:  # > 12GB
                    score *= 1.3
                elif gpu_memory > 8000:  # > 8GB
                    score *= 1.1
                elif gpu_memory < 4000:  # < 4GB
                    score *= 0.8
            
            return score
        
        # Tri par score de performance (meilleur en premier)
        available_clients.sort(key=client_performance_score, reverse=True)
        
        return [mac for mac, client in available_clients]
    
    def _prioritize_batches(self, batches: List[Batch]) -> List[Batch]:
        """Priorise les lots selon différents critères"""
        def batch_priority_score(batch):
            score = 0
            
            # Priorité aux lots plus anciens
            age_hours = (datetime.now() - batch.created_at).total_seconds() / 3600
            score += age_hours * 10
            
            # Priorité aux lots avec moins de tentatives
            score += (config.MAX_RETRIES - batch.retry_count) * 5
            
            # Priorité selon la taille (plus petit = plus facile à compléter)
            score += (100 - len(batch.frame_paths)) * 0.1
            
            return score
        
        return sorted(batches, key=batch_priority_score, reverse=True)
    
    def _should_create_duplicates(self, pending_batches: List[Batch], available_clients: List[str]) -> bool:
        """Détermine s'il faut créer des doublons de lots"""
        # Conditions pour créer des doublons
        conditions = [
            len(pending_batches) < config.DUPLICATE_THRESHOLD,  # Peu de lots en attente
            len(available_clients) > len(pending_batches),      # Plus de clients que de lots
            len(pending_batches) > 0,                           # Il y a des lots à dupliquer
            self._is_duplication_beneficial()                   # Duplication historiquement bénéfique
        ]
        
        return all(conditions)
    
    def _is_duplication_beneficial(self) -> bool:
        """Vérifie si la duplication a été bénéfique historiquement"""
        if len(self.batch_performance_history) < 10:
            return True  # Pas assez d'historique, on autorise
        
        # Analyse des performances avec/sans doublons
        recent_history = self.batch_performance_history[-20:]
        
        duplicated_performance = [
            perf for perf in recent_history 
            if perf.get('was_duplicated', False)
        ]
        
        single_performance = [
            perf for perf in recent_history 
            if not perf.get('was_duplicated', False)
        ]
        
        if not duplicated_performance or not single_performance:
            return True
        
        # Comparaison des temps moyens
        avg_duplicated_time = sum(p['completion_time'] for p in duplicated_performance) / len(duplicated_performance)
        avg_single_time = sum(p['completion_time'] for p in single_performance) / len(single_performance)
        
        # Duplication bénéfique si amélioration > 20%
        return avg_duplicated_time < avg_single_time * 0.8
    
    def _create_duplicate_assignments(self, pending_batches: List[Batch], 
                                    remaining_clients: List[str], 
                                    max_assignments: int) -> List[Tuple[str, Batch]]:
        """Crée des assignations de lots dupliqués"""
        assignments = []
        
        for client_mac in remaining_clients[:max_assignments]:
            if not pending_batches:
                break
                
            # Sélection du lot le plus approprié pour duplication
            best_batch = self._select_best_batch_for_duplication(pending_batches)
            
            if best_batch:
                # Vérification du nombre de doublons existants
                duplicate_count = sum(1 for b in self.server.batches.values()
                                    if (b.frame_start == best_batch.frame_start and 
                                        b.job_id == best_batch.job_id and
                                        b.status in [BatchStatus.ASSIGNED, BatchStatus.PROCESSING]))
                
                if duplicate_count < 3:  # Maximum 3 copies par lot
                    # Création du lot dupliqué
                    duplicate_batch = self._create_duplicate_batch(best_batch)
                    self.server.batches[duplicate_batch.id] = duplicate_batch
                    assignments.append((client_mac, duplicate_batch))
                    
                    self.logger.debug(f"Lot dupliqué créé: {duplicate_batch.id} pour client {client_mac}")
        
        return assignments
    
    def _select_best_batch_for_duplication(self, batches: List[Batch]) -> Optional[Batch]:
        """Sélectionne le meilleur lot pour duplication"""
        if not batches:
            return None
        
        # Critères de sélection pour duplication
        def duplication_score(batch):
            score = 0
            
            # Priorité aux lots plus anciens
            age_hours = (datetime.now() - batch.created_at).total_seconds() / 3600
            score += age_hours * 5
            
            # Priorité aux lots avec plus de tentatives (plus susceptibles d'échouer)
            score += batch.retry_count * 10
            
            # Priorité aux lots plus petits (duplication moins coûteuse)
            score += (config.BATCH_SIZE - len(batch.frame_paths)) * 0.5
            
            return score
        
        return max(batches, key=duplication_score)
    
    def _create_duplicate_batch(self, original_batch: Batch) -> Batch:
        """Crée un lot dupliqué"""
        duplicate = Batch(
            job_id=original_batch.job_id,
            frame_start=original_batch.frame_start,
            frame_end=original_batch.frame_end,
            frame_paths=original_batch.frame_paths.copy(),
            status=BatchStatus.DUPLICATE
        )
        
        return duplicate
    
    def create_batches_from_frames(self, job: Job, frame_paths: List[str], 
                                 batch_size: Optional[int] = None) -> List[Batch]:
        """Crée des lots à partir d'une liste de frames avec optimisations"""
        if batch_size is None:
            batch_size = optimized_realesrgan.get_optimal_batch_size()
        
        batches = []
        
        # Création des lots avec taille optimisée
        for i in range(0, len(frame_paths), batch_size):
            batch_frames = frame_paths[i:i + batch_size]
            
            batch = Batch(
                job_id=job.id,
                frame_start=i,
                frame_end=min(i + batch_size - 1, len(frame_paths) - 1),
                frame_paths=batch_frames
            )
            
            # Estimation du temps de traitement pour ce lot
            batch.estimated_time = self._estimate_batch_processing_time(batch)
            
            batches.append(batch)
            self.server.batches[batch.id] = batch
        
        self.logger.info(f"Créé {len(batches)} lots pour le job {job.id} "
                        f"(taille optimisée: {batch_size})")
        return batches
    
    def _estimate_batch_processing_time(self, batch: Batch) -> int:
        """Estime le temps de traitement d'un lot"""
        frame_count = len(batch.frame_paths)
        
        # Temps de base par frame selon le matériel
        system_status = optimized_realesrgan.get_system_status()
        base_time_per_frame = 2.0  # secondes par défaut
        
        if system_status.get('system_detected', False):
            if system_status.get('gpu_count', 0) > 0:
                gpu = system_status['gpus'][0]
                tier = gpu.get('tier', 'medium')
                
                if tier == 'extreme':
                    base_time_per_frame = 0.5
                elif tier == 'high':
                    base_time_per_frame = 1.0
                elif tier == 'medium':
                    base_time_per_frame = 2.0
                else:  # low
                    base_time_per_frame = 4.0
            else:
                base_time_per_frame = 8.0  # CPU seulement
        
        return int(frame_count * base_time_per_frame)
    
    def record_batch_completion(self, batch: Batch, processing_time: float, was_duplicated: bool = False):
        """Enregistre la completion d'un lot pour l'analyse de performance"""
        performance_record = {
            'batch_id': batch.id,
            'frame_count': len(batch.frame_paths),
            'processing_time': processing_time,
            'completion_time': time.time(),
            'retry_count': batch.retry_count,
            'was_duplicated': was_duplicated,
            'frames_per_second': len(batch.frame_paths) / processing_time if processing_time > 0 else 0
        }
        
        self.batch_performance_history.append(performance_record)
        
        # Limitation de l'historique
        if len(self.batch_performance_history) > 200:
            self.batch_performance_history.pop(0)
        
        # Analyse de tendance pour optimisation future
        self._analyze_performance_trends()
    
    def _analyze_performance_trends(self):
        """Analyse les tendances de performance pour optimisation"""
        if len(self.batch_performance_history) < 20:
            return
        
        recent_performance = self.batch_performance_history[-20:]
        
        # Calcul des métriques
        avg_fps = sum(p['frames_per_second'] for p in recent_performance) / len(recent_performance)
        avg_retry_rate = sum(p['retry_count'] for p in recent_performance) / len(recent_performance)
        
        # Recommandations d'optimisation
        recommendations = []
        
        if avg_fps < 0.5:  # Moins de 0.5 FPS
            recommendations.append("Performance faible détectée - vérifier la configuration GPU")
        
        if avg_retry_rate > 0.2:  # Plus de 20% de retry
            recommendations.append("Taux d'échec élevé - vérifier la stabilité des clients")
        
        # Log des recommandations
        for rec in recommendations:
            self.logger.warning(f"Recommandation d'optimisation: {rec}")
    
    def get_batch_statistics(self) -> Dict[str, Any]:
        """Retourne les statistiques détaillées des lots"""
        if not self.batch_performance_history:
            return {}
        
        recent_performance = self.batch_performance_history[-50:]  # 50 derniers
        
        return {
            'total_batches_processed': len(self.batch_performance_history),
            'recent_avg_fps': sum(p['frames_per_second'] for p in recent_performance) / len(recent_performance),
            'recent_avg_processing_time': sum(p['processing_time'] for p in recent_performance) / len(recent_performance),
            'recent_retry_rate': sum(p['retry_count'] for p in recent_performance) / len(recent_performance),
            'duplication_usage_rate': sum(1 for p in recent_performance if p['was_duplicated']) / len(recent_performance) * 100,
            'optimal_batch_size': optimized_realesrgan.get_optimal_batch_size(),
            'recommended_concurrent_batches': optimized_realesrgan.get_recommended_concurrent_batches()
        }
    
    def optimize_batch_distribution(self) -> Dict[str, Any]:
        """Optimise la distribution des lots en temps réel"""
        stats = self.get_batch_statistics()
        optimizations = {}
        
        # Ajustement de la taille des lots selon les performances
        if stats.get('recent_avg_fps', 0) < 0.3:
            # Performance faible, réduire la taille des lots
            new_batch_size = max(20, optimized_realesrgan.get_optimal_batch_size() // 2)
            optimizations['batch_size'] = new_batch_size
            optimizations['reason'] = "Réduction taille lot pour performance faible"
            
        elif stats.get('recent_avg_fps', 0) > 2.0:
            # Performance élevée, augmenter la taille des lots
            new_batch_size = min(100, optimized_realesrgan.get_optimal_batch_size() * 1.5)
            optimizations['batch_size'] = new_batch_size
            optimizations['reason'] = "Augmentation taille lot pour performance élevée"
        
        # Ajustement de la stratégie de duplication
        retry_rate = stats.get('recent_retry_rate', 0)
        if retry_rate > 0.3:
            optimizations['increase_duplication'] = True
            optimizations['reason'] = optimizations.get('reason', '') + " Augmentation duplication pour échecs"
        
        return optimizations
    
    async def smart_batch_recovery(self):
        """Récupération intelligente des lots échoués"""
        failed_batches = [
            batch for batch in self.server.batches.values()
            if batch.status == BatchStatus.FAILED and batch.retry_count < config.MAX_RETRIES
        ]
        
        if not failed_batches:
            return
        
        self.logger.info(f"Récupération de {len(failed_batches)} lots échoués")
        
        for batch in failed_batches:
            # Analyse de la cause d'échec
            if self._should_retry_batch(batch):
                # Adaptation de la configuration pour retry
                self._adapt_batch_for_retry(batch)
                
                # Remise en attente
                batch.reset()
                self.logger.info(f"Lot {batch.id} remis en attente (tentative {batch.retry_count + 1})")
            else:
                self.logger.warning(f"Lot {batch.id} abandonné après analyse")
    
    def _should_retry_batch(self, batch: Batch) -> bool:
        """Détermine si un lot doit être réessayé"""
        # Facteurs de décision
        factors = {
            'retry_count_ok': batch.retry_count < config.MAX_RETRIES,
            'not_too_old': (datetime.now() - batch.created_at).total_seconds() < 3600,  # < 1h
            'error_not_fatal': 'CUDA out of memory' not in batch.error_message.lower(),
            'client_available': len([c for c in self.server.clients.values() if c.is_online]) > 0
        }
        
        # Décision basée sur la majorité des facteurs
        positive_factors = sum(factors.values())
        return positive_factors >= 3
    
    def _adapt_batch_for_retry(self, batch: Batch):
        """Adapte un lot pour retry avec configuration réduite"""
        # Réduction de la taille si échec répété
        if batch.retry_count >= 2:
            # Division du lot en plus petits lots
            frame_count = len(batch.frame_paths)
            if frame_count > 20:
                # Créer des sous-lots plus petits
                mid_point = frame_count // 2
                
                # Premier sous-lot
                sub_batch1 = Batch(
                    job_id=batch.job_id,
                    frame_start=batch.frame_start,
                    frame_end=batch.frame_start + mid_point - 1,
                    frame_paths=batch.frame_paths[:mid_point]
                )
                
                # Second sous-lot
                sub_batch2 = Batch(
                    job_id=batch.job_id,
                    frame_start=batch.frame_start + mid_point,
                    frame_end=batch.frame_end,
                    frame_paths=batch.frame_paths[mid_point:]
                )
                
                # Ajout des sous-lots
                self.server.batches[sub_batch1.id] = sub_batch1
                self.server.batches[sub_batch2.id] = sub_batch2
                
                # Suppression du lot original
                if batch.id in self.server.batches:
                    del self.server.batches[batch.id]
                
                self.logger.info(f"Lot {batch.id} divisé en 2 sous-lots pour retry")