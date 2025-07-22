# core/client_manager.py  
class ClientManager:
    """Gestionnaire des clients connectés"""
    
    def __init__(self, server):
        self.server = server
        self.logger = get_logger(__name__)
    
    def get_client_stats(self, mac_address: str) -> Optional[dict]:
        """Retourne les statistiques d'un client"""
        if mac_address not in self.server.clients:
            return None
        
        client = self.server.clients[mac_address]
        
        return {
            "mac_address": client.mac_address,
            "ip_address": client.ip_address,
            "hostname": client.hostname,
            "platform": client.platform,
            "status": client.status.value,
            "connected_at": client.connected_at.isoformat(),
            "last_heartbeat": client.last_heartbeat.isoformat(),
            "is_online": client.is_online,
            "current_batch": client.current_batch,
            "batches_completed": client.batches_completed,
            "batches_failed": client.batches_failed,
            "success_rate": client.success_rate,
            "average_batch_time": client.average_batch_time,
            "connection_time": client.connection_time,
            "gpu_info": client.gpu_info,
            "cpu_info": client.cpu_info
        }
    
    def get_all_clients_stats(self) -> List[dict]:
        """Retourne les statistiques de tous les clients"""
        return [self.get_client_stats(mac) for mac in self.server.clients.keys()]
    
    def disconnect_client(self, mac_address: str) -> bool:
        """Déconnecte un client"""
        if mac_address not in self.server.clients:
            return False
        
        client = self.server.clients[mac_address]
        client.disconnect()
        
        # Libération du lot en cours
        if client.current_batch and client.current_batch in self.server.batches:
            batch = self.server.batches[client.current_batch]
            batch.reset()
            self.logger.info(f"Lot {batch.id} libéré suite à déconnexion forcée")
        
        # Fermeture de la connexion WebSocket
        if mac_address in self.server.websockets:
            asyncio.create_task(self.server.websockets[mac_address].close())
            del self.server.websockets[mac_address]
        
        self.logger.info(f"Client {mac_address} déconnecté")
        return True(f"Erreur dans heartbeat_monitor: {e}")
                await asyncio.sleep(5)
    
    async def _batch_monitor(self):
        """Surveille et assigne les lots"""
        while self.running:
            try:
                await self.batch_manager.assign_pending_batches()
                await asyncio.sleep(1)  # Vérification chaque seconde
                
            except Exception as e:
                self.logger.error