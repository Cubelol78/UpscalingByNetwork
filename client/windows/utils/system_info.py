# client-windows/src/utils/system_info.py
import platform
import subprocess
import logging
import uuid
import sys
from typing import Dict, Optional, List
import json

# Imports optionnels avec gestion d'erreur
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import pynvml
    PYNVML_AVAILABLE = True
except ImportError:
    PYNVML_AVAILABLE = False

class SystemInfo:
    """Collecteur d'informations système pour le client"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._gpu_info_cache = None
        self._memory_info_cache = None
        self._cpu_info_cache = None
        
        self.logger.debug("SystemInfo initialisé")
    
    def get_mac_address(self) -> str:
        """Retourne l'adresse MAC de la machine"""
        try:
            # Récupération de l'adresse MAC de la première interface réseau
            mac = uuid.UUID(int=uuid.getnode()).hex[-12:]
            formatted_mac = ":".join([mac[i:i+2] for i in range(0, 12, 2)])
            return formatted_mac.upper()
        except Exception as e:
            self.logger.error(f"Erreur récupération MAC: {e}")
            return "00:00:00:00:00:00"
    
    def get_os_info(self) -> Dict[str, str]:
        """Retourne les informations du système d'exploitation"""
        try:
            return {
                'system': platform.system(),
                'release': platform.release(),
                'version': platform.version(),
                'architecture': platform.architecture()[0],
                'machine': platform.machine(),
                'processor': platform.processor(),
                'python_version': platform.python_version()
            }
        except Exception as e:
            self.logger.error(f"Erreur info OS: {e}")
            return {'system': 'Unknown', 'error': str(e)}
    
    def get_cpu_info(self) -> Dict:
        """Retourne les informations du processeur"""
        if self._cpu_info_cache:
            return self._cpu_info_cache
        
        try:
            cpu_info = {
                'model': platform.processor(),
                'architecture': platform.machine(),
                'cores_physical': 1,
                'cores_logical': 1,
                'frequency_mhz': 0
            }
            
            if PSUTIL_AVAILABLE:
                cpu_info.update({
                    'cores_physical': psutil.cpu_count(logical=False) or 1,
                    'cores_logical': psutil.cpu_count(logical=True) or 1,
                    'frequency_mhz': psutil.cpu_freq().current if psutil.cpu_freq() else 0
                })
            
            # Tentative d'amélioration avec des commandes système
            self._enhance_cpu_info_with_system_commands(cpu_info)
            
            self._cpu_info_cache = cpu_info
            return cpu_info
            
        except Exception as e:
            self.logger.error(f"Erreur info CPU: {e}")
            return {'model': 'Unknown', 'cores': 1, 'error': str(e)}
    
    def _enhance_cpu_info_with_system_commands(self, cpu_info: Dict):
        """Améliore les infos CPU avec des commandes système"""
        try:
            if sys.platform == "win32":
                # Windows: utilisation de wmic
                result = subprocess.run([
                    'wmic', 'cpu', 'get', 'Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed',
                    '/format:csv'
                ], capture_output=True, text=True, timeout=5)
                
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    if len(lines) > 1:
                        # Parsing basique des résultats wmic
                        for line in lines[1:]:
                            if line.strip():
                                parts = line.split(',')
                                if len(parts) >= 4:
                                    try:
                                        cpu_info['model'] = parts[2] if parts[2] else cpu_info['model']
                                        cpu_info['cores_physical'] = int(parts[3]) if parts[3] else cpu_info['cores_physical']
                                        cpu_info['frequency_mhz'] = int(parts[1]) if parts[1] else cpu_info['frequency_mhz']
                                    except (ValueError, IndexError):
                                        pass
            
            elif sys.platform.startswith("linux"):
                # Linux: utilisation de /proc/cpuinfo
                with open('/proc/cpuinfo', 'r') as f:
                    cpuinfo = f.read()
                
                # Extraction du nom du processeur
                for line in cpuinfo.split('\n'):
                    if 'model name' in line:
                        cpu_info['model'] = line.split(':')[1].strip()
                        break
                
        except Exception as e:
            self.logger.debug(f"Impossible d'améliorer les infos CPU: {e}")
    
    def get_memory_info(self) -> Dict:
        """Retourne les informations mémoire"""
        if self._memory_info_cache:
            return self._memory_info_cache
        
        try:
            memory_info = {
                'total_gb': 4.0,  # Valeur par défaut
                'available_gb': 2.0,
                'used_gb': 2.0,
                'usage_percent': 50.0
            }
            
            if PSUTIL_AVAILABLE:
                memory = psutil.virtual_memory()
                memory_info.update({
                    'total_gb': round(memory.total / (1024**3), 2),
                    'available_gb': round(memory.available / (1024**3), 2),
                    'used_gb': round(memory.used / (1024**3), 2),
                    'usage_percent': memory.percent
                })
            else:
                # Fallback avec commandes système
                self._get_memory_info_fallback(memory_info)
            
            self._memory_info_cache = memory_info
            return memory_info
            
        except Exception as e:
            self.logger.error(f"Erreur info mémoire: {e}")
            return {'total_gb': 4.0, 'error': str(e)}
    
    def _get_memory_info_fallback(self, memory_info: Dict):
        """Récupère les infos mémoire sans psutil"""
        try:
            if sys.platform == "win32":
                # Windows: utilisation de wmic
                result = subprocess.run([
                    'wmic', 'computersystem', 'get', 'TotalPhysicalMemory', '/value'
                ], capture_output=True, text=True, timeout=5)
                
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'TotalPhysicalMemory=' in line:
                            total_bytes = int(line.split('=')[1])
                            memory_info['total_gb'] = round(total_bytes / (1024**3), 2)
                            memory_info['available_gb'] = round(memory_info['total_gb'] * 0.5, 2)
                            break
            
            elif sys.platform.startswith("linux"):
                # Linux: utilisation de /proc/meminfo
                with open('/proc/meminfo', 'r') as f:
                    meminfo = f.read()
                
                for line in meminfo.split('\n'):
                    if 'MemTotal:' in line:
                        total_kb = int(line.split()[1])
                        memory_info['total_gb'] = round(total_kb / (1024**2), 2)
                    elif 'MemAvailable:' in line:
                        available_kb = int(line.split()[1])
                        memory_info['available_gb'] = round(available_kb / (1024**2), 2)
        
        except Exception as e:
            self.logger.debug(f"Fallback mémoire échoué: {e}")
    
    def get_gpu_info(self) -> Optional[Dict]:
        """Retourne les informations GPU (NVIDIA prioritaire)"""
        if self._gpu_info_cache:
            return self._gpu_info_cache
        
        gpu_info = None
        
        # Tentative NVIDIA avec pynvml
        if PYNVML_AVAILABLE:
            gpu_info = self._get_nvidia_gpu_info()
        
        # Fallback avec nvidia-smi
        if not gpu_info:
            gpu_info = self._get_gpu_info_nvidia_smi()
        
        # Fallback avec commandes système génériques
        if not gpu_info:
            gpu_info = self._get_gpu_info_fallback()
        
        self._gpu_info_cache = gpu_info
        return gpu_info
    
    def _get_nvidia_gpu_info(self) -> Optional[Dict]:
        """Récupère les infos GPU NVIDIA avec pynvml"""
        try:
            pynvml.nvmlInit()
            device_count = pynvml.nvmlDeviceGetCount()
            
            if device_count > 0:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)  # Premier GPU
                
                name = pynvml.nvmlDeviceGetName(handle).decode('utf-8')
                memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                
                return {
                    'name': name,
                    'memory_mb': round(memory_info.total / (1024**2)),
                    'memory_free_mb': round(memory_info.free / (1024**2)),
                    'memory_used_mb': round(memory_info.used / (1024**2)),
                    'driver_version': pynvml.nvmlSystemGetDriverVersion().decode('utf-8'),
                    'vendor': 'NVIDIA',
                    'index': 0
                }
                
        except Exception as e:
            self.logger.debug(f"Erreur pynvml GPU: {e}")
            return None
    
    def _get_gpu_info_nvidia_smi(self) -> Optional[Dict]:
        """Récupère les infos GPU avec nvidia-smi"""
        try:
            result = subprocess.run([
                'nvidia-smi', '--query-gpu=name,memory.total,memory.free,memory.used,driver_version',
                '--format=csv,noheader,nounits'
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and result.stdout.strip():
                line = result.stdout.strip().split('\n')[0]
                parts = [p.strip() for p in line.split(',')]
                
                if len(parts) >= 4:
                    return {
                        'name': parts[0],
                        'memory_mb': int(parts[1]),
                        'memory_free_mb': int(parts[2]),
                        'memory_used_mb': int(parts[3]),
                        'driver_version': parts[4] if len(parts) > 4 else 'Unknown',
                        'vendor': 'NVIDIA',
                        'index': 0
                    }
        
        except Exception as e:
            self.logger.debug(f"Erreur nvidia-smi: {e}")
            return None
    
    def _get_gpu_info_fallback(self) -> Optional[Dict]:
        """Récupère les infos GPU avec méthodes génériques"""
        try:
            if sys.platform == "win32":
                # Windows: utilisation de wmic
                result = subprocess.run([
                    'wmic', 'path', 'win32_VideoController', 'get', 
                    'Name,AdapterRAM', '/format:csv'
                ], capture_output=True, text=True, timeout=10)
                
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    for line in lines[1:]:
                        if line.strip():
                            parts = line.split(',')
                            if len(parts) >= 3 and parts[1] and parts[2]:
                                try:
                                    memory_bytes = int(parts[1])
                                    memory_mb = round(memory_bytes / (1024**2))
                                    
                                    return {
                                        'name': parts[2],
                                        'memory_mb': memory_mb,
                                        'vendor': 'Unknown',
                                        'index': 0
                                    }
                                except (ValueError, IndexError):
                                    continue
            
            elif sys.platform.startswith("linux"):
                # Linux: utilisation de lspci
                result = subprocess.run([
                    'lspci', '-mm'
                ], capture_output=True, text=True, timeout=5)
                
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'VGA' in line or 'Display' in line:
                            # Parsing basique des résultats lspci
                            if 'NVIDIA' in line or 'AMD' in line or 'Intel' in line:
                                return {
                                    'name': line.split('"')[5] if '"' in line else 'GPU détecté',
                                    'memory_mb': 0,  # Non disponible via lspci
                                    'vendor': 'Detected',
                                    'index': 0
                                }
        
        except Exception as e:
            self.logger.debug(f"Fallback GPU échoué: {e}")
        
        return None
    
    def get_disk_info(self) -> Dict:
        """Retourne les informations de stockage"""
        try:
            disk_info = {
                'total_gb': 100.0,
                'free_gb': 50.0,
                'used_gb': 50.0,
                'usage_percent': 50.0
            }
            
            if PSUTIL_AVAILABLE:
                disk_usage = psutil.disk_usage('/')
                disk_info.update({
                    'total_gb': round(disk_usage.total / (1024**3), 2),
                    'free_gb': round(disk_usage.free / (1024**3), 2),
                    'used_gb': round(disk_usage.used / (1024**3), 2),
                    'usage_percent': round((disk_usage.used / disk_usage.total) * 100, 2)
                })
            
            return disk_info
            
        except Exception as e:
            self.logger.error(f"Erreur info disque: {e}")
            return {'total_gb': 100.0, 'error': str(e)}
    
    def get_network_info(self) -> Dict:
        """Retourne les informations réseau"""
        try:
            network_info = {
                'hostname': platform.node(),
                'mac_address': self.get_mac_address(),
                'interfaces': []
            }
            
            if PSUTIL_AVAILABLE:
                # Récupération des interfaces réseau
                net_if_addrs = psutil.net_if_addrs()
                for interface, addresses in net_if_addrs.items():
                    interface_info = {'name': interface, 'addresses': []}
                    
                    for addr in addresses:
                        interface_info['addresses'].append({
                            'family': str(addr.family),
                            'address': addr.address,
                            'netmask': addr.netmask
                        })
                    
                    network_info['interfaces'].append(interface_info)
            
            return network_info
            
        except Exception as e:
            self.logger.error(f"Erreur info réseau: {e}")
            return {'hostname': 'Unknown', 'mac_address': self.get_mac_address()}
    
    def get_complete_system_info(self) -> Dict:
        """Retourne toutes les informations système"""
        return {
            'os': self.get_os_info(),
            'cpu': self.get_cpu_info(),
            'memory': self.get_memory_info(),
            'gpu': self.get_gpu_info(),
            'disk': self.get_disk_info(),
            'network': self.get_network_info(),
            'capabilities': self.get_processing_capabilities()
        }
    
    def get_processing_capabilities(self) -> Dict:
        """Évalue les capacités de traitement de la machine"""
        cpu_info = self.get_cpu_info()
        memory_info = self.get_memory_info()
        gpu_info = self.get_gpu_info()
        
        # Score de performance basé sur les composants
        performance_score = 0
        
        # Score CPU (0-30 points)
        cpu_cores = cpu_info.get('cores_logical', 1)
        performance_score += min(cpu_cores * 3, 30)
        
        # Score mémoire (0-20 points)
        memory_gb = memory_info.get('total_gb', 0)
        performance_score += min(memory_gb * 2, 20)
        
        # Score GPU (0-50 points)
        if gpu_info:
            gpu_memory = gpu_info.get('memory_mb', 0)
            if 'RTX' in gpu_info.get('name', '').upper():
                performance_score += min(gpu_memory / 100, 50)  # RTX = bonus
            else:
                performance_score += min(gpu_memory / 200, 25)  # Autres GPU
        
        # Détermination du niveau de performance
        if performance_score >= 80:
            performance_tier = 'high'
            recommended_batch_size = 50
        elif performance_score >= 50:
            performance_tier = 'medium'
            recommended_batch_size = 35
        else:
            performance_tier = 'low'
            recommended_batch_size = 20
        
        return {
            'performance_score': round(performance_score, 2),
            'performance_tier': performance_tier,
            'recommended_batch_size': recommended_batch_size,
            'has_gpu': gpu_info is not None,
            'gpu_suitable_for_ai': gpu_info is not None and gpu_info.get('memory_mb', 0) >= 2048,
            'estimated_time_per_frame': self._estimate_processing_time_per_frame(performance_score)
        }
    
    def _estimate_processing_time_per_frame(self, performance_score: float) -> float:
        """Estime le temps de traitement par frame en secondes"""
        if performance_score >= 80:
            return 1.0  # Machine puissante
        elif performance_score >= 50:
            return 2.5  # Machine moyenne
        else:
            return 5.0  # Machine faible
    
    def refresh_cache(self):
        """Rafraîchit le cache des informations système"""
        self._gpu_info_cache = None
        self._memory_info_cache = None
        self._cpu_info_cache = None
        self.logger.debug("Cache informations système rafraîchi")