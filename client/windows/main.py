# client/windows/main.py
"""
Point d'entrée principal du client Windows d'upscaling distribué
"""

import sys
import os
import asyncio
import logging
from pathlib import Path

# Ajout du dossier parent au path pour les imports
sys.path.insert(0, str(Path(__file__).parent))

try:
    from PyQt5.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon
    from PyQt5.QtCore import QTimer
    from PyQt5.QtGui import QIcon
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False
    print("PyQt5 non disponible - Mode console seulement")

from core.client import DistributedUpscalingClient
from utils.config import config
from utils.system_info import SystemInfo

def setup_logging():
    """Configure le système de logging"""
    log_level = config.get("client.log_level", "INFO")
    
    # Dossier de logs
    log_dir = config.get_work_directory() / "logs"
    log_dir.mkdir(exist_ok=True)
    
    # Configuration du logging
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_dir / 'client.log')
        ]
    )
    
    return logging.getLogger(__name__)

def validate_environment():
    """Valide l'environnement d'exécution du client"""
    logger = logging.getLogger(__name__)
    issues = []
    warnings = []
    
    # Vérification de la configuration
    if not config.validate_config():
        issues.append("Configuration client incomplète")
    
    # Vérification de Real-ESRGAN
    from core.processor import ClientProcessor
    
    # Test temporaire du processeur
    try:
        temp_client = type('TempClient', (), {})()
        processor = ClientProcessor(temp_client)
        realesrgan_test = processor.test_realesrgan()
        
        if not realesrgan_test['available']:
            issues.append(f"Real-ESRGAN non disponible: {realesrgan_test.get('error', 'Raison inconnue')}")
        else:
            logger.info(f"Real-ESRGAN détecté: {realesrgan_test.get('version', 'Version inconnue')}")
            
            if not realesrgan_test['gpu_support']:
                warnings.append("Support GPU non détecté - traitement CPU seulement")
                
    except Exception as e:
        issues.append(f"Erreur test Real-ESRGAN: {e}")
    
    # Vérification des informations système
    try:
        system_info = SystemInfo()
        sys_info = system_info.get_system_info()
        
        # Vérifications de base
        if sys_info['hardware']['memory'].get('total_ram_gb', 0) < 4:
            warnings.append("RAM faible détectée (< 4GB) - performances réduites")
        
        if not sys_info['vulkan']['supported']:
            warnings.append("Support Vulkan non détecté - compatibilité limitée")
            
    except Exception as e:
        warnings.append(f"Impossible de collecter les informations système: {e}")
    
    # Vérification des dossiers de travail
    try:
        work_dir = config.get_work_directory()
        if not work_dir.exists():
            work_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Dossier de travail créé: {work_dir}")
    except Exception as e:
        issues.append(f"Impossible de créer le dossier de travail: {e}")
    
    # Affichage des résultats
    if warnings:
        logger.warning("Avertissements détectés:")
        for warning in warnings:
            logger.warning(f"  - {warning}")
    
    if issues:
        logger.error("Problèmes critiques détectés:")
        for issue in issues:
            logger.error(f"  - {issue}")
    
    return len(issues) == 0, issues, warnings

