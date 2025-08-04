# UpscalingByNetwork/scripts/monitor.py

"""
Outil de monitoring en temps réel pour UpscalingByNetwork
UpscalingByNetwork/scripts/monitor.py
"""

import asyncio
import websockets
import json
import time
import argparse
import sys
from datetime import datetime
from typing import Dict, Any

class NetworkMonitor:
    """Moniteur de réseau UpscalingByNetwork"""
    
    def __init__(self, host: str = "localhost", port: int = 8888):
        self.host = host
        self.port = port
        self.running = False
        
        # Statistiques
        self.stats = {
            'start_time': time.time(),
            'clients_seen': set(),
            'messages_received': 0,
            'jobs_processed': 0,
            'batches_completed': 0
        }
    
    async def connect_and_monitor(self):
        """Se connecte et surveille le serveur"""
        uri = f"ws://{self.host}:{self.port}"
        
        print(f"🔗 Connexion au serveur {uri}...")
        
        try:
            async with websockets.connect(uri) as websocket:
                print("✅ Connecté au serveur")
                print("📊 Surveillance en cours... (Ctrl+C pour arrêter)")
                print("-" * 60)
                
                self.running = True
                
                # Envoi du message de connexion pour monitoring
                connect_msg = {
                    'type': 'monitor_connect',
                    'client_mac': 'MONITOR',
                    'timestamp': time.time(),
                    'data': {'monitor': True}
                }
                
                await websocket.send(json.dumps(connect_msg))
                
                # Boucle de surveillance
                async for message in websocket:
                    await self.process_message(message)
                    
        except websockets.exceptions.ConnectionClosed:
            print("🔌 Connexion fermée par le serveur")
        except Exception as e:
            print(f"❌ Erreur de connexion: {e}")
            print(f"💡 Vérifiez que le serveur fonctionne sur {self.host}:{self.port}")
    
    async def process_message(self, message_str: str):
        """Traite un message reçu"""
        try:
            message = json.loads(message_str)
            self.stats['messages_received'] += 1
            
            timestamp = datetime.fromtimestamp(message.get('timestamp', time.time()))
            msg_type = message.get('type', 'unknown')
            client_mac = message.get('client_mac', 'unknown')
            data = message.get('data', {})
            
            # Ajout du client aux statistiques
            if client_mac != 'unknown' and client_mac != 'MONITOR':
                self.stats['clients_seen'].add(client_mac)
            
            # Affichage selon le type de message
            if msg_type == 'client_connect':
                print(f"🔌 [{timestamp.strftime('%H:%M:%S')}] Client connecté: {client_mac[:8]}...")
                
            elif msg_type == 'client_disconnect':
                print(f"🔌 [{timestamp.strftime('%H:%M:%S')}] Client déconnecté: {client_mac[:8]}...")
                
            elif msg_type == 'batch_assignment':
                batch_id = data.get('batch_id', 'unknown')
                frame_count = data.get('frame_count', 0)
                print(f"📦 [{timestamp.strftime('%H:%M:%S')}] Lot assigné: {batch_id[:8]}... "
                      f"({frame_count} images) -> {client_mac[:8]}...")
                
            elif msg_type == 'batch_progress':
                batch_id = data.get('batch_id', 'unknown')
                progress = data.get('progress', 0)
                current_frame = data.get('current_frame', 0)
                print(f"⚡ [{timestamp.strftime('%H:%M:%S')}] Progression: {batch_id[:8]}... "
                      f"{progress:.1f}% ({current_frame} images)")
                
            elif msg_type == 'batch_completed':
                batch_id = data.get('batch_id', 'unknown')
                processing_time = data.get('processing_time', 0)
                frames_processed = data.get('frames_processed', 0)
                print(f"✅ [{timestamp.strftime('%H:%M:%S')}] Lot terminé: {batch_id[:8]}... "
                      f"({processing_time:.1f}s, {frames_processed} images)")
                self.stats['batches_completed'] += 1
                
            elif msg_type == 'batch_failed':
                batch_id = data.get('batch_id', 'unknown')
                error = data.get('error_message', 'Erreur inconnue')
                print(f"❌ [{timestamp.strftime('%H:%M:%S')}] Lot échoué: {batch_id[:8]}... "
                      f"({error})")
                
            elif msg_type == 'heartbeat':
                status = data.get('status', 'unknown')
                current_batch = data.get('current_batch')
                progress = data.get('progress', 0)
                
                if current_batch:
                    print(f"💓 [{timestamp.strftime('%H:%M:%S')}] Heartbeat: {client_mac[:8]}... "
                          f"({status}, lot: {current_batch[:8]}..., {progress:.1f}%)")
                
            elif msg_type == 'error':
                error_msg = data.get('error_message', 'Erreur inconnue')
                print(f"🚨 [{timestamp.strftime('%H:%M:%S')}] ERREUR: {error_msg}")
            
            # Affichage périodique des statistiques
            if self.stats['messages_received'] % 50 == 0:
                self.display_stats()
                
        except json.JSONDecodeError:
            print(f"⚠️  Message non-JSON reçu: {message_str[:100]}...")
        except Exception as e:
            print(f"⚠️  Erreur traitement message: {e}")
    
    def display_stats(self):
        """Affiche les statistiques"""
        uptime = time.time() - self.stats['start_time']
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        
        print("-" * 60)
        print(f"📊 STATISTIQUES ({hours:02d}h{minutes:02d}m)")
        print(f"   Messages reçus: {self.stats['messages_received']}")
        print(f"   Clients vus: {len(self.stats['clients_seen'])}")
        print(f"   Lots terminés: {self.stats['batches_completed']}")
        print(f"   Débit moyen: {self.stats['messages_received'] / max(uptime, 1):.1f} msg/s")
        print("-" * 60)

async def main():
    """Point d'entrée principal"""
    parser = argparse.ArgumentParser(description="Moniteur réseau UpscalingByNetwork")
    parser.add_argument('--host', default='localhost', help='Adresse du serveur')
    parser.add_argument('--port', type=int, default=8888, help='Port du serveur')
    parser.add_argument('--stats-interval', type=int, default=30, 
                       help='Intervalle d\'affichage des stats (secondes)')
    
    args = parser.parse_args()
    
    monitor = NetworkMonitor(args.host, args.port)
    
    try:
        await monitor.connect_and_monitor()
    except KeyboardInterrupt:
        print("\n🛑 Surveillance interrompue par l'utilisateur")
        monitor.display_stats()
    except Exception as e:
        print(f"❌ Erreur de monitoring: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())