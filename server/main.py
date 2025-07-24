# server/main.py
"""
Point d'entrée principal du serveur d'upscaling distribué
"""

import sys
import os
import asyncio
import logging
from pathlib import Path

# Ajout du dossier parent au path pour les imports
sys.path.insert(0, str(Path(__file__).parent))

try:
    from PyQt5.QtWidgets import QApplication, QMessageBox
    from PyQt5.QtCore import QTimer
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False
    print("PyQt5 non disponible - Mode console seulement")

from core.server import UpscalingServer
from utils.config import config
from utils.logger import setup_logger

def setup_logging():
    """Configure le système de logging"""
    log_level = config.get("monitoring.log_level", "INFO")
    
    # Configuration basique si pas de logger personnalisé
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('server.log')
        ]
    )
    
    return logging.getLogger(__name__)

def validate_environment():
    """Valide l'environnement d'exécution"""
    logger = logging.getLogger(__name__)
    issues = []
    
    # Vérification de la configuration
    validation = config.validate_config()
    if not validation['valid']:
        issues.extend(validation['errors'])
    
    # Vérification des dépendances critiques
    dependencies = [
        ('ffmpeg', 'FFmpeg requis pour l\'extraction/assemblage vidéo'),
        ('realesrgan-ncnn-vulkan', 'Real-ESRGAN requis pour l\'upscaling')
    ]
    
    for dep, description in dependencies:
        if not check_dependency(dep):
            issues.append(f"{description} - {dep} non trouvé dans PATH")
    
    # Vérification des dossiers
    try:
        directories = config.get_work_directories()
        for name, path in directories.items():
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
                logger.info(f"Dossier {name} créé: {path}")
    except Exception as e:
        issues.append(f"Impossible de créer les dossiers de travail: {e}")
    
    if issues:
        logger.warning("Problèmes détectés dans l'environnement:")
        for issue in issues:
            logger.warning(f"  - {issue}")
    
    return len(issues) == 0, issues

def check_dependency(command):
    """Vérifie si une commande est disponible dans le PATH"""
    import shutil
    return shutil.which(command) is not None

class ServerApplication:
    """Application serveur principale"""
    
    def __init__(self, gui_mode=True):
        self.logger = setup_logging()
        self.gui_mode = gui_mode and GUI_AVAILABLE
        self.server = None
        self.app = None
        self.main_window = None
        
        self.logger.info("=== Serveur d'Upscaling Distribué ===")
        self.logger.info(f"Mode: {'GUI' if self.gui_mode else 'Console'}")
    
    async def start_server(self):
        """Démarre le serveur"""
        try:
            self.server = UpscalingServer()
            await self.server.start()
            self.logger.info("Serveur démarré avec succès")
            return True
        except Exception as e:
            self.logger.error(f"Erreur démarrage serveur: {e}")
            return False
    
    async def stop_server(self):
        """Arrête le serveur"""
        if self.server:
            try:
                await self.server.stop()
                self.logger.info("Serveur arrêté")
            except Exception as e:
                self.logger.error(f"Erreur arrêt serveur: {e}")
    
    def run_gui(self):
        """Lance l'application en mode GUI"""
        if not GUI_AVAILABLE:
            self.logger.error("PyQt5 non disponible - impossible de lancer l'interface graphique")
            return False
        
        try:
            from gui.main_window import MainWindow
            
            self.app = QApplication(sys.argv)
            self.app.setApplicationName("Distributed Upscaling Server")
            self.app.setApplicationVersion("1.0.0")
            
            # Validation de l'environnement
            env_valid, issues = validate_environment()
            if not env_valid:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Warning)
                msg.setWindowTitle("Problèmes d'environnement")
                msg.setText("Des problèmes ont été détectés dans l'environnement:")
                msg.setDetailedText("\n".join(issues))
                msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
                
                if msg.exec_() == QMessageBox.Cancel:
                    return False
            
            # Création de la fenêtre principale
            self.main_window = MainWindow(self.server)
            self.main_window.show()
            
            # Démarrage du serveur
            asyncio.create_task(self.start_server())
            
            # Lancement de l'application
            return self.app.exec_() == 0
            
        except Exception as e:
            self.logger.error(f"Erreur lancement GUI: {e}")
            return False
    
    async def run_console(self):
        """Lance l'application en mode console"""
        self.logger.info("Démarrage en mode console")
        
        # Validation de l'environnement
        env_valid, issues = validate_environment()
        if not env_valid:
            self.logger.warning("Problèmes d'environnement détectés, continuation...")
        
        # Démarrage du serveur
        if not await self.start_server():
            self.logger.error("Impossible de démarrer le serveur")
            return False
        
        try:
            # Boucle principale
            self.logger.info("Serveur en fonctionnement - Ctrl+C pour arrêter")
            
            while True:
                await asyncio.sleep(1)
                
                # Affichage périodique des statistiques
                if hasattr(self.server, 'clients'):
                    clients_online = len([c for c in self.server.clients.values() if c.is_online])
                    if clients_online > 0:
                        self.logger.info(f"Clients connectés: {clients_online}")
                
        except KeyboardInterrupt:
            self.logger.info("Arrêt demandé par l'utilisateur")
        except Exception as e:
            self.logger.error(f"Erreur serveur: {e}")
        finally:
            await self.stop_server()
        
        return True
    
    def run(self):
        """Lance l'application"""
        if self.gui_mode:
            return self.run_gui()
        else:
            return asyncio.run(self.run_console())

def main():
    """Fonction principale"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Serveur d'Upscaling Distribué")
    parser.add_argument("--console", action="store_true", 
                       help="Lance en mode console (sans interface graphique)")
    parser.add_argument("--config", type=str, 
                       help="Fichier de configuration personnalisé")
    parser.add_argument("--port", type=int, 
                       help="Port du serveur (défaut: 8765)")
    parser.add_argument("--host", type=str, 
                       help="Adresse d'écoute (défaut: 0.0.0.0)")
    parser.add_argument("--log-level", choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help="Niveau de logging")
    
    args = parser.parse_args()
    
    # Configuration des paramètres
    if args.config and os.path.exists(args.config):
        # TODO: Charger fichier de configuration personnalisé
        pass
    
    if args.port:
        config.set("server.port", args.port)
    
    if args.host:
        config.set("server.host", args.host)
    
    if args.log_level:
        config.set("monitoring.log_level", args.log_level)
    
    # Lancement de l'application
    gui_mode = not args.console
    app = ServerApplication(gui_mode=gui_mode)
    
    try:
        success = app.run()
        sys.exit(0 if success else 1)
    except Exception as e:
        logging.error(f"Erreur fatale: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()