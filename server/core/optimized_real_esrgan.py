# server/core/optimized_real_esrgan.py
"""
Module optimisé pour Real-ESRGAN avec détection automatique du matériel
Version entièrement corrigée avec appels de méthodes fixes
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
        """Recherche manuelle de Real-ESRGAN selon la structure du projet"""
        executable_name = "realesrgan-ncnn-vulkan.exe" if sys.platform == "win32" else "realesrgan-ncnn-vulkan"
        
        # Chemins de recherche selon la structure du projet
        project_root = Path(__file__).parent.parent
        possible_paths = [
            # Structure standard du projet
            project_root / "realesrgan-ncnn-vulkan" / executable_name,
            project_root / "realesrgan-ncnn-vulkan" / "Windows" / executable_name,
            
            # Structure alternative
            project_root / "dependencies" / executable_name,
            
            # Dossier courant
            Path.cwd() / "realesrgan-ncnn-vulkan" / executable_name,
            Path.cwd() / executable_name,
        ]
        
        for path in possible_paths:
            if path.exists() and path.is_file():
                # Test simple de l'exécutable
                if self._test_executable_simple(path):
                    self.logger.info(f"✅ Real-ESRGAN trouvé et testé: {path}")
                    return str(path)
                else:
                    self.logger.warning(f"⚠️ Fichier trouvé mais test échoué: {path}")
        
        self.logger.warning("⚠️ Real-ESRGAN exécutable non trouvé dans les chemins standards")
        self.logger.warning("📥 Veuillez télécharger Real-ESRGAN depuis: https://github.com/xinntao/Real-ESRGAN/releases")
        self.logger.warning(f"📁 Et le placer dans: {project_root / 'realesrgan-ncnn-vulkan'}")
        return None
    
    def _test_executable_simple(self, executable_path: Path) -> bool:
        """Test simple de l'exécutable Real-ESRGAN"""
        try:
            # Test avec -h (aide) ou --help
            result = subprocess.run(
                [str(executable_path), "-h"],
                capture_output=True,
                timeout=5,
                text=True
            )
            # Real-ESRGAN retourne souvent 1 même pour -h, donc on vérifie aussi la sortie
            return result.returncode in [0, 1] and ("Real-ESRGAN" in result.stdout or "Real-ESRGAN" in result.stderr)
        except subprocess.TimeoutExpired:
            self.logger.warning(f"Test timeout pour {executable_path}")
            return False
        except Exception as e:
            self.logger.debug(f"Test échoué pour {executable_path}: {e}")
            return False

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
        """Détection matérielle sécurisée avec appel CORRIGÉ"""
        try:
            # Tentative d'import des modules de détection hardware
            try:
                from utils.hardware_detector import hardware_detector
                print("🔍 Détection des GPUs NVIDIA...")
                
                # ✅ CORRECTION CRITIQUE : Utilisation de la bonne méthode
                self.system_info = hardware_detector.detect_system_info()
                
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
                
                # Configuration basique adaptée
                self.optimal_config = {
                    'model': 'realesr-animevideov3',
                    'scale': 4,
                    'tile_size': 512 if system_type == 'desktop' else 256,
                    'gpu_id': 0,  # Utiliser le premier GPU disponible
                    'threads': f"{cpu_cores//4}:{cpu_cores//2}:{cpu_cores//4}",
                    'use_fp16': True,
                    'tta_mode': False,
                }
                print(f"🔧 Configuration basique générée: {self.optimal_config}")
                
            else:
                # Utilisation du nouveau système de détection avec SystemInfo
                try:
                    from utils.hardware_detector import hardware_detector
                    self.optimal_config = hardware_detector.optimize_realesrgan_config(
                        self.system_info, 
                        model="realesr-animevideov3"
                    )
                    print(f"🔧 Configuration avancée générée: {self.optimal_config}")
                except Exception as e:
                    print(f"⚠️ Erreur optimisation config avancée: {e}")
                    self.optimal_config = self.fallback_config.copy()
                    print(f"🛡️ Configuration de secours utilisée: {self.optimal_config}")
            
        except Exception as e:
            print(f"❌ Erreur génération config: {e}")
            self._use_fallback_config()
    
    def _use_fallback_config(self):
        """Utilise la configuration de secours"""
        self.optimal_config = self.fallback_config.copy()
        print(f"🛡️ Configuration de secours activée: {self.optimal_config}")
    
    def get_optimal_batch_size(self) -> int:
        """Retourne la taille de lot optimale"""
        if not self.system_info:
            return 10  # Valeur de secours conservative
        
        try:
            if isinstance(self.system_info, dict):
                # Logique basique
                cpu_cores = self.system_info.get('cpu_cores', 4)
                return max(5, min(50, cpu_cores * 2))
            else:
                # Logique avancée avec SystemInfo
                gpu_memory_gb = 0
                if hasattr(self.system_info, 'gpus') and self.system_info.gpus:
                    gpu_memory_gb = self.system_info.gpus[0].memory_total_mb / 1024
                
                if gpu_memory_gb >= 8:
                    return 50
                elif gpu_memory_gb >= 4:
                    return 30
                else:
                    return 15
        except Exception:
            return 10
    
    def get_recommended_concurrent_batches(self) -> int:
        """Retourne le nombre de lots concurrents recommandés"""
        if not self.system_info:
            return 2
        
        try:
            if isinstance(self.system_info, dict):
                cpu_cores = self.system_info.get('cpu_cores', 4)
                return max(1, min(4, cpu_cores // 4))
            else:
                # Logique basée sur les GPUs disponibles
                gpu_count = len(self.system_info.gpus) if hasattr(self.system_info, 'gpus') else 1
                return max(1, min(4, gpu_count))
        except Exception:
            return 2
    
    async def process_batch(self, input_dir: Path, output_dir: Path, 
                          config_override: Optional[Dict] = None) -> ProcessingResult:
        """Traite un lot d'images avec Real-ESRGAN"""
        if not self.executable_path:
            return ProcessingResult(
                success=False,
                processing_time=0.0,
                frames_processed=0,
                error_message="Exécutable Real-ESRGAN non disponible"
            )
        
        start_time = time.time()
        config = {**self.optimal_config, **(config_override or {})}
        
        try:
            # Construction de la commande
            cmd = [
                self.executable_path,
                "-i", str(input_dir),
                "-o", str(output_dir),
                "-n", config['model'],
                "-s", str(config['scale']),
                "-t", str(config['tile_size']),
                "-g", str(config['gpu_id']),
                "-j", config['threads']
            ]
            
            # Options additionnelles
            if config.get('use_fp16'):
                cmd.append("-h")
            
            if config.get('tta_mode'):
                cmd.append("-x")
            
            # Exécution
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            processing_time = time.time() - start_time
            
            if process.returncode == 0:
                # Compte les images traitées
                frames_processed = len(list(output_dir.glob("*.png"))) if output_dir.exists() else 0
                
                return ProcessingResult(
                    success=True,
                    processing_time=processing_time,
                    frames_processed=frames_processed
                )
            else:
                error_msg = stderr.decode('utf-8') if stderr else "Erreur inconnue"
                return ProcessingResult(
                    success=False,
                    processing_time=processing_time,
                    frames_processed=0,
                    error_message=error_msg
                )
                
        except Exception as e:
            return ProcessingResult(
                success=False,
                processing_time=time.time() - start_time,
                frames_processed=0,
                error_message=str(e)
            )

# Instance globale
optimized_realesrgan = OptimizedRealESRGAN()