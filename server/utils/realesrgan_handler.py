# UpscalingByNetwork/server/utils/realesrgan_handler.py
"""
Gestionnaire Real-ESRGAN pour l'upscaling d'images
Détecte automatiquement l'exécutable et gère les différents modèles
"""

import asyncio
import logging
import subprocess
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import shutil
import re

class RealESRGANHandler:
    """Gestionnaire des opérations Real-ESRGAN"""
    
    def __init__(self, realesrgan_path: Path = None, models_dir: Path = None):
        self.logger = logging.getLogger(__name__)
        
        # Détection automatique de l'exécutable
        self.realesrgan_path = self._find_realesrgan_executable(realesrgan_path)
        self.models_dir = self._find_models_directory(models_dir)
        
        # Configuration par défaut
        self.default_model = "realesr-animevideov3"
        self.default_scale = 4
        self.default_tile_size = 0  # Auto-détection
        self.gpu_id = 0  # GPU par défaut
        
        # Modèles supportés avec leurs caractéristiques
        self.supported_models = {
            'realesr-animevideov3': {
                'name': 'Real-ESRGAN Anime Video v3',
                'scales': [2, 3, 4],
                'best_for': 'anime, animation, cartoon',
                'tile_size_recommend': 128
            },
            'realesrgan-x4plus': {
                'name': 'Real-ESRGAN x4 Plus',
                'scales': [4],
                'best_for': 'general images, photography',
                'tile_size_recommend': 200
            },
            'realesrgan-x4plus-anime': {
                'name': 'Real-ESRGAN x4 Plus Anime',
                'scales': [4],
                'best_for': 'anime, illustration',
                'tile_size_recommend': 128
            },
            'RealESRNet_x4plus': {
                'name': 'RealESRNet x4 Plus',
                'scales': [4],
                'best_for': 'conservative upscaling',
                'tile_size_recommend': 400
            }
        }
        
        # Statistiques et monitoring
        self.processing_stats = {
            'total_images': 0,
            'total_time': 0.0,
            'avg_time_per_image': 0.0,
            'last_error': None
        }
        
        # Vérification de la disponibilité
        if not self._verify_realesrgan():
            raise RuntimeError("Real-ESRGAN non disponible ou non fonctionnel")
        
        self.logger.info(f"Real-ESRGAN initialisé: {self.realesrgan_path}")
        self._log_system_info()
    
    def _find_realesrgan_executable(self, custom_path: Path = None) -> Path:
        """Trouve l'exécutable Real-ESRGAN"""
        if custom_path and custom_path.exists():
            return custom_path
        
        # Noms possibles selon la plateforme
        executable_names = [
            "realesrgan-ncnn-vulkan.exe",  # Windows
            "realesrgan-ncnn-vulkan",      # Linux
            "realesrgan-ncnn-vulkan-x64.exe"  # Windows alternative
        ]
        
        # Chercher dans le dossier du projet
        search_dirs = [
            Path("realesrgan-ncnn-vulkan"),
            Path("../realesrgan-ncnn-vulkan"),
            Path("tools/realesrgan-ncnn-vulkan"),
            Path.cwd()
        ]
        
        for search_dir in search_dirs:
            for exe_name in executable_names:
                exe_path = search_dir / exe_name
                if exe_path.exists():
                    return exe_path.resolve()
        
        # Chercher dans le PATH système
        for exe_name in executable_names:
            system_path = shutil.which(exe_name)
            if system_path:
                return Path(system_path)
        
        # Fallback - sera vérifié plus tard
        return Path("realesrgan-ncnn-vulkan.exe")
    
    def _find_models_directory(self, custom_dir: Path = None) -> Path:
        """Trouve le dossier des modèles"""
        if custom_dir and custom_dir.exists():
            return custom_dir
        
        # Le dossier des modèles est généralement à côté de l'exécutable
        exe_dir = self.realesrgan_path.parent
        models_candidates = [
            exe_dir / "models",
            exe_dir,  # Parfois les modèles sont dans le même dossier
            exe_dir.parent / "models"
        ]
        
        for models_dir in models_candidates:
            if models_dir.exists() and any(models_dir.glob("*.bin")):
                return models_dir
        
        # Fallback
        return exe_dir / "models"
    
    def _verify_realesrgan(self) -> bool:
        """Vérifie que Real-ESRGAN fonctionne"""
        try:
            result = subprocess.run(
                [str(self.realesrgan_path)],
                capture_output=True,
                text=True,
                timeout=10
            )
            # Real-ESRGAN retourne une erreur si pas d'arguments, mais ça prouve qu'il fonctionne
            return "Usage:" in result.stderr or result.returncode == -1
        except Exception as e:
            self.logger.error(f"Erreur vérification Real-ESRGAN: {e}")
            return False
    
    def _log_system_info(self):
        """Log les informations système pour le debugging"""
        try:
            # Vérifier Vulkan
            vulkan_info = self._check_vulkan_support()
            self.logger.info(f"Support Vulkan: {vulkan_info}")
            
            # Lister les modèles disponibles
            available_models = self._list_available_models()
            self.logger.info(f"Modèles disponibles: {list(available_models.keys())}")
            
        except Exception as e:
            self.logger.warning(f"Impossible d'obtenir les infos système: {e}")
    
    def _check_vulkan_support(self) -> Dict[str, Any]:
        """Vérifie le support Vulkan"""
        try:
            # Tenter d'exécuter avec une commande qui liste les GPUs
            result = subprocess.run(
                [str(self.realesrgan_path), "-g", "-1"],  # Liste les GPUs
                capture_output=True,
                text=True,
                timeout=5
            )
            
            gpu_count = 0
            gpu_info = []
            
            for line in result.stderr.split('\n'):
                if 'gpu' in line.lower() and 'device' in line.lower():
                    gpu_count += 1
                    gpu_info.append(line.strip())
            
            return {
                'supported': gpu_count > 0,
                'gpu_count': gpu_count,
                'gpu_info': gpu_info
            }
            
        except Exception:
            return {'supported': False, 'gpu_count': 0, 'gpu_info': []}
    
    def _list_available_models(self) -> Dict[str, Path]:
        """Liste les modèles disponibles"""
        available = {}
        
        if not self.models_dir.exists():
            return available
        
        # Chercher les fichiers de modèles (.bin et .param)
        for model_name in self.supported_models.keys():
            bin_file = self.models_dir / f"{model_name}.bin"
            param_file = self.models_dir / f"{model_name}.param"
            
            if bin_file.exists() and param_file.exists():
                available[model_name] = bin_file
        
        return available
    
    async def upscale_image(self, input_path: Path, output_path: Path,
                          model: str = None, scale: int = None, 
                          tile_size: int = None) -> bool:
        """Upscale une image individuelle"""
        start_time = time.time()
        
        try:
            # Paramètres par défaut
            model = model or self.default_model
            scale = scale or self.default_scale
            tile_size = tile_size or self._get_optimal_tile_size(model)
            
            # Validation
            if not input_path.exists():
                raise FileNotFoundError(f"Image d'entrée non trouvée: {input_path}")
            
            if model not in self.supported_models:
                raise ValueError(f"Modèle non supporté: {model}")
            
            if scale not in self.supported_models[model]['scales']:
                raise ValueError(f"Échelle {scale} non supportée pour le modèle {model}")
            
            # Créer le dossier de sortie
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Construction de la commande
            cmd = [
                str(self.realesrgan_path),
                "-i", str(input_path),
                "-o", str(output_path),
                "-n", model,
                "-s", str(scale),
                "-g", str(self.gpu_id)
            ]
            
            # Ajout de la taille de tuile si spécifiée
            if tile_size > 0:
                cmd.extend(["-t", str(tile_size)])
            
            # Ajout du format de sortie
            cmd.extend(["-f", "png"])
            
            self.logger.debug(f"Commande upscaling: {' '.join(cmd)}")
            
            # Exécution asynchrone
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            # Vérification du résultat
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Erreur inconnue"
                raise RuntimeError(f"Erreur Real-ESRGAN: {error_msg}")
            
            # Vérification du fichier de sortie
            if not output_path.exists():
                raise RuntimeError("Fichier de sortie non créé")
            
            # Statistiques
            processing_time = time.time() - start_time
            self._update_stats(processing_time, True)
            
            self.logger.debug(f"Image upscalée en {processing_time:.2f}s: {input_path.name}")
            
            return True
            
        except Exception as e:
            processing_time = time.time() - start_time
            self._update_stats(processing_time, False)
            self.processing_stats['last_error'] = str(e)
            
            self.logger.error(f"Erreur upscaling {input_path}: {e}")
            return False
    
    async def upscale_batch(self, input_dir: Path, output_dir: Path,
                          model: str = None, scale: int = None,
                          tile_size: int = None, 
                          progress_callback=None) -> Dict[str, Any]:
        """Upscale un lot d'images"""
        start_time = time.time()
        
        try:
            # Validation des dossiers
            if not input_dir.exists():
                raise FileNotFoundError(f"Dossier d'entrée non trouvé: {input_dir}")
            
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Recherche des images
            image_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.webp'}
            image_files = []
            
            for ext in image_extensions:
                image_files.extend(input_dir.glob(f"*{ext}"))
                image_files.extend(input_dir.glob(f"*{ext.upper()}"))
            
            image_files = sorted(set(image_files))
            
            if not image_files:
                raise ValueError(f"Aucune image trouvée dans {input_dir}")
            
            self.logger.info(f"Upscaling de {len(image_files)} images")
            
            # Traitement des images
            results = {
                'total_images': len(image_files),
                'processed_images': 0,
                'failed_images': 0,
                'processing_time': 0,
                'failed_files': [],
                'success': False
            }
            
            for i, image_path in enumerate(image_files):
                try:
                    # Nom de fichier de sortie
                    output_path = output_dir / f"{image_path.stem}_upscaled.png"
                    
                    # Traitement
                    success = await self.upscale_image(
                        image_path, output_path, model, scale, tile_size
                    )
                    
                    if success:
                        results['processed_images'] += 1
                    else:
                        results['failed_images'] += 1
                        results['failed_files'].append(str(image_path))
                    
                    # Callback de progression
                    if progress_callback:
                        progress = (i + 1) / len(image_files)
                        await progress_callback(progress, i + 1, len(image_files))
                    
                except Exception as e:
                    self.logger.error(f"Erreur traitement {image_path}: {e}")
                    results['failed_images'] += 1
                    results['failed_files'].append(str(image_path))
            
            # Finalisation des résultats
            results['processing_time'] = time.time() - start_time
            results['success'] = results['failed_images'] == 0
            
            self.logger.info(
                f"Lot terminé: {results['processed_images']}/{results['total_images']} "
                f"réussies en {results['processing_time']:.1f}s"
            )
            
            return results
            
        except Exception as e:
            self.logger.error(f"Erreur traitement lot {input_dir}: {e}")
            return {
                'total_images': 0,
                'processed_images': 0,
                'failed_images': 0,
                'processing_time': time.time() - start_time,
                'failed_files': [],
                'success': False,
                'error': str(e)
            }
    
    def _get_optimal_tile_size(self, model: str) -> int:
        """Détermine la taille de tuile optimale selon le modèle et le GPU"""
        if self.default_tile_size > 0:
            return self.default_tile_size
        
        # Taille recommandée par modèle
        base_size = self.supported_models.get(model, {}).get('tile_size_recommend', 200)
        
        # Ajustement selon la mémoire GPU (approximation)
        try:
            vulkan_info = self._check_vulkan_support()
            if vulkan_info['gpu_count'] > 0:
                # GPU disponible - peut utiliser des tuiles plus grandes
                return min(base_size * 2, 512)
            else:
                # CPU uniquement - tuiles plus petites
                return max(base_size // 2, 64)
        except:
            return base_size
    
    def _update_stats(self, processing_time: float, success: bool):
        """Met à jour les statistiques de traitement"""
        if success:
            self.processing_stats['total_images'] += 1
            self.processing_stats['total_time'] += processing_time
            
            if self.processing_stats['total_images'] > 0:
                self.processing_stats['avg_time_per_image'] = (
                    self.processing_stats['total_time'] / 
                    self.processing_stats['total_images']
                )
    
    async def test_model_performance(self, model: str, test_image_path: Path = None) -> Dict[str, Any]:
        """Test la performance d'un modèle"""
        try:
            # Créer une image de test si pas fournie
            if not test_image_path or not test_image_path.exists():
                test_image_path = await self._create_test_image()
            
            temp_output = Path("temp_test_output.png")
            
            # Test avec différentes tailles de tuiles
            tile_sizes = [0, 128, 256, 512]  # 0 = auto
            results = {}
            
            for tile_size in tile_sizes:
                start_time = time.time()
                
                success = await self.upscale_image(
                    test_image_path, temp_output, model, 2, tile_size
                )
                
                processing_time = time.time() - start_time
                
                results[f"tile_{tile_size}"] = {
                    'success': success,
                    'time': processing_time,
                    'tile_size': tile_size
                }
                
                # Nettoyage
                if temp_output.exists():
                    temp_output.unlink()
            
            # Nettoyage de l'image de test si créée
            if test_image_path.name.startswith("temp_test_"):
                test_image_path.unlink()
            
            return results
            
        except Exception as e:
            self.logger.error(f"Erreur test performance {model}: {e}")
            return {'error': str(e)}
    
    async def _create_test_image(self) -> Path:
        """Crée une image de test simple"""
        try:
            from PIL import Image, ImageDraw
            
            # Créer une image de test 256x256
            img = Image.new('RGB', (256, 256), color='white')
            draw = ImageDraw.Draw(img)
            
            # Dessiner quelques formes pour le test
            draw.rectangle([50, 50, 200, 200], fill='blue', outline='black', width=2)
            draw.ellipse([100, 100, 150, 150], fill='red')
            
            test_path = Path("temp_test_image.png")
            img.save(test_path)
            
            return test_path
            
        except ImportError:
            # Fallback si PIL n'est pas disponible - créer un fichier factice
            test_path = Path("temp_test_image.txt")
            test_path.write_text("Test image placeholder")
            return test_path
    
    def get_model_info(self, model: str) -> Dict[str, Any]:
        """Retourne les informations sur un modèle"""
        if model not in self.supported_models:
            return {'error': f'Modèle {model} non supporté'}
        
        info = self.supported_models[model].copy()
        
        # Vérifier la disponibilité
        available_models = self._list_available_models()
        info['available'] = model in available_models
        
        if info['available']:
            model_path = available_models[model]
            info['model_path'] = str(model_path)
            info['model_size'] = model_path.stat().st_size
        
        return info
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de traitement"""
        stats = self.processing_stats.copy()
        
        # Ajout d'informations système
        stats.update({
            'executable_path': str(self.realesrgan_path),
            'models_dir': str(self.models_dir),
            'vulkan_support': self._check_vulkan_support(),
            'available_models': list(self._list_available_models().keys())
        })
        
        return stats
    
    def reset_stats(self):
        """Remet à zéro les statistiques"""
        self.processing_stats = {
            'total_images': 0,
            'total_time': 0.0,
            'avg_time_per_image': 0.0,
            'last_error': None
        }
        self.logger.info("Statistiques réinitialisées")
    
    def estimate_batch_time(self, image_count: int, model: str = None) -> Dict[str, float]:
        """Estime le temps de traitement d'un lot"""
        model = model or self.default_model
        
        # Temps de base selon le modèle et les stats actuelles
        if self.processing_stats['avg_time_per_image'] > 0:
            avg_time = self.processing_stats['avg_time_per_image']
        else:
            # Estimations par défaut selon le modèle
            model_base_times = {
                'realesr-animevideov3': 2.5,
                'realesrgan-x4plus': 3.0,
                'realesrgan-x4plus-anime': 2.8,
                'RealESRNet_x4plus': 2.0
            }
            avg_time = model_base_times.get(model, 2.5)
        
        # Calculs
        total_time = image_count * avg_time
        overhead = max(10, total_time * 0.1)  # 10% d'overhead minimum
        
        return {
            'estimated_seconds': total_time + overhead,
            'estimated_minutes': (total_time + overhead) / 60,
            'avg_time_per_image': avg_time,
            'overhead_seconds': overhead
        }
    
    def validate_input_image(self, image_path: Path) -> Tuple[bool, str]:
        """Valide une image d'entrée"""
        if not image_path.exists():
            return False, "Fichier inexistant"
        
        # Vérifier l'extension
        valid_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.webp'}
        if image_path.suffix.lower() not in valid_extensions:
            return False, f"Format non supporté: {image_path.suffix}"
        
        # Vérifier la taille du fichier
        file_size = image_path.stat().st_size
        if file_size == 0:
            return False, "Fichier vide"
        
        if file_size > 100 * 1024 * 1024:  # 100MB
            return False, "Fichier trop volumineux (>100MB)"
        
        try:
            # Validation basique avec PIL si disponible
            from PIL import Image
            with Image.open(image_path) as img:
                width, height = img.size
                if width * height > 50000000:  # ~7K x 7K pixels
                    return False, "Image trop grande (>50MP)"
                if width < 16 or height < 16:
                    return False, "Image trop petite (<16px)"
        except ImportError:
            # PIL non disponible, validation basique uniquement
            pass
        except Exception as e:
            return False, f"Image corrompue: {e}"
        
        return True, "Image valide"