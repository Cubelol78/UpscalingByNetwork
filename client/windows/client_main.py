# UpscalingByNetwork/client/windows/client_main.py

"""
Point d'entrée principal pour le client Windows
UpscalingByNetwork/client/windows/client_main.py
"""

import sys
import os
import asyncio
import argparse
import logging
import signal
from pathlib import Path

# Ajout du dossier parent au PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

def setup_logging(level: str = "INFO", log_file: str = None):
    """Configure le logging pour le client"""
    
    # Niveau de logging
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    # Format des logs
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Configuration de base
    handlers = [logging.StreamHandler(sys.stdout)]
    
    # Fichier de log si spécifié
    if log_file:
        log_dir = Path(log_file).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding='utf-8'))
    
    logging.basicConfig(
        level=numeric_level,
        format=log_format,
        handlers=handlers
    )
    
    # Configuration spécifique
    logging.getLogger('websockets').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)

def check_dependencies():
    """Vérifie les dépendances requises"""
    logger = logging.getLogger(__name__)
    
    missing_deps = []
    
    # Vérification des modules Python
    required_modules = [
        'websockets',
        'cryptography',
        'psutil',
        'PyQt5'
    ]
    
    for module in required_modules:
        try:
            __import__(module)
        except ImportError:
            missing_deps.append(f"Module Python: {module}")
    
    # Vérification de Real-ESRGAN (obligatoire côté client)
    realesrgan_path = Path("realesrgan-ncnn-vulkan/realesrgan-ncnn-vulkan.exe")
    if not realesrgan_path.exists():
        missing_deps.append(f"Real-ESRGAN: {realesrgan_path}")
        logger.error(f"Real-ESRGAN non trouvé à {realesrgan_path}")
        logger.error("Le client ne peut pas fonctionner sans Real-ESRGAN")
    
    if missing_deps:
        logger.error("Dépendances manquantes:")
        for dep in missing_deps:
            logger.error(f"  - {dep}")
        return False
    
    logger.info("Toutes les dépendances sont satisfaites")
    return True

def create_directories():
    """Crée les dossiers nécessaires"""
    logger = logging.getLogger(__name__)
    
    directories = [
        'client_work',
        'client_work/temp',
        'client_work/temp/received_batches',
        'client_work/temp/processed_batches',
        'client_work/logs'
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        logger.debug(f"Dossier créé/vérifié: {directory}")

async def run_client_gui():
    """Lance le client avec interface graphique"""
    try:
        import qasync
        from PyQt5.QtWidgets import QApplication
        from gui.client_window import ClientWindow
        
        # Application Qt
        app = QApplication(sys.argv)
        app.setApplicationName("UpscalingByNetwork Client")
        app.setApplicationVersion("1.0.0")
        app.setQuitOnLastWindowClosed(False)  # Continue avec l'icône système
        
        # Event loop asynchrone
        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)
        
        # Fenêtre principale
        window = ClientWindow()
        window.show()
        
        logger = logging.getLogger(__name__)
        logger.info("Interface graphique client démarrée")
        
        # Connexion automatique si configurée
        if window.config.get('auto_connect', False):
            host = window.config['server_host']
            port = window.config['server_port']
            await window.client.connect_to_server(host, port)
        
        # Boucle principale
        with loop:
            await loop.create_future()  # Run forever
            
    except ImportError as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Interface graphique non disponible: {e}")
        logger.info("Utilisez --no-gui pour le mode console")
        return False
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Erreur interface graphique: {e}")
        return False

