# UpscalingByNetwork/client/windows/utils/system_monitor.py
"""
Moniteur système pour le client d'upscaling distribué
Surveille CPU, RAM, GPU, disque et températures
"""

import logging
import time
import platform
from typing import Dict, List, Optional, Any
from pathlib import Path
import json

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import GPUtil
    GPUTIL_AVAILABLE = True
except ImportError:
    GPUTIL_AVAILABLE = False

class SystemMonitor:
    """Moniteur des ressources système"""
    
    def __init__(self, update_interval: float = 5.0):
        self.logger = logging.getLogger(__name__)
        self.update_interval = update_interval
        
        # Historique des mesures
        self.history_size = 60  # Garder 60 mesures (5 minutes à 5s d'intervalle)
        self.cpu_history = []
        self.memory_history = []
        self.disk_history = []
        self.gpu_history = []
        
        # Cache des informations système
        self.system_info = None
        self.last_update = 0
        
        # Seuils d'alerte
        self.alert_thresholds = {
            'cpu_percent': 90.0,
            'memory_percent': 85.0,
            'disk_percent': 90.0,
            'gpu_percent': 95.0,
            'temperature': 80.0
        }
        
        # Initialisation
        self.initialize_system_info()
        
        if not PSUTIL_AVAILABLE:
            self.logger.warning("psutil non disponible - monitoring limité")
        
        self.logger.info("Moniteur système initialisé")
    
    def initialize_system_info(self):
        """Initialise les informations système statiques"""
        try:
            self.system_info = {
                'platform': platform.system(),
                'platform_version': platform.version(),
                'architecture': platform.architecture()[0],
                'processor': platform.processor(),
                'hostname': platform.node(),
                'python_version': platform.python_version()
            }
            
            if PSUTIL_AVAILABLE:
                # Informations CPU
                self.system_info.update({
                    'cpu_count_logical': psutil.cpu_count(logical=True),
                    'cpu_count_physical': psutil.cpu_count(logical=False),
                    'cpu_freq_max': psutil.cpu_freq().max if psutil.cpu_freq() else None
                })
                
                # Informations mémoire
                memory = psutil.virtual_memory()
                self.system_info.update({
                    'memory_total_gb': round(memory.total / (1024**3), 2),
                    'memory_total_bytes': memory.total
                })
                
                # Informations disque
                disk_usage = psutil.disk_usage('/')
                self.system_info.update({
                    'disk_total_gb': round(disk_usage.total / (1024**3), 2),
                    'disk_total_bytes': disk_usage.total
                })
            
            # Informations GPU si disponibles
            if GPUTIL_AVAILABLE:
                try:
                    gpus = GPUtil.getGPUs()
                    self.system_info['gpu_count'] = len(gpus)
                    self.system_info['gpu_info'] = [
                        {
                            'id': gpu.id,
                            'name': gpu.name,
                            'memory_total': gpu.memoryTotal,
                            'driver': gpu.driver
                        }
                        for gpu in gpus
                    ]
                except:
                    self.system_info['gpu_count'] = 0
                    self.system_info['gpu_info'] = []
            else:
                self.system_info['gpu_count'] = 0
                self.system_info['gpu_info'] = []
            
        except Exception as e:
            self.logger.error(f"Erreur initialisation infos système: {e}")
            self.system_info = {'error': str(e)}
    
    def get_current_stats(self) -> Dict[str, Any]:
        """Récupère les statistiques actuelles du système"""
        current_time = time.time()
        
        # Mise à jour si nécessaire
        if current_time - self.last_update >= self.update_interval:
            self.update_stats()
        
        stats = {
            'timestamp': current_time,
            'uptime': self.get_uptime(),
            'cpu_percent': 0.0,
            'memory_percent': 0.0,
            'memory_used_gb': 0.0,
            'memory_available_gb': 0.0,
            'disk_percent': 0.0,
            'disk_used_gb': 0.0,
            'disk_free_gb': 0.0,
            'gpu_stats': [],
            'network_stats': {},
            'temperatures': {},
            'processes_count': 0,
            'load_average': None
        }
        
        if not PSUTIL_AVAILABLE:
            return stats
        
        try:
            # CPU
            cpu_percent = psutil.cpu_percent(interval=None)
            stats['cpu_percent'] = cpu_percent
            
            # Mémoire
            memory = psutil.virtual_memory()
            stats.update({
                'memory_percent': memory.percent,
                'memory_used_gb': round(memory.used / (1024**3), 2),
                'memory_available_gb': round(memory.available / (1024**3), 2)
            })
            
            # Disque
            disk_usage = psutil.disk_usage('/')
            stats.update({
                'disk_percent': disk_usage.percent,
                'disk_used_gb': round(disk_usage.used / (1024**3), 2),
                'disk_free_gb': round(disk_usage.free / (1024**3), 2)
            })
            
            # Réseau
            network = psutil.net_io_counters()
            if network:
                stats['network_stats'] = {
                    'bytes_sent': network.bytes_sent,
                    'bytes_recv': network.bytes_recv,
                    'packets_sent': network.packets_sent,
                    'packets_recv': network.packets_recv
                }
            
            # Processus
            stats['processes_count'] = len(psutil.pids())
            
            # Load average (Linux/Mac)
            if hasattr(psutil, 'getloadavg'):
                try:
                    stats['load_average'] = psutil.getloadavg()
                except:
                    pass
            
            # Températures
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    for name, entries in temps.items():
                        for entry in entries:
                            stats['temperatures'][f"{name}_{entry.label or 'sensor'}"] = entry.current
            except:
                pass
            
        except Exception as e:
            self.logger.error(f"Erreur récupération stats système: {e}")
            stats['error'] = str(e)
        
        # GPU stats si disponibles
        if GPUTIL_AVAILABLE:
            try:
                gpus = GPUtil.getGPUs()
                for gpu in gpus:
                    gpu_stat = {
                        'id': gpu.id,
                        'name': gpu.name,
                        'load': gpu.load * 100,
                        'memory_percent': (gpu.memoryUsed / gpu.memoryTotal) * 100,
                        'memory_used_mb': gpu.memoryUsed,
                        'memory_total_mb': gpu.memoryTotal,
                        'temperature': gpu.temperature
                    }
                    stats['gpu_stats'].append(gpu_stat)
            except Exception as e:
                self.logger.debug(f"Erreur stats GPU: {e}")
        
        return stats
    
    def update_stats(self):
        """Met à jour les statistiques et l'historique"""
        try:
            current_stats = self.get_current_stats()
            
            # Mise à jour de l'historique
            self.cpu_history.append(current_stats['cpu_percent'])
            self.memory_history.append(current_stats['memory_percent'])
            self.disk_history.append(current_stats['disk_percent'])
            
            # GPU history
            if current_stats['gpu_stats']:
                gpu_load_avg = sum(gpu['load'] for gpu in current_stats['gpu_stats']) / len(current_stats['gpu_stats'])
                self.gpu_history.append(gpu_load_avg)
            else:
                self.gpu_history.append(0.0)
            
            # Limiter la taille de l'historique
            for history in [self.cpu_history, self.memory_history, self.disk_history, self.gpu_history]:
                if len(history) > self.history_size:
                    history.pop(0)
            
            self.last_update = time.time()
            
        except Exception as e:
            self.logger.error(f"Erreur mise à jour stats: {e}")
    
    def get_uptime(self) -> float:
        """Récupère l'uptime du système en secondes"""
        try:
            if PSUTIL_AVAILABLE:
                return time.time() - psutil.boot_time()
            else:
                # Fallback approximatif
                return 0.0
        except:
            return 0.0
    
    def get_historical_stats(self) -> Dict[str, List[float]]:
        """Récupère l'historique des statistiques"""
        return {
            'cpu_history': self.cpu_history.copy(),
            'memory_history': self.memory_history.copy(),
            'disk_history': self.disk_history.copy(),
            'gpu_history': self.gpu_history.copy(),
            'timestamps': [time.time() - (i * self.update_interval) 
                          for i in range(len(self.cpu_history)-1, -1, -1)]
        }
    
    def get_system_info(self) -> Dict[str, Any]:
        """Récupère les informations système statiques"""
        return self.system_info.copy() if self.system_info else {}
    
    def check_resource_alerts(self) -> List[Dict[str, Any]]:
        """Vérifie les seuils d'alerte et retourne les alertes actives"""
        alerts = []
        
        try:
            current_stats = self.get_current_stats()
            
            # Vérification CPU
            if current_stats['cpu_percent'] > self.alert_thresholds['cpu_percent']:
                alerts.append({
                    'type': 'cpu_high',
                    'message': f"CPU élevé: {current_stats['cpu_percent']:.1f}%",
                    'value': current_stats['cpu_percent'],
                    'threshold': self.alert_thresholds['cpu_percent'],
                    'severity': 'warning'
                })
            
            # Vérification mémoire
            if current_stats['memory_percent'] > self.alert_thresholds['memory_percent']:
                alerts.append({
                    'type': 'memory_high',
                    'message': f"Mémoire élevée: {current_stats['memory_percent']:.1f}%",
                    'value': current_stats['memory_percent'],
                    'threshold': self.alert_thresholds['memory_percent'],
                    'severity': 'warning'
                })
            
            # Vérification disque
            if current_stats['disk_percent'] > self.alert_thresholds['disk_percent']:
                alerts.append({
                    'type': 'disk_high',
                    'message': f"Disque plein: {current_stats['disk_percent']:.1f}%",
                    'value': current_stats['disk_percent'],
                    'threshold': self.alert_thresholds['disk_percent'],
                    'severity': 'critical'
                })
            
            # Vérification GPU
            for gpu_stat in current_stats['gpu_stats']:
                if gpu_stat['load'] > self.alert_thresholds['gpu_percent']:
                    alerts.append({
                        'type': 'gpu_high',
                        'message': f"GPU {gpu_stat['id']} élevé: {gpu_stat['load']:.1f}%",
                        'value': gpu_stat['load'],
                        'threshold': self.alert_thresholds['gpu_percent'],
                        'severity': 'warning'
                    })
                
                if gpu_stat['temperature'] > self.alert_thresholds['temperature']:
                    alerts.append({
                        'type': 'gpu_temp_high',
                        'message': f"GPU {gpu_stat['id']} chaud: {gpu_stat['temperature']:.1f}°C",
                        'value': gpu_stat['temperature'],
                        'threshold': self.alert_thresholds['temperature'],
                        'severity': 'critical'
                    })
            
        except Exception as e:
            self.logger.error(f"Erreur vérification alertes: {e}")
        
        return alerts
    
    def get_performance_recommendations(self) -> List[str]:
        """Génère des recommandations de performance basées sur les stats"""
        recommendations = []
        
        try:
            current_stats = self.get_current_stats()
            
            # Recommandations CPU
            if current_stats['cpu_percent'] > 80:
                recommendations.append("CPU élevé - Réduisez la taille des tuiles ou le nombre de processus parallèles")
            
            # Recommandations mémoire
            memory_gb = current_stats.get('memory_available_gb', 0)
            if memory_gb < 2:
                recommendations.append("Mémoire faible - Fermez les applications inutiles")
            elif memory_gb < 4:
                recommendations.append("Mémoire limitée - Considérez réduire la taille des tuiles")
            
            # Recommandations disque
            disk_free_gb = current_stats.get('disk_free_gb', 0)
            if disk_free_gb < 5:
                recommendations.append("Espace disque critique - Libérez de l'espace")
            elif disk_free_gb < 20:
                recommendations.append("Espace disque faible - Nettoyez les fichiers temporaires")
            
            # Recommandations GPU
            for gpu_stat in current_stats['gpu_stats']:
                if gpu_stat['memory_percent'] > 90:
                    recommendations.append(f"Mémoire GPU {gpu_stat['id']} saturée - Réduisez la taille des tuiles")
                elif gpu_stat['temperature'] > 75:
                    recommendations.append(f"GPU {gpu_stat['id']} chaud - Vérifiez la ventilation")
            
            # Recommandations générales
            if len(current_stats['gpu_stats']) == 0:
                recommendations.append("Aucun GPU détecté - Le traitement sera plus lent en CPU")
            
            if not recommendations:
                recommendations.append("Configuration optimale pour l'upscaling")
            
        except Exception as e:
            self.logger.error(f"Erreur génération recommandations: {e}")
            recommendations.append("Impossible de générer des recommandations")
        
        return recommendations
    
    def estimate_processing_capacity(self) -> Dict[str, Any]:
        """Estime la capacité de traitement de la machine"""
        try:
            current_stats = self.get_current_stats()
            system_info = self.get_system_info()
            
            # Score basique basé sur les ressources
            cpu_score = min(system_info.get('cpu_count_logical', 1) * 10, 100)
            memory_score = min(system_info.get('memory_total_gb', 1) * 10, 100)
            
            # Score GPU
            gpu_score = 0
            if current_stats['gpu_stats']:
                # Score basé sur la mémoire GPU et le nombre de GPUs
                total_gpu_memory = sum(gpu['memory_total_mb'] for gpu in current_stats['gpu_stats'])
                gpu_score = min(total_gpu_memory / 100, 100)  # 100MB = 1 point
            
            # Score global (CPU + RAM + GPU)
            overall_score = (cpu_score * 0.3 + memory_score * 0.3 + gpu_score * 0.4)
            
            # Recommandations de configuration
            if overall_score > 80:
                tier = "high_end"
                recommended_tile_size = 512
                max_concurrent_batches = 2
            elif overall_score > 50:
                tier = "mid_range"
                recommended_tile_size = 256
                max_concurrent_batches = 1
            else:
                tier = "low_end"
                recommended_tile_size = 128
                max_concurrent_batches = 1
            
            return {
                'overall_score': round(overall_score, 1),
                'cpu_score': round(cpu_score, 1),
                'memory_score': round(memory_score, 1),
                'gpu_score': round(gpu_score, 1),
                'tier': tier,
                'recommended_tile_size': recommended_tile_size,
                'max_concurrent_batches': max_concurrent_batches,
                'estimated_images_per_minute': self.estimate_throughput(overall_score)
            }
            
        except Exception as e:
            self.logger.error(f"Erreur estimation capacité: {e}")
            return {
                'overall_score': 0,
                'tier': 'unknown',
                'recommended_tile_size': 128,
                'max_concurrent_batches': 1,
                'estimated_images_per_minute': 1
            }
    
    def estimate_throughput(self, performance_score: float) -> int:
        """Estime le débit d'images par minute"""
        # Estimation basique basée sur le score de performance
        # Ces valeurs sont approximatives et peuvent être ajustées
        if performance_score > 80:
            return 30  # Haut de gamme
        elif performance_score > 50:
            return 15  # Milieu de gamme
        else:
            return 5   # Bas de gamme
    
    def save_stats_to_file(self, file_path: Path):
        """Sauvegarde les statistiques dans un fichier"""
        try:
            stats_data = {
                'timestamp': time.time(),
                'system_info': self.get_system_info(),
                'current_stats': self.get_current_stats(),
                'historical_stats': self.get_historical_stats(),
                'capacity_estimate': self.estimate_processing_capacity(),
                'alerts': self.check_resource_alerts(),
                'recommendations': self.get_performance_recommendations()
            }
            
            with open(file_path, 'w') as f:
                json.dump(stats_data, f, indent=2, default=str)
            
            self.logger.info(f"Statistiques sauvegardées dans {file_path}")
            
        except Exception as e:
            self.logger.error(f"Erreur sauvegarde stats: {e}")
    
    def set_alert_threshold(self, resource: str, threshold: float):
        """Configure un seuil d'alerte"""
        if resource in self.alert_thresholds:
            self.alert_thresholds[resource] = threshold
            self.logger.info(f"Seuil {resource} mis à jour: {threshold}")
        else:
            self.logger.warning(f"Ressource inconnue: {resource}")
    
    def reset_history(self):
        """Remet à zéro l'historique des statistiques"""
        self.cpu_history.clear()
        self.memory_history.clear()
        self.disk_history.clear()
        self.gpu_history.clear()
        self.logger.info("Historique des statistiques réinitialisé")

