#!/usr/bin/env python3
"""
Point d'entrée principal du serveur de calcul distribué pour upscaling vidéo
Version corrigée pour les problèmes de coroutine et d'arrêt
"""

import sys
import os
import asyncio
import threading
import signal
from pathlib import Path

# Ajout du chemin racine au PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

from PyQt5.QtWidgets import QApplication, QStyleFactory
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
import qdarkstyle

from core.server import UpscalingServer
from gui.main_window import MainWindow
from utils.logger import setup_logger
from config.settings import config

# Variable globale pour le serveur (pour le signal handler)
global_server = None

def signal_handler(signum, frame):
    """Gestionnaire de signaux pour arrêt propre"""
    global global_server
    print(f"\nSignal {signum} reçu, arrêt en cours...")
    
    if global_server and global_server.running:
        try:
            global_server.stop_sync()
        except Exception as e:
            print(f"Erreur lors de l'arrêt du serveur: {e}")
    
    sys.exit(0)

def main():
    """Point d'entrée principal"""
    global global_server
    
    # Configuration du logging
    logger = setup_logger()
    logger.info("Démarrage du serveur d'upscaling distribué")
    
    # Installation des gestionnaires de signaux
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Création de l'application Qt
    app = QApplication(sys.argv)
    app.setApplicationName("Distributed Upscaling Server")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("DistributedUpscaling")
    
    # Application du thème sombre
    try:
        app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())
    except Exception as e:
        logger.warning(f"Impossible de charger le thème sombre: {e}")
    
    # Création du serveur backend
    server = UpscalingServer()
    global_server = server  # Pour le signal handler
    
    # Création de l'interface graphique
    main_window = MainWindow(server)
    main_window.show()
    
    logger.info("Interface graphique démarrée")
    
    # Gestionnaire de fermeture de l'application
    def cleanup_on_quit():
        """Nettoyage lors de la fermeture de l'application"""
        logger.info("Fermeture de l'application")
        
        if server.running:
            try:
                server.stop_sync()
                logger.info("Serveur arrêté proprement")
            except Exception as e:
                logger.error(f"Erreur lors de l'arrêt du serveur: {e}")
    
    # Connexion du signal de fermeture
    app.aboutToQuit.connect(cleanup_on_quit)
    
    # Boucle principale
    try:
        exit_code = app.exec_()
        
    except KeyboardInterrupt:
        logger.info("Interruption clavier détectée")
        exit_code = 0
        
    except Exception as e:
        logger.error(f"Erreur dans la boucle principale: {e}")
        exit_code = 1
    
    finally:
        # Nettoyage final
        logger.info("Nettoyage final")
        
        if server.running:
            try:
                server.stop_sync()
            except Exception as e:
                logger.error(f"Erreur nettoyage final: {e}")
    
    return exit_code

def run_server(server):
    """Lance le serveur dans une nouvelle boucle d'événements - OBSOLÈTE"""
    # Cette fonction est maintenant obsolète car la gestion est faite dans server_control.py
    pass

if __name__ == "__main__":
    sys.exit(main())