class ClientApplication:
    """Application client principale"""
    
    def __init__(self, gui_mode=True):
        self.logger = setup_logging()
        self.gui_mode = gui_mode and GUI_AVAILABLE
        self.client = None
        self.app = None
        self.main_window = None
        self.system_tray = None
        
        self.logger.info("=== Client d'Upscaling Distribué ===")
        self.logger.info(f"Mode: {'GUI' if self.gui_mode else 'Console'}")
        self.logger.info(f"Plateforme: {sys.platform}")
    
    async def start_client(self):
        """Démarre le client"""
        try:
            self.client = DistributedUpscalingClient()
            
            # Configuration automatique si nécessaire
            server_config = config.get_server_config()
            if server_config.get('host') and server_config.get('port'):
                await self.client.connect(
                    server_config['host'], 
                    server_config['port']
                )
            
            self.logger.info("Client initialisé avec succès")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur démarrage client: {e}")
            return False
    
    async def stop_client(self):
        """Arrête le client"""
        if self.client:
            try:
                await self.client.disconnect()
                self.logger.info("Client arrêté")
            except Exception as e:
                self.logger.error(f"Erreur arrêt client: {e}")
    
    def setup_system_tray(self):
        """Configure l'icône dans la barre système"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return False
        
        try:
            # Icône simple (peut être remplacée par une vraie icône)
            self.system_tray = QSystemTrayIcon(self.app)
            
            # Menu contextuel
            from PyQt5.QtWidgets import QMenu, QAction
            
            tray_menu = QMenu()
            
            show_action = QAction("Afficher", self.app)
            show_action.triggered.connect(self.show_main_window)
            tray_menu.addAction(show_action)
            
            tray_menu.addSeparator()
            
            quit_action = QAction("Quitter", self.app)
            quit_action.triggered.connect(self.quit_application)
            tray_menu.addAction(quit_action)
            
            self.system_tray.setContextMenu(tray_menu)
            self.system_tray.show()
            
            # Messages d'information
            self.system_tray.showMessage(
                "Client d'Upscaling",
                "Client démarré en arrière-plan",
                QSystemTrayIcon.Information,
                3000
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur configuration barre système: {e}")
            return False
    
    def show_main_window(self):
        """Affiche la fenêtre principale"""
        if self.main_window:
            self.main_window.show()
            self.main_window.raise_()
            self.main_window.activateWindow()
    
    def quit_application(self):
        """Quitte l'application"""
        if self.app:
            self.app.quit()
    
    def run_gui(self):
        """Lance l'application en mode GUI"""
        if not GUI_AVAILABLE:
            self.logger.error("PyQt5 non disponible - impossible de lancer l'interface graphique")
            return False
        
        try:
            from gui.main_window import ClientMainWindow
            
            self.app = QApplication(sys.argv)
            self.app.setApplicationName("Distributed Upscaling Client")
            self.app.setApplicationVersion("1.0.0")
            
            # Configuration pour rester en arrière-plan
            self.app.setQuitOnLastWindowClosed(False)
            
            # Validation de l'environnement
            env_valid, issues, warnings = validate_environment()
            
            if not env_valid:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Critical)
                msg.setWindowTitle("Problèmes critiques")
                msg.setText("Des problèmes critiques empêchent le démarrage du client:")
                msg.setDetailedText("\n".join(issues))
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec_()
                return False
            
            if warnings:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Warning)
                msg.setWindowTitle("Avertissements")
                msg.setText("Des avertissements ont été détectés:")
                msg.setDetailedText("\n".join(warnings))
                msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
                
                if msg.exec_() == QMessageBox.Cancel:
                    return False
            
            # Démarrage du client
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Création de la fenêtre principale
            self.main_window = ClientMainWindow(self.client)
            
            # Configuration de la barre système
            if not self.setup_system_tray():
                # Si pas de barre système, montrer la fenêtre
                self.main_window.show()
            
            # Démarrage asynchrone du client
            loop.create_task(self.start_client())
            
            # Timer pour traiter les événements asyncio
            timer = QTimer()
            timer.timeout.connect(lambda: loop.run_until_complete(asyncio.sleep(0.01)))
            timer.start(10)  # 10ms
            
            # Lancement de l'application
            result = self.app.exec_()
            
            # Nettoyage
            loop.run_until_complete(self.stop_client())
            loop.close()
            
            return result == 0
            
        except Exception as e:
            self.logger.error(f"Erreur lancement GUI: {e}")
            return False
    
    async def run_console(self):
        """Lance l'application en mode console"""
        self.logger.info("Démarrage en mode console")
        
        # Validation de l'environnement
        env_valid, issues, warnings = validate_environment()
        
        if not env_valid:
            self.logger.error("Problèmes critiques détectés:")
            for issue in issues:
                self.logger.error(f"  - {issue}")
            return False
        
        if warnings:
            self.logger.warning("Avertissements (continuation possible):")
            for warning in warnings:
                self.logger.warning(f"  - {warning}")
        
        # Démarrage du client
        if not await self.start_client():
            self.logger.error("Impossible de démarrer le client")
            return False
        
        try:
            # Boucle principale
            self.logger.info("Client en fonctionnement - Ctrl+C pour arrêter")
            self.logger.info("Commandes disponibles:")
            self.logger.info("  status - Affiche le statut")
            self.logger.info("  connect <host> <port> - Se connecte à un serveur")
            self.logger.info("  disconnect - Se déconnecte")
            self.logger.info("  quit - Quitte l'application")
            
            # Interface console simple
            import threading
            
            def console_input():
                while True:
                    try:
                        command = input("> ").strip().lower()
                        if command == "quit":
                            break
                        elif command == "status":
                            self.print_status()
                        elif command.startswith("connect"):
                            parts = command.split()
                            if len(parts) == 3:
                                host, port = parts[1], int(parts[2])
                                asyncio.run_coroutine_threadsafe(
                                    self.client.connect(host, port), 
                                    asyncio.get_event_loop()
                                )
                        elif command == "disconnect":
                            asyncio.run_coroutine_threadsafe(
                                self.client.disconnect(), 
                                asyncio.get_event_loop()
                            )
                    except KeyboardInterrupt:
                        break
                    except Exception as e:
                        print(f"Erreur commande: {e}")
            
            # Démarrage du thread console
            console_thread = threading.Thread(target=console_input, daemon=True)
            console_thread.start()
            
            # Boucle principale asynchrone
            while True:
                await asyncio.sleep(1)
                
                # Affichage périodique du statut si connecté
                if self.client and hasattr(self.client, 'is_connected') and self.client.is_connected:
                    if hasattr(self.client, 'processor') and self.client.processor.is_processing:
                        batch_id = self.client.processor.current_batch_id
                        duration = self.client.processor.processing_start_time
                        if duration:
                            duration = asyncio.get_event_loop().time() - duration
                            self.logger.info(f"Traitement en cours: {batch_id} ({duration:.1f}s)")
                
        except KeyboardInterrupt:
            self.logger.info("Arrêt demandé par l'utilisateur")
        except Exception as e:
            self.logger.error(f"Erreur client: {e}")
        finally:
            await self.stop_client()
        
        return True
    
    def print_status(self):
        """Affiche le statut du client"""
        if not self.client:
            print("Client non initialisé")
            return
        
        print("\n=== Statut du Client ===")
        
        # État de connexion
        if hasattr(self.client, 'is_connected'):
            status = "Connecté" if self.client.is_connected else "Déconnecté"
            print(f"Connexion: {status}")
            
            if self.client.is_connected and hasattr(self.client, 'server_host'):
                print(f"Serveur: {self.client.server_host}:{self.client.server_port}")
        
        # État du processeur
        if hasattr(self.client, 'processor'):
            processor = self.client.processor
            stats = processor.get_stats()
            
            print(f"Traitement: {'En cours' if processor.is_processing else 'Inactif'}")
            if processor.current_batch_id:
                print(f"Lot actuel: {processor.current_batch_id}")
            
            print(f"Lots traités: {stats['performance_stats']['batches_processed']}")
            print(f"Frames traitées: {stats['performance_stats']['total_frames_processed']}")
            print(f"Erreurs: {stats['performance_stats']['errors_count']}")
        
        # Informations système
        try:
            system_info = SystemInfo()
            performance_score = system_info.get_performance_score()
            print(f"Score de performance: {performance_score:.1f}/100")
        except:
            pass
        
        print("========================\n")
    
    def run(self):
        """Lance l'application"""
        if self.gui_mode:
            return self.run_gui()
        else:
            return asyncio.run(self.run_console())

