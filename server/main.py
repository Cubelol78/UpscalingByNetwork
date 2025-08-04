# UpscalingByNetwork/server/server_main.py
"""
Point d'entrée principal du serveur d'upscaling distribué
Version corrigée pour les imports relatifs
"""

import sys
import os
import asyncio
import logging
from pathlib import Path

# CORRECTIF IMPORT: Ajouter le dossier parent au PYTHONPATH
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent  # UpscalingByNetwork/
server_root = current_dir  # UpscalingByNetwork/server/

# Ajouter les chemins nécessaires
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(server_root))

# Configuration du logging avant tous les autres imports
def setup_logging():
    """Configure le système de logging"""
    log_dir = server_root / "logs"
    log_dir.mkdir(exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_dir / "server.log"),
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
    
    if missing_deps:
        logger = logging.getLogger(__name__)
        logger.error("Dépendances manquantes:")
        for dep in missing_deps:
            logger.error(f"  - {dep}")
        logger.error("Installez avec: pip install PyQt5 qasync cryptography")
        return False
    
    return True

def create_directories():
    """Crée les dossiers nécessaires"""
    directories = [
        server_root / "server_work",
        server_root / "server_work" / "jobs",
        server_root / "server_work" / "temp",
        server_root / "server_work" / "encryption_keys",
        server_root / "logs",
        server_root / "output"
    ]
    
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

async def run_server_gui(host: str = "0.0.0.0", port: int = 8888):
    """Lance le serveur avec interface graphique"""
    try:
        # Import des modules GUI après correction du PYTHONPATH
        import qasync
        from PyQt5.QtWidgets import QApplication
        from gui.server_window import ServerWindow
        
        # Application Qt
        app = QApplication(sys.argv)
        app.setApplicationName("UpscalingByNetwork Server")
        app.setApplicationVersion("1.0.0")
        app.setOrganizationName("UpscalingByNetwork")
        
        # Event loop asynchrone  
        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)
        
        # Fenêtre principale
        window = ServerWindow()
        window.set_server_config(host, port)
        window.show()
        
        logger = logging.getLogger(__name__)
        logger.info(f"Interface graphique serveur démarrée sur {host}:{port}")
        
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

async def run_server_console(host: str = "0.0.0.0", port: int = 8888):
    """Lance le serveur en mode console"""
    try:
        # Import du serveur distribué
        from core.distributed_server import DistributedServer
        
        logger = logging.getLogger(__name__)
        logger.info(f"Démarrage serveur console sur {host}:{port}")
        
        # Création et démarrage du serveur
        server = DistributedServer()
        await server.start(host, port)
        
        logger.info("Serveur démarré. Appuyez sur Ctrl+C pour arrêter.")
        
        # Boucle principale
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Arrêt du serveur...")
            await server.stop()
            
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Erreur serveur console: {e}")
        return False

def main():
    """Point d'entrée principal"""
    import argparse
    
    # Configuration des arguments
    parser = argparse.ArgumentParser(description="Serveur d'upscaling distribué")
    parser.add_argument("--host", default="0.0.0.0", help="Adresse d'écoute")
    parser.add_argument("--port", type=int, default=8888, help="Port d'écoute")
    parser.add_argument("--no-gui", action="store_true", help="Mode console uniquement")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], 
                       default="INFO", help="Niveau de log")
    
    args = parser.parse_args()
    
    # Configuration du logging
    setup_logging()
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    logger = logging.getLogger(__name__)
    logger.info("=== DÉMARRAGE SERVEUR UPSCALING DISTRIBUÉ ===")
    logger.info(f"Racine projet: {project_root}")
    logger.info(f"Racine serveur: {server_root}")
    
    # Vérifications préliminaires
    if not check_dependencies():
        return 1
    
    create_directories()
    
    # Démarrage selon le mode
    try:
        if args.no_gui:
            asyncio.run(run_server_console(args.host, args.port))
        else:
            asyncio.run(run_server_gui(args.host, args.port))
    except KeyboardInterrupt:
        logger.info("Arrêt demandé par l'utilisateur")
    except Exception as e:
        logger.error(f"Erreur fatale: {e}")
        return 1
    
    logger.info("Serveur arrêté")
    return 0

if __name__ == "__main__":
    sys.exit(main())