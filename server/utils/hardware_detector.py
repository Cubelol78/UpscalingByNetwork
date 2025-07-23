"""
Détecteur de matériel pour optimiser automatiquement Real-ESRGAN
Version corrigée pour la détection GPU RTX 3050
"""

import subprocess
import json
import logging
import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from pathlib import Path

# Import optionnel de pynvml avec gestion d'erreur améliorée
try:
    import pynvml
    NVML_AVAILABLE = True
    print("✅ NVML (NVIDIA) disponible")
except ImportError as e:
    NVML_AVAILABLE = False
    print(f"⚠️ NVML non disponible: {e}")

try:
    import psutil
    PSUTIL_AVAILABLE = True
    print("✅ psutil disponible")
except ImportError:
    PSUTIL_AVAILABLE = False
    print("⚠️ psutil non disponible")

@dataclass
class GPUInfo:
    """Informations détaillées sur un GPU"""
    index: int
    name: str
    memory_total_mb: int
    memory_free_mb: int
    compute_capability: Optional[str] = None
    driver_version: Optional[str] = None
    cuda_cores: Optional[int] = None
    memory_bandwidth_gbps: Optional[float] = None
    boost_clock_mhz: Optional[int] = None
    is_vulkan_compatible: bool = True
    performance_tier: str = "medium"  # low, medium, high, extreme
    recommended_tile_size: int = 256
    recommended_threads: str = "2:2:2"

@dataclass
class CPUInfo:
    """Informations détaillées sur le CPU"""
    model: str
    cores_physical: int
    cores_logical: int
    frequency_mhz: float
    cache_l3_mb: Optional[int] = None
    is_laptop: bool = False
    performance_tier: str = "medium"

@dataclass
class SystemInfo:
    """Informations système complètes"""
    gpus: List[GPUInfo]
    cpu: CPUInfo
    ram_total_gb: float
    ram_available_gb: float
    is_laptop: bool = False
    power_profile: str = "balanced"  # power_save, balanced, performance

