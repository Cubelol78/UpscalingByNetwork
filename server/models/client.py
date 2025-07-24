# server/models/client.py
"""
Modèle de données pour les clients connectés
"""

import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

class ClientStatus(Enum):
    """États possibles d'un client"""
    CONNECTING = "connecting"      # En cours de connexion
    CONNECTED = "connected"        # Connecté et disponible
    PROCESSING = "processing"      # En cours de traitement d'un lot
    IDLE = "idle"                 # Connecté mais inactif
    DISCONNECTED = "disconnected"  # Déconnecté
    ERROR = "error"               # En erreur
    BANNED = "banned"             # Banni temporairement

class ClientCapability(Enum):
    """Capacités d'un client"""
    BASIC_UPSCALING = "basic_upscaling"
    GPU_ACCELERATION = "gpu_acceleration"
    VULKAN_SUPPORT = "vulkan_support"
    HIGH_MEMORY = "high_memory"
    FAST_NETWORK = "fast_network"

@dataclass
class ClientHardwareInfo:
    """Informations matérielles du client"""
    platform: str = ""
    cpu_cores: int = 0
    cpu_frequency: float = 0.0
    ram_gb: float = 0.0
    gpu_name: str = ""
    gpu_memory_mb: int = 0
    vulkan_support: bool = False
    performance_score: float = 0.0

@dataclass
class ClientNetworkInfo:
    """Informations réseau du client"""
    ip_address: str = ""
    hostname: str = ""
    connection_quality: float = 100.0  # Pourcentage
    latency_ms: float = 0.0
    bandwidth_mbps: float = 0.0

