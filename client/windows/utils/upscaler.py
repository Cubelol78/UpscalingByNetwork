"""
Utilitaires pour le client Windows
UpscalingByNetwork/client/windows/utils/upscaler.py
"""

import os
import subprocess
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
import platform
import shutil

class RealESRGANUpscaler:
    """Interface pour Real-ESRGAN sur Windows"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Chemins des exécutables
        self.realesrgan_path = Path("realesrgan-ncnn-vulkan")
        self.executable_path = self.realesrgan_path / "realesrgan-ncnn-vulkan.exe"
        
        # Configuration par défaut
        self.default_config = {
            'model': 'realesr-animevideov3',
            'scale': 4,
            'tile_size': 256,
            'gpu_id': 0,
            'denoise': True,
            'face_enhance': False
        }
        
        # Cache des modèles disponibles
        self._available_models = None
        self._gpu_info = None
        
        self.logger.info("RealESRGANUpscaler initialisé")
    
    def is_available(self) -> bool:
        """Vérifie si Real-ESRGAN est disponible"""
        try:
            if not self.executable_path.exists():
                self.logger.warning(f"Exécutable Real-ESRGAN non trouvé: {self.executable_path}")
                return False
            
            # Test de lancement rapide
            result = subprocess.run(
                [str(self.executable_path), "--help"],
                capture_output=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            )
            
            success = result.returncode == 0
            if success:
                self.logger.info("Real-ESRGAN disponible et fonctionnel")
            else:
                self.logger.error(f"Real-ESRGAN test échoué: {result.stderr.decode()}")
            
            return success
            
        except subprocess.TimeoutExpired:
            self.logger.error("Timeout lors du test Real-ESRGAN")
            return False
        except Exception as e:
            self.logger.error(f"Erreur test Real-ESRGAN: {e}")
            return False
    
    def get_available_models(self) -> List[str]:
        """Retourne la liste des modèles disponibles"""
        if self._available_models is not None:
            return self._available_models
        
        try:
            models_dir = self.realesrgan_path / "models"
            if not models_dir.exists():
                self.logger.warning(f"Dossier modèles non trouvé: {models_dir}")
                return []
            
            # Recherche des fichiers .bin de modèles
            model_files = list(models_dir.glob("*.bin"))
            models = []
            
            for model_file in model_files:
                model_name = model_file.stem
                # Suppression des suffixes techniques
                clean_name = model_name.replace("-model", "").replace("_model", "")
                if clean_name not in models:
                    models.append(clean_name)
            
            # Modèles standards si aucun trouvé
            if not models:
                models = [
                    "realesr-animevideov3",
                    "realesrgan-x4plus",
                    "realesrgan-x4plus-anime"
                ]
            
            self._available_models = sorted(models)
            self.logger.info(f"Modèles disponibles: {self._available_models}")
            
            return self._available_models
            
        except Exception as e:
            self.logger.error(f"Erreur récupération modèles: {e}")
            return ["realesr-animevideov3"]  # Fallback
    
    def get_gpu_info(self) -> Dict[str, Any]:
        """Récupère les informations sur les GPU disponibles"""
        if self._gpu_info is not None:
            return self._gpu_info
        
        try:
            # Test avec Real-ESRGAN pour détecter les GPU
            result = subprocess.run(
                [str(self.executable_path), "-v"],
                capture_output=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            )
            
            gpu_info = {
                'gpu_count': 1,  # Par défaut
                'gpu_names': ['GPU 0'],
                'vulkan_available': False
            }
            
            if result.returncode == 0:
                output = result.stdout.decode() + result.stderr.decode()
                
                # Analyse basique de la sortie
                if "vulkan" in output.lower():
                    gpu_info['vulkan_available'] = True
                
                # Comptage des GPU (heuristique)
                gpu_lines = [line for line in output.split('\n') if 'gpu' in line.lower()]
                if gpu_lines:
                    gpu_info['gpu_count'] = len(gpu_lines)
                    gpu_info['gpu_names'] = [f"GPU {i}" for i in range(len(gpu_lines))]
            
            self._gpu_info = gpu_info
            self.logger.info(f"Info GPU: {gpu_info}")
            
            return gpu_info
            
        except Exception as e:
            self.logger.error(f"Erreur récupération info GPU: {e}")
            return {
                'gpu_count': 1,
                'gpu_names': ['GPU 0'],
                'vulkan_available': False
            }
    
    async def upscale_batch(self, input_dir: Path, output_dir: Path, 
                           config: Optional[Dict[str, Any]] = None,
                           progress_callback=None) -> bool:
        """
        Upscale un lot d'images
        
        Args:
            input_dir: Dossier contenant les images à upscaler
            output_dir: Dossier de sortie
            config: Configuration d'upscaling
            progress_callback: Fonction de callback pour progression
            
        Returns:
            True si succès, False sinon
        """
        try:
            if not self.is_available():
                raise Exception("Real-ESRGAN n'est pas disponible")
            
            # Configuration effective
            effective_config = self.default_config.copy()
            if config:
                effective_config.update(config)
            
            # Vérification des dossiers
            if not input_dir.exists():
                raise Exception(f"Dossier d'entrée non trouvé: {input_dir}")
            
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Construction de la commande
            cmd = [
                str(self.executable_path),
                "-i", str(input_dir),
                "-o", str(output_dir),
                "-n", effective_config['model'],
                "-s", str(effective_config['scale']),
                "-t", str(effective_config['tile_size']),
                "-g", str(effective_config['gpu_id'])
            ]
            
            # Options additionnelles
            if effective_config.get('denoise', False):
                cmd.extend(["-x"])  # Option de débruitage si supportée
            
            self.logger.info(f"Commande Real-ESRGAN: {' '.join(cmd)}")
            
            # Exécution asynchrone
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            )
            
            # Suivi de progression si callback fourni
            if progress_callback:
                await self._monitor_progress(process, input_dir, output_dir, progress_callback)
            
            # Attente de fin
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore')
                raise Exception(f"Erreur Real-ESRGAN (code {process.returncode}): {error_msg}")
            
            # Vérification des résultats
            input_files = list(input_dir.glob("*.png")) + list(input_dir.glob("*.jpg"))
            output_files = list(output_dir.glob("*.png")) + list(output_dir.glob("*.jpg"))
            
            if len(output_files) != len(input_files):
                self.logger.warning(f"Nombre de fichiers différent: {len(output_files)}/{len(input_files)}")
            
            self.logger.info(f"Upscaling terminé: {len(output_files)} fichiers générés")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur upscaling: {e}")
            return False
    
    async def _monitor_progress(self, process, input_dir: Path, output_dir: Path, 
                              progress_callback):
        """Surveille la progression du traitement"""
        try:
            input_count = len(list(input_dir.glob("*.png")) + list(input_dir.glob("*.jpg")))
            
            while process.returncode is None:
                await asyncio.sleep(1)
                
                # Comptage des fichiers de sortie
                output_count = len(list(output_dir.glob("*.png")) + list(output_dir.glob("*.jpg")))
                
                if input_count > 0:
                    progress = (output_count / input_count) * 100
                    progress_callback(progress, output_count)
                
        except Exception as e:
            self.logger.error(f"Erreur monitoring progression: {e}")
    
    def upscale_single_image(self, input_path: Path, output_path: Path,
                           config: Optional[Dict[str, Any]] = None) -> bool:
        """
        Upscale une seule image (synchrone)
        
        Args:
            input_path: Chemin de l'image d'entrée
            output_path: Chemin de l'image de sortie
            config: Configuration d'upscaling
            
        Returns:
            True si succès, False sinon
        """
        try:
            if not self.is_available():
                raise Exception("Real-ESRGAN n'est pas disponible")
            
            if not input_path.exists():
                raise Exception(f"Fichier d'entrée non trouvé: {input_path}")
            
            # Configuration effective
            effective_config = self.default_config.copy()
            if config:
                effective_config.update(config)
            
            # Création du dossier de sortie
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Construction de la commande
            cmd = [
                str(self.executable_path),
                "-i", str(input_path),
                "-o", str(output_path),
                "-n", effective_config['model'],
                "-s", str(effective_config['scale']),
                "-t", str(effective_config['tile_size']),
                "-g", str(effective_config['gpu_id'])
            ]
            
            self.logger.info(f"Upscaling image: {input_path.name}")
            
            # Exécution
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=300,  # 5 minutes max par image
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            )
            
            if result.returncode != 0:
                error_msg = result.stderr.decode('utf-8', errors='ignore')
                raise Exception(f"Erreur Real-ESRGAN: {error_msg}")
            
            if not output_path.exists():
                raise Exception("Fichier de sortie non créé")
            
            self.logger.info(f"Image upscalée avec succès: {output_path.name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur upscaling image {input_path}: {e}")
            return False
    
    def get_recommended_tile_size(self, image_resolution: tuple) -> int:
        """
        Recommande une taille de tuile basée sur la résolution
        
        Args:
            image_resolution: (width, height)
            
        Returns:
            Taille de tuile recommandée
        """
        width, height = image_resolution
        total_pixels = width * height
        
        # Heuristiques basées sur la résolution
        if total_pixels > 2073600:  # > 1920x1080
            return 128
        elif total_pixels > 921600:  # > 1280x720
            return 256
        else:
            return 512
    
    def estimate_processing_time(self, image_count: int, 
                               average_resolution: tuple) -> float:
        """
        Estime le temps de traitement
        
        Args:
            image_count: Nombre d'images
            average_resolution: Résolution moyenne (width, height)
            
        Returns:
            Temps estimé en secondes
        """
        width, height = average_resolution
        
        # Estimation basée sur des benchmarks empiriques
        # Base: ~2 secondes par image 1920x1080
        base_pixels = 1920 * 1080
        image_pixels = width * height
        
        time_per_image = 2.0 * (image_pixels / base_pixels)
        
        # Facteur GPU (si pas de Vulkan, plus lent)
        gpu_info = self.get_gpu_info()
        if not gpu_info.get('vulkan_available', False):
            time_per_image *= 1.5
        
        return image_count * time_per_image
    
    def cleanup_temp_files(self, directory: Path):
        """Nettoie les fichiers temporaires"""
        try:
            temp_patterns = ["*.tmp", "*.temp", "*.bak"]
            
            for pattern in temp_patterns:
                for temp_file in directory.glob(pattern):
                    temp_file.unlink()
                    self.logger.debug(f"Fichier temporaire supprimé: {temp_file}")
                    
        except Exception as e:
            self.logger.error(f"Erreur nettoyage fichiers temporaires: {e}")