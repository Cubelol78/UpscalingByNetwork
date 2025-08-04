# UpscalingByNetwork/client/windows/client_main.py
"""
Point d'entrée principal du client Windows d'upscaling distribué
Version corrigée pour les imports relatifs
"""

import sys
import os
import asyncio
import logging
from pathlib import Path

# CORRECTIF IMPORT: Ajouter les dossiers nécessaires au PYTHONPATH
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent  # UpscalingByNetwork/
client_root = current_dir  # UpscalingByNetwork/client/windows/
shared_root = project_root / "shared"

# Ajouter les chemins nécessaires
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(client_root))
sys.path.insert(0, str(shared_root))

# Configuration du logging avant tous les autres imports
def setup_logging():
    """Configure le système de logging"""
    log_dir = client_root / "client_work" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_dir / "client.log"),
            logging.StreamHandler(sys.stdout)
        ]
    )

def check_dependencies():
    """Vérifie les dépendances critiques"""
    missing_deps = []
    
    try:
        import PyQt5
    except ImportError:
        missing_deps.append("PyQt5")
    
    try:
        import qasync
    except ImportError:
        missing_deps.append("qasync")
    
    try:
        import cryptography
    except ImportError:
        missing_deps.append("cryptography")
    
    try:
        import psutil
    except ImportError:
        missing_deps.append("psutil")
    
    if missing_deps:
        logger = logging.getLogger(__name__)
        logger.error("Dépendances manquantes:")
        for dep in missing_deps:
            logger.error(f"  - {dep}")
        logger.error("Installez avec: pip install PyQt5 qasync cryptography psutil")
        return False
    
    return True

def check_realesrgan():
    """Vérifie la présence de Real-ESRGAN"""
    realesrgan_dir = client_root / "realesrgan-ncnn-vulkan"
    realesrgan_exe = realesrgan_dir / "realesrgan-ncnn-vulkan.exe"
    
    if not realesrgan_exe.exists():
        logger = logging.getLogger(__name__)
        logger.error(f"Real-ESRGAN non trouvé: {realesrgan_exe}")
        logger.error("Téléchargez Real-ESRGAN depuis:")
        logger.error("https://github.com/xinntao/Real-ESRGAN/releases")
        logger.error(f"Et extraire dans: {realesrgan_dir}")
        return False
    
    return True

def create_directories():
    """Crée les dossiers nécessaires"""
    directories = [
        client_root / "client_work",
        client_root / "client_work" / "temp",
        client_root / "client_work" / "temp" / "received_batches",
        client_root / "client_work" / "temp" / "processed_batches",
        client_root / "client_work" / "logs"
    ]
    
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

async def run_client_gui(server_host: str = None, server_port: int = None):
    """Lance le client avec interface graphique"""
    try:
        # Import des modules GUI après correction du PYTHONPATH
        import qasync
        from PyQt5.QtWidgets import QApplication
        from gui.client_window import ClientWindow
        
        # Application Qt
        app = QApplication(sys.argv)
        app.setApplicationName("UpscalingByNetwork Client")
        app.setApplicationVersion("1.0.0")
        app.setOrganizationName("UpscalingByNetwork")
        app.setQuitOnLastWindowClosed(False)  # Continue avec l'icône système
        
        # Event loop asynchrone
        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)
        
        # Fenêtre principale
        window = ClientWindow()
        
        # Configuration du serveur si fournie
        if server_host:
            window.set_server_config(server_host, server_port or 8888)
        
        window.show()
        
        logger = logging.getLogger(__name__)
        logger.info("Interface graphique client démarrée")
        
        # Connexion automatique si configurée
        if window.config.get('auto_connect', False):
            host = window.config['server_host']
            port = window.config['server_port']
            asyncio.create_task(window.connect_to_server(host, port))
        
        # Boucle principale
        with loop:
            await loop.create_future()
            
    except ImportError as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Interface graphique non disponible: {e}")
        logger.info("Solution: pip install PyQt5 qasync")
        logger.info("Ou utilisez --no-gui pour le mode console")
        return False
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Erreur interface graphique: {e}")
        return False

async def run_client_console(server_host: str, server_port: int = 8888):
    """Lance le client en mode console"""
    try:
        # Import du client distribué
        from core.distributed_client import DistributedClient
        
        logger = logging.getLogger(__name__)
        logger.info(f"Démarrage client console vers {server_host}:{server_port}")
        
        # Création et connexion du client
        client = DistributedClient()
        
        # Configuration du client
        client.realesrgan_path = client_root / "realesrgan-ncnn-vulkan" / "realesrgan-ncnn-vulkan.exe"
        client.work_dir = client_root / "client_work"
        
        # Connexion au serveur
        success = await client.connect_to_server(server_host, server_port)
        if not success:
            logger.error("Impossible de se connecter au serveur")
            return False
        
        logger.info("Client connecté. Appuyez sur Ctrl+C pour arrêter.")
        
        # Boucle principale
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Arrêt du client...")
            await client.disconnect()
            
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Erreur client console: {e}")
        return False

def main():
    """Point d'entrée principal"""
    import argparse
    
    # Configuration des arguments
    parser = argparse.ArgumentParser(description="Client d'upscaling distribué")
    parser.add_argument("--host", default="localhost", help="Adresse du serveur")
    parser.add_argument("--port", type=int, default=8888, help="Port du serveur")
    parser.add_argument("--no-gui", action="store_true", help="Mode console uniquement")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], 
                       default="INFO", help="Niveau de log")
    
    args = parser.parse_args()
    
    # Configuration du logging
    setup_logging()
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    logger = logging.getLogger(__name__)
    logger.info("=== DÉMARRAGE CLIENT UPSCALING DISTRIBUÉ ===")
    logger.info(f"Racine projet: {project_root}")
    logger.info(f"Racine client: {client_root}")
    
    # Vérifications préliminaires
    if not check_dependencies():
        return 1
    
    if not check_realesrgan():
        return 1
    
    create_directories()
    
    # Démarrage selon le mode
    try:
        if args.no_gui:
            asyncio.run(run_client_console(args.host, args.port))
        else:
            asyncio.run(run_client_gui(args.host, args.port))
    except KeyboardInterrupt:
        logger.info("Arrêt demandé par l'utilisateur")
    except Exception as e:
        logger.error(f"Erreur fatale: {e}")
        return 1
    
    logger.info("Client arrêté")
    return 0

if __name__ == "__main__":
    sys.exit(main())