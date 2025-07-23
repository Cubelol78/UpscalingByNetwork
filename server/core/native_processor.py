"""
Processeur natif pour traiter les lots directement sur le serveur - VERSION CORRIGÉE
"""

import os
import subprocess
import asyncio
import shutil
from pathlib import Path
from typing import List, Optional
import time

from models.batch import Batch, BatchStatus
from config.settings import config
from utils.logger import get_logger

class NativeProcessor:
    """Processeur natif du serveur pour traiter les lots localement"""
    
    def __init__(self, server):
        self.server = server
        self.logger = get_logger(__name__)
        self.is_processing = False
        self.current_batch = None
        self.realesrgan_path = None
        
        # Vérifier la disponibilité de Real-ESRGAN
        self.realesrgan_available = self._check_realesrgan_availability()
    
    def _check_realesrgan_availability(self) -> bool:
        """Vérifie si Real-ESRGAN est disponible"""
        try:
            # Chemin vers Real-ESRGAN intégré
            project_root = Path(__file__).parent.parent
            realesrgan_path = project_root / "realesrgan-ncnn-vulkan" / "Windows" / "realesrgan-ncnn-vulkan.exe"
            
            self.logger.info(f"Vérification de Real-ESRGAN dans: {realesrgan_path}")
            
            if realesrgan_path.exists():
                self.realesrgan_path = str(realesrgan_path)
                self.logger.info(f"✅ Real-ESRGAN trouvé: {realesrgan_path}")
                return True
            else:
                # Essayer dans le dossier du projet actuel
                current_realesrgan = Path.cwd() / "realesrgan-ncnn-vulkan.exe"
                if current_realesrgan.exists():
                    self.realesrgan_path = str(current_realesrgan)
                    self.logger.info(f"✅ Real-ESRGAN trouvé: {current_realesrgan}")
                    return True
                else:
                    self.logger.warning(f"❌ Real-ESRGAN non trouvé dans: {realesrgan_path} ou {current_realesrgan}")
                    return False
            
        except Exception as e:
            self.logger.warning(f"Erreur vérification Real-ESRGAN: {e}")
            return False
    
    async def start_native_processing(self):
        """Démarre le traitement natif des lots"""
        if not self.realesrgan_available:
            self.logger.warning("Traitement natif impossible - Real-ESRGAN non disponible")
            return
        
        if self.is_processing:
            return
        
        self.is_processing = True
        self.logger.info("Traitement natif démarré")
        
        # Boucle de traitement
        while self.is_processing and self.server.running:
            try:
                # Chercher un lot en attente
                pending_batch = self._get_next_pending_batch()
                
                if pending_batch:
                    await self._process_batch_native(pending_batch)
                else:
                    # Aucun lot en attente, attendre un peu
                    await asyncio.sleep(2)
                    
            except Exception as e:
                self.logger.error(f"Erreur dans la boucle de traitement natif: {e}")
                await asyncio.sleep(5)
        
        self.is_processing = False
        self.logger.info("Traitement natif arrêté")
    
    def stop_native_processing(self):
        """Arrête le traitement natif"""
        self.is_processing = False
        if self.current_batch:
            # Remettre le lot en attente
            batch = self.server.batches.get(self.current_batch)
            if batch and batch.status == BatchStatus.PROCESSING:
                batch.reset()
                self.logger.info(f"Lot {self.current_batch} remis en attente")
        self.current_batch = None
    
    def _get_next_pending_batch(self) -> Optional[Batch]:
        """Récupère le prochain lot en attente"""
        # Chercher les lots en attente, triés par ancienneté
        pending_batches = [
            batch for batch in self.server.batches.values()
            if batch.status == BatchStatus.PENDING
        ]
        
        if not pending_batches:
            return None
        
        # Trier par date de création (plus ancien en premier)
        pending_batches.sort(key=lambda b: b.created_at)
        return pending_batches[0]
    
    async def _process_batch_native(self, batch: Batch):
        """Traite un lot nativement"""
        try:
            self.current_batch = batch.id
            batch.assign_to_client("SERVER_NATIVE")
            batch.start_processing()
            
            self.logger.info(f"Traitement natif du lot {batch.id} - {len(batch.frame_paths)} frames")
            
            # Préparer les dossiers
            input_dir = Path(config.TEMP_DIR) / f"job_{batch.job_id}_frames"
            output_dir = Path(config.TEMP_DIR) / f"job_{batch.job_id}_upscaled"
            
            if not input_dir.exists():
                raise Exception(f"Dossier d'entrée non trouvé: {input_dir}")
            
            output_dir.mkdir(exist_ok=True)
            
            # Traiter les frames avec Real-ESRGAN
            success = await self._run_realesrgan(input_dir, output_dir, batch)
            
            if success:
                batch.complete()
                self.logger.info(f"Lot {batch.id} traité avec succès en natif")
                
                # Mettre à jour la progression du job
                await self.server._update_job_progress(batch.job_id)
            else:
                batch.fail("Erreur lors du traitement Real-ESRGAN")
                self.logger.error(f"Échec du traitement natif du lot {batch.id}")
            
            self.current_batch = None
            
        except Exception as e:
            batch.fail(str(e))
            self.current_batch = None
            self.logger.error(f"Erreur traitement natif lot {batch.id}: {e}")
    
    async def _run_realesrgan(self, input_dir: Path, output_dir: Path, batch: Batch) -> bool:
        """Exécute Real-ESRGAN avec configuration forcée RTX 3050"""
        try:
            # Configuration forcée pour RTX 3050
            from config.settings import FORCE_RTX_3050, RTX_3050_OVERRIDE
            
            if FORCE_RTX_3050:
                print("🎯 FORCE RTX 3050 MODE ACTIVÉ")
                
                # Configuration optimisée spécifiquement pour RTX 3050
                rtx_config = {
                    'gpu_id': 0,  # FORCER GPU 0 (RTX 3050)
                    'model': 'realesr-animevideov3',
                    'tile_size': 256,
                    'threads': '3:6:3',  # Configuration agressive
                    'use_fp16': True
                }
                
                print(f"🚀 Configuration RTX 3050 forcée: {rtx_config}")
            else:
                # Utilisation de la configuration optimisée du système
                from core.optimized_real_esrgan import optimized_realesrgan
                rtx_config = optimized_realesrgan.optimal_config
                
                # Correction si le mauvais GPU est sélectionné
                if rtx_config.get('gpu_id', -1) != 0:
                    print(f"⚠️ GPU incorrect détecté ({rtx_config.get('gpu_id')}), correction vers GPU 0 (RTX 3050)")
                    rtx_config['gpu_id'] = 0
                    rtx_config['threads'] = '3:6:3'  # Configuration plus agressive
            
            print(f"🎯 Configuration finale pour lot {batch.id}: {rtx_config}")
            
            # Construction de la commande Real-ESRGAN
            cmd = [self.realesrgan_path]
            
            # Paramètres de base
            cmd.extend(["-i", str(input_dir)])
            cmd.extend(["-o", str(output_dir)])
            cmd.extend(["-n", rtx_config.get('model', 'realesr-animevideov3')])
            cmd.extend(["-f", "png"])
            
            # Configuration GPU - FORCER RTX 3050
            gpu_id = rtx_config.get('gpu_id', 0)
            cmd.extend(["-g", str(gpu_id)])
            print(f"🎯 FORCÉ: Utilisation GPU {gpu_id} (RTX 3050)")
            
            # Tile size optimisé
            tile_size = rtx_config.get('tile_size', 256)
            cmd.extend(["-t", str(tile_size)])
            print(f"🔲 Tile size: {tile_size}")
            
            # Threads optimisés pour performance maximale
            threads = rtx_config.get('threads', '3:6:3')
            cmd.extend(["-j", threads])
            print(f"🧵 Threads agressifs: {threads}")
            
            # Mode verbose
            cmd.append("-v")
            
            self.logger.info(f"Exécution Real-ESRGAN RTX 3050 FORCÉ: {' '.join(cmd)}")
            print(f"🚀 Commande RTX 3050: {' '.join(cmd)}")
            
            # Exécuter le processus
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Attendre la fin du processus
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                # Vérifier que les frames ont été créées
                expected_frames = len(batch.frame_paths)
                output_frames = len(list(output_dir.glob("*.png")))
                
                if output_frames >= expected_frames * 0.9:  # Tolérance de 10%
                    self.logger.info(f"RTX 3050 Real-ESRGAN réussi: {output_frames}/{expected_frames} frames")
                    print(f"✅ RTX 3050 Real-ESRGAN réussi: {output_frames}/{expected_frames} frames")
                    return True
                else:
                    self.logger.error(f"Frames manquantes: {output_frames}/{expected_frames}")
                    print(f"❌ Frames manquantes: {output_frames}/{expected_frames}")
                    return False
            else:
                error_msg = stderr.decode() if stderr else "Erreur inconnue"
                self.logger.error(f"RTX 3050 Real-ESRGAN échoué (code {process.returncode}): {error_msg}")
                print(f"❌ RTX 3050 Real-ESRGAN échoué: {error_msg}")
                
                # Si échec avec RTX, essayer avec configuration de secours
                print("🔄 Tentative avec configuration de secours...")
                return await self._run_realesrgan_fallback(input_dir, output_dir, batch)
                
        except Exception as e:
            self.logger.error(f"Erreur exécution RTX 3050 Real-ESRGAN: {e}")
            print(f"❌ Erreur exécution RTX 3050: {e}")
            return False
    
    async def _run_realesrgan_fallback(self, input_dir: Path, output_dir: Path, batch: Batch) -> bool:
        """Configuration de secours si RTX 3050 échoue"""
        try:
            print("🔄 Mode de secours: configuration conservative")
            
            cmd = [
                self.realesrgan_path,
                "-i", str(input_dir),
                "-o", str(output_dir),
                "-n", "realesr-animevideov3",
                "-f", "png",
                "-g", "0",  # Essayer GPU 0 avec config conservative
                "-t", "128",  # Tile size réduit
                "-j", "1:2:1",  # Threads réduits
                "-v"
            ]
            
            print(f"🔄 Commande de secours: {' '.join(cmd)}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                expected_frames = len(batch.frame_paths)
                output_frames = len(list(output_dir.glob("*.png")))
                
                if output_frames >= expected_frames * 0.8:  # Tolérance de 20% en mode secours
                    print(f"✅ Mode secours réussi: {output_frames}/{expected_frames} frames")
                    return True
                    
            return False
            
        except Exception as e:
            print(f"❌ Erreur mode secours: {e}")
            return False

    def get_status(self) -> dict:
        """Retourne le statut du processeur natif"""
        return {
            "available": self.realesrgan_available,
            "processing": self.is_processing,
            "current_batch": self.current_batch,
            "model": config.REALESRGAN_MODEL,
            "tile_size": config.TILE_SIZE,
            "gpu_id": config.GPU_ID,
            "executable_path": self.realesrgan_path
        }