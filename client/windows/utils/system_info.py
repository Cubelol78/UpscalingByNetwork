# client/windows/utils/system_info.py
"""
Module d'informations système pour le client Windows d'upscaling distribué
"""

import os
import platform
import socket
import time
from typing import Dict, List, Optional, Any
from pathlib import Path
import logging

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

class SystemInfo:
    """Collecteur d'informations système pour le client Windows"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.start_time = time.time()
        
        if not PSUTIL_AVAILABLE:
            self.logger.warning("psutil non disponible - Informations système limitées")
    
    def get_basic_info(self) -> Dict[str, Any]:
        """Récupère les informations de base du système"""
        try:
            info = {
                'hostname': socket.gethostname(),
                'platform': platform.system(),
                'platform_release': platform.release(),
                'platform_version': platform.version(),
                'architecture': platform.architecture()[0],
                'machine': platform.machine(),
                'processor': platform.processor(),
                'python_version': platform.python_version(),
                'timestamp': time.time()
            }
            
            # Adresse IP locale
            try:
                local_ip = socket.gethostbyname(socket.gethostname())
                info['local_ip'] = local_ip
            except:
                info['local_ip'] = '127.0.0.1'
            
            return info
            
        except Exception as e:
            self.logger.error(f"Erreur récupération infos de base: {e}")
            return {
                'hostname': 'unknown',
                'platform': 'Windows',
                'local_ip': '127.0.0.1',
                'timestamp': time.time()
            }
    
    def get_hardware_info(self) -> Dict[str, Any]:
        """Récupère les informations matérielles"""
        hardware = {
            'cpu_cores': 4,  # Valeur par défaut
            'memory_total_gb': 8.0,
            'memory_available_gb': 4.0,
            'cpu_usage_percent': 0.0,
            'memory_usage_percent': 50.0
        }
        
        if PSUTIL_AVAILABLE:
            try:
                # CPU
                hardware['cpu_cores'] = psutil.cpu_count(logical=True)
                hardware['cpu_physical_cores'] = psutil.cpu_count(logical=False)
                hardware['cpu_usage_percent'] = psutil.cpu_percent(interval=1)
                
                # Mémoire
                memory = psutil.virtual_memory()
                hardware['memory_total_gb'] = round(memory.total / (1024**3), 2)
                hardware['memory_available_gb'] = round(memory.available / (1024**3), 2)
                hardware['memory_used_gb'] = round(memory.used / (1024**3), 2)
                hardware['memory_usage_percent'] = memory.percent
                
                # Fréquence CPU
                cpu_freq = psutil.cpu_freq()
                if cpu_freq:
                    hardware['cpu_frequency_mhz'] = cpu_freq.current
                    hardware['cpu_frequency_max_mhz'] = cpu_freq.max
                
            except Exception as e:
                self.logger.error(f"Erreur récupération infos matérielles: {e}")
        
        return hardware
    
    def get_gpu_info(self) -> List[Dict[str, Any]]:
        """Récupère les informations GPU"""
        gpus = []
        
        # Tentative de détection GPU NVIDIA
        try:
            import pynvml
            pynvml.nvmlInit()
            
            device_count = pynvml.nvmlDeviceGetCount()
            for i in range(device_count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                
                name = pynvml.nvmlDeviceGetName(handle).decode('utf-8')
                memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                
                gpu_info = {
                    'index': i,
                    'name': name,
                    'memory_total_mb': memory_info.total // (1024 * 1024),
                    'memory_used_mb': memory_info.used // (1024 * 1024),
                    'memory_free_mb': memory_info.free // (1024 * 1024),
                    'type': 'NVIDIA'
                }
                
                # Température si disponible
                try:
                    temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                    gpu_info['temperature_c'] = temp
                except:
                    pass
                
                # Utilisation si disponible
                try:
                    util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                    gpu_info['utilization_percent'] = util.gpu
                except:
                    pass
                
                gpus.append(gpu_info)
                
        except ImportError:
            self.logger.debug("pynvml non disponible pour les GPU NVIDIA")
        except Exception as e:
            self.logger.debug(f"Erreur détection GPU NVIDIA: {e}")
        
        # Si aucun GPU détecté, essayer une détection basique
        if not gpus:
            gpus.append({
                'index': 0,
                'name': 'GPU non détecté',
                'memory_total_mb': 0,
                'type': 'unknown'
            })
        
        return gpus
    
    def get_disk_info(self) -> Dict[str, Any]:
        """Récupère les informations disque"""
        disk_info = {
            'total_gb': 100.0,  # Valeurs par défaut
            'free_gb': 50.0,
            'used_gb': 50.0,
            'usage_percent': 50.0
        }
        
        if PSUTIL_AVAILABLE:
            try:
                # Disque principal (C: sur Windows)
                disk_usage = psutil.disk_usage('C:' if os.name == 'nt' else '/')
                
                disk_info['total_gb'] = round(disk_usage.total / (1024**3), 2)
                disk_info['free_gb'] = round(disk_usage.free / (1024**3), 2)
                disk_info['used_gb'] = round(disk_usage.used / (1024**3), 2)
                disk_info['usage_percent'] = round((disk_usage.used / disk_usage.total) * 100, 1)
                
            except Exception as e:
                self.logger.error(f"Erreur récupération infos disque: {e}")
        
        return disk_info
    
    def get_work_directory_status(self, work_dir: str = "./work") -> Dict[str, Any]:
        """Vérifie le statut du dossier de travail"""
        try:
            work_path = Path(work_dir)
            
            if not work_path.exists():
                return {
                    'exists': False,
                    'path': str(work_path.absolute()),
                    'writable': False,
                    'size_mb': 0,
                    'file_count': 0
                }
            
            # Test d'écriture
            test_file = work_path / ".write_test"
            writable = True
            try:
                test_file.write_text("test")
                test_file.unlink()
            except:
                writable = False
            
            # Taille et nombre de fichiers
            total_size = 0
            file_count = 0
            
            try:
                for item in work_path.rglob('*'):
                    if item.is_file():
                        total_size += item.stat().st_size
                        file_count += 1
            except Exception as e:
                self.logger.debug(f"Erreur calcul taille dossier: {e}")
            
            return {
                'exists': True,
                'path': str(work_path.absolute()),
                'writable': writable,
                'size_mb': round(total_size / (1024 * 1024), 2),
                'file_count': file_count
            }
            
        except Exception as e:
            self.logger.error(f"Erreur vérification dossier de travail: {e}")
            return {
                'exists': False,
                'path': work_dir,
                'writable': False,
                'size_mb': 0,
                'file_count': 0,
                'error': str(e)
            }
    
    def get_performance_capabilities(self) -> Dict[str, Any]:
        """Évalue les capacités de performance du client"""
        capabilities = {
            'processing_power': 'medium',  # low, medium, high
            'memory_adequate': True,
            'disk_space_adequate': True,
            'gpu_available': False,
            'recommended_batch_size': 25,
            'max_concurrent_batches': 2
        }
        
        try:
            hardware = self.get_hardware_info()
            gpus = self.get_gpu_info()
            disk = self.get_disk_info()
            
            # Évaluation CPU
            cpu_cores = hardware.get('cpu_cores', 4)
            if cpu_cores >= 8:
                capabilities['processing_power'] = 'high'
                capabilities['recommended_batch_size'] = 50
                capabilities['max_concurrent_batches'] = 3
            elif cpu_cores >= 4:
                capabilities['processing_power'] = 'medium'
                capabilities['recommended_batch_size'] = 30
                capabilities['max_concurrent_batches'] = 2
            else:
                capabilities['processing_power'] = 'low'
                capabilities['recommended_batch_size'] = 15
                capabilities['max_concurrent_batches'] = 1
            
            # Évaluation mémoire
            memory_gb = hardware.get('memory_total_gb', 8)
            capabilities['memory_adequate'] = memory_gb >= 8
            
            # Évaluation espace disque
            free_gb = disk.get('free_gb', 50)
            capabilities['disk_space_adequate'] = free_gb >= 10  # 10GB minimum
            
            # Évaluation GPU
            for gpu in gpus:
                if gpu.get('name', '').lower() != 'gpu non détecté':
                    capabilities['gpu_available'] = True
                    # Bonus pour GPU
                    capabilities['recommended_batch_size'] += 10
                    break
            
        except Exception as e:
            self.logger.error(f"Erreur évaluation capacités: {e}")
        
        return capabilities
    
    def get_network_status(self) -> Dict[str, Any]:
        """Récupère le statut réseau"""
        network = {
            'connected': False,
            'local_ip': '127.0.0.1',
            'interfaces': []
        }
        
        try:
            # Test de connectivité basique
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            network['connected'] = True
        except:
            network['connected'] = False
        
        # Adresse IP locale
        try:
            network['local_ip'] = socket.gethostbyname(socket.gethostname())
        except:
            pass
        
        # Interfaces réseau si psutil disponible
        if PSUTIL_AVAILABLE:
            try:
                for interface_name, interface_addresses in psutil.net_if_addrs().items():
                    for address in interface_addresses:
                        if address.family == socket.AF_INET:  # IPv4
                            network['interfaces'].append({
                                'name': interface_name,
                                'ip': address.address,
                                'netmask': address.netmask
                            })
            except Exception as e:
                self.logger.debug(f"Erreur récupération interfaces: {e}")
        
        return network
    
    def get_client_identifier(self) -> str:
        """Génère un identifiant unique pour le client"""
        try:
            # Utilise l'adresse MAC comme identifiant
            if PSUTIL_AVAILABLE:
                # Première interface avec une adresse MAC
                for interface_name, interface_stats in psutil.net_if_stats().items():
                    if hasattr(interface_stats, 'address') and interface_stats.address:
                        mac_address = interface_stats.address
                        if mac_address != '00:00:00:00:00:00':
                            return mac_address.replace(':', '').upper()
            
            # Fallback: combinaison hostname + platform
            hostname = socket.gethostname()
            platform_info = platform.machine()
            return f"{hostname}_{platform_info}".replace(' ', '_').upper()
            
        except Exception as e:
            self.logger.error(f"Erreur génération identifiant client: {e}")
            # Identifiant d'urgence basé sur le timestamp
            return f"CLIENT_{int(time.time())}"
    
    def get_complete_system_info(self) -> Dict[str, Any]:
        """Récupère toutes les informations système du client"""
        return {
            'timestamp': time.time(),
            'client_id': self.get_client_identifier(),
            'basic_info': self.get_basic_info(),
            'hardware': self.get_hardware_info(),
            'gpus': self.get_gpu_info(),
            'disk': self.get_disk_info(),
            'network': self.get_network_status(),
            'capabilities': self.get_performance_capabilities(),
            'work_directory': self.get_work_directory_status(),
            'uptime_seconds': time.time() - self.start_time,
            'psutil_available': PSUTIL_AVAILABLE
        }
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Récupère un résumé de statut pour l'interface"""
        try:
            hardware = self.get_hardware_info()
            disk = self.get_disk_info()
            network = self.get_network_status()
            capabilities = self.get_performance_capabilities()
            
            return {
                'ready': (
                    capabilities['memory_adequate'] and 
                    capabilities['disk_space_adequate'] and 
                    network['connected']
                ),
                'cpu_usage': hardware.get('cpu_usage_percent', 0),
                'memory_usage': hardware.get('memory_usage_percent', 0),
                'disk_free_gb': disk.get('free_gb', 0),
                'network_connected': network['connected'],
                'gpu_available': capabilities['gpu_available'],
                'recommended_batch_size': capabilities['recommended_batch_size'],
                'processing_power': capabilities['processing_power']
            }
            
        except Exception as e:
            self.logger.error(f"Erreur résumé statut: {e}")
            return {
                'ready': False,
                'error': str(e)
            }
    
    def monitor_resources(self, duration: float = 60.0, interval: float = 5.0) -> Dict[str, List]:
        """Surveille les ressources pendant une durée donnée"""
        monitoring_data = {
            'timestamps': [],
            'cpu_percent': [],
            'memory_percent': [],
            'disk_free_gb': []
        }
        
        if not PSUTIL_AVAILABLE:
            self.logger.warning("Surveillance impossible sans psutil")
            return monitoring_data
        
        start_time = time.time()
        
        try:
            while time.time() - start_time < duration:
                current_time = time.time()
                
                # CPU
                cpu_percent = psutil.cpu_percent(interval=1)
                
                # Mémoire
                memory = psutil.virtual_memory()
                memory_percent = memory.percent
                
                # Disque
                disk_usage = psutil.disk_usage('C:' if os.name == 'nt' else '/')
                disk_free_gb = disk_usage.free / (1024**3)
                
                # Enregistrement
                monitoring_data['timestamps'].append(current_time)
                monitoring_data['cpu_percent'].append(cpu_percent)
                monitoring_data['memory_percent'].append(memory_percent)
                monitoring_data['disk_free_gb'].append(round(disk_free_gb, 2))
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            self.logger.info("Surveillance interrompue")
        except Exception as e:
            self.logger.error(f"Erreur surveillance: {e}")
        
        return monitoring_data