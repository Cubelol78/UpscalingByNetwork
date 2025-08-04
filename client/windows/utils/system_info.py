# UpscalingByNetwork/client/windows/utils/system_info.py

import platform
import psutil
import subprocess
import logging
from typing import Dict, Any, List, Optional
import json

class SystemInfo:
    """Collecteur d'informations système pour Windows"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Cache des informations statiques
        self._static_info = None
        self._gpu_info = None
        
        self.logger.info("SystemInfo initialisé")
    
    def get_system_info(self) -> Dict[str, Any]:
        """Retourne les informations système complètes"""
        if self._static_info is None:
            self._static_info = self._collect_static_info()
        
        # Informations dynamiques
        dynamic_info = self._collect_dynamic_info()
        
        # Fusion
        result = self._static_info.copy()
        result.update(dynamic_info)
        
        return result
    
    def _collect_static_info(self) -> Dict[str, Any]:
        """Collecte les informations statiques du système"""
        try:
            info = {
                # Système d'exploitation
                'os': platform.system(),
                'os_version': platform.version(),
                'os_release': platform.release(),
                'architecture': platform.architecture()[0],
                'machine': platform.machine(),
                'processor': platform.processor(),
                
                # CPU
                'cpu_count': psutil.cpu_count(logical=False),
                'cpu_count_logical': psutil.cpu_count(logical=True),
                'cpu_freq_max': psutil.cpu_freq().max if psutil.cpu_freq() else 0,
                
                # Mémoire
                'ram_total': psutil.virtual_memory().total,
                'ram_gb': round(psutil.virtual_memory().total / (1024**3), 1),
                
                # Stockage
                'disk_info': self._get_disk_info(),
                
                # GPU
                'gpu_info': self.get_gpu_info(),
                
                # Réseau
                'network_interfaces': self._get_network_interfaces(),
                
                # Python
                'python_version': platform.python_version(),
                'python_implementation': platform.python_implementation()
            }
            
            self.logger.info("Informations système collectées")
            return info
            
        except Exception as e:
            self.logger.error(f"Erreur collecte info système: {e}")
            return self._get_minimal_info()
    
    def _collect_dynamic_info(self) -> Dict[str, Any]:
        """Collecte les informations dynamiques du système"""
        try:
            return {
                'current_load': {
                    'cpu_percent': psutil.cpu_percent(interval=1),
                    'memory_percent': psutil.virtual_memory().percent,
                    'disk_usage_percent': psutil.disk_usage('.').percent,
                    'boot_time': psutil.boot_time()
                },
                'process_count': len(psutil.pids()),
                'uptime': self._get_uptime()
            }
        except Exception as e:
            self.logger.error(f"Erreur collecte info dynamiques: {e}")
            return {}
    
    def get_gpu_info(self) -> List[Dict[str, Any]]:
        """Récupère les informations détaillées sur les GPU"""
        if self._gpu_info is not None:
            return self._gpu_info
        
        gpus = []
        
        try:
            # Tentative avec nvidia-ml-py (si GPU NVIDIA)
            try:
                import pynvml
                pynvml.nvmlInit()
                device_count = pynvml.nvmlDeviceGetCount()
                
                for i in range(device_count):
                    handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                    name = pynvml.nvmlDeviceGetName(handle).decode()
                    memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    
                    gpu_info = {
                        'id': i,
                        'name': name,
                        'vendor': 'NVIDIA',
                        'memory_total': memory_info.total,
                        'memory_total_gb': round(memory_info.total / (1024**3), 1),
                        'driver_version': pynvml.nvmlSystemGetDriverVersion().decode()
                    }
                    gpus.append(gpu_info)
                
                pynvml.nvmlShutdown()
                
            except ImportError:
                self.logger.debug("pynvml non disponible")
            except Exception as e:
                self.logger.debug(f"Erreur pynvml: {e}")
            
            # Fallback avec WMIC sur Windows
            if not gpus and platform.system() == "Windows":
                gpus = self._get_gpu_info_wmic()
            
            # Fallback générique
            if not gpus:
                gpus = [{
                    'id': 0,
                    'name': 'GPU Détecté',
                    'vendor': 'Inconnu',
                    'memory_total': 0,
                    'memory_total_gb': 0,
                    'driver_version': 'Inconnu'
                }]
            
            self._gpu_info = gpus
            self.logger.info(f"GPU détectés: {len(gpus)}")
            
            return gpus
            
        except Exception as e:
            self.logger.error(f"Erreur récupération info GPU: {e}")
            return [{
                'id': 0,
                'name': 'GPU Inconnu',
                'vendor': 'Inconnu',
                'memory_total': 0,
                'memory_total_gb': 0,
                'driver_version': 'Inconnu'
            }]
    
    def _get_gpu_info_wmic(self) -> List[Dict[str, Any]]:
        """Récupère info GPU via WMIC sur Windows"""
        try:
            result = subprocess.run([
                "wmic", "path", "win32_VideoController",
                "get", "Name,AdapterRAM,DriverVersion", "/format:csv"
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                return []
            
            gpus = []
            lines = result.stdout.strip().split('\n')[1:]  # Skip header
            
            for i, line in enumerate(lines):
                if line.strip():
                    parts = line.split(',')
                    if len(parts) >= 4:
                        name = parts[2].strip()
                        ram = parts[1].strip()
                        driver = parts[3].strip()
                        
                        if name and name != "Name":
                            gpu_info = {
                                'id': i,
                                'name': name,
                                'vendor': self._detect_gpu_vendor(name),
                                'memory_total': int(ram) if ram.isdigit() else 0,
                                'memory_total_gb': round(int(ram) / (1024**3), 1) if ram.isdigit() else 0,
                                'driver_version': driver
                            }
                            gpus.append(gpu_info)
            
            return gpus
            
        except Exception as e:
            self.logger.error(f"Erreur WMIC GPU: {e}")
            return []
    
    def _detect_gpu_vendor(self, gpu_name: str) -> str:
        """Détecte le fabricant du GPU à partir du nom"""
        gpu_name_lower = gpu_name.lower()
        
        if 'nvidia' in gpu_name_lower or 'geforce' in gpu_name_lower or 'quadro' in gpu_name_lower:
            return 'NVIDIA'
        elif 'amd' in gpu_name_lower or 'radeon' in gpu_name_lower:
            return 'AMD'
        elif 'intel' in gpu_name_lower:
            return 'Intel'
        else:
            return 'Inconnu'
    
    def _get_disk_info(self) -> List[Dict[str, Any]]:
        """Récupère les informations des disques"""
        try:
            disks = []
            partitions = psutil.disk_partitions()
            
            for partition in partitions:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disk_info = {
                        'device': partition.device,
                        'mountpoint': partition.mountpoint,
                        'fstype': partition.fstype,
                        'total': usage.total,
                        'used': usage.used,
                        'free': usage.free,
                        'percent': round((usage.used / usage.total) * 100, 1),
                        'total_gb': round(usage.total / (1024**3), 1),
                        'free_gb': round(usage.free / (1024**3), 1)
                    }
                    disks.append(disk_info)
                except PermissionError:
                    # Ignore les disques non accessibles
                    continue
            
            return disks
            
        except Exception as e:
            self.logger.error(f"Erreur info disques: {e}")
            return []
    
    def _get_network_interfaces(self) -> List[Dict[str, Any]]:
        """Récupère les informations des interfaces réseau"""
        try:
            interfaces = []
            net_if_addrs = psutil.net_if_addrs()
            net_if_stats = psutil.net_if_stats()
            
            for interface_name, addresses in net_if_addrs.items():
                interface_info = {
                    'name': interface_name,
                    'addresses': [],
                    'is_up': net_if_stats[interface_name].isup if interface_name in net_if_stats else False
                }
                
                for addr in addresses:
                    if addr.family.name in ['AF_INET', 'AF_INET6']:
                        interface_info['addresses'].append({
                            'family': addr.family.name,
                            'address': addr.address,
                            'netmask': addr.netmask
                        })
                
                interfaces.append(interface_info)
            
            return interfaces
            
        except Exception as e:
            self.logger.error(f"Erreur info réseau: {e}")
            return []
    
    def _get_uptime(self) -> float:
        """Récupère l'uptime du système en secondes"""
        try:
            import time
            return time.time() - psutil.boot_time()
        except Exception:
            return 0.0
    
    def _get_minimal_info(self) -> Dict[str, Any]:
        """Informations minimales en cas d'erreur"""
        return {
            'os': platform.system(),
            'cpu_count': psutil.cpu_count(),
            'ram_gb': round(psutil.virtual_memory().total / (1024**3), 1),
            'python_version': platform.python_version()
        }
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Récupère les métriques de performance actuelles"""
        try:
            return {
                'cpu': {
                    'percent': psutil.cpu_percent(interval=1),
                    'per_cpu': psutil.cpu_percent(percpu=True),
                    'freq': psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None
                },
                'memory': {
                    'virtual': psutil.virtual_memory()._asdict(),
                    'swap': psutil.swap_memory()._asdict()
                },
                'disk': {
                    'io': psutil.disk_io_counters()._asdict() if psutil.disk_io_counters() else None
                },
                'network': {
                    'io': psutil.net_io_counters()._asdict() if psutil.net_io_counters() else None
                },
                'processes': {
                    'count': len(psutil.pids()),
                    'top_cpu': self._get_top_processes_by_cpu(5),
                    'top_memory': self._get_top_processes_by_memory(5)
                }
            }
        except Exception as e:
            self.logger.error(f"Erreur métriques performance: {e}")
            return {}
    
    def _get_top_processes_by_cpu(self, limit: int) -> List[Dict[str, Any]]:
        """Récupère les processus qui consomment le plus de CPU"""
        try:
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
                try:
                    processes.append(proc.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # Tri par CPU
            processes.sort(key=lambda x: x['cpu_percent'] or 0, reverse=True)
            return processes[:limit]
            
        except Exception as e:
            self.logger.error(f"Erreur top CPU: {e}")
            return []
    
    def _get_top_processes_by_memory(self, limit: int) -> List[Dict[str, Any]]:
        """Récupère les processus qui consomment le plus de mémoire"""
        try:
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'memory_percent']):
                try:
                    processes.append(proc.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # Tri par mémoire
            processes.sort(key=lambda x: x['memory_percent'] or 0, reverse=True)
            return processes[:limit]
            
        except Exception as e:
            self.logger.error(f"Erreur top mémoire: {e}")
            return []
    
    def get_gpu_count(self) -> int:
        """Retourne le nombre de GPU détectés"""
        return len(self.get_gpu_info())
    
    def is_gpu_available(self) -> bool:
        """Vérifie si au moins un GPU est disponible"""
        gpus = self.get_gpu_info()
        return len(gpus) > 0 and gpus[0]['name'] != 'GPU Inconnu'
    
    def get_recommended_settings(self) -> Dict[str, Any]:
        """Recommande des paramètres basés sur le système"""
        try:
            system_info = self.get_system_info()
            
            # Recommandations basées sur les specs
            ram_gb = system_info.get('ram_gb', 4)
            cpu_count = system_info.get('cpu_count', 2)
            gpu_count = self.get_gpu_count()
            
            recommendations = {
                'max_concurrent_batches': min(2, max(1, cpu_count // 4)),
                'tile_size': 256 if ram_gb >= 8 else 128,
                'gpu_id': 0 if gpu_count > 0 else -1,  # -1 pour CPU
                'cpu_threads': max(2, min(cpu_count, 8))
            }
            
            # Ajustements pour systèmes faibles
            if ram_gb < 4:
                recommendations['max_concurrent_batches'] = 1
                recommendations['tile_size'] = 128
            
            return recommendations
            
        except Exception as e:
            self.logger.error(f"Erreur recommandations: {e}")
            return {
                'max_concurrent_batches': 1,
                'tile_size': 256,
                'gpu_id': 0,
                'cpu_threads': 4
            }