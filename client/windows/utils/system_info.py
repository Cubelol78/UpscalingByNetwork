# client/windows/utils/system_info.py
"""
Collecte d'informations système pour le client
"""

import os
import sys
import platform
import psutil
import socket
import uuid
import subprocess
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

class SystemInfo:
    """
    Collecteur d'informations système pour le client
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._system_info = None
        self._gpu_info = None
        self._refresh_interval = 300  # 5 minutes
        self._last_refresh = 0
    
    def get_system_info(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Collecte les informations système complètes
        
        Args:
            force_refresh: Force la collecte même si les données sont récentes
            
        Returns:
            Dictionnaire avec toutes les informations système
        """
        import time
        current_time = time.time()
        
        if (not force_refresh and 
            self._system_info and 
            current_time - self._last_refresh < self._refresh_interval):
            return self._system_info
        
        try:
            self._system_info = {
                'basic': self._get_basic_info(),
                'hardware': self._get_hardware_info(),
                'network': self._get_network_info(),
                'gpu': self._get_gpu_info(),
                'performance': self._get_performance_info(),
                'storage': self._get_storage_info(),
                'vulkan': self._check_vulkan_support()
            }
            
            self._last_refresh = current_time
            self.logger.info("Informations système collectées")
            
        except Exception as e:
            self.logger.error(f"Erreur collecte informations système: {e}")
            self._system_info = self._get_minimal_info()
        
        return self._system_info
    
    def _get_basic_info(self) -> Dict[str, Any]:
        """Informations système de base"""
        return {
            'platform': platform.system(),
            'platform_version': platform.version(),
            'platform_release': platform.release(),
            'architecture': platform.architecture()[0],
            'machine': platform.machine(),
            'processor': platform.processor(),
            'hostname': socket.gethostname(),
            'python_version': sys.version,
            'python_executable': sys.executable,
            'current_user': os.getenv('USERNAME' if os.name == 'nt' else 'USER', 'unknown')
        }
    
    def _get_hardware_info(self) -> Dict[str, Any]:
        """Informations matérielles"""
        try:
            # Informations CPU
            cpu_info = {
                'physical_cores': psutil.cpu_count(logical=False),
                'logical_cores': psutil.cpu_count(logical=True),
                'max_frequency': psutil.cpu_freq().max if psutil.cpu_freq() else 0,
                'current_frequency': psutil.cpu_freq().current if psutil.cpu_freq() else 0,
                'cpu_usage_percent': psutil.cpu_percent(interval=1)
            }
            
            # Informations mémoire
            memory = psutil.virtual_memory()
            memory_info = {
                'total_ram_gb': round(memory.total / (1024**3), 2),
                'available_ram_gb': round(memory.available / (1024**3), 2),
                'used_ram_gb': round(memory.used / (1024**3), 2),
                'ram_usage_percent': memory.percent
            }
            
            return {
                'cpu': cpu_info,
                'memory': memory_info
            }
            
        except Exception as e:
            self.logger.error(f"Erreur collecte informations matérielles: {e}")
            return {'cpu': {}, 'memory': {}}
    
    def _get_network_info(self) -> Dict[str, Any]:
        """Informations réseau"""
        try:
            # Adresse MAC
            mac_address = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff) 
                                   for elements in range(0, 2*6, 2)][::-1])
            
            # Adresses IP
            ip_addresses = []
            for interface_name, interface_addresses in psutil.net_if_addrs().items():
                for address in interface_addresses:
                    if address.family == socket.AF_INET and not address.address.startswith('127.'):
                        ip_addresses.append({
                            'interface': interface_name,
                            'ip': address.address,
                            'netmask': address.netmask,
                            'broadcast': address.broadcast
                        })
            
            return {
                'mac_address': mac_address,
                'ip_addresses': ip_addresses,
                'hostname': socket.gethostname(),
                'fqdn': socket.getfqdn()
            }
            
        except Exception as e:
            self.logger.error(f"Erreur collecte informations réseau: {e}")
            return {
                'mac_address': 'unknown',
                'ip_addresses': [],
                'hostname': 'unknown',
                'fqdn': 'unknown'
            }
    
    def _get_gpu_info(self) -> Dict[str, Any]:
        """Informations GPU (NVIDIA, AMD, Intel)"""
        gpu_info = {
            'nvidia_gpus': [],
            'other_gpus': [],
            'vulkan_devices': []
        }
        
        try:
            # Tentative de collecte via nvidia-ml-py (NVIDIA)
            try:
                import pynvml
                pynvml.nvmlInit()
                device_count = pynvml.nvmlDeviceGetCount()
                
                for i in range(device_count):
                    handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                    name = pynvml.nvmlDeviceGetName(handle).decode('utf-8')
                    memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    
                    gpu_info['nvidia_gpus'].append({
                        'index': i,
                        'name': name,
                        'memory_total_mb': memory_info.total // (1024*1024),
                        'memory_used_mb': memory_info.used // (1024*1024),
                        'memory_free_mb': memory_info.free // (1024*1024),
                        'driver_version': pynvml.nvmlSystemGetDriverVersion().decode('utf-8')
                    })
                    
            except ImportError:
                self.logger.info("pynvml non disponible - informations NVIDIA limitées")
            except Exception as e:
                self.logger.error(f"Erreur collecte GPU NVIDIA: {e}")
            
            # Collecte via wmi sur Windows
            if sys.platform == "win32":
                try:
                    import wmi
                    c = wmi.WMI()
                    for gpu in c.Win32_VideoController():
                        if gpu.Name:
                            gpu_info['other_gpus'].append({
                                'name': gpu.Name,
                                'driver_version': gpu.DriverVersion,
                                'memory_mb': gpu.AdapterRAM // (1024*1024) if gpu.AdapterRAM else 0,
                                'status': gpu.Status
                            })
                except ImportError:
                    self.logger.info("wmi non disponible")
                except Exception as e:
                    self.logger.error(f"Erreur collecte GPU Windows: {e}")
            
            # Collecte des dispositifs Vulkan
            gpu_info['vulkan_devices'] = self._get_vulkan_devices()
            
        except Exception as e:
            self.logger.error(f"Erreur générale collecte GPU: {e}")
        
        return gpu_info
    
    def _get_vulkan_devices(self) -> List[Dict[str, Any]]:
        """Collecte les dispositifs Vulkan disponibles"""
        devices = []
        
        try:
            # Tentative d'utilisation de vulkan via subprocess
            if sys.platform == "win32":
                vulkan_info_cmd = ["vulkaninfo", "--summary"]
            else:
                vulkan_info_cmd = ["vulkaninfo", "--summary"]
            
            result = subprocess.run(vulkan_info_cmd, 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=10)
            
            if result.returncode == 0:
                # Parse simple du résultat vulkaninfo
                lines = result.stdout.split('\n')
                current_device = {}
                
                for line in lines:
                    line = line.strip()
                    if 'GPU' in line and 'Device Name' in line:
                        if current_device:
                            devices.append(current_device)
                        current_device = {'name': line.split(':')[-1].strip()}
                    elif 'Device Type' in line and current_device:
                        current_device['type'] = line.split(':')[-1].strip()
                    elif 'Driver Version' in line and current_device:
                        current_device['driver_version'] = line.split(':')[-1].strip()
                
                if current_device:
                    devices.append(current_device)
                    
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            self.logger.info("vulkaninfo non disponible ou échec")
        except Exception as e:
            self.logger.error(f"Erreur collecte dispositifs Vulkan: {e}")
        
        return devices
    
    def _get_performance_info(self) -> Dict[str, Any]:
        """Informations de performance actuelles"""
        try:
            # Utilisation CPU sur 1 seconde
            cpu_percent = psutil.cpu_percent(interval=1, percpu=True)
            
            # Utilisation mémoire
            memory = psutil.virtual_memory()
            
            # Utilisation disque
            disk_usage = psutil.disk_usage('/')
            
            # Charge système
            if hasattr(os, 'getloadavg'):
                load_avg = os.getloadavg()
            else:
                load_avg = (0, 0, 0)  # Windows n'a pas getloadavg
            
            return {
                'cpu_percent_per_core': cpu_percent,
                'cpu_percent_total': sum(cpu_percent) / len(cpu_percent),
                'memory_percent': memory.percent,
                'disk_percent': (disk_usage.used / disk_usage.total) * 100,
                'load_average': {
                    '1min': load_avg[0],
                    '5min': load_avg[1],
                    '15min': load_avg[2]
                },
                'process_count': len(psutil.pids())
            }
            
        except Exception as e:
            self.logger.error(f"Erreur collecte informations performance: {e}")
            return {}
    
    def _get_storage_info(self) -> Dict[str, Any]:
        """Informations de stockage"""
        try:
            storage_info = {
                'drives': [],
                'total_space_gb': 0,
                'free_space_gb': 0
            }
            
            # Collecte des disques
            partitions = psutil.disk_partitions()
            
            for partition in partitions:
                try:
                    partition_usage = psutil.disk_usage(partition.mountpoint)
                    
                    drive_info = {
                        'device': partition.device,
                        'mountpoint': partition.mountpoint,
                        'filesystem': partition.fstype,
                        'total_gb': round(partition_usage.total / (1024**3), 2),
                        'used_gb': round(partition_usage.used / (1024**3), 2),
                        'free_gb': round(partition_usage.free / (1024**3), 2),
                        'percent_used': round((partition_usage.used / partition_usage.total) * 100, 2)
                    }
                    
                    storage_info['drives'].append(drive_info)
                    storage_info['total_space_gb'] += drive_info['total_gb']
                    storage_info['free_space_gb'] += drive_info['free_gb']
                    
                except PermissionError:
                    # Ignorer les partitions non accessibles
                    continue
                    
            return storage_info
            
        except Exception as e:
            self.logger.error(f"Erreur collecte informations stockage: {e}")
            return {'drives': [], 'total_space_gb': 0, 'free_space_gb': 0}
    
    def _check_vulkan_support(self) -> Dict[str, Any]:
        """Vérifie le support Vulkan"""
        vulkan_info = {
            'supported': False,
            'version': None,
            'instance_extensions': [],
            'device_extensions': []
        }
        
        try:
            # Vérification simple via vulkaninfo
            result = subprocess.run(['vulkaninfo', '--summary'], 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=5)
            
            if result.returncode == 0:
                vulkan_info['supported'] = True
                
                # Parse des informations version
                for line in result.stdout.split('\n'):
                    if 'Vulkan Instance Version' in line:
                        vulkan_info['version'] = line.split(':')[-1].strip()
                        break
                        
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            vulkan_info['supported'] = False
        except Exception as e:
            self.logger.error(f"Erreur vérification support Vulkan: {e}")
            vulkan_info['supported'] = False
        
        return vulkan_info
    
    def _get_minimal_info(self) -> Dict[str, Any]:
        """Informations minimales en cas d'erreur"""
        return {
            'basic': {
                'platform': platform.system(),
                'hostname': socket.gethostname(),
                'python_version': sys.version
            },
            'hardware': {'cpu': {}, 'memory': {}},
            'network': {'mac_address': 'unknown', 'ip_addresses': []},
            'gpu': {'nvidia_gpus': [], 'other_gpus': [], 'vulkan_devices': []},
            'performance': {},
            'storage': {'drives': []},
            'vulkan': {'supported': False}
        }
    
    def get_mac_address(self) -> str:
        """Retourne l'adresse MAC formatée"""
        try:
            mac = uuid.getnode()
            mac_str = ':'.join(['{:02x}'.format((mac >> elements) & 0xff) 
                               for elements in range(0, 2*6, 2)][::-1])
            return mac_str.upper()
        except:
            return "00:00:00:00:00:00"
    
    def get_primary_ip(self) -> str:
        """Retourne l'IP principale (non-localhost)"""
        try:
            system_info = self.get_system_info()
            ip_addresses = system_info.get('network', {}).get('ip_addresses', [])
            
            for ip_info in ip_addresses:
                ip = ip_info.get('ip', '')
                if ip and not ip.startswith('127.') and not ip.startswith('169.254.'):
                    return ip
            
            return '127.0.0.1'
            
        except:
            return '127.0.0.1'
    
    def get_cpu_count(self) -> int:
        """Retourne le nombre de cœurs CPU logiques"""
        try:
            return psutil.cpu_count(logical=True) or 1
        except:
            return 1
    
    def get_memory_gb(self) -> float:
        """Retourne la quantité de RAM en GB"""
        try:
            return round(psutil.virtual_memory().total / (1024**3), 2)
        except:
            return 0.0
    
    def is_gpu_available(self) -> bool:
        """Vérifie si un GPU est disponible"""
        try:
            system_info = self.get_system_info()
            gpu_info = system_info.get('gpu', {})
            
            has_nvidia = len(gpu_info.get('nvidia_gpus', [])) > 0
            has_other = len(gpu_info.get('other_gpus', [])) > 0
            has_vulkan = len(gpu_info.get('vulkan_devices', [])) > 0
            
            return has_nvidia or has_other or has_vulkan
            
        except:
            return False
    
    def get_performance_score(self) -> float:
        """
        Calcule un score de performance approximatif basé sur le matériel
        Score de 0 à 100
        """
        try:
            system_info = self.get_system_info()
            score = 0.0
            
            # Score CPU (40% du total)
            cpu_cores = system_info.get('hardware', {}).get('cpu', {}).get('logical_cores', 1)
            cpu_freq = system_info.get('hardware', {}).get('cpu', {}).get('max_frequency', 1000)
            cpu_score = min(40, (cpu_cores * cpu_freq / 1000) / 10)
            score += cpu_score
            
            # Score RAM (30% du total)
            ram_gb = system_info.get('hardware', {}).get('memory', {}).get('total_ram_gb', 1)
            ram_score = min(30, ram_gb * 2)
            score += ram_score
            
            # Score GPU (30% du total)
            gpu_info = system_info.get('gpu', {})
            if gpu_info.get('nvidia_gpus'):
                score += 30  # GPU NVIDIA = score maximum
            elif gpu_info.get('vulkan_devices'):
                score += 20  # Support Vulkan = bon score
            elif gpu_info.get('other_gpus'):
                score += 10  # Autre GPU = score moyen
            
            return min(100.0, score)
            
        except:
            return 50.0  # Score par défaut