def main():
    """Fonction principale"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Client d'Upscaling Distribué")
    parser.add_argument("--console", action="store_true", 
                       help="Lance en mode console (sans interface graphique)")
    parser.add_argument("--server", type=str, 
                       help="Adresse du serveur (format host:port)")
    parser.add_argument("--auto-connect", action="store_true",
                       help="Connexion automatique au démarrage")
    parser.add_argument("--log-level", choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help="Niveau de logging")
    parser.add_argument("--work-dir", type=str,
                       help="Dossier de travail personnalisé")
    
    args = parser.parse_args()
    
    # Configuration des paramètres
    if args.server:
        try:
            host, port = args.server.split(':')
            config.set("server.host", host)
            config.set("server.port", int(port))
        except ValueError:
            print("Format serveur invalide. Utilisez host:port")
            sys.exit(1)
    
    if args.auto_connect:
        config.set("client.auto_connect", True)
    
    if args.log_level:
        config.set("client.log_level", args.log_level)
    
    if args.work_dir:
        config.set("processing.work_directory", args.work_dir)
    
    # Lancement de l'application
    gui_mode = not args.console
    app = ClientApplication(gui_mode=gui_mode)
    
    try:
        success = app.run()
        sys.exit(0 if success else 1)
    except Exception as e:
        logging.error(f"Erreur fatale: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()