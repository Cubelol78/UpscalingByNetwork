"""
Mixin pour la gestion de la configuration avec sauvegarde persistante
"""

from PyQt5.QtWidgets import QMessageBox
from pathlib import Path
from config.settings import config

class ConfigurationMixin:
    """Mixin pour les fonctionnalités de configuration"""
    
    def save_configuration(self):
        """Sauvegarde la configuration de manière persistante"""
        try:
            # Vérification si le serveur est en cours d'exécution
            if self.server.running:
                reply = QMessageBox.question(
                    self, "Serveur en cours", 
                    "Le serveur est en cours d'exécution. Certains changements nécessitent un redémarrage.\n"
                    "Voulez-vous continuer?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    return
            
            # Récupération des paramètres depuis l'onglet config
            config_tab = self.tabs_manager.config_tab
            
            # Application et sauvegarde automatique avec la nouvelle méthode
            success = config.apply_and_save(
                # Paramètres réseau
                HOST=config_tab.host_input.text().strip(),
                PORT=config_tab.port_input.value(),
                MAX_CLIENTS=config_tab.max_clients_spin.value(),
                
                # Paramètres stockage
                AUTO_CLEANUP=config_tab.auto_cleanup_check.isChecked(),
                MIN_FREE_SPACE_GB=config_tab.min_free_space_spin.value(),
                
                # Paramètres lots
                BATCH_SIZE=config_tab.batch_size_spin.value(),
                MAX_RETRIES=config_tab.max_retries_spin.value(),
                
                # Paramètres Real-ESRGAN
                REALESRGAN_MODEL=config_tab.model_combo.currentText(),
                TILE_SIZE=config_tab.tile_size_spin.value(),
                
                # Paramètres sécurité
                USE_ENCRYPTION=config_tab.encryption_check.isChecked()
            )
            
            if success:
                # Mise à jour de l'affichage du port dans la status bar
                if hasattr(self, 'status_bar'):
                    self.status_bar.server_port_label.setText(f"Port: {config.PORT}")
                
                QMessageBox.information(self, "Succès", 
                    f"Configuration sauvegardée de manière permanente\n"
                    f"Serveur: {config.HOST}:{config.PORT}\n"
                    f"Disque de travail: {config.WORK_DRIVE}\n"
                    f"Fichier: {config.get_config_file_path()}")
            else:
                QMessageBox.warning(self, "Avertissement", 
                    "Configuration appliquée mais erreur lors de la sauvegarde sur disque")
            
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur lors de la sauvegarde:\n{str(e)}")
    
    def reset_configuration(self):
        """Remet la configuration par défaut et sauvegarde"""
        reply = QMessageBox.question(
            self, "Confirmation", 
            "Remettre la configuration par défaut?\n"
            "Cette action supprimera toutes vos modifications personnalisées.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                # Remise à zéro avec sauvegarde automatique
                config.reset_to_defaults()
                
                # Mise à jour de l'interface
                config_tab = self.tabs_manager.config_tab
                
                # Rechargement des valeurs par défaut dans l'interface
                config_tab.host_input.setText(config.HOST)
                config_tab.port_input.setValue(config.PORT)
                config_tab.max_clients_spin.setValue(config.MAX_CLIENTS)
                config_tab.auto_cleanup_check.setChecked(config.AUTO_CLEANUP)
                config_tab.min_free_space_spin.setValue(config.MIN_FREE_SPACE_GB)
                config_tab.batch_size_spin.setValue(config.BATCH_SIZE)
                config_tab.max_retries_spin.setValue(config.MAX_RETRIES)
                config_tab.model_combo.setCurrentText(config.REALESRGAN_MODEL)
                config_tab.tile_size_spin.setValue(config.TILE_SIZE)
                config_tab.encryption_check.setChecked(config.USE_ENCRYPTION)
                
                # Actualisation des disques
                config_tab.refresh_drives()
                
                QMessageBox.information(self, "Succès", 
                    "Configuration remise par défaut et sauvegardée")
                
            except Exception as e:
                QMessageBox.critical(self, "Erreur", 
                    f"Erreur lors de la remise à zéro:\n{str(e)}")
    
    def load_saved_configuration(self):
        """Charge la configuration sauvegardée dans l'interface"""
        try:
            # La configuration est déjà chargée automatiquement au démarrage
            # Ici on met juste à jour l'interface avec les valeurs chargées
            
            # Vérifier que les widgets sont créés avant de les utiliser
            if not hasattr(self, 'tabs_manager'):
                self.logger.warning("Interface pas encore initialisée, chargement de la config ignoré")
                return
                
            if hasattr(self.tabs_manager, 'config_tab'):
                config_tab = self.tabs_manager.config_tab
                
                # Mise à jour des champs avec les valeurs chargées
                config_tab.host_input.setText(config.HOST)
                config_tab.port_input.setValue(config.PORT)
                config_tab.max_clients_spin.setValue(config.MAX_CLIENTS)
                config_tab.auto_cleanup_check.setChecked(config.AUTO_CLEANUP)
                config_tab.min_free_space_spin.setValue(config.MIN_FREE_SPACE_GB)
                config_tab.batch_size_spin.setValue(config.BATCH_SIZE)
                config_tab.max_retries_spin.setValue(config.MAX_RETRIES)
                config_tab.model_combo.setCurrentText(config.REALESRGAN_MODEL)
                config_tab.tile_size_spin.setValue(config.TILE_SIZE)
                config_tab.encryption_check.setChecked(config.USE_ENCRYPTION)
                
                # Actualisation des disques pour afficher le bon disque sélectionné
                config_tab.refresh_drives()
                
                # Mise à jour du port dans la status bar
                if hasattr(self, 'status_bar'):
                    self.status_bar.server_port_label.setText(f"Port: {config.PORT}")
                
                self.logger.info("Configuration chargée dans l'interface")
            else:
                self.logger.warning("Onglet configuration pas encore créé")
                
        except Exception as e:
            self.logger.error(f"Erreur chargement interface config: {e}")