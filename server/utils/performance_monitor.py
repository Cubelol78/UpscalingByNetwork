# utils/performance_monitor.py
import time
import threading
from collections import deque
from typing import Dict, List, Tuple

class PerformanceMonitor:
    """Moniteur de performance pour le serveur"""
    
    def __init__(self, max_samples: int = 1000):
        self.max_samples = max_samples
        self.metrics = {
            'cpu_usage': deque(maxlen=max_samples),
            'memory_usage': deque(maxlen=max_samples),
            'network_io': deque(maxlen=max_samples),
            'disk_io': deque(maxlen=max_samples),
            'client_count': deque(maxlen=max_samples),
            'batch_queue_size': deque(maxlen=max_samples),
            'processing_rate': deque(maxlen=max_samples)
        }
        self.timestamps = deque(maxlen=max_samples)
        self.running = False
        self.monitor_thread = None
        self.logger = get_logger(__name__)
    
    def start_monitoring(self, interval: float = 5.0):
        """Démarre le monitoring"""
        if self.running:
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, args=(interval,))
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        self.logger.info("Monitoring de performance démarré")
    
    def stop_monitoring(self):
        """Arrête le monitoring"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join()
        self.logger.info("Monitoring de performance arrêté")
    
    def _monitor_loop(self, interval: float):
        """Boucle principale de monitoring"""
        while self.running:
            try:
                timestamp = time.time()
                
                # Collecte des métriques système
                cpu_percent = psutil.cpu_percent(interval=0.1)
                memory = psutil.virtual_memory()
                network = psutil.net_io_counters()
                disk = psutil.disk_io_counters()
                
                # Stockage des métriques
                self.timestamps.append(timestamp)
                self.metrics['cpu_usage'].append(cpu_percent)
                self.metrics['memory_usage'].append(memory.percent)
                self.metrics['network_io'].append({
                    'bytes_sent': network.bytes_sent,
                    'bytes_recv': network.bytes_recv
                })
                self.metrics['disk_io'].append({
                    'read_bytes': disk.read_bytes,
                    'write_bytes': disk.write_bytes
                })
                
                time.sleep(interval)
                
            except Exception as e:
                self.logger.error(f"Erreur monitoring performance: {e}")
                time.sleep(interval)
    
    def add_server_metrics(self, server):
        """Ajoute les métriques spécifiques au serveur"""
        try:
            if hasattr(server, 'clients') and hasattr(server, 'batches'):
                online_clients = sum(1 for c in server.clients.values() if c.is_online)
                pending_batches = sum(1 for b in server.batches.values() 
                                    if b.status.value == 'pending')
                
                self.metrics['client_count'].append(online_clients)
                self.metrics['batch_queue_size'].append(pending_batches)
                
                # Calcul du taux de traitement (lots/minute)
                if len(self.timestamps) >= 2:
                    time_diff = self.timestamps[-1] - self.timestamps[-2]
                    if time_diff > 0:
                        completed_batches = sum(1 for b in server.batches.values() 
                                              if b.status.value == 'completed')
                        rate = (completed_batches / time_diff) * 60  # par minute
                        self.metrics['processing_rate'].append(rate)
                
        except Exception as e:
            self.logger.error(f"Erreur métriques serveur: {e}")
    
    def get_current_stats(self) -> Dict[str, Any]:
        """Obtient les statistiques actuelles"""
        stats = {}
        
        try:
            for metric_name, values in self.metrics.items():
                if values:
                    if isinstance(values[-1], dict):
                        stats[metric_name] = values[-1]
                    else:
                        stats[metric_name] = {
                            'current': values[-1],
                            'average': sum(values) / len(values),
                            'min': min(values),
                            'max': max(values)
                        }
        
        except Exception as e:
            self.logger.error(f"Erreur calcul statistiques: {e}")
        
        return stats
    
    def get_time_series_data(self, metric: str, duration_minutes: int = 60) -> Tuple[List[float], List[float]]:
        """Obtient les données de série temporelle pour un métrique"""
        if metric not in self.metrics:
            return [], []
        
        current_time = time.time()
        cutoff_time = current_time - (duration_minutes * 60)
        
        timestamps = []
        values = []
        
        for i, timestamp in enumerate(self.timestamps):
            if timestamp >= cutoff_time and i < len(self.metrics[metric]):
                timestamps.append(timestamp)
                value = self.metrics[metric][i]
                if isinstance(value, dict):
                    # Pour les métriques complexes, prendre une valeur représentative
                    if 'current' in value:
                        values.append(value['current'])
                    else:
                        values.append(sum(value.values()) / len(value.values()))
                else:
                    values.append(value)
        
        return timestamps, values

# Moniteur de performance global
performance_monitor = PerformanceMonitor()