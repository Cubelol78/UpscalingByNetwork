"""
Mixin pour le contrôle du serveur avec logique simplifiée
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
            self.logger.warning("Tentative de démarrage d'un serveur déjà en cours")
            return
        
        try:
            # Mise à jour de la configuration avant démarrage (depuis l'interface)
            if hasattr(self.tabs_manager, 'config_tab'):
                config_tab = self.tabs_manager.config_tab
                
                # Mise à jour des paramètres réseau depuis l'interface
                new_host = config_tab.host_input.text().strip()
                new_port = config_tab.port_input.value()
                
                if new_host != config.HOST or new_port != config.PORT:
                    # Sauvegarde automatique des nouveaux paramètres
                    config.apply_and_save(HOST=new_host, PORT=new_port)
            
            # Démarrage du serveur dans un thread séparé
            self.server_thread = threading.Thread(target=self.run_server, daemon=True)
            self.server_thread.start()
            
            # Mise à jour immédiate de l'interface
            self.status_bar.update_button_states()
            
            self.logger.info(f"Serveur démarré sur {config.HOST}:{config.PORT}")
            
        except Exception as e:
            self.logger.error(f"Erreur démarrage serveur: {e}")
            QMessageBox.critical(self, "Erreur", f"Impossible de démarrer le serveur:\n{str(e)}")
    
    def stop_server(self):
        """Arrête le serveur avec confirmation"""
        if not self.server.running:
            self.logger.warning("Tentative d'arrêt d'un serveur déjà arrêté")
            return
        
        # Vérification des jobs en cours
        active_jobs = len([job for job in self.server.jobs.values() 
                          if job.status.value in ['processing', 'extracting', 'assembling']])
        
        # Message de confirmation adapté
        if active_jobs > 0:
            message = (f"Le serveur traite actuellement {active_jobs} job(s).\n"
                      "Êtes-vous sûr de vouloir l'arrêter?\n"
                      "Les jobs en cours seront interrompus.")
            icon = QMessageBox.Warning
        else:
            message = "Êtes-vous sûr de vouloir arrêter le serveur?"
            icon = QMessageBox.Question
        
        reply = QMessageBox.question(
            self, "Confirmation d'arrêt", message,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                # Arrêt du serveur de manière synchrone
                if self.server.running:
                    # Utiliser la méthode synchrone pour éviter les problèmes d'asyncio
                    self.server.stop_sync()
                
                # Mise à jour immédiate de l'interface
                self.status_bar.update_button_states()
                
                self.logger.info("Serveur arrêté")
                
                # Notification optionnelle si des jobs étaient en cours
                if active_jobs > 0:
                    QMessageBox.information(self, "Serveur arrêté", 
                        f"Serveur arrêté. {active_jobs} job(s) ont été interrompus.")
                
            except Exception as e:
                self.logger.error(f"Erreur arrêt serveur: {e}")
                QMessageBox.critical(self, "Erreur", f"Erreur lors de l'arrêt:\n{str(e)}")
                
                # Forcer la mise à jour de l'interface même en cas d'erreur
                self.status_bar.update_button_states()
    
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
                self.status_bar.update_button_states()
    
    def get_server_status_info(self) -> dict:
        """Retourne les informations d'état du serveur"""
        return {
            'running': self.server.running,
            'host': config.HOST,
            'port': config.PORT,
            'clients_connected': len(self.server.clients) if hasattr(self.server, 'clients') else 0,
            'active_jobs': len([job for job in self.server.jobs.values() 
                               if job.status.value in ['processing', 'extracting', 'assembling']]) 
                          if hasattr(self.server, 'jobs') else 0
        }