async def run_client_console(host: str, port: int):
    """Lance le client en mode console"""
    from core.distributed_client import DistributedClient
    
    logger = logging.getLogger(__name__)
    logger.info("Démarrage du client en mode console")
    
    # Création du client
    client = DistributedClient()
    
    # Callbacks pour affichage console
    def on_connection_changed(connected: bool, info: str):
        if connected:
            logger.info(f"✅ Connecté au serveur: {info}")
        else:
            logger.info("❌ Déconnecté du serveur")
    
    def on_batch_received(batch_id: str, frame_count: int):
        short_id = batch_id.split('_')[-1] if '_' in batch_id else batch_id[:8]
        logger.info(f"📦 Nouveau lot reçu: {short_id} ({frame_count} images)")
    
    def on_progress_update(batch_id: str, progress: float, current_frame: int):
        short_id = batch_id.split('_')[-1] if '_' in batch_id else batch_id[:8]
        logger.info(f"⚡ Progression {short_id}: {progress:.1f}% ({current_frame} images)")
    
    def on_batch_completed(batch_id: str, processing_time: float, frames_processed: int):
        short_id = batch_id.split('_')[-1] if '_' in batch_id else batch_id[:8]
        logger.info(f"✅ Lot terminé {short_id}: {processing_time:.1f}s ({frames_processed} images)")
    
    def on_error(error_message: str):
        logger.error(f"❌ Erreur: {error_message}")
    
    # Configuration des callbacks
    client.on_connection_changed = on_connection_changed
    client.on_batch_received = on_batch_received
    client.on_progress_update = on_progress_update
    client.on_batch_completed = on_batch_completed
    client.on_error = on_error
    
    # Gestionnaire de signaux pour arrêt propre
    def signal_handler(signum, frame):
        logger.info(f"Signal {signum} reçu, arrêt du client...")
        asyncio.create_task(client.disconnect())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Connexion au serveur
        logger.info(f"Connexion au serveur {host}:{port}...")
        success = await client.connect_to_server(host, port)
        
        if not success:
            logger.error("Impossible de se connecter au serveur")
            return False
        
        # Attente indéfinie (le client travaille en arrière-plan)
        logger.info("Client connecté et prêt à recevoir des lots")
        logger.info("Appuyez sur Ctrl+C pour arrêter")
        
        while client.connected:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Interruption clavier, arrêt du client...")
    except Exception as e:
        logger.error(f"Erreur client: {e}")
    finally:
        if client.connected:
            await client.disconnect()
    
    return True

def main():
    """Point d'entrée principal"""
    parser = argparse.ArgumentParser(
        description="Client d'upscaling distribué UpscalingByNetwork",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  %(prog)s                          # Interface graphique
  %(prog)s --no-gui --host 192.168.1.100  # Mode console vers serveur distant
  %(prog)s --auto-connect           # Connexion automatique au démarrage
  %(prog)s --log-level DEBUG        # Logs détaillés
        """
    )
    
    parser.add_argument(
        '--host',
        default='localhost',
        help='Adresse du serveur (défaut: localhost)'
    )
    
    parser.add_argument(
        '--port',
        type=int,
        default=8888,
        help='Port du serveur (défaut: 8888)'
    )
    
    parser.add_argument(
        '--no-gui',
        action='store_true',
        help='Mode console sans interface graphique'
    )
    
    parser.add_argument(
        '--auto-connect',
        action='store_true',
        help='Connexion automatique au démarrage'
    )
    
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Niveau de logging (défaut: INFO)'
    )
    
    parser.add_argument(
        '--log-file',
        help='Fichier de log (défaut: client_work/logs/client.log)'
    )
    
    parser.add_argument(
        '--check-deps',
        action='store_true',
        help='Vérifie uniquement les dépendances et quitte'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='UpscalingByNetwork Client Windows 1.0.0'
    )
    
    args = parser.parse_args()
    
    # Configuration du logging
    log_file = args.log_file or "client_work/logs/client.log"
    setup_logging(args.log_level, log_file)
    
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("UpscalingByNetwork - Client Windows v1.0.0")
    logger.info("=" * 60)
    
    # Vérification des dépendances
    if not check_dependencies():
        if args.check_deps:
            print("❌ Dépendances manquantes")
            sys.exit(1)
        else:
            logger.error("Dépendances manquantes, le client ne peut pas démarrer")
            sys.exit(1)
    elif args.check_deps:
        print("✅ Toutes les dépendances sont satisfaites")
        sys.exit(0)
    
    # Création des dossiers
    create_directories()
    
    # Validation des paramètres
    if not (1024 <= args.port <= 65535):
        logger.error(f"Port invalide: {args.port} (doit être entre 1024 et 65535)")
        sys.exit(1)
    
    logger.info(f"Configuration client:")
    logger.info(f"  - Serveur: {args.host}:{args.port}")
    logger.info(f"  - Mode: {'Console' if args.no_gui else 'Interface graphique'}")
    logger.info(f"  - Connexion auto: {'Oui' if args.auto_connect else 'Non'}")
    logger.info(f"  - Niveau log: {args.log_level}")
    logger.info(f"  - Fichier log: {log_file}")
    
    try:
        if args.no_gui:
            # Mode console
            success = asyncio.run(run_client_console(args.host, args.port))
            sys.exit(0 if success else 1)
        else:
            # Mode interface graphique
            asyncio.run(run_client_gui())
            
    except KeyboardInterrupt:
        logger.info("Arrêt demandé par l'utilisateur")
    except Exception as e:
        logger.error(f"Erreur fatale: {e}")
        sys.exit(1)
    
    logger.info("Client arrêté")
    sys.exit(0)

if __name__ == "__main__":
    main()