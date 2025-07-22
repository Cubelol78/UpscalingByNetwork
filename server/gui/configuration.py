"""
Mixin pour la gestion de la configuration
"""

from PyQt5.QtWidgets import QMessageBox
from pathlib import Path
from config.settings import config

class ConfigurationMixin:
    """Mixin pour les fonctionnalités de configuration"""
    
    def save_configuration(self):
        """Sauvegarde la configuration"""
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
            
            # Sauvegarde des paramètres réseau
            config.HOST = config_tab.host_input.text().strip()
            config.PORT = config_tab.port_input.value()
            config.MAX_CLIENTS = config_tab.max_clients_spin.value()
            
            # Sauvegarde des paramètres stockage
            config.AUTO_CLEANUP = config_tab.auto_cleanup_check.isChecked()
            config.MIN_FREE_SPACE_GB = config_tab.min_free_space_spin.value()
            
            # Sauvegarde des paramètres lots
            config.BATCH_SIZE = config_tab.batch_size_spin.value()
            config.MAX_RETRIES = config_tab.max_retries_spin.value()
            
            # Sauvegarde des paramètres Real-ESRGAN
            config.REALESRGAN_MODEL = config_tab.model_combo.currentText()
            config.TILE_SIZE = config_tab.tile_size_spin.value()
            
            # Sauvegarde des paramètres sécurité
            config.USE_ENCRYPTION = config_tab.encryption_check.isChecked()
            
            # Mise à jour de l'affichage du port dans la status bar
            if hasattr(self, 'status_bar'):
                self.status_bar.server_port_label.setText(f"Port: {config.PORT}")
            
            QMessageBox.information(self, "Succès", 
                f"Configuration sauvegardée\n"
                f"Serveur: {config.HOST}:{config.PORT}\n"
                f"Disque de travail: {config.WORK_DRIVE}")
            
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur lors de la sauvegarde:\n{str(e)}")
    
    def reset_configuration(self):
        """Remet la configuration par défaut"""
        reply = QMessageBox.question(
            self, "Confirmation", "Remettre la configuration par défaut?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            config_tab = self.tabs_manager.config_tab
            
            # Remise à zéro des paramètres réseau
            config_tab.host_input.setText("0.0.0.0")
            config_tab.port_input.setValue(8888)
            config_tab.max_clients_spin.setValue(50)
            
            # Remise à zéro des paramètres stockage
            config_tab.auto_cleanup_check.setChecked(True)
            config_tab.min_free_space_spin.setValue(50)
            
            # Remise à zéro des paramètres lots
            config_tab.batch_size_spin.setValue(50)
            config_tab.max_retries_spin.setValue(3)
            
            # Remise à zéro des paramètres Real-ESRGAN
            config_tab.model_combo.setCurrentText("realesr-animevideov3")
            config_tab.tile_size_spin.setValue(256)
            
            # Remise à zéro des paramètres sécurité
            config_tab.encryption_check.setChecked(True)
            
            # Remise à zéro du disque de travail
            config.WORK_DRIVE = config.get_best_drive()
            config.update_paths()
            config.create_directories()
            config_tab.refresh_drives()