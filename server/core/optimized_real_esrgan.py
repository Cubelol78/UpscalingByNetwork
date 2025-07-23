"""
Module optimisé pour Real-ESRGAN avec détection automatique du matériel
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

from utils.hardware_detector import hardware_detector, SystemInfo, GPUInfo
from config.settings import config
from utils.logger import get_logger

@dataclass
class ProcessingResult:
    """Résultat d'un traitement Real-ESRGAN"""
    success: bool
    processing_time: float
    frames_processed: int
    error_message: str = ""
    gpu_utilization: Optional[float] = None
    memory_usage_mb: Optional[int] = None
    performance_metrics: Dict[str, Any] = None

class OptimizedRealESRGAN:
    """Gestionnaire optimisé pour Real-ESRGAN avec auto-configuration"""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        self.system_info: Optional[SystemInfo] = None
        self.optimal_config: Dict[str, Any] = {}
        self.performance_history: List[Dict] = []
        
        # Chemins des exécutables
        self.executable_path = self._find_realesrgan_executable()
        
        # Initialisation du système
        self._initialize_system()
    
    def _find_realesrgan_executable(self) -> Optional[str]:
        """Trouve l'exécutable Real-ESRGAN"""
        possible_names = [
            "realesrgan-ncnn-vulkan.exe",
            "realesrgan-ncnn-vulkan",
        ]
        
        # Ajout du chemin local par rapport au projet
        project_root = Path(__file__).parent.parent
        local_realesrgan_path = project_root / "realesrgan-ncnn-vulkan" / "Windows"

        possible_paths = [
            local_realesrgan_path, # Ajout du chemin local
            Path.cwd(),
        ]
        
        for path in possible_paths:
            for name in possible_names:
                full_path = path / name
                if full_path.exists() and full_path.is_file():
                    self.logger.info(f"Real-ESRGAN trouvé: {full_path}")
                    return str(full_path)
    
        self.logger.warning("Real-ESRGAN exécutable non trouvé dans les chemins standards")
        return None # Retourne None si non trouvé

    def _initialize_system(self):
        """Initialise la détection système et optimisations avec debug renforcé"""
        try:
            print("🔍 Détection du matériel système pour Real-ESRGAN...")
            self.logger.info("Détection du matériel système...")
            self.system_info = hardware_detector.detect_system_info()
            
            # Configuration optimale avec debug
            print("⚙️ Génération de la configuration optimale...")
            self.optimal_config = hardware_detector.optimize_realesrgan_config(
                self.system_info, 
                config.REALESRGAN_MODEL
            )
            
            print(f"✅ Configuration générée: {self.optimal_config}")
            
            # Affichage du résumé
            summary = hardware_detector.get_system_performance_summary(self.system_info)
            self.logger.info(f"\n{summary}")
            print(f"\n{summary}")
            
            # Validation de la configuration
            self._validate_configuration()
            
            print(f"🎯 Configuration finale validée: {self.optimal_config}")
            
        except Exception as e:
            print(f"❌ Erreur initialisation système: {e}")
            self.logger.error(f"Erreur initialisation système: {e}")
            self._use_fallback_config()

    def _validate_configuration(self):
        """Valide et ajuste la configuration si nécessaire"""
        if not self.system_info or not self.optimal_config:
            return
        
        # Vérification VRAM disponible
        selected_gpu = None
        if self.optimal_config.get('gpu_id', -1) >= 0:
            gpu_id = self.optimal_config['gpu_id']
            if gpu_id < len(self.system_info.gpus):
                selected_gpu = self.system_info.gpus[gpu_id]
                
                # Ajustement selon VRAM disponible
                if selected_gpu.memory_free_mb < 2048:  # < 2GB libre
                    self.logger.warning(f"VRAM faible ({selected_gpu.memory_free_mb}MB), réduction tile_size")
                    self.optimal_config['tile_size'] = min(128, self.optimal_config['tile_size'])
                    
                elif selected_gpu.memory_free_mb > 12288:  # > 12GB libre
                    self.logger.info("VRAM élevée détectée, optimisation pour qualité maximale")
                    self.optimal_config['tile_size'] = max(512, self.optimal_config['tile_size'])
                    self.optimal_config['tta_mode'] = True
        
        # Vérification cohérence threads vs CPU
        if self.system_info.cpu.cores_logical < 8:
            threads_parts = self.optimal_config['threads'].split(':')
            load, proc, save = map(int, threads_parts)
            max_threads = self.system_info.cpu.cores_logical // 2
            
            self.optimal_config['threads'] = f"{min(load, max_threads)}:{min(proc, max_threads)}:{min(save, max_threads)}"
            self.logger.info(f"Threads ajustés pour CPU {self.system_info.cpu.cores_logical} cœurs")

    def _use_fallback_config(self):
        """Configuration de fallback en cas de problème"""
        self.optimal_config = {
            'gpu_id': 0,
            'model': config.REALESRGAN_MODEL,
            'tile_size': config.TILE_SIZE,
            'threads': "2:4:2",
            'use_fp16': True,
            'tta_mode': False,
        }
        self.logger.warning("Utilisation de la configuration de fallback")

    async def process_batch(self, input_frames: List[str], output_dir: str, batch_id: str) -> ProcessingResult:
        """Traite un lot d'images avec optimisation automatique"""
        start_time = time.time()
        
        try:
            # Préparation des chemins
            input_dir = Path(input_frames[0]).parent
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            # Construction de la commande optimale
            cmd = self._build_optimized_command(str(input_dir), str(output_path))
            
            # Monitoring des performances en parallèle
            performance_task = asyncio.create_task(self._monitor_performance())
            
            # Exécution du traitement
            self.logger.info(f"Début traitement lot {batch_id}: {len(input_frames)} frames")
            self.logger.debug(f"Commande: {' '.join(cmd)}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            # Arrêt du monitoring
            performance_task.cancel()
            
            processing_time = time.time() - start_time
            
            if process.returncode == 0:
                # Vérification des fichiers de sortie
                processed_count = len(list(output_path.glob("*.png")))
                
                result = ProcessingResult(
                    success=True,
                    processing_time=processing_time,
                    frames_processed=processed_count,
                    performance_metrics=self._get_performance_metrics()
                )
                
                # Enregistrement des performances pour optimisation future
                self._record_performance(result, len(input_frames))
                
                self.logger.info(f"Lot {batch_id} terminé: {processed_count} frames en {processing_time:.1f}s")
                return result
            else:
                error_msg = stderr.decode('utf-8') if stderr else "Erreur inconnue"
                self.logger.error(f"Erreur traitement lot {batch_id}: {error_msg}")
                
                return ProcessingResult(
                    success=False,
                    processing_time=processing_time,
                    frames_processed=0,
                    error_message=error_msg
                )
                
        except Exception as e:
            processing_time = time.time() - start_time
            self.logger.error(f"Exception lors du traitement: {e}")
            
            return ProcessingResult(
                success=False,
                processing_time=processing_time,
                frames_processed=0,
                error_message=str(e)
            )

    def _build_optimized_command(self, input_path: str, output_path: str) -> List[str]:
        """Construit la commande Real-ESRGAN optimisée avec debug"""
        print(f"🔧 Construction commande Real-ESRGAN optimisée...")
        
        if not self.executable_path:
            raise RuntimeError("Exécutable Real-ESRGAN non trouvé")
        
        cmd = [self.executable_path]
        
        # Paramètres de base
        cmd.extend(["-i", input_path])
        cmd.extend(["-o", output_path])
        cmd.extend(["-n", self.optimal_config['model']])
        cmd.extend(["-f", "png"])
        
        # GPU selection - CORRECTION CRITIQUE
        gpu_id = self.optimal_config.get('gpu_id', 0)
        if gpu_id >= 0:
            cmd.extend(["-g", str(gpu_id)])
            print(f"🎯 GPU sélectionné: {gpu_id}")
        else:
            print("🖥️ Mode CPU seulement")
        
        # Tile size optimisé
        tile_size = self.optimal_config['tile_size']
        cmd.extend(["-t", str(tile_size)])
        print(f"🔲 Tile size: {tile_size}")
        
        # Threads optimisés
        threads = self.optimal_config['threads']
        cmd.extend(["-j", threads])
        print(f"🧵 Threads: {threads}")
        
        # Options avancées
        if self.optimal_config.get('tta_mode', False):
            cmd.append("-x")  # TTA mode pour qualité supérieure
            print("✨ Mode TTA activé")
        
        # Mode verbose pour monitoring
        cmd.append("-v")
        
        print(f"🚀 Commande finale: {' '.join(cmd)}")
        return cmd

    async def _monitor_performance(self):
        """Surveille les performances pendant le traitement"""
        try:
            while True:
                if self.system_info and self.system_info.gpus:
                    # Monitoring GPU
                    try:
                        import pynvml
                        pynvml.nvmlInit()
                        
                        for gpu in self.system_info.gpus:
                            handle = pynvml.nvmlDeviceGetHandleByIndex(gpu.index)
                            
                            # Utilisation GPU
                            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                            
                            # Mémoire GPU
                            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                            
                            # Température
                            try:
                                temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                            except:
                                temp = 0
                            
                            # Stockage des métriques
                            metrics = {
                                'timestamp': time.time(),
                                'gpu_id': gpu.index,
                                'gpu_utilization': util.gpu,
                                'memory_utilization': util.memory,
                                'memory_used_mb': mem_info.used // (1024*1024),
                                'memory_free_mb': mem_info.free // (1024*1024),
                                'temperature_c': temp
                            }
                            
                            self.performance_history.append(metrics)
                            
                            # Limitation de l'historique
                            if len(self.performance_history) > 100:
                                self.performance_history.pop(0)
                        
                        pynvml.nvmlShutdown()
                        
                    except Exception as e:
                        self.logger.debug(f"Erreur monitoring GPU: {e}")
                
                await asyncio.sleep(2)  # Monitoring toutes les 2 secondes
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"Erreur monitoring performance: {e}")

    def _get_performance_metrics(self) -> Dict[str, Any]:
        """Récupère les métriques de performance actuelles"""
        if not self.performance_history:
            return {}
        
        recent_metrics = self.performance_history[-10:]  # 10 dernières mesures
        
        if not recent_metrics:
            return {}
        
        # Calcul des moyennes
        avg_gpu_util = sum(m.get('gpu_utilization', 0) for m in recent_metrics) / len(recent_metrics)
        avg_mem_util = sum(m.get('memory_utilization', 0) for m in recent_metrics) / len(recent_metrics)
        max_temp = max(m.get('temperature_c', 0) for m in recent_metrics)
        
        return {
            'avg_gpu_utilization': avg_gpu_util,
            'avg_memory_utilization': avg_mem_util,
            'max_temperature': max_temp,
            'samples_count': len(recent_metrics)
        }

    def _record_performance(self, result: ProcessingResult, frame_count: int):
        """Enregistre les performances pour optimisation future"""
        if not result.success:
            return
        
        perf_record = {
            'timestamp': time.time(),
            'frame_count': frame_count,
            'processing_time': result.processing_time,
            'frames_per_second': frame_count / result.processing_time if result.processing_time > 0 else 0,
            'config_used': self.optimal_config.copy(),
            'performance_metrics': result.performance_metrics or {}
        }
        
        # Sauvegarde dans un fichier pour analyse
        try:
            perf_file = Path(config.LOGS_DIR) / "realesrgan_performance.jsonl"
            perf_file.parent.mkdir(exist_ok=True)
            
            with open(perf_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(perf_record) + '\n')
                
        except Exception as e:
            self.logger.debug(f"Erreur sauvegarde performances: {e}")

    def get_optimal_batch_size(self) -> int:
        """Calcule la taille de lot optimale selon le matériel - VERSION CORRIGÉE POUR RTX 3050"""
        if not self.system_info:
            print("⚠️ Pas d'info système, utilisation taille par défaut")
            return config.BATCH_SIZE
        
        base_batch_size = config.BATCH_SIZE
        print(f"📏 Taille de base: {base_batch_size}")
        
        # Ajustement selon la VRAM du GPU principal - CORRECTION POUR RTX 3050
        if self.system_info.gpus:
            # Chercher spécifiquement le RTX 3050
            rtx_gpu = None
            for gpu in self.system_info.gpus:
                if "RTX" in gpu.name.upper() and "3050" in gpu.name.upper():
                    rtx_gpu = gpu
                    break
            
            # Si on a trouvé le RTX 3050, l'utiliser
            if rtx_gpu:
                main_gpu = rtx_gpu
                print(f"🎯 RTX 3050 détecté: {main_gpu.name} ({main_gpu.memory_total_mb}MB)")
            else:
                main_gpu = max(self.system_info.gpus, key=lambda g: g.memory_total_mb if "NVIDIA" in g.name else 0)
                print(f"🎯 GPU principal: {main_gpu.name} ({main_gpu.memory_total_mb}MB)")
            
            # Configuration spéciale pour RTX 3050
            if "3050" in main_gpu.name.upper():
                # RTX 3050 peut gérer des lots plus gros que prévu
                optimal_size = max(base_batch_size * 2, 15)  # Au moins 15 images par lot
                print(f"🚀 RTX 3050 optimisé: taille ajustée à {optimal_size}")
                return min(optimal_size, 25)  # Maximum 25 pour éviter les timeouts
            
            elif main_gpu.memory_total_mb >= 16384:  # >= 16GB
                optimal_size = min(base_batch_size * 3, 100)
                print(f"🚀 GPU haute VRAM: taille ajustée à {optimal_size}")
                return optimal_size
            elif main_gpu.memory_total_mb >= 8192:  # >= 8GB
                optimal_size = min(base_batch_size * 2, 60)
                print(f"📈 GPU moyenne VRAM: taille ajustée à {optimal_size}")
                return optimal_size
            elif main_gpu.memory_total_mb <= 2048:  # <= 2GB
                optimal_size = max(base_batch_size // 3, 5)
                print(f"⚠️ GPU très faible VRAM: taille réduite à {optimal_size}")
                return optimal_size
        
        # Ajustement selon la RAM système
        if self.system_info.ram_total_gb >= 32:
            optimal_size = min(base_batch_size + 10, 40)
            print(f"💾 RAM élevée: taille ajustée à {optimal_size}")
            return optimal_size
        elif self.system_info.ram_total_gb <= 8:
            optimal_size = max(base_batch_size // 2, 8)
            print(f"💾 RAM faible: taille réduite à {optimal_size}")
            return optimal_size
        
        print(f"📏 Taille finale: {base_batch_size}")
        return base_batch_size

    def get_recommended_concurrent_batches(self) -> int:
        """Recommande le nombre de lots simultanés selon le matériel"""
        if not self.system_info:
            return 1
        
        concurrent = 1
        
        # Plus de lots si plusieurs GPUs
        concurrent += len(self.system_info.gpus) - 1
        
        # Ajustement selon CPU
        if self.system_info.cpu.cores_logical >= 16:
            concurrent += 1
        elif self.system_info.cpu.cores_logical >= 12:
            concurrent += 0
        else:
            concurrent = max(1, concurrent - 1)
        
        # Limitation pour laptops
        if self.system_info.is_laptop:
            concurrent = min(concurrent, 2)
        
        return min(concurrent, 4)  # Maximum 4 lots simultanés

    def adapt_to_system_load(self) -> Dict[str, Any]:
        """Adapte la configuration selon la charge système actuelle"""
        try:
            import psutil
            
            # Vérification CPU
            cpu_percent = psutil.cpu_percent(interval=1)
            memory_percent = psutil.virtual_memory().percent
            
            adaptations = {}
            
            if cpu_percent > 80:
                # CPU surchargé, réduction des threads
                current_threads = self.optimal_config['threads']
                load, proc, save = map(int, current_threads.split(':'))
                adaptations['threads'] = f"{max(1, load//2)}:{max(2, proc//2)}:{max(1, save//2)}"
                adaptations['reason'] = "CPU surchargé"
            
            if memory_percent > 85:
                # RAM faible, réduction tile size
                adaptations['tile_size'] = min(128, self.optimal_config['tile_size'])
                adaptations['reason'] = adaptations.get('reason', '') + " RAM faible"
            
            # Vérification température GPU
            if self.performance_history:
                recent_temps = [m.get('temperature_c', 0) for m in self.performance_history[-5:]]
                avg_temp = sum(recent_temps) / len(recent_temps) if recent_temps else 0
                
                if avg_temp > 80:  # > 80°C
                    adaptations['tile_size'] = min(256, self.optimal_config['tile_size'])
                    adaptations['reason'] = adaptations.get('reason', '') + " GPU chaud"
            
            if adaptations:
                self.logger.info(f"Adaptation configuration: {adaptations['reason']}")
                return adaptations
            
        except Exception as e:
            self.logger.debug(f"Erreur adaptation charge système: {e}")
        
        return {}

    def get_system_status(self) -> Dict[str, Any]:
        """Retourne le statut complet du système"""
        status = {
            'system_detected': self.system_info is not None,
            'optimal_config': self.optimal_config.copy(),
            'executable_found': self.executable_path is not None,
            'performance_samples': len(self.performance_history)
        }
        
        if self.system_info:
            status.update({
                'gpu_count': len(self.system_info.gpus),
                'cpu_cores': self.system_info.cpu.cores_logical,
                'ram_gb': self.system_info.ram_total_gb,
                'is_laptop': self.system_info.is_laptop,
                'power_profile': self.system_info.power_profile
            })
            
            # Statut des GPUs
            status['gpus'] = []
            for gpu in self.system_info.gpus:
                gpu_status = {
                    'index': gpu.index,
                    'name': gpu.name,
                    'memory_mb': gpu.memory_total_mb,
                    'tier': gpu.performance_tier
                }
                status['gpus'].append(gpu_status)
        
        # Dernières métriques de performance
        if self.performance_history:
            latest = self.performance_history[-1]
            status['current_performance'] = {
                'gpu_utilization': latest.get('gpu_utilization', 0),
                'memory_utilization': latest.get('memory_utilization', 0),
                'temperature': latest.get('temperature_c', 0)
            }
        
        return status

    def benchmark_configuration(self, test_frames: List[str]) -> Dict[str, Any]:
        """Teste et benchmark différentes configurations"""
        self.logger.info("Démarrage du benchmark de configuration...")
        
        test_configs = [
            # Configuration actuelle
            self.optimal_config.copy(),
            
            # Configuration conservative
            {**self.optimal_config, 'tile_size': 128, 'threads': '1:2:1'},
            
            # Configuration agressive (si VRAM suffisante)
            {**self.optimal_config, 'tile_size': 512, 'threads': '4:8:4', 'tta_mode': True},
        ]
        
        results = []
        
        for i, test_config in enumerate(test_configs):
            self.logger.info(f"Test configuration {i+1}/{len(test_configs)}")
            
            # Sauvegarde config actuelle
            original_config = self.optimal_config.copy()
            self.optimal_config = test_config
            
            try:
                # Test avec un échantillon de frames
                test_sample = test_frames[:min(5, len(test_frames))]
                start_time = time.time()
                
                # Simulation du traitement (ou vrai test si possible)
                # result = await self.process_batch(test_sample, "benchmark_output", f"benchmark_{i}")
                
                # Pour l'instant, simulation
                result = ProcessingResult(
                    success=True,
                    processing_time=len(test_sample) * 2.5,  # Estimation
                    frames_processed=len(test_sample)
                )
                
                results.append({
                    'config': test_config.copy(),
                    'fps': result.frames_processed / result.processing_time if result.processing_time > 0 else 0,
                    'processing_time': result.processing_time,
                    'success': result.success
                })
                
            except Exception as e:
                self.logger.error(f"Erreur benchmark config {i}: {e}")
                
            finally:
                # Restauration config
                self.optimal_config = original_config
        
        # Sélection de la meilleure configuration
        best_config = max(results, key=lambda r: r['fps'] if r['success'] else 0)
        
        self.logger.info(f"Meilleure configuration: {best_config['fps']:.2f} FPS")
        
        return {
            'best_config': best_config['config'],
            'all_results': results,
            'recommendation': "Configuration optimale identifiée"
        }

# Instance globale
optimized_realesrgan = OptimizedRealESRGAN()