class HardwareDetector:
    """Détecteur de matériel pour optimisation automatique"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Tables de correspondance pour optimisation - MISE À JOUR
        self.gpu_database = {
            # RTX 40 Series
            'RTX 4090': {'tier': 'extreme', 'vram': 24576, 'tile': 512, 'threads': '8:12:8', 'cuda_cores': 16384},
            'RTX 4080': {'tier': 'extreme', 'vram': 16384, 'tile': 512, 'threads': '6:10:6', 'cuda_cores': 9728},
            'RTX 4070': {'tier': 'high', 'vram': 12288, 'tile': 384, 'threads': '4:8:4', 'cuda_cores': 5888},
            'RTX 4060': {'tier': 'medium', 'vram': 8192, 'tile': 256, 'threads': '3:6:3', 'cuda_cores': 3072},
            
            # RTX 30 Series - CORRECTION POUR LAPTOP
            'RTX 3090': {'tier': 'extreme', 'vram': 24576, 'tile': 512, 'threads': '8:10:8', 'cuda_cores': 10496},
            'RTX 3080': {'tier': 'extreme', 'vram': 12288, 'tile': 512, 'threads': '6:8:6', 'cuda_cores': 8704},
            'RTX 3070': {'tier': 'high', 'vram': 8192, 'tile': 384, 'threads': '4:6:4', 'cuda_cores': 5888},
            'RTX 3060': {'tier': 'medium', 'vram': 12288, 'tile': 256, 'threads': '3:4:3', 'cuda_cores': 3584},
            'RTX 3050': {'tier': 'medium', 'vram': 4096, 'tile': 256, 'threads': '2:4:2', 'cuda_cores': 2560},  # CORRECTION: 4GB VRAM
            'RTX 3050 Ti': {'tier': 'medium', 'vram': 4096, 'tile': 256, 'threads': '2:4:2', 'cuda_cores': 2560},
            'RTX 3050 Laptop': {'tier': 'medium', 'vram': 4096, 'tile': 256, 'threads': '2:4:2', 'cuda_cores': 2048},  # Version laptop
            
            # RTX 20 Series
            'RTX 2080': {'tier': 'high', 'vram': 11264, 'tile': 384, 'threads': '4:6:4', 'cuda_cores': 2944},
            'RTX 2070': {'tier': 'medium', 'vram': 8192, 'tile': 256, 'threads': '3:4:3', 'cuda_cores': 2304},
            'RTX 2060': {'tier': 'medium', 'vram': 6144, 'tile': 256, 'threads': '2:3:2', 'cuda_cores': 1920},
            
            # GTX Series
            'GTX 1080': {'tier': 'medium', 'vram': 8192, 'tile': 256, 'threads': '2:4:2', 'cuda_cores': 2560},
            'GTX 1070': {'tier': 'medium', 'vram': 8192, 'tile': 256, 'threads': '2:3:2', 'cuda_cores': 1920},
            'GTX 1060': {'tier': 'low', 'vram': 6144, 'tile': 256, 'threads': '2:2:2', 'cuda_cores': 1280},
            
            # AMD GPUs (approximatif pour Vulkan)
            'RX 7900': {'tier': 'extreme', 'vram': 20480, 'tile': 512, 'threads': '6:8:6', 'cuda_cores': 5376},
            'RX 6800': {'tier': 'high', 'vram': 16384, 'tile': 384, 'threads': '4:6:4', 'cuda_cores': 3840},
            'RX 580': {'tier': 'low', 'vram': 8192, 'tile': 128, 'threads': '1:2:1', 'cuda_cores': 2304},
        }
        
        self.cpu_database = {
            # Intel 13th gen
            'i9-13900': {'tier': 'extreme', 'threads': 24, 'is_laptop': False},
            'i7-13700': {'tier': 'high', 'threads': 16, 'is_laptop': False},
            'i5-13600': {'tier': 'medium', 'threads': 14, 'is_laptop': False},
            'i5-13400': {'tier': 'medium', 'threads': 10, 'is_laptop': False},
            
            # Intel 12th gen
            'i9-12900': {'tier': 'extreme', 'threads': 24, 'is_laptop': False},
            'i7-12700': {'tier': 'high', 'threads': 20, 'is_laptop': False},
            'i5-12600': {'tier': 'medium', 'threads': 12, 'is_laptop': False},
            'i5-12500': {'tier': 'medium', 'threads': 12, 'is_laptop': False},
            'i5-12400': {'tier': 'medium', 'threads': 12, 'is_laptop': False},
            
            # Laptop variants
            'i9-12900H': {'tier': 'high', 'threads': 20, 'is_laptop': True},
            'i7-12700H': {'tier': 'high', 'threads': 20, 'is_laptop': True},
            'i5-12500H': {'tier': 'medium', 'threads': 16, 'is_laptop': True},  # Votre config
            
            # AMD Ryzen
            'Ryzen 9 7900': {'tier': 'extreme', 'threads': 24, 'is_laptop': False},
            'Ryzen 7 7700': {'tier': 'high', 'threads': 16, 'is_laptop': False},
            'Ryzen 5 7600': {'tier': 'medium', 'threads': 12, 'is_laptop': False},
        }
    
    def detect_system_info(self) -> SystemInfo:
        """Détecte toutes les informations système avec debug amélioré"""
        try:
            print("🔍 Début de la détection système...")
            
            gpus = self._detect_gpus()
            print(f"📊 GPUs détectés: {len(gpus)}")
            
            cpu = self._detect_cpu()
            print(f"🖥️ CPU détecté: {cpu.model}")
            
            ram_info = self._detect_ram()
            print(f"💾 RAM détectée: {ram_info['total']:.1f}GB")
            
            is_laptop = self._detect_if_laptop()
            print(f"💻 Type: {'Laptop' if is_laptop else 'Desktop'}")
            
            system = SystemInfo(
                gpus=gpus,
                cpu=cpu,
                ram_total_gb=ram_info['total'],
                ram_available_gb=ram_info['available'],
                is_laptop=is_laptop,
                power_profile=self._determine_power_profile(is_laptop, cpu, gpus)
            )
            
            print(f"✅ Système détecté: {len(gpus)} GPU(s), {cpu.model}, {ram_info['total']:.1f}GB RAM")
            return system
            
        except Exception as e:
            print(f"❌ Erreur détection système: {e}")
            self.logger.error(f"Erreur détection système: {e}")
            return self._get_fallback_system()
    
    def _detect_gpus(self) -> List[GPUInfo]:
        """Détecte les GPUs NVIDIA disponibles avec debug amélioré"""
        gpus = []
        
        print("🔍 Détection des GPUs NVIDIA...")
        if NVML_AVAILABLE:
            nvidia_gpus = self._detect_nvidia_gpus()
            gpus.extend(nvidia_gpus)
            print(f"📊 GPUs NVIDIA trouvés: {len(nvidia_gpus)}")
        else:
            print("⚠️ NVML non disponible, détection NVIDIA impossible")
        
        # Détection Vulkan pour AMD/Intel
        print("🔍 Détection des GPUs Vulkan...")
        vulkan_gpus = self._detect_vulkan_gpus()
        for vk_gpu in vulkan_gpus:
            # Éviter les doublons NVIDIA
            if not any(gpu.name in vk_gpu.name for gpu in gpus):
                gpus.append(vk_gpu)
        print(f"📊 GPUs Vulkan additionnels trouvés: {len(vulkan_gpus)}")
        
        if not gpus:
            print("⚠️ Aucun GPU compatible détecté, utilisation CPU uniquement")
            self.logger.warning("Aucun GPU compatible détecté, utilisation CPU uniquement")
            gpus.append(self._get_fallback_gpu())
        
        return gpus
    
    def _detect_nvidia_gpus(self) -> List[GPUInfo]:
        """Détecte les GPUs NVIDIA via NVML avec debug renforcé"""
        gpus = []
        
        try:
            print("🔧 Initialisation NVML...")
            pynvml.nvmlInit()
            device_count = pynvml.nvmlDeviceGetCount()
            print(f"📊 Nombre de GPUs NVIDIA détectés: {device_count}")
            
            for i in range(device_count):
                print(f"🔍 Analyse GPU {i}...")
                
                try:
                    handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                    
                    # Informations de base - CORRECTION DU BUG DECODE
                    try:
                        name_bytes = pynvml.nvmlDeviceGetName(handle)
                        # Correction : vérifier si c'est déjà une string ou des bytes
                        if isinstance(name_bytes, bytes):
                            name = name_bytes.decode('utf-8')
                        else:
                            name = str(name_bytes)  # Déjà une string
                        print(f"   📛 Nom: {name}")
                    except Exception as e:
                        print(f"   ⚠️ Erreur lecture nom GPU {i}: {e}")
                        name = f"NVIDIA GPU {i}"
                    
                    try:
                        memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                        memory_total_mb = memory_info.total // (1024 * 1024)
                        memory_free_mb = memory_info.free // (1024 * 1024)
                        print(f"   💾 VRAM: {memory_total_mb}MB total, {memory_free_mb}MB libre")
                    except Exception as e:
                        print(f"   ⚠️ Erreur lecture mémoire GPU {i}: {e}")
                        memory_total_mb = 4096  # Fallback conservateur
                        memory_free_mb = 3072
                    
                    # Informations avancées - avec gestion d'erreur
                    driver_version = "Unknown"
                    try:
                        driver_version_bytes = pynvml.nvmlSystemGetDriverVersion()
                        if isinstance(driver_version_bytes, bytes):
                            driver_version = driver_version_bytes.decode('utf-8')
                        else:
                            driver_version = str(driver_version_bytes)
                        print(f"   🔧 Driver: {driver_version}")
                    except Exception as e:
                        print(f"   ⚠️ Erreur lecture driver version: {e}")
                    
                    compute_capability = None
                    try:
                        major, minor = pynvml.nvmlDeviceGetCudaComputeCapability(handle)
                        compute_capability = f"{major}.{minor}"
                        print(f"   🧮 Compute Capability: {compute_capability}")
                    except Exception as e:
                        print(f"   ⚠️ Erreur lecture compute capability: {e}")
                    
                    # Optimisations basées sur le nom - RECHERCHE AMÉLIORÉE
                    gpu_config = self._get_gpu_config(name)
                    print(f"   ⚙️ Configuration: {gpu_config['tier']} tier, {gpu_config['tile']}px tile")
                    
                    # CORRECTION SPÉCIALE POUR RTX 3050
                    if "3050" in name.upper():
                        print(f"   🔧 Détection RTX 3050 - Application optimisations spécifiques")
                        gpu_config = {
                            'tier': 'medium',
                            'vram': 4096,  # 4GB VRAM
                            'tile': 256,   # Taille conservative pour 4GB
                            'threads': '2:4:2',  # Threads modestes
                            'cuda_cores': 2048 if 'laptop' in name.lower() else 2560
                        }
                    
                    gpu = GPUInfo(
                        index=i,
                        name=name,
                        memory_total_mb=memory_total_mb,
                        memory_free_mb=memory_free_mb,
                        compute_capability=compute_capability,
                        driver_version=driver_version,
                        cuda_cores=gpu_config.get('cuda_cores'),
                        performance_tier=gpu_config['tier'],
                        recommended_tile_size=gpu_config['tile'],
                        recommended_threads=gpu_config['threads']
                    )
                    
                    gpus.append(gpu)
                    print(f"   ✅ GPU {i} ajouté: {name} ({memory_total_mb}MB VRAM, {gpu_config['tier']} tier)")
                    
                except Exception as e:
                    print(f"   ❌ Erreur traitement GPU {i}: {e}")
                    self.logger.error(f"Erreur traitement GPU {i}: {e}")
            
            pynvml.nvmlShutdown()
            print("✅ NVML fermé proprement")
            
        except Exception as e:
            print(f"❌ Erreur détection NVIDIA globale: {e}")
            self.logger.error(f"Erreur détection NVIDIA: {e}")
        
        return gpus
    
    def _get_gpu_config(self, gpu_name: str) -> Dict[str, Any]:
        """Récupère la configuration optimale pour un GPU avec recherche améliorée"""
        gpu_name_upper = gpu_name.upper()
        print(f"🔍 Recherche configuration pour: '{gpu_name_upper}'")
        
        # Recherche exacte d'abord
        for pattern, config in self.gpu_database.items():
            if pattern.upper() == gpu_name_upper:
                print(f"✅ Correspondance exacte trouvée: {pattern}")
                return config
        
        # Recherche par mots-clés
        for pattern, config in self.gpu_database.items():
            pattern_parts = pattern.upper().split()
            if all(part in gpu_name_upper for part in pattern_parts):
                print(f"✅ Correspondance par mots-clés: {pattern}")
                return config
        
        # Recherche partielle pour les séries
        if "RTX 3050" in gpu_name_upper:
            print("🎯 Détection RTX 3050 - Configuration spécifique")
            return {
                'tier': 'medium',
                'vram': 4096,
                'tile': 256,
                'threads': '2:4:2',
                'cuda_cores': 2048 if 'LAPTOP' in gpu_name_upper else 2560
            }
        elif "RTX 3060" in gpu_name_upper:
            return {'tier': 'medium', 'vram': 12288, 'tile': 256, 'threads': '3:4:3', 'cuda_cores': 3584}
        elif "RTX 3070" in gpu_name_upper:
            return {'tier': 'high', 'vram': 8192, 'tile': 384, 'threads': '4:6:4', 'cuda_cores': 5888}
        elif "RTX 3080" in gpu_name_upper:
            return {'tier': 'extreme', 'vram': 12288, 'tile': 512, 'threads': '6:8:6', 'cuda_cores': 8704}
        elif "RTX 3090" in gpu_name_upper:
            return {'tier': 'extreme', 'vram': 24576, 'tile': 512, 'threads': '8:10:8', 'cuda_cores': 10496}
        
        print(f"⚠️ Aucune correspondance trouvée pour '{gpu_name_upper}', utilisation config par défaut")
        
        # Configuration par défaut pour GPU inconnu
        return {
            'tier': 'medium',
            'vram': 8192,
            'tile': 256,
            'threads': '2:4:2',
            'cuda_cores': 2048
        }
    
    def _detect_vulkan_gpus(self) -> List[GPUInfo]:
        """Détecte les GPUs compatibles Vulkan (AMD, Intel)"""
        gpus = []
        
        try:
            # Tentative avec vulkaninfo
            result = subprocess.run(['vulkaninfo', '--summary'], 
                                  capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                # Parse la sortie pour extraire les GPUs
                lines = result.stdout.split('\n')
                for i, line in enumerate(lines):
                    if 'deviceName' in line:
                        name = line.split(':')[-1].strip().strip('"')
                        
                        # Configuration basée sur le nom
                        gpu_config = self._get_gpu_config(name)
                        
                        gpu = GPUInfo(
                            index=len(gpus),
                            name=name,
                            memory_total_mb=gpu_config.get('vram', 8192),  # Estimation
                            memory_free_mb=gpu_config.get('vram', 8192),
                            is_vulkan_compatible=True,
                            performance_tier=gpu_config['tier'],
                            recommended_tile_size=gpu_config['tile'],
                            recommended_threads=gpu_config['threads']
                        )
                        gpus.append(gpu)
                        
        except Exception as e:
            print(f"⚠️ Vulkaninfo non disponible: {e}")
        
        return gpus
    
    def _detect_cpu(self) -> CPUInfo:
        """Détecte les informations CPU avec debug amélioré"""
        try:
            if PSUTIL_AVAILABLE:
                # Informations de base via psutil
                cpu_freq = psutil.cpu_freq()
                frequency = cpu_freq.current if cpu_freq else 2400.0
                
                physical_cores = psutil.cpu_count(logical=False)
                logical_cores = psutil.cpu_count(logical=True)
                
                print(f"🖥️ CPU: {logical_cores} threads logiques, {physical_cores} cœurs physiques")
                
                # Nom du CPU - VERSION CORRIGÉE
                cpu_name = "Unknown CPU"
                try:
                    # Méthode 1: Via platform
                    import platform
                    cpu_name = platform.processor()
                    print(f"📛 CPU nom (platform): '{cpu_name}'")
                    
                    # Si vide, essayer une autre méthode
                    if not cpu_name or cpu_name.strip() == "":
                        # Méthode 2: Via cpuinfo sur Windows
                        import os
                        if os.name == 'nt':
                            cpu_name = os.environ.get('PROCESSOR_IDENTIFIER', 'Unknown CPU')
                            print(f"📛 CPU nom (env): '{cpu_name}'")
                        
                    # Méthode 3: Via wmic sur Windows (fallback)
                    if not cpu_name or "Unknown" in cpu_name:
                        try:
                            result = subprocess.run(['wmic', 'cpu', 'get', 'name'], 
                                                  capture_output=True, text=True, timeout=5)
                            if result.returncode == 0:
                                lines = result.stdout.strip().split('\n')
                                for line in lines:
                                    if line.strip() and 'Name' not in line:
                                        cpu_name = line.strip()
                                        print(f"📛 CPU nom (wmic): '{cpu_name}'")
                                        break
                        except Exception as e:
                            print(f"⚠️ Erreur wmic: {e}")
                            
                except Exception as e:
                    print(f"⚠️ Erreur détection nom CPU: {e}")
                
                # Configuration basée sur le nom
                cpu_config = self._get_cpu_config(cpu_name)
                print(f"⚙️ CPU config: {cpu_config['tier']} tier, laptop: {cpu_config['is_laptop']}")
                
                return CPUInfo(
                    model=cpu_name,
                    cores_physical=physical_cores or 4,
                    cores_logical=logical_cores or 8,
                    frequency_mhz=frequency,
                    is_laptop=cpu_config['is_laptop'],
                    performance_tier=cpu_config['tier']
                )
            else:
                print("⚠️ psutil non disponible, utilisation fallback CPU")
                return self._get_fallback_cpu()
                
        except Exception as e:
            print(f"❌ Erreur détection CPU: {e}")
            self.logger.error(f"Erreur détection CPU: {e}")
            return self._get_fallback_cpu()
    
    def _detect_ram(self) -> Dict[str, float]:
        """Détecte les informations RAM"""
        try:
            if PSUTIL_AVAILABLE:
                memory = psutil.virtual_memory()
                return {
                    'total': memory.total / (1024**3),  # GB
                    'available': memory.available / (1024**3)
                }
            else:
                return {'total': 16.0, 'available': 8.0}  # Estimation
        except:
            return {'total': 16.0, 'available': 8.0}
    
    def _detect_if_laptop(self) -> bool:
        """Détecte si c'est un laptop avec debug"""
        try:
            # Méthode 1: Vérifier la batterie
            if PSUTIL_AVAILABLE:
                battery = psutil.sensors_battery()
                if battery is not None:
                    print("💻 Laptop détecté via batterie")
                    return True
            
            # Méthode 2: Vérifier les noms de CPU laptop
            cpu_name = ""
            try:
                import platform
                cpu_name = platform.processor().upper()
                if any(suffix in cpu_name for suffix in ['H', 'U', 'Y', 'MOBILE']):
                    print(f"💻 Laptop détecté via CPU: {cpu_name}")
                    return True
            except:
                pass
            
            print("🖥️ Desktop détecté")
            return False
            
        except Exception as e:
            print(f"⚠️ Erreur détection laptop: {e}")
            return False
    
    def _get_cpu_config(self, cpu_name: str) -> Dict[str, Any]:
        """Récupère la configuration optimale pour un CPU"""
        cpu_name_upper = cpu_name.upper()
        
        for pattern, config in self.cpu_database.items():
            if pattern.upper().replace('-', '').replace(' ', '') in cpu_name_upper.replace('-', '').replace(' ', ''):
                return config
        
        # Détection laptop via suffixes
        is_laptop = any(suffix in cpu_name_upper for suffix in ['H', 'U', 'Y', 'MOBILE'])
        
        return {
            'tier': 'medium',
            'threads': 8,
            'is_laptop': is_laptop
        }
    
    def _determine_power_profile(self, is_laptop: bool, cpu: CPUInfo, gpus: List[GPUInfo]) -> str:
        """Détermine le profil de puissance optimal"""
        if is_laptop:
            # Pour laptops, profil plus conservateur
            if any(gpu.performance_tier in ['extreme', 'high'] for gpu in gpus):
                return 'balanced'
            else:
                return 'power_save'
        else:
            # Pour desktops, privilégier la performance
            if any(gpu.performance_tier == 'extreme' for gpu in gpus):
                return 'performance'
            else:
                return 'balanced'
    
    def optimize_realesrgan_config(self, system: SystemInfo, model: str = "realesr-animevideov3") -> Dict[str, Any]:
        """Génère une configuration optimale pour Real-ESRGAN avec sélection GPU corrigée"""
        print(f"🔧 Optimisation configuration Real-ESRGAN pour modèle: {model}")
        
        # Sélection du meilleur GPU - CORRECTION CRITIQUE
        best_gpu = None
        
        if system.gpus:
            # Priorité aux GPUs NVIDIA dédiés
            nvidia_gpus = [gpu for gpu in system.gpus if 'NVIDIA' in gpu.name.upper() and 'RTX' in gpu.name.upper()]
            if nvidia_gpus:
                best_gpu = nvidia_gpus[0]  # Premier GPU NVIDIA RTX trouvé
                print(f"🎯 GPU NVIDIA RTX sélectionné: {best_gpu.name} (index {best_gpu.index})")
            else:
                # Fallback sur le GPU avec le plus de VRAM
                best_gpu = max(system.gpus, key=lambda g: g.memory_total_mb)
                print(f"🎯 GPU fallback sélectionné: {best_gpu.name} (index {best_gpu.index})")
        
        if not best_gpu:
            print("⚠️ Aucun GPU trouvé, configuration CPU uniquement")
            return self._get_cpu_only_config(system)
        
        print(f"🎯 GPU final sélectionné: {best_gpu.name} ({best_gpu.memory_total_mb}MB VRAM, index {best_gpu.index})")
        
        # Configuration de base
        config = {
            'gpu_id': best_gpu.index,
            'model': model,
            'tile_size': best_gpu.recommended_tile_size,
            'threads': best_gpu.recommended_threads,
            'use_fp16': True,
            'tta_mode': False,
        }
        
        print(f"⚙️ Configuration de base: tile={config['tile_size']}, threads={config['threads']}, gpu_id={config['gpu_id']}")
        
        # Ajustements spéciaux pour RTX 3050
        if "3050" in best_gpu.name.upper():
            print("🔧 Optimisations spéciales RTX 3050:")
            
            # Configuration agressive pour maximiser l'utilisation
            config['tile_size'] = 256  # Taille optimale pour 4GB
            config['threads'] = "3:6:3"  # Plus de threads pour utiliser davantage le GPU
            config['use_fp16'] = True  # Économie mémoire
            
            # Mode performance pour laptop
            if system.is_laptop and "LAPTOP" in best_gpu.name.upper():
                config['threads'] = "2:5:2"  # Légèrement réduit pour laptop mais toujours agressif
                print(f"💻 Mode laptop RTX 3050: threads={config['threads']}")
            
            print(f"🚀 RTX 3050 optimisé: tile={config['tile_size']}, threads={config['threads']}")
        
        # Ajustements selon la VRAM disponible
        if best_gpu.memory_total_mb <= 4096:  # <= 4GB
            if config['tile_size'] > 256:
                config['tile_size'] = 256
                print("🔧 VRAM ≤ 4GB: limitation tile_size à 256")
        elif best_gpu.memory_total_mb >= 8192:  # >= 8GB
            config['tile_size'] = max(config['tile_size'], 384)
            config['tta_mode'] = False  # Garder false pour la vitesse
            print("🔧 VRAM ≥ 8GB: augmentation tile_size")
        
        # Mode performance pour système puissant
        if system.ram_total_gb >= 16 and best_gpu.memory_total_mb >= 4096:
            # Augmenter les threads pour plus d'utilisation
            if ":" in config['threads']:
                load, proc, save = map(int, config['threads'].split(':'))
                config['threads'] = f"{load+1}:{proc+2}:{save+1}"
                print(f"🚀 Mode performance: threads augmentés à {config['threads']}")
        
        print(f"✅ Configuration finale: GPU {best_gpu.index} ({best_gpu.name}), "
            f"Tile: {config['tile_size']}, Threads: {config['threads']}")
        
        return config
    
    # Configuration pour laptop RTX 3050 avec optimisations agressives
    def get_rtx_3050_laptop_config(self) -> Dict[str, Any]:
        """Configuration spécialisée pour RTX 3050 Laptop"""
        return {
            'gpu_id': 0,  # Forcer l'utilisation du RTX (généralement index 0)
            'model': 'realesr-animevideov3',
            'tile_size': 256,
            'threads': '2:5:2',  # Configuration agressive mais stable
            'use_fp16': True,
            'tta_mode': False,
        }

    def _get_cpu_only_config(self, system: SystemInfo) -> Dict[str, Any]:
        """Configuration pour traitement CPU uniquement"""
        threads = min(system.cpu.cores_logical, 8)  # Limiter pour éviter la surchauffe
        
        print(f"🖥️ Configuration CPU uniquement: {threads} threads")
        
        return {
            'gpu_id': -1,  # CPU uniquement
            'model': "realesr-animevideov3",
            'tile_size': 64,  # Plus petit pour CPU
            'threads': f"{threads//3}:{threads//2}:{threads//3}",
            'use_fp16': False,  # CPU généralement FP32
            'tta_mode': False,
        }
    
    def _get_fallback_system(self) -> SystemInfo:
        """Système de fallback en cas d'erreur"""
        return SystemInfo(
            gpus=[self._get_fallback_gpu()],
            cpu=self._get_fallback_cpu(),
            ram_total_gb=16.0,
            ram_available_gb=8.0,
            is_laptop=False
        )
    
    def _get_fallback_gpu(self) -> GPUInfo:
        """GPU de fallback"""
        return GPUInfo(
            index=0,
            name="Unknown GPU",
            memory_total_mb=8192,
            memory_free_mb=6144,
            performance_tier="medium",
            recommended_tile_size=256,
            recommended_threads="2:4:2"
        )
    
    def _get_fallback_cpu(self) -> CPUInfo:
        """CPU de fallback"""
        return CPUInfo(
            model="Unknown CPU",
            cores_physical=4,
            cores_logical=8,
            frequency_mhz=2400.0,
            performance_tier="medium"
        )
    
    def get_system_performance_summary(self, system: SystemInfo) -> str:
        """Génère un résumé des performances système"""
        summary = []
        summary.append(f"=== RÉSUMÉ PERFORMANCE SYSTÈME ===")
        summary.append(f"CPU: {system.cpu.model} ({system.cpu.cores_logical} threads)")
        summary.append(f"RAM: {system.ram_total_gb:.1f}GB total, {system.ram_available_gb:.1f}GB disponible")
        summary.append(f"Type: {'Laptop' if system.is_laptop else 'Desktop'}")
        summary.append(f"Profil: {system.power_profile}")
        summary.append("")
        
        summary.append("GPUs détectés:")
        for gpu in system.gpus:
            summary.append(f"  - {gpu.name}: {gpu.memory_total_mb}MB VRAM ({gpu.performance_tier})")
            summary.append(f"    Optimisé: Tile {gpu.recommended_tile_size}, Threads {gpu.recommended_threads}")
        
        return "\n".join(summary)

# Instance globale
hardware_detector = HardwareDetector()