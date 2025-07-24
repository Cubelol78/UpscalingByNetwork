# client-windows/src/core/processor.py
import os
import sys
import tempfile
import zipfile
import subprocess
import asyncio
import logging
import shutil
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import io
import time

from ..security.client_security import ClientSecurity
from ..utils.config import ClientConfig
from ..utils.system_info import SystemInfo

class ClientProcessor:
    """
    Processeur client pour l'upscaling distribué
    Gère la réception, traitement et renvoi des lots
    """
    
    def __init__(self, client_instance):
        self.client = client_instance
        self.logger = logging.getLogger(__name__)
        self.config = ClientConfig()
        self.security = ClientSecurity()
        self.system_info = SystemInfo()
        
        # État du processeur
        self.is_processing = False
        self.current_batch_id = None
        self.processing_start_time = None
        
        # Dossiers de travail
        self.work_dir = Path(tempfile.gettempdir()) / "distributed_upscaler_client"
        self.work_dir.mkdir(exist_ok=True)
        
        # Chemin vers Real-ESRGAN
        self.realesrgan_path = self._find_realesrgan_executable()
        
        # Statistiques
        self.stats = {
            'batches_processed': 0,
            'total_frames_processed': 0,
            'total_processing_time': 0,
            'average_time_per_frame': 0,
            'errors_count': 0,
            'last_error': None
        }
        
        self.logger.info("Processeur client initialisé")
    
    def _find_realesrgan_executable(self) -> Optional[str]:
        """Trouve l'exécutable Real-ESRGAN selon la plateforme"""
        if sys.platform == "win32":
            executable_name = "realesrgan-ncnn-vulkan.exe"
        else:
            executable_name = "realesrgan-ncnn-vulkan"
        
        # Recherche dans le dossier des dépendances
        client_dir = Path(__file__).parent.parent.parent
        dependencies_dir = client_dir / "dependencies"
        executable_path = dependencies_dir / executable_name
        
        if executable_path.exists():
            self.logger.info(f"Real-ESRGAN trouvé: {executable_path}")
            return str(executable_path)
        
        # Recherche dans le PATH système
        if shutil.which(executable_name):
            path = shutil.which(executable_name)
            self.logger.info(f"Real-ESRGAN trouvé dans PATH: {path}")
            return path
        
        self.logger.error(f"Real-ESRGAN non trouvé: {executable_name}")
        return None
    
    async def process_batch(self, batch_data: dict, encrypted_zip_data: bytes) -> Optional[bytes]:
        """
        Traite un lot reçu du serveur
        
        Args:
            batch_data: Métadonnées du lot
            encrypted_zip_data: Données ZIP chiffrées
            
        Returns:
            Données ZIP chiffrées du résultat ou None en cas d'erreur
        """
        if self.is_processing:
            self.logger.warning("Traitement déjà en cours, lot refusé")
            return None
        
        if not self.realesrgan_path:
            self.logger.error("Real-ESRGAN non disponible")
            return None
        
        batch_id = batch_data.get('id')
        self.current_batch_id = batch_id
        self.is_processing = True
        self.processing_start_time = time.time()
        
        try:
            self.logger.info(f"Début traitement lot {batch_id}")
            
            # 1. Déchiffrement des données
            zip_data = await self._decrypt_batch_data(encrypted_zip_data)
            if not zip_data:
                raise Exception("Échec déchiffrement")
            
            # 2. Extraction des images
            input_dir = await self._extract_batch_images(batch_id, zip_data)
            if not input_dir:
                raise Exception("Échec extraction images")
            
            # 3. Traitement Real-ESRGAN
            output_dir = await self._process_with_realesrgan(
                batch_data, input_dir
            )
            if not output_dir:
                raise Exception("Échec traitement Real-ESRGAN")
            
            # 4. Validation du résultat
            if not await self._validate_output(batch_data, output_dir):
                raise Exception("Validation résultat échouée")
            
            # 5. Compression et chiffrement du résultat
            result_data = await self._prepare_result(batch_id, output_dir)
            
            # 6. Nettoyage
            await self._cleanup_batch_files(batch_id)
            
            # 7. Mise à jour des statistiques
            self._update_stats(batch_data, success=True)
            
            self.logger.info(f"Lot {batch_id} traité avec succès")
            return result_data
            
        except Exception as e:
            self.logger.error(f"Erreur traitement lot {batch_id}: {e}")
            self.stats['errors_count'] += 1
            self.stats['last_error'] = str(e)
            
            # Nettoyage en cas d'erreur
            await self._cleanup_batch_files(batch_id)
            return None
            
        finally:
            self.is_processing = False
            self.current_batch_id = None
            self.processing_start_time = None
    
    async def _decrypt_batch_data(self, encrypted_data: bytes) -> Optional[bytes]:
        """Déchiffre les données du lot"""
        try:
            session_key = self.security.get_session_key()
            if not session_key:
                raise Exception("Aucune clé de session disponible")
            
            decrypted_data = self.security.decrypt_data(encrypted_data, session_key)
            
            self.logger.debug(f"Données déchiffrées: {len(decrypted_data)} bytes")
            return decrypted_data
            
        except Exception as e:
            self.logger.error(f"Erreur déchiffrement: {e}")
            return None
    
    async def _extract_batch_images(self, batch_id: str, zip_data: bytes) -> Optional[Path]:
        """Extrait les images du ZIP dans un dossier temporaire"""
        try:
            # Création dossier d'extraction
            extract_dir = self.work_dir / f"batch_{batch_id}_input"
            extract_dir.mkdir(exist_ok=True)
            
            # Extraction du ZIP
            with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zip_file:
                zip_file.extractall(extract_dir)
            
            # Vérification des fichiers extraits
            image_files = list(extract_dir.glob("*.png"))
            if not image_files:
                raise Exception("Aucune image trouvée dans le ZIP")
            
            self.logger.debug(f"Extrait {len(image_files)} images dans {extract_dir}")
            return extract_dir
            
        except Exception as e:
            self.logger.error(f"Erreur extraction images: {e}")
            return None
    
    async def _process_with_realesrgan(self, batch_data: dict, input_dir: Path) -> Optional[Path]:
        """Exécute Real-ESRGAN sur le dossier d'entrée"""
        try:
            batch_id = batch_data['id']
            scale_factor = batch_data.get('scale_factor', 4)
            model_name = batch_data.get('model_name', 'realesrgan-x4plus')
            
            # Création dossier de sortie
            output_dir = self.work_dir / f"batch_{batch_id}_output"
            output_dir.mkdir(exist_ok=True)
            
            # Construction de la commande Real-ESRGAN
            cmd = [
                self.realesrgan_path,
                "-i", str(input_dir),
                "-o", str(output_dir),
                "-s", str(scale_factor),
                "-n", model_name
            ]
            
            # Ajout des optimisations système
            system_optimizations = self._get_system_optimizations()
            cmd.extend(system_optimizations)
            
            self.logger.info(f"Exécution Real-ESRGAN: {' '.join(cmd)}")
            
            # Exécution avec timeout
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), 
                    timeout=self.config.PROCESSING_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                process.kill()
                raise Exception("Timeout Real-ESRGAN")
            
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore')
                raise Exception(f"Real-ESRGAN a échoué: {error_msg}")
            
            # Vérification des fichiers de sortie
            output_files = list(output_dir.glob("*.png"))
            if not output_files:
                raise Exception("Aucun fichier de sortie généré")
            
            self.logger.info(f"Real-ESRGAN terminé: {len(output_files)} fichiers générés")
            return output_dir
            
        except Exception as e:
            self.logger.error(f"Erreur Real-ESRGAN: {e}")
            return None
    
    def _get_system_optimizations(self) -> List[str]:
        """Retourne les optimisations selon le matériel détecté"""
        optimizations = []
        
        # Détection GPU
        gpu_info = self.system_info.get_gpu_info()
        if gpu_info:
            # Optimisations spécifiques GPU
            if "RTX" in gpu_info.get('name', ''):
                optimizations.extend(["-t", "256"])  # Tile size optimisé
            else:
                optimizations.extend(["-t", "128"])  # Tile size conservateur
        else:
            # Mode CPU uniquement
            optimizations.extend(["-t", "64"])
        
        # Optimisations mémoire
        memory_gb = self.system_info.get_memory_info().get('total_gb', 0)
        if memory_gb < 8:
            optimizations.extend(["-j", "1:1:1"])  # Thread limité
        elif memory_gb >= 16:
            optimizations.extend(["-j", "2:2:2"])  # Threads élevés
        
        return optimizations
    
    async def _validate_output(self, batch_data: dict, output_dir: Path) -> bool:
        """Valide le résultat du traitement"""
        try:
            expected_count = len(batch_data.get('frame_paths', []))
            actual_files = list(output_dir.glob("*.png"))
            actual_count = len(actual_files)
            
            if actual_count != expected_count:
                self.logger.warning(f"Nombre de fichiers incorrect: {actual_count}/{expected_count}")
                return False
            
            # Vérification de la taille des fichiers (upscaling = fichiers plus gros)
            for file_path in actual_files:
                file_size = file_path.stat().st_size
                if file_size < 1024:  # Moins de 1KB = probablement erreur
                    self.logger.warning(f"Fichier trop petit: {file_path} ({file_size} bytes)")
                    return False
            
            self.logger.debug("Validation résultat: OK")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur validation: {e}")
            return False
    
    async def _prepare_result(self, batch_id: str, output_dir: Path) -> bytes:
        """Prépare le résultat pour envoi (compression + chiffrement)"""
        try:
            # 1. Compression en ZIP (sans compression pour optimiser)
            zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_STORED) as zip_file:
                for image_file in output_dir.glob("*.png"):
                    zip_file.write(image_file, image_file.name)
            
            zip_data = zip_buffer.getvalue()
            self.logger.debug(f"Résultat compressé: {len(zip_data)} bytes")
            
            # 2. Chiffrement
            session_key = self.security.get_session_key()
            if not session_key:
                raise Exception("Aucune clé de session pour chiffrement")
            
            encrypted_data = self.security.encrypt_data(zip_data, session_key)
            
            self.logger.debug(f"Résultat chiffré: {len(encrypted_data)} bytes")
            return encrypted_data
            
        except Exception as e:
            self.logger.error(f"Erreur préparation résultat: {e}")
            raise
    
    async def _cleanup_batch_files(self, batch_id: str):
        """Nettoie les fichiers temporaires du lot"""
        try:
            folders_to_clean = [
                self.work_dir / f"batch_{batch_id}_input",
                self.work_dir / f"batch_{batch_id}_output"
            ]
            
            for folder in folders_to_clean:
                if folder.exists():
                    shutil.rmtree(folder)
                    self.logger.debug(f"Dossier nettoyé: {folder}")
            
        except Exception as e:
            self.logger.warning(f"Erreur nettoyage lot {batch_id}: {e}")
    
    def _update_stats(self, batch_data: dict, success: bool):
        """Met à jour les statistiques de traitement"""
        if success:
            self.stats['batches_processed'] += 1
            frame_count = len(batch_data.get('frame_paths', []))
            self.stats['total_frames_processed'] += frame_count
            
            if self.processing_start_time:
                processing_time = time.time() - self.processing_start_time
                self.stats['total_processing_time'] += processing_time
                
                # Calcul moyenne temps par frame
                if self.stats['total_frames_processed'] > 0:
                    self.stats['average_time_per_frame'] = (
                        self.stats['total_processing_time'] / 
                        self.stats['total_frames_processed']
                    )
    
    def get_processing_status(self) -> dict:
        """Retourne l'état actuel du traitement"""
        status = {
            'is_processing': self.is_processing,
            'current_batch_id': self.current_batch_id,
            'realesrgan_available': self.realesrgan_path is not None,
            'work_directory': str(self.work_dir)
        }
        
        if self.is_processing and self.processing_start_time:
            status['processing_duration'] = time.time() - self.processing_start_time
        
        return status
    
    def get_statistics(self) -> dict:
        """Retourne les statistiques de traitement"""
        return self.stats.copy()
    
    def get_capabilities(self) -> dict:
        """Retourne les capacités du client"""
        gpu_info = self.system_info.get_gpu_info()
        memory_info = self.system_info.get_memory_info()
        
        return {
            'realesrgan_available': self.realesrgan_path is not None,
            'gpu_available': gpu_info is not None,
            'gpu_name': gpu_info.get('name', '') if gpu_info else '',
            'gpu_memory_mb': gpu_info.get('memory_mb', 0) if gpu_info else 0,
            'system_memory_gb': memory_info.get('total_gb', 0),
            'recommended_batch_size': self._calculate_recommended_batch_size(),
            'estimated_time_per_frame': self.stats.get('average_time_per_frame', 2.0)
        }
    
    def _calculate_recommended_batch_size(self) -> int:
        """Calcule la taille de lot recommandée selon les capacités"""
        base_size = 25  # Taille de base conservative
        
        gpu_info = self.system_info.get_gpu_info()
        if gpu_info:
            gpu_memory = gpu_info.get('memory_mb', 0)
            
            if gpu_memory >= 8192:  # 8GB+
                return 50
            elif gpu_memory >= 6144:  # 6GB+
                return 40
            elif gpu_memory >= 4096:  # 4GB+
                return 30
        
        # Mode CPU ou GPU faible
        return base_size

class ProgressTracker:
    """Gestionnaire de progression pour le traitement"""
    
    def __init__(self, callback=None):
        self.callback = callback
        self.current_progress = 0.0
        self.total_steps = 0
        self.completed_steps = 0
    
    def set_total_steps(self, total: int):
        """Définit le nombre total d'étapes"""
        self.total_steps = total
        self.completed_steps = 0
        self.current_progress = 0.0
    
    def step_completed(self, step_name: str = ""):
        """Marque une étape comme terminée"""
        self.completed_steps += 1
        
        if self.total_steps > 0:
            self.current_progress = (self.completed_steps / self.total_steps) * 100
        
        if self.callback:
            self.callback(self.current_progress, step_name)
    
    def set_progress(self, progress: float, description: str = ""):
        """Définit directement le pourcentage de progression"""
        self.current_progress = max(0, min(100, progress))
        
        if self.callback:
            self.callback(self.current_progress, description)
    
    def get_progress(self) -> float:
        """Retourne la progression actuelle"""
        return self.current_progress