class Client:
    """
    Représente un client connecté au serveur
    """
    
    def __init__(self, mac_address: str, ip_address: str = "", hostname: str = ""):
        # Identifiants
        self.mac_address = mac_address  # Identifiant unique
        self.client_id = self._generate_client_id()
        
        # Informations de connexion
        self.ip_address = ip_address
        self.hostname = hostname or f"client-{mac_address[-6:].replace(':', '')}"
        
        # État
        self.status = ClientStatus.CONNECTING
        self.connected_at = datetime.now()
        self.last_heartbeat = datetime.now()
        self.last_activity = datetime.now()
        
        # Traitement en cours
        self.current_batch: Optional[str] = None
        self.current_batch_started_at: Optional[datetime] = None
        
        # Statistiques de performance
        self.batches_completed = 0
        self.batches_failed = 0
        self.total_frames_processed = 0
        self.total_processing_time = 0.0  # En secondes
        self.total_data_transferred_mb = 0.0
        
        # Informations système
        self.hardware_info = ClientHardwareInfo()
        self.network_info = ClientNetworkInfo(ip_address=ip_address, hostname=hostname)
        self.capabilities: List[ClientCapability] = []
        
        # Configuration
        self.max_concurrent_batches = 1
        self.preferred_batch_size = 50
        self.processing_config: Dict[str, Any] = {}
        
        # Gestion d'erreurs
        self.consecutive_failures = 0
        self.last_error: Optional[str] = None
        self.last_error_at: Optional[datetime] = None
        self.ban_until: Optional[datetime] = None
        
        # Métadonnées
        self.metadata: Dict[str, Any] = {}
        self.tags: List[str] = []
        
        # Historique des performances
        self.performance_history: List[Dict[str, Any]] = []
        self.max_history_entries = 100
    
    def _generate_client_id(self) -> str:
        """Génère un ID client unique"""
        import hashlib
        data = f"{self.mac_address}-{time.time()}".encode()
        return hashlib.md5(data).hexdigest()[:12]
    
    @property
    def is_online(self) -> bool:
        """Vérifie si le client est en ligne"""
        if self.status == ClientStatus.DISCONNECTED:
            return False
        
        # Vérification du heartbeat (timeout après 90 secondes)
        timeout = timedelta(seconds=90)
        return datetime.now() - self.last_heartbeat < timeout
    
    @property
    def is_available(self) -> bool:
        """Vérifie si le client peut accepter un nouveau lot"""
        return (self.is_online and 
                self.status in [ClientStatus.CONNECTED, ClientStatus.IDLE] and
                self.current_batch is None and
                not self.is_banned)
    
    @property
    def is_processing(self) -> bool:
        """Vérifie si le client traite actuellement un lot"""
        return (self.status == ClientStatus.PROCESSING and 
                self.current_batch is not None)
    
    @property
    def is_banned(self) -> bool:
        """Vérifie si le client est banni"""
        if self.ban_until is None:
            return False
        return datetime.now() < self.ban_until
    
    @property
    def connection_time(self) -> float:
        """Durée de connexion en secondes"""
        return (datetime.now() - self.connected_at).total_seconds()
    
    @property
    def idle_time(self) -> float:
        """Temps d'inactivité en secondes"""
        return (datetime.now() - self.last_activity).total_seconds()
    
    @property
    def success_rate(self) -> float:
        """Taux de succès en pourcentage"""
        total_batches = self.batches_completed + self.batches_failed
        if total_batches == 0:
            return 100.0
        return (self.batches_completed / total_batches) * 100.0
    
    @property
    def average_batch_time(self) -> float:
        """Temps moyen de traitement par lot en secondes"""
        if self.batches_completed == 0:
            return 0.0
        return self.total_processing_time / self.batches_completed
    
    @property
    def average_frame_time(self) -> float:
        """Temps moyen de traitement par frame en secondes"""
        if self.total_frames_processed == 0:
            return 0.0
        return self.total_processing_time / self.total_frames_processed
    
    @property
    def throughput_frames_per_minute(self) -> float:
        """Débit en frames par minute"""
        if self.total_processing_time == 0:
            return 0.0
        return (self.total_frames_processed / self.total_processing_time) * 60
    
    def update_heartbeat(self):
        """Met à jour le heartbeat du client"""
        self.last_heartbeat = datetime.now()
        if self.status == ClientStatus.DISCONNECTED:
            self.status = ClientStatus.CONNECTED
    
    def update_activity(self):
        """Met à jour l'activité du client"""
        self.last_activity = datetime.now()
        self.update_heartbeat()
    
    def assign_batch(self, batch_id: str) -> bool:
        """
        Assigne un lot au client
        
        Args:
            batch_id: ID du lot à assigner
            
        Returns:
            True si assigné avec succès
        """
        if not self.is_available:
            return False
        
        self.current_batch = batch_id
        self.current_batch_started_at = datetime.now()
        self.status = ClientStatus.PROCESSING
        self.update_activity()
        
        return True
    
    def complete_batch(self, batch_id: str, frames_processed: int, processing_time: float):
        """
        Marque un lot comme terminé
        
        Args:
            batch_id: ID du lot terminé
            frames_processed: Nombre de frames traitées
            processing_time: Temps de traitement en secondes
        """
        if self.current_batch != batch_id:
            return False
        
        # Mise à jour des statistiques
        self.batches_completed += 1
        self.total_frames_processed += frames_processed
        self.total_processing_time += processing_time
        self.consecutive_failures = 0
        
        # Ajout à l'historique
        self._add_performance_entry(batch_id, frames_processed, processing_time, True)
        
        # Remise à zéro de l'état
        self.current_batch = None
        self.current_batch_started_at = None
        self.status = ClientStatus.CONNECTED
        self.update_activity()
        
        return True
    
    def fail_batch(self, batch_id: str, error_message: str):
        """
        Marque un lot comme échoué
        
        Args:
            batch_id: ID du lot échoué
            error_message: Message d'erreur
        """
        if self.current_batch != batch_id:
            return False
        
        # Mise à jour des statistiques d'erreur
        self.batches_failed += 1
        self.consecutive_failures += 1
        self.last_error = error_message
        self.last_error_at = datetime.now()
        
        # Ajout à l'historique
        processing_time = 0
        if self.current_batch_started_at:
            processing_time = (datetime.now() - self.current_batch_started_at).total_seconds()
        
        self._add_performance_entry(batch_id, 0, processing_time, False, error_message)
        
        # Bannissement temporaire si trop d'échecs consécutifs
        if self.consecutive_failures >= 3:
            self.ban_temporarily(minutes=10)
        
        # Remise à zéro de l'état
        self.current_batch = None
        self.current_batch_started_at = None
        self.status = ClientStatus.ERROR if self.consecutive_failures < 3 else ClientStatus.BANNED
        self.update_activity()
        
        return True
    
    def _add_performance_entry(self, batch_id: str, frames: int, time_sec: float, 
                             success: bool, error: str = None):
        """Ajoute une entrée à l'historique des performances"""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'batch_id': batch_id,
            'frames_processed': frames,
            'processing_time': time_sec,
            'success': success,
            'error': error,
            'frames_per_second': frames / max(time_sec, 0.1) if time_sec > 0 else 0
        }
        
        self.performance_history.append(entry)
        
        # Limitation de l'historique
        if len(self.performance_history) > self.max_history_entries:
            self.performance_history = self.performance_history[-self.max_history_entries:]
    
    def ban_temporarily(self, minutes: int = 10):
        """
        Bannit temporairement le client
        
        Args:
            minutes: Durée du bannissement en minutes
        """
        self.ban_until = datetime.now() + timedelta(minutes=minutes)
        self.status = ClientStatus.BANNED
        
    def ban_temporarily(self, minutes: int = 10):
        """
        Bannit temporairement le client
        
        Args:
            minutes: Durée du bannissement en minutes
        """
        self.ban_until = datetime.now() + timedelta(minutes=minutes)
        self.status = ClientStatus.BANNED
        
        # Libération du lot en cours
        if self.current_batch:
            self.current_batch = None
            self.current_batch_started_at = None
    
    def unban(self):
        """Lève le bannissement du client"""
        self.ban_until = None
        self.consecutive_failures = 0
        if self.status == ClientStatus.BANNED:
            self.status = ClientStatus.CONNECTED
    
    def disconnect(self):
        """Déconnecte le client"""
        self.status = ClientStatus.DISCONNECTED
        self.current_batch = None
        self.current_batch_started_at = None
    
    def update_hardware_info(self, hardware_info: Dict[str, Any]):
        """
        Met à jour les informations matérielles
        
        Args:
            hardware_info: Dictionnaire avec les infos matérielles
        """
        self.hardware_info.platform = hardware_info.get('platform', '')
        self.hardware_info.cpu_cores = hardware_info.get('cpu_cores', 0)
        self.hardware_info.cpu_frequency = hardware_info.get('cpu_frequency', 0.0)
        self.hardware_info.ram_gb = hardware_info.get('ram_gb', 0.0)
        self.hardware_info.gpu_name = hardware_info.get('gpu_name', '')
        self.hardware_info.gpu_memory_mb = hardware_info.get('gpu_memory_mb', 0)
        self.hardware_info.vulkan_support = hardware_info.get('vulkan_support', False)
        self.hardware_info.performance_score = hardware_info.get('performance_score', 0.0)
        
        # Mise à jour des capacités basées sur le matériel
        self._update_capabilities()
    
    def update_network_info(self, network_info: Dict[str, Any]):
        """
        Met à jour les informations réseau
        
        Args:
            network_info: Dictionnaire avec les infos réseau
        """
        self.network_info.ip_address = network_info.get('ip_address', self.ip_address)
        self.network_info.hostname = network_info.get('hostname', self.hostname)
        self.network_info.connection_quality = network_info.get('connection_quality', 100.0)
        self.network_info.latency_ms = network_info.get('latency_ms', 0.0)
        self.network_info.bandwidth_mbps = network_info.get('bandwidth_mbps', 0.0)
    
    def _update_capabilities(self):
        """Met à jour les capacités basées sur les informations matérielles"""
        self.capabilities = [ClientCapability.BASIC_UPSCALING]
        
        # GPU
        if self.hardware_info.gpu_name and self.hardware_info.gpu_memory_mb > 0:
            self.capabilities.append(ClientCapability.GPU_ACCELERATION)
        
        # Vulkan
        if self.hardware_info.vulkan_support:
            self.capabilities.append(ClientCapability.VULKAN_SUPPORT)
        
        # Mémoire élevée
        if self.hardware_info.ram_gb >= 16:
            self.capabilities.append(ClientCapability.HIGH_MEMORY)
        
        # Réseau rapide (si latence < 50ms)
        if self.network_info.latency_ms > 0 and self.network_info.latency_ms < 50:
            self.capabilities.append(ClientCapability.FAST_NETWORK)
    
    def get_performance_score(self) -> float:
        """
        Calcule un score de performance global
        
        Returns:
            Score de 0 à 100
        """
        if self.hardware_info.performance_score > 0:
            base_score = self.hardware_info.performance_score
        else:
            # Calcul basique si pas de score matériel
            base_score = 50.0
        
        # Ajustement basé sur l'historique
        success_factor = self.success_rate / 100.0
        
        # Pénalité pour les échecs récents
        recent_failures = 0
        if len(self.performance_history) >= 5:
            recent_entries = self.performance_history[-5:]
            recent_failures = sum(1 for entry in recent_entries if not entry['success'])
        failure_penalty = recent_failures * 10
        
        # Bonus pour la rapidité
        speed_bonus = 0
        if self.average_frame_time > 0:
            # Bonus si traitement < 1 seconde par frame
            if self.average_frame_time < 1.0:
                speed_bonus = 10
            elif self.average_frame_time < 0.5:
                speed_bonus = 20
        
        final_score = (base_score * success_factor) - failure_penalty + speed_bonus
        return max(0, min(100, final_score))
    
    def get_recommended_batch_size(self) -> int:
        """
        Recommande une taille de lot optimale
        
        Returns:
            Taille de lot recommandée
        """
        base_size = 50
        
        # Ajustement basé sur la performance
        performance_score = self.get_performance_score()
        
        if performance_score >= 80:
            multiplier = 1.5
        elif performance_score >= 60:
            multiplier = 1.2
        elif performance_score >= 40:
            multiplier = 1.0
        else:
            multiplier = 0.7
        
        # Ajustement basé sur la mémoire
        if self.hardware_info.ram_gb >= 32:
            multiplier *= 1.3
        elif self.hardware_info.ram_gb >= 16:
            multiplier *= 1.1
        elif self.hardware_info.ram_gb < 8:
            multiplier *= 0.8
        
        # Ajustement basé sur l'historique de temps de traitement
        if self.average_batch_time > 0:
            if self.average_batch_time > 300:  # > 5 minutes
                multiplier *= 0.7
            elif self.average_batch_time < 60:  # < 1 minute
                multiplier *= 1.2
        
        recommended_size = int(base_size * multiplier)
        return max(10, min(100, recommended_size))
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convertit le client en dictionnaire
        
        Returns:
            Représentation en dictionnaire
        """
        return {
            'mac_address': self.mac_address,
            'client_id': self.client_id,
            'ip_address': self.ip_address,
            'hostname': self.hostname,
            'status': self.status.value,
            'connected_at': self.connected_at.isoformat(),
            'last_heartbeat': self.last_heartbeat.isoformat(),
            'last_activity': self.last_activity.isoformat(),
            'is_online': self.is_online,
            'is_available': self.is_available,
            'is_processing': self.is_processing,
            'is_banned': self.is_banned,
            'connection_time': self.connection_time,
            'idle_time': self.idle_time,
            'current_batch': self.current_batch,
            'current_batch_started_at': (
                self.current_batch_started_at.isoformat() 
                if self.current_batch_started_at else None
            ),
            'performance': {
                'batches_completed': self.batches_completed,
                'batches_failed': self.batches_failed,
                'total_frames_processed': self.total_frames_processed,
                'success_rate': self.success_rate,
                'average_batch_time': self.average_batch_time,
                'average_frame_time': self.average_frame_time,
                'throughput_frames_per_minute': self.throughput_frames_per_minute,
                'performance_score': self.get_performance_score(),
                'consecutive_failures': self.consecutive_failures
            },
            'hardware': {
                'platform': self.hardware_info.platform,
                'cpu_cores': self.hardware_info.cpu_cores,
                'cpu_frequency': self.hardware_info.cpu_frequency,
                'ram_gb': self.hardware_info.ram_gb,
                'gpu_name': self.hardware_info.gpu_name,
                'gpu_memory_mb': self.hardware_info.gpu_memory_mb,
                'vulkan_support': self.hardware_info.vulkan_support,
                'performance_score': self.hardware_info.performance_score
            },
            'network': {
                'ip_address': self.network_info.ip_address,
                'hostname': self.network_info.hostname,
                'connection_quality': self.network_info.connection_quality,
                'latency_ms': self.network_info.latency_ms,
                'bandwidth_mbps': self.network_info.bandwidth_mbps
            },
            'capabilities': [cap.value for cap in self.capabilities],
            'config': {
                'max_concurrent_batches': self.max_concurrent_batches,
                'preferred_batch_size': self.preferred_batch_size,
                'recommended_batch_size': self.get_recommended_batch_size(),
                'processing_config': self.processing_config
            },
            'error_info': {
                'last_error': self.last_error,
                'last_error_at': self.last_error_at.isoformat() if self.last_error_at else None,
                'ban_until': self.ban_until.isoformat() if self.ban_until else None
            },
            'metadata': self.metadata,
            'tags': self.tags,
            'performance_history': self.performance_history[-10:]  # Dernières 10 entrées
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Client':
        """
        Crée un client à partir d'un dictionnaire
        
        Args:
            data: Données du client
            
        Returns:
            Instance de Client
        """
        client = cls(
            mac_address=data['mac_address'],
            ip_address=data.get('ip_address', ''),
            hostname=data.get('hostname', '')
        )
        
        # Restauration de l'état
        client.client_id = data.get('client_id', client.client_id)
        client.status = ClientStatus(data.get('status', ClientStatus.DISCONNECTED.value))
        
        # Dates
        if data.get('connected_at'):
            client.connected_at = datetime.fromisoformat(data['connected_at'])
        if data.get('last_heartbeat'):
            client.last_heartbeat = datetime.fromisoformat(data['last_heartbeat'])
        if data.get('last_activity'):
            client.last_activity = datetime.fromisoformat(data['last_activity'])
        
        # Lot en cours
        client.current_batch = data.get('current_batch')
        if data.get('current_batch_started_at'):
            client.current_batch_started_at = datetime.fromisoformat(data['current_batch_started_at'])
        
        # Statistiques de performance
        perf = data.get('performance', {})
        client.batches_completed = perf.get('batches_completed', 0)
        client.batches_failed = perf.get('batches_failed', 0)
        client.total_frames_processed = perf.get('total_frames_processed', 0)
        client.total_processing_time = perf.get('total_processing_time', 0.0)
        client.consecutive_failures = perf.get('consecutive_failures', 0)
        
        # Informations matérielles
        hw = data.get('hardware', {})
        client.update_hardware_info(hw)
        
        # Informations réseau
        net = data.get('network', {})
        client.update_network_info(net)
        
        # Configuration
        config = data.get('config', {})
        client.max_concurrent_batches = config.get('max_concurrent_batches', 1)
        client.preferred_batch_size = config.get('preferred_batch_size', 50)
        client.processing_config = config.get('processing_config', {})
        
        # Informations d'erreur
        error_info = data.get('error_info', {})
        client.last_error = error_info.get('last_error')
        if error_info.get('last_error_at'):
            client.last_error_at = datetime.fromisoformat(error_info['last_error_at'])
        if error_info.get('ban_until'):
            client.ban_until = datetime.fromisoformat(error_info['ban_until'])
        
        # Métadonnées
        client.metadata = data.get('metadata', {})
        client.tags = data.get('tags', [])
        client.performance_history = data.get('performance_history', [])
        
        return client
    
    def __str__(self) -> str:
        return f"Client(mac={self.mac_address}, status={self.status.value}, batches={self.batches_completed})"
    
    def __repr__(self) -> str:
        return self.__str__()

class ClientManager:
    """Gestionnaire de clients avec fonctionnalités avancées"""
    
    def __init__(self):
        self.clients: Dict[str, Client] = {}
        self.client_groups: Dict[str, List[str]] = {}  # Groupes de clients
    
    def add_client(self, client: Client) -> bool:
        """
        Ajoute un client
        
        Args:
            client: Client à ajouter
            
        Returns:
            True si ajouté avec succès
        """
        if client.mac_address in self.clients:
            return False
        
        self.clients[client.mac_address] = client
        return True
    
    def remove_client(self, mac_address: str) -> bool:
        """
        Supprime un client
        
        Args:
            mac_address: MAC du client à supprimer
            
        Returns:
            True si supprimé avec succès
        """
        if mac_address not in self.clients:
            return False
        
        del self.clients[mac_address]
        
        # Suppression des groupes
        for group_name, members in self.client_groups.items():
            if mac_address in members:
                members.remove(mac_address)
        
        return True
    
    def get_available_clients(self, min_performance_score: float = 0) -> List[Client]:
        """
        Retourne les clients disponibles
        
        Args:
            min_performance_score: Score minimum requis
            
        Returns:
            Liste des clients disponibles
        """
        available = []
        for client in self.clients.values():
            if (client.is_available and 
                client.get_performance_score() >= min_performance_score):
                available.append(client)
        
        # Tri par score de performance décroissant
        return sorted(available, key=lambda c: c.get_performance_score(), reverse=True)
    
    def get_client_statistics(self) -> Dict[str, Any]:
        """
        Retourne les statistiques globales des clients
        
        Returns:
            Statistiques des clients
        """
        if not self.clients:
            return {
                'total_clients': 0,
                'online_clients': 0,
                'available_clients': 0,
                'processing_clients': 0,
                'total_batches_completed': 0,
                'total_frames_processed': 0,
                'average_performance_score': 0
            }
        
        online = [c for c in self.clients.values() if c.is_online]
        available = [c for c in self.clients.values() if c.is_available]
        processing = [c for c in self.clients.values() if c.is_processing]
        
        total_batches = sum(c.batches_completed for c in self.clients.values())
        total_frames = sum(c.total_frames_processed for c in self.clients.values())
        
        performance_scores = [c.get_performance_score() for c in online]
        avg_performance = sum(performance_scores) / len(performance_scores) if performance_scores else 0
        
        return {
            'total_clients': len(self.clients),
            'online_clients': len(online),
            'available_clients': len(available),
            'processing_clients': len(processing),
            'banned_clients': len([c for c in self.clients.values() if c.is_banned]),
            'total_batches_completed': total_batches,
            'total_frames_processed': total_frames,
            'average_performance_score': avg_performance,
            'clients_by_platform': self._get_platform_distribution(),
            'performance_distribution': self._get_performance_distribution()
        }
    
    def _get_platform_distribution(self) -> Dict[str, int]:
        """Distribution des clients par plateforme"""
        distribution = {}
        for client in self.clients.values():
            platform = client.hardware_info.platform or 'Unknown'
            distribution[platform] = distribution.get(platform, 0) + 1
        return distribution
    
    def _get_performance_distribution(self) -> Dict[str, int]:
        """Distribution des clients par niveau de performance"""
        distribution = {'Excellent (80-100)': 0, 'Good (60-79)': 0, 'Average (40-59)': 0, 'Poor (0-39)': 0}
        
        for client in self.clients.values():
            score = client.get_performance_score()
            if score >= 80:
                distribution['Excellent (80-100)'] += 1
            elif score >= 60:
                distribution['Good (60-79)'] += 1
            elif score >= 40:
                distribution['Average (40-59)'] += 1
            else:
                distribution['Poor (0-39)'] += 1
        
        return distribution