# server/core/optimized_real_esrgan.py
"""
Module optimisé pour Real-ESRGAN avec détection automatique du matériel
Version corrigée avec gestion d'erreur robuste
"""

import os
import subprocess
import asyncio
import time
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import logging
import sys

from dataclasses import dataclass, field

@dataclass
class ProcessingResult:
    """Résultat d'un traitement Real-ESRGAN"""
    success: bool
    processing_time: float
    frames_processed: int
    error_message: str = ""
    gpu_utilization: Optional[float] = None
    memory_usage_mb: Optional[int] = None
    performance_metrics: Dict[str, Any] = field(default_factory=dict)

class OptimizedRealESRGAN:
    """Gestionnaire optimisé pour Real-ESRGAN avec auto-configuration"""
    
    def __init__(self):
        self.logger = self._setup_logger()
        self.system_info: Optional[Any] = None
        self.optimal_config: Dict[str, Any] = {}
        self.performance_history: List[Dict] = []
        
        # Configuration par défaut de secours
        self.fallback_config = {
            'model': 'RealESRGAN_x4plus',
            'scale': 4,
            'tile_size': 256,
            'gpu_id': 0,
            'threads': '1:2:2',
            'use_fp16': False,
            'tta_mode': False
        }
        
        # Chemins des exécutables
        self.executable_path = self._find_realesrgan_executable()
        
        # Initialisation sécurisée du système
        self._initialize_system_safe()
    
    def _setup_logger(self):
        """Configure le logger de manière sécurisée"""
        logger = logging.getLogger(__name__)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger
    
    def _find_realesrgan_executable(self) -> Optional[str]:
        """Trouve l'exécutable Real-ESRGAN en utilisant le détecteur"""
        try:
            # Utilisation du détecteur d'exécutables
            from utils.executable_detector import executable_detector
            return executable_detector.find_realesrgan()
            
        except ImportError:
            self.logger.warning("Détecteur d'exécutables non disponible, recherche manuelle...")
            return self._manual_realesrgan_search()
    
    def _manual_realesrgan_search(self) -> Optional[str]:
        """Recherche manuelle de Real-ESRGAN en cas d'absence du détecteur"""
        possible_names = [
            "realesrgan-ncnn-vulkan.exe",
            "realesrgan-ncnn-vulkan",
        ]
        
        # Chemins de recherche
        project_root = Path(__file__).parent.parent
        possible_paths = [
            project_root / "realesrgan-ncnn-vulkan",
            project_root / "realesrgan-ncnn-vulkan" / "Windows",
            project_root / "dependencies",
            Path.cwd(),
        ]
        
        for path in possible_paths:
            for name in possible_names:
                full_path = path / name
                if full_path.exists() and full_path.is_file():
                    self.logger.info(f"✅ Real-ESRGAN trouvé: {full_path}")
                    return str(full_path)
        
        self.logger.warning("⚠️ Real-ESRGAN exécutable non trouvé dans les chemins standards")
        return None

    def _initialize_system_safe(self):
        """Initialise la détection système de manière sécurisée"""
        try:
            print("🔍 Début de la détection système...")
            self._detect_hardware_safe()
            self._generate_optimal_config()
            print("✅ Système détecté et configuré avec succès")
            
        except Exception as e:
            print(f"⚠️ Erreur lors de l'initialisation système: {e}")
            print("🔄 Utilisation de la configuration de secours...")
            self._use_fallback_config()
    
    def _detect_hardware_safe(self):
        """Détection matérielle sécurisée"""
        try:
            # Tentative d'import des modules de détection hardware
            try:
                from utils.hardware_detector import hardware_detector
                print("🔍 Détection des GPUs NVIDIA...")
                self.system_info = hardware_detector.detect_system()
                print(f"📊 GPUs détectés: {len(self.system_info.gpus) if self.system_info else 0}")
                
            except ImportError as e:
                print(f"⚠️ Module hardware_detector non disponible: {e}")
                print("🔄 Utilisation détection basique...")
                self._basic_hardware_detection()
                
        except Exception as e:
            print(f"❌ Erreur détection hardware: {e}")
            self.system_info = None
    
    def _basic_hardware_detection(self):
        """Détection matérielle basique sans dépendances externes"""
        try:
            # Détection basique du système
            import platform
            system_type = "laptop" if self._is_laptop() else "desktop"
            
            # Configuration basique basée sur le type de système
            basic_info = {
                'gpus': [],
                'cpu_cores': os.cpu_count() or 4,
                'system_type': system_type,
                'total_ram_gb': 8  # Estimation conservative
            }
            
            print(f"💻 Système détecté: {system_type}, {basic_info['cpu_cores']} cœurs")
            self.system_info = basic_info
            
        except Exception as e:
            print(f"❌ Erreur détection basique: {e}")
            self.system_info = None
    
    def _is_laptop(self) -> bool:
        """Détecte si le système est un laptop"""
        try:
            # Méthodes de détection laptop
            import psutil
            
            # Vérification de la batterie
            if hasattr(psutil, 'sensors_battery'):
                battery = psutil.sensors_battery()
                if battery is not None:
                    return True
            
            # Vérification des adaptateurs AC
            if hasattr(psutil, 'sensors_fans'):
                fans = psutil.sensors_fans()
                if fans and len(fans) < 3:  # Laptops ont généralement moins de ventilateurs
                    return True
            
        except:
            pass
        
        return False  # Par défaut, considérer comme desktop
    
    def _generate_optimal_config(self):
        """Génère la configuration optimale basée sur le hardware détecté"""
        try:
            print("⚙️ Génération de la configuration optimale...")
            
            if not self.system_info:
                print("⚠️ Informations système non disponibles, utilisation config par défaut")
                self.optimal_config = self.fallback_config.copy()
                return
            
            # Configuration basée sur le type de système
            if isinstance(self.system_info, dict):
                system_type = self.system_info.get('system_type', 'desktop')
                cpu_cores = self.system_info.get('cpu_cores', 4)
                
                if system_type == 'laptop':
                    # Configuration conservative pour laptop
                    self.optimal_config = {
                        'model': 'RealESRGAN_x4plus',
                        'tile_size': 256,
                        'gpu_id': 0,
                        'threads': f'1:{min(2, cpu_cores//2)}:1',
                        'use_fp16': True,
                        'tta_mode': False
                    }
                else:
                    # Configuration plus agressive pour desktop
                    self.optimal_config = {
                        'model': 'RealESRGAN_x4plus',
                        'tile_size': 512,
                        'gpu_id': 0,
                        'threads': f'2:{min(4, cpu_cores//2)}:2',
                        'use_fp16': True,
                        'tta_mode': False
                    }
            else:
                # Utilisation de l'ancienne interface si disponible
                self.optimal_config = self.fallback_config.copy()
            
            print(f"🎯 Configuration générée: {self.optimal_config}")
            
        except Exception as e:
            print(f"❌ Erreur génération config: {e}")
            self._use_fallback_config()
    
    def _use_fallback_config(self):
        """Utilise la configuration de secours"""
        try:
            print("🔄 Application de la configuration de secours...")
            
            # Chargement sécurisé de la configuration serveur
            config_value = None
            try:
                # Tentative d'import de la configuration
                from utils.config import config as server_config
                config_value = server_config
                
            except ImportError:
                print("⚠️ Module config non disponible")
            except Exception as e:
                print(f"⚠️ Erreur chargement config: {e}")
            
            # Configuration de base
            if config_value:
                # Utilisation des méthodes disponibles
                try:
                    if hasattr(config_value, 'get'):
                        # Nouvelle API
                        model = config_value.get('processing.realesrgan_model', 'RealESRGAN_x4plus')
                        tile_size = config_value.get('processing.tile_size', 256)
                    elif hasattr(config_value, 'REALESRGAN_MODEL'):
                        # Ancienne API
                        model = config_value.REALESRGAN_MODEL
                        tile_size = getattr(config_value, 'TILE_SIZE', 256)
                    else:
                        # Configuration par défaut si aucune API disponible
                        model = 'RealESRGAN_x4plus'
                        tile_size = 256
                        
                except Exception as e:
                    print(f"⚠️ Erreur accès config: {e}")
                    model = 'RealESRGAN_x4plus'
                    tile_size = 256
            else:
                model = 'RealESRGAN_x4plus'
                tile_size = 256
            
            # Configuration finale
            self.optimal_config = {
                'model': model,
                'scale': 4,
                'tile_size': tile_size,
                'gpu_id': 0,
                'threads': '1:2:1',
                'use_fp16': True,
                'tta_mode': False
            }
            
            print(f"✅ Configuration de secours appliquée: {self.optimal_config}")
            
        except Exception as e:
            print(f"❌ Erreur configuration de secours: {e}")
            # Configuration minimale en dernier recours
            self.optimal_config = self.fallback_config.copy()
    
    def get_optimal_config(self) -> Dict[str, Any]:
        """Retourne la configuration optimale actuelle"""
        return self.optimal_config.copy()
    
    def is_available(self) -> bool:
        """Vérifie si Real-ESRGAN est disponible"""
        return self.executable_path is not None
    
    def get_executable_path(self) -> Optional[str]:
        """Retourne le chemin vers l'exécutable"""
        return self.executable_path
    
    async def process_batch(self, input_path: str, output_path: str, batch_id: str = None) -> ProcessingResult:
        """Traite un lot d'images avec Real-ESRGAN"""
        if not self.is_available():
            return ProcessingResult(
                success=False,
                processing_time=0,
                frames_processed=0,
                error_message="Real-ESRGAN exécutable non disponible"
            )
        
        start_time = time.time()
        frames_processed = 0
        
        try:
            # Préparation des chemins
            input_dir = Path(input_path)
            output_dir = Path(output_path)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Comptage des images d'entrée
            image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp'}
            input_images = [f for f in input_dir.glob('*') if f.suffix.lower() in image_extensions]
            total_images = len(input_images)
            
            if total_images == 0:
                return ProcessingResult(
                    success=False,
                    processing_time=0,
                    frames_processed=0,
                    error_message="Aucune image trouvée dans le dossier d'entrée"
                )
            
            # Construction de la commande Real-ESRGAN
            cmd = [self.executable_path]
            cmd.extend(["-i", str(input_dir)])
            cmd.extend(["-o", str(output_dir)])
            cmd.extend(["-n", self.optimal_config.get('model', 'RealESRGAN_x4plus')])
            cmd.extend(["-f", "png"])
            cmd.extend(["-g", str(self.optimal_config.get('gpu_id', 0))])
            cmd.extend(["-t", str(self.optimal_config.get('tile_size', 256))])
            cmd.extend(["-j", self.optimal_config.get('threads', '1:2:1')])
            
            self.logger.info(f"🚀 Démarrage traitement lot {batch_id or 'unknown'}: {total_images} images")
            self.logger.debug(f"Commande: {' '.join(cmd)}")
            
            # Exécution avec timeout
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=Path(self.executable_path).parent
            )
            
            # Attente avec timeout de 30 minutes
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), 
                    timeout=1800  # 30 minutes
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ProcessingResult(
                    success=False,
                    processing_time=time.time() - start_time,
                    frames_processed=0,
                    error_message="Timeout: traitement trop long (>30min)"
                )
            
            # Vérification du code de retour
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore') if stderr else "Erreur inconnue"
                return ProcessingResult(
                    success=False,
                    processing_time=time.time() - start_time,
                    frames_processed=0,
                    error_message=f"Erreur Real-ESRGAN (code {process.returncode}): {error_msg}"
                )
            
            # Vérification des images de sortie
            output_images = [f for f in output_dir.glob('*') if f.suffix.lower() in image_extensions]
            frames_processed = len(output_images)
            
            processing_time = time.time() - start_time
            
            # Enregistrement des performances
            self._record_performance({
                'batch_id': batch_id,
                'frames_processed': frames_processed,
                'processing_time': processing_time,
                'fps': frames_processed / processing_time if processing_time > 0 else 0,
                'config_used': self.optimal_config.copy()
            })
            
            success = frames_processed >= total_images * 0.8  # 80% de réussite minimum
            
            self.logger.info(f"✅ Traitement terminé: {frames_processed}/{total_images} images en {processing_time:.1f}s")
            
            return ProcessingResult(
                success=success,
                processing_time=processing_time,
                frames_processed=frames_processed,
                performance_metrics={
                    'fps': frames_processed / processing_time if processing_time > 0 else 0,
                    'total_images': total_images,
                    'success_rate': (frames_processed / total_images) * 100 if total_images > 0 else 0
                }
            )
            
        except Exception as e:
            error_msg = f"Erreur traitement batch: {str(e)}"
            self.logger.error(error_msg)
            
            return ProcessingResult(
                success=False,
                processing_time=time.time() - start_time,
                frames_processed=frames_processed,
                error_message=error_msg
            )
    
    def _record_performance(self, performance_data: Dict[str, Any]):
        """Enregistre les données de performance"""
        try:
            performance_data['timestamp'] = time.time()
            self.performance_history.append(performance_data)
            
            # Limiter l'historique à 100 entrées
            if len(self.performance_history) > 100:
                self.performance_history = self.performance_history[-100:]
                
        except Exception as e:
            self.logger.warning(f"Erreur enregistrement performance: {e}")
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de performance"""
        if not self.performance_history:
            return {
                'total_batches': 0,
                'average_fps': 0,
                'total_frames': 0,
                'total_time': 0
            }
        
        try:
            total_batches = len(self.performance_history)
            total_frames = sum(p.get('frames_processed', 0) for p in self.performance_history)
            total_time = sum(p.get('processing_time', 0) for p in self.performance_history)
            average_fps = sum(p.get('fps', 0) for p in self.performance_history) / total_batches
            
            return {
                'total_batches': total_batches,
                'average_fps': round(average_fps, 2),
                'total_frames': total_frames,
                'total_time': round(total_time, 1),
                'last_batch_fps': self.performance_history[-1].get('fps', 0) if self.performance_history else 0
            }
            
        except Exception as e:
            self.logger.warning(f"Erreur calcul statistiques: {e}")
            return {
                'total_batches': 0,
                'average_fps': 0,
                'total_frames': 0,
                'total_time': 0
            }
    
    def update_config(self, new_config: Dict[str, Any]):
        """Met à jour la configuration optimale"""
        try:
            self.optimal_config.update(new_config)
            self.logger.info(f"Configuration mise à jour: {self.optimal_config}")
        except Exception as e:
            self.logger.error(f"Erreur mise à jour config: {e}")
    
    def benchmark_configurations(self, test_frames: List[str]) -> Dict[str, Any]:
        """Effectue un benchmark des différentes configurations"""
        try:
            if not test_frames or len(test_frames) < 3:
                return {
                    'error': 'Pas assez d\'images de test pour le benchmark'
                }
            
            # Configurations de test
            test_configs = [
                # Configuration actuelle
                self.optimal_config.copy(),
                
                # Configuration conservative
                {**self.optimal_config, 'tile_size': 128, 'threads': '1:2:1'},
                
                # Configuration agressive (si possible)
                {**self.optimal_config, 'tile_size': 512, 'threads': '2:4:2'},
            ]
            
            results = []
            
            for i, test_config in enumerate(test_configs):
                self.logger.info(f"Test configuration {i+1}/{len(test_configs)}")
                
                # Sauvegarde config actuelle
                original_config = self.optimal_config.copy()
                self.optimal_config = test_config
                
                try:
                    # Estimation basée sur la configuration
                    estimated_fps = self._estimate_performance(test_config)
                    
                    results.append({
                        'config': test_config.copy(),
                        'estimated_fps': estimated_fps,
                        'tile_size': test_config.get('tile_size', 256),
                        'threads': test_config.get('threads', '1:2:1')
                    })
                    
                except Exception as e:
                    self.logger.error(f"Erreur benchmark config {i}: {e}")
                    
                finally:
                    # Restauration config
                    self.optimal_config = original_config
            
            # Sélection de la meilleure configuration
            if results:
                best_config = max(results, key=lambda r: r.get('estimated_fps', 0))
                
                return {
                    'best_config': best_config['config'],
                    'all_results': results,
                    'recommendation': f"Configuration optimale estimée: {best_config['estimated_fps']:.1f} FPS"
                }
            else:
                return {'error': 'Aucun résultat de benchmark disponible'}
                
        except Exception as e:
            self.logger.error(f"Erreur benchmark: {e}")
            return {'error': f'Erreur benchmark: {str(e)}'}
    
    def _estimate_performance(self, config: Dict[str, Any]) -> float:
        """Estime les performances d'une configuration"""
        try:
            # Facteurs de performance basés sur la configuration
            base_fps = 2.0  # FPS de base
            
            # Ajustement selon la taille des tuiles
            tile_size = config.get('tile_size', 256)
            if tile_size <= 128:
                tile_factor = 1.2  # Plus rapide avec petites tuiles
            elif tile_size <= 256:
                tile_factor = 1.0  # Performance standard
            elif tile_size <= 512:
                tile_factor = 0.8  # Plus lent avec grandes tuiles
            else:
                tile_factor = 0.6  # Très lent
            
            # Ajustement selon les threads
            threads_str = config.get('threads', '1:2:1')
            try:
                # Parse format "load:proc:save"
                load_threads, proc_threads, save_threads = map(int, threads_str.split(':'))
                thread_factor = min(1.5, 1.0 + (proc_threads - 1) * 0.1)
            except:
                thread_factor = 1.0
            
            # Ajustement selon le GPU
            gpu_factor = 1.5 if config.get('gpu_id', 0) >= 0 else 0.5
            
            # Calcul final
            estimated_fps = base_fps * tile_factor * thread_factor * gpu_factor
            
            return round(estimated_fps, 2)
            
        except Exception as e:
            self.logger.warning(f"Erreur estimation performance: {e}")
            return 1.0  # Valeur par défaut conservative

# Instance globale créée de manière sécurisée
try:
    optimized_realesrgan = OptimizedRealESRGAN()
    print("✅ OptimizedRealESRGAN initialisé avec succès")
except Exception as e:
    print(f"❌ Erreur initialisation OptimizedRealESRGAN: {e}")
    print("🔄 Création d'une instance de secours...")
    
    # Instance de secours minimale
    class FallbackRealESRGAN:
        def __init__(self):
            self.optimal_config = {
                'model': 'RealESRGAN_x4plus',
                'tile_size': 256,
                'gpu_id': 0,
                'threads': '1:2:1'
            }
            self.executable_path = None
        
        def is_available(self):
            return False
        
        def get_optimal_config(self):
            return self.optimal_config.copy()
    
    optimized_realesrgan = FallbackRealESRGAN()
    print("⚠️ Instance de secours créée")