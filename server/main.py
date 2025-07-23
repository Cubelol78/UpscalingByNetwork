#!/usr/bin/env python3
"""
Point d'entrée principal du serveur de calcul distribué pour upscaling vidéo
Version corrigée pour les problèmes de coroutine
"""

import sys
import os
import asyncio
import threading
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
from config.settings import ServerConfig

def main():
    """Point d'entrée principal"""
    # Configuration du logging
    logger = setup_logger()
    logger.info("Démarrage du serveur d'upscaling distribué")
    
    # Création de l'application Qt
    app = QApplication(sys.argv)
    app.setApplicationName("Distributed Upscaling Server")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("DistributedUpscaling")
    
    # Application du thème sombre
    app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())
    
    # Création du serveur backend
    server = UpscalingServer()
    
    # Création de l'interface graphique
    main_window = MainWindow(server)
    main_window.show()
    
    logger.info("Interface graphique démarrée")
    
    # Boucle principale
    exit_code = app.exec_()
    
    # Nettoyage - CORRECTION DU PROBLÈME COROUTINE
    logger.info("Arrêt du serveur")
    
    # Arrêt synchrone du serveur si en cours
    if server.running:
        try:
            # Créer une nouvelle boucle pour l'arrêt propre
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(server.stop())
            loop.close()
        except Exception as e:
            logger.error(f"Erreur lors de l'arrêt du serveur: {e}")
    
    return exit_code

def run_server(server):
    """Lance le serveur dans une nouvelle boucle d'événements"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(server.start())

if __name__ == "__main__":
    sys.exit(main())