class ProcessMonitor:
    """Moniteur spécifique aux processus d'upscaling"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.monitored_processes = {}
        self.realesrgan_stats = {
            'total_runs': 0,
            'successful_runs': 0,
            'failed_runs': 0,
            'total_time': 0.0,
            'avg_time_per_image': 0.0
        }
    
    def start_monitoring_process(self, process_id: str, pid: int):
        """Commence à surveiller un processus"""
        if not PSUTIL_AVAILABLE:
            return
        
        try:
            process = psutil.Process(pid)
            self.monitored_processes[process_id] = {
                'pid': pid,
                'process': process,
                'start_time': time.time(),
                'cpu_times': process.cpu_times(),
                'memory_info': process.memory_info()
            }
            
            self.logger.debug(f"Surveillance du processus {process_id} (PID: {pid})")
            
        except Exception as e:
            self.logger.error(f"Erreur surveillance processus {process_id}: {e}")
    
    def get_process_stats(self, process_id: str) -> Optional[Dict[str, Any]]:
        """Récupère les statistiques d'un processus surveillé"""
        if process_id not in self.monitored_processes:
            return None
        
        try:
            process_info = self.monitored_processes[process_id]
            process = process_info['process']
            
            current_cpu = process.cpu_times()
            current_memory = process.memory_info()
            
            stats = {
                'pid': process_info['pid'],
                'status': process.status(),
                'cpu_percent': process.cpu_percent(),
                'memory_mb': round(current_memory.rss / (1024**2), 2),
                'memory_percent': process.memory_percent(),
                'runtime': time.time() - process_info['start_time'],
                'threads': process.num_threads()
            }
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Erreur stats processus {process_id}: {e}")
            return None
    
    def stop_monitoring_process(self, process_id: str):
        """Arrête la surveillance d'un processus"""
        if process_id in self.monitored_processes:
            del self.monitored_processes[process_id]
            self.logger.debug(f"Surveillance du processus {process_id} arrêtée")
    
    def update_realesrgan_stats(self, success: bool, processing_time: float, image_count: int = 1):
        """Met à jour les statistiques Real-ESRGAN"""
        self.realesrgan_stats['total_runs'] += 1
        
        if success:
            self.realesrgan_stats['successful_runs'] += 1
            self.realesrgan_stats['total_time'] += processing_time
            
            total_images = self.realesrgan_stats['successful_runs'] * image_count
            if total_images > 0:
                self.realesrgan_stats['avg_time_per_image'] = (
                    self.realesrgan_stats['total_time'] / total_images
                )
        else:
            self.realesrgan_stats['failed_runs'] += 1
    
    def get_realesrgan_stats(self) -> Dict[str, Any]:
        """Récupère les statistiques Real-ESRGAN"""
        stats = self.realesrgan_stats.copy()
        
        if stats['total_runs'] > 0:
            stats['success_rate'] = (stats['successful_runs'] / stats['total_runs']) * 100
        else:
            stats['success_rate'] = 0.0
        
        return stats