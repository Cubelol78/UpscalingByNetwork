"""
Mixin pour le contrôle du serveur
"""

import threading
import asyncio
from PyQt5.QtWidgets import QMessageBox
from config.settings import config

class ServerControlMixin:
    """Mixin pour les fonctionnalités de contrôle du serveur"""
    
    def start_server(self):
        """Démarre le serveur"""
        if self.server.running:
            return
        
        try:
            # Mise à jour de la configuration avant démarrage
            if hasattr(self, 'status_bar'):
                # Récupération des paramètres depuis l'onglet config si disponible
                if hasattr(self.tabs_manager, 'config_tab'):
                    config_tab = self.tabs_manager.config_tab
                    config.HOST = config_tab.host_input.text().strip()
                    config.PORT = config_tab.port_input.value()
            
            # Démarrage du serveur dans un thread séparé
            self.server_thread = threading.Thread(target=self.run_server, daemon=True)
            self.server_thread.start()
            
            # Mise à jour de l'interface
            self.status_bar.set_server_running(True)
            
            self.logger.info(f"Serveur démarré sur {config.HOST}:{config.PORT}")
            
        except Exception as e:
            self.logger.error(f"Erreur démarrage serveur: {e}")
            QMessageBox.critical(self, "Erreur", f"Impossible de démarrer le serveur:\n{str(e)}")
    
    def stop_server(self):
        """Arrête le serveur"""
        reply = QMessageBox.question(
            self, "Confirmation", "Êtes-vous sûr de vouloir arrêter le serveur?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                # Arrêt du serveur
                if self.server.running:
                    # Créer une nouvelle boucle d'événements pour l'arrêt
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self.server.stop())
                    loop.close()
                
                # Mise à jour de l'interface
                self.status_bar.set_server_running(False)
                
                self.logger.info("Serveur arrêté")
                
            except Exception as e:
                self.logger.error(f"Erreur arrêt serveur: {e}")
    
    def run_server(self):
        """Lance le serveur dans une nouvelle boucle d'événements"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.server.start())
        except Exception as e:
            self.logger.error(f"Erreur dans run_server: {e}")
        finally:
            # Mise à jour de l'interface en cas d'arrêt inattendu
            if hasattr(self, 'status_bar'):
                self.status_bar.set_server_running(False)