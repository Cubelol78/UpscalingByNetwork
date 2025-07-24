# server/utils/system_info.py
"""
Module d'informations système pour le serveur d'upscaling distribué
"""

import os
import platform
import psutil
import socket
import time
from typing import Dict, List, Optional, Any
from pathlib import Path
import logging

class SystemInfo:
    """Collecteur d'informations système pour le serveur"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.start_time = time.time()
        
    def get_cpu_info(self) -> Dict[str, Any]:
        """Récupère les informations CPU"""
        try:
            return {
                'physical_cores': psutil.cpu_count(logical=False),
                'logical_cores': psutil.cpu_count(logical=True),
                'current_frequency': psutil.cpu_freq().current if psutil.cpu_freq() else 0,
                'max_frequency': psutil.cpu_freq().max if psutil.cpu_freq() else 0,
                'usage_percent': psutil.cpu_percent(interval=1),
                'architecture': platform.architecture()[0],
                'processor': platform.processor()
            }
        except Exception as e:
            self.logger.error(f"Erreur récupération info CPU: {e}")
            return {
                'physical_cores': 4,
                'logical_cores': 8,
                'current_frequency': 0,
                'max_frequency': 0,
                'usage_percent': 0,
                'architecture': 'unknown',
                'processor': 'unknown'
            }
    
    def get_memory_info(self) -> Dict[str, Any]:
        """Récupère les informations mémoire"""
        try:
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            return {
                'total_gb': round(memory.total / (1024**3), 2),
                'available_gb': round(memory.available / (1024**3), 2),
                'used_gb': round(memory.used / (1024**3), 2),
                'usage_percent': memory.percent,
                'swap_total_gb': round(swap.total / (1024**3), 2),
                'swap_used_gb': round(swap.used / (1024**3), 2),
                'swap_percent': swap.percent
            }
        except Exception as e:
            self.logger.error(f"Erreur récupération info mémoire: {e}")
            return {
                'total_gb': 8.0,
                'available_gb': 4.0,
                'used_gb': 4.0,
                'usage_percent': 50.0,
                'swap_total_gb': 0.0,
                'swap_used_gb': 0.0,
                'swap_percent': 0.0
            }
    
    def get_disk_info(self) -> List[Dict[str, Any]]:
        """Récupère les informations disques"""
        disks = []
        
        try:
            for partition in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    
                    disk_info = {
                        'device': partition.device,
                        'mountpoint': partition.mountpoint,
                        'filesystem': partition.fstype,
                        'total_gb': round(usage.total / (1024**3), 2),
                        'used_gb': round(usage.used / (1024**3), 2),
                        'free_gb': round(usage.free / (1024**3), 2),
                        'usage_percent': round((usage.used / usage.total) * 100, 1)
                    }
                    
                    disks.append(disk_info)
                    
                except PermissionError:
                    # Ignorer les disques non accessibles
                    continue
                except Exception as e:
                    self.logger.warning(f"Erreur lecture partition {partition.device}: {e}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"Erreur récupération info disques: {e}")
            
        return disks
    
    def get_network_info(self) -> Dict[str, Any]:
        """Récupère les informations réseau"""
        try:
            # Informations réseau de base
            hostname = socket.gethostname()
            
            # Adresses IP
            ip_addresses = []
            for interface, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.family == socket.AF_INET:
                        ip_addresses.append({
                            'interface': interface,
                            'ip': addr.address,
                            'netmask': addr.netmask
                        })
            
            # Statistiques réseau
            net_io = psutil.net_io_counters()
            
            return {
                'hostname': hostname,
                'ip_addresses': ip_addresses,
                'bytes_sent': net_io.bytes_sent,
                'bytes_recv': net_io.bytes_recv,
                'packets_sent': net_io.packets_sent,
                'packets_recv': net_io.packets_recv
            }
            
        except Exception as e:
            self.logger.error(f"Erreur récupération info réseau: {e}")
            return {
                'hostname': 'unknown',
                'ip_addresses': [],
                'bytes_sent': 0,
                'bytes_recv': 0,
                'packets_sent': 0,
                'packets_recv': 0
            }
    
    def get_gpu_info(self) -> List[Dict[str, Any]]:
        """Récupère les informations GPU (si disponibles)"""
        gpus = []
        
        try:
            # Tentative d'utilisation de pynvml pour NVIDIA
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
                        'memory_total_mb': memory_info.total // (1024**2),
                        'memory_used_mb': memory_info.used // (1024**2),
                        'memory_free_mb': memory_info.free // (1024**2),
                        'vendor': 'NVIDIA'
                    }
                    
                    try:
                        utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
                        gpu_info['utilization_gpu'] = utilization.gpu
                        gpu_info['utilization_memory'] = utilization.memory
                    except:
                        gpu_info['utilization_gpu'] = 0
                        gpu_info['utilization_memory'] = 0
                    
                    gpus.append(gpu_info)
                    
            except ImportError:
                self.logger.info("pynvml non disponible, pas d'info GPU NVIDIA")
            except Exception as e:
                self.logger.warning(f"Erreur récupération GPU NVIDIA: {e}")
                
        except Exception as e:
            self.logger.error(f"Erreur récupération info GPU: {e}")
            
        return gpus
    
    def get_process_info(self) -> Dict[str, Any]:
        """Récupère les informations du processus actuel"""
        try:
            process = psutil.Process()
            
            # Informations de base
            process_info = {
                'pid': process.pid,
                'name': process.name(),
                'status': process.status(),
                'created': process.create_time(),
                'uptime_seconds': time.time() - self.start_time
            }
            
            # Utilisation ressources
            try:
                memory_info = process.memory_info()
                process_info.update({
                    'memory_rss_mb': memory_info.rss // (1024**2),
                    'memory_vms_mb': memory_info.vms // (1024**2),
                    'memory_percent': process.memory_percent(),
                    'cpu_percent': process.cpu_percent(),
                    'num_threads': process.num_threads()
                })
            except:
                process_info.update({
                    'memory_rss_mb': 0,
                    'memory_vms_mb': 0,
                    'memory_percent': 0,
                    'cpu_percent': 0,
                    'num_threads': 1
                })
            
            return process_info
            
        except Exception as e:
            self.logger.error(f"Erreur récupération info processus: {e}")
            return {
                'pid': os.getpid(),
                'name': 'unknown',
                'status': 'unknown',
                'created': time.time(),
                'uptime_seconds': 0,
                'memory_rss_mb': 0,
                'memory_vms_mb': 0,
                'memory_percent': 0,
                'cpu_percent': 0,
                'num_threads': 1
            }
    
    def get_platform_info(self) -> Dict[str, Any]:
        """Récupère les informations de plateforme"""
        try:
            return {
                'system': platform.system(),
                'release': platform.release(),
                'version': platform.version(),
                'machine': platform.machine(),
                'processor': platform.processor(),
                'python_version': platform.python_version(),
                'python_implementation': platform.python_implementation()
            }
        except Exception as e:
            self.logger.error(f"Erreur récupération info plateforme: {e}")
            return {
                'system': 'unknown',
                'release': 'unknown',
                'version': 'unknown',
                'machine': 'unknown',
                'processor': 'unknown',
                'python_version': 'unknown',
                'python_implementation': 'unknown'
            }
    
    def get_storage_paths_info(self, paths: List[str]) -> Dict[str, Dict[str, Any]]:
        """Récupère les informations d'espace disque pour des chemins spécifiques"""
        paths_info = {}
        
        for path_str in paths:
            try:
                path = Path(path_str)
                if path.exists():
                    usage = psutil.disk_usage(str(path))
                    
                    paths_info[path_str] = {
                        'exists': True,
                        'total_gb': round(usage.total / (1024**3), 2),
                        'used_gb': round(usage.used / (1024**3), 2),
                        'free_gb': round(usage.free / (1024**3), 2),
                        'usage_percent': round((usage.used / usage.total) * 100, 1),
                        'is_writable': os.access(path, os.W_OK)
                    }
                else:
                    paths_info[path_str] = {
                        'exists': False,
                        'total_gb': 0,
                        'used_gb': 0,
                        'free_gb': 0,
                        'usage_percent': 0,
                        'is_writable': False
                    }
                    
            except Exception as e:
                self.logger.error(f"Erreur info chemin {path_str}: {e}")
                paths_info[path_str] = {
                    'exists': False,
                    'error': str(e)
                }
        
        return paths_info
    
    def get_complete_system_info(self, work_paths: Optional[List[str]] = None) -> Dict[str, Any]:
        """Récupère toutes les informations système"""
        system_info = {
            'timestamp': time.time(),
            'platform': self.get_platform_info(),
            'cpu': self.get_cpu_info(),
            'memory': self.get_memory_info(),
            'disks': self.get_disk_info(),
            'network': self.get_network_info(),
            'gpus': self.get_gpu_info(),
            'process': self.get_process_info()
        }
        
        # Ajout des informations de chemins de travail si fournis
        if work_paths:
            system_info['work_paths'] = self.get_storage_paths_info(work_paths)
        
        return system_info
    
    def is_system_ready_for_processing(self) -> Dict[str, Any]:
        """Vérifie si le système est prêt pour le traitement"""
        try:
            cpu_info = self.get_cpu_info()
            memory_info = self.get_memory_info()
            gpu_info = self.get_gpu_info()
            
            # Critères de base
            cpu_ready = cpu_info['usage_percent'] < 80
            memory_ready = memory_info['available_gb'] > 2.0  # Au moins 2GB libre
            gpu_ready = len(gpu_info) > 0  # Au moins un GPU détecté
            
            # Score global
            readiness_score = 0
            if cpu_ready:
                readiness_score += 30
            if memory_ready:
                readiness_score += 40
            if gpu_ready:
                readiness_score += 30
            
            return {
                'ready': readiness_score >= 70,
                'readiness_score': readiness_score,
                'cpu_ready': cpu_ready,
                'memory_ready': memory_ready,
                'gpu_ready': gpu_ready,
                'recommendations': self._get_performance_recommendations(cpu_info, memory_info, gpu_info)
            }
            
        except Exception as e:
            self.logger.error(f"Erreur vérification état système: {e}")
            return {
                'ready': False,
                'readiness_score': 0,
                'error': str(e)
            }
    
    def _get_performance_recommendations(self, cpu_info: Dict, memory_info: Dict, gpu_info: List) -> List[str]:
        """Génère des recommandations de performance"""
        recommendations = []
        
        # Recommandations CPU
        if cpu_info['usage_percent'] > 80:
            recommendations.append("CPU fortement utilisé - réduire les tâches en arrière-plan")
        
        if cpu_info['logical_cores'] < 4:
            recommendations.append("Nombre de cœurs limité - performances de traitement réduites")
        
        # Recommandations mémoire
        if memory_info['available_gb'] < 4:
            recommendations.append("Mémoire disponible faible - risque de ralentissement")
        
        if memory_info['usage_percent'] > 85:
            recommendations.append("Utilisation mémoire élevée - fermer des applications non nécessaires")
        
        # Recommandations GPU
        if not gpu_info:
            recommendations.append("Aucun GPU détecté - le traitement sera effectué sur CPU (plus lent)")
        
        # Recommandations générales
        if not recommendations:
            recommendations.append("Système optimisé pour le traitement d'upscaling")
        
        return recommendations

# Instance globale
system_info = SystemInfo()