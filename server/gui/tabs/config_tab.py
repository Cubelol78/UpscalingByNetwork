"""
Onglet de configuration
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
                            QGroupBox, QGridLayout, QLabel, QLineEdit, QSpinBox,
                            QComboBox, QCheckBox, QPushButton, QMessageBox)
from PyQt5.QtCore import Qt
from pathlib import Path

from config.settings import config

class ConfigTab(QScrollArea):
    """Onglet de configuration"""
    
    def __init__(self, server, main_window):
        super().__init__()
        self.server = server
        self.main_window = main_window
        
        self.setWidgetResizable(True)
        self.setup_ui()
    
    def setup_ui(self):
        """Configuration de l'interface"""
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(15)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Configuration réseau
        self.create_network_group(layout)
        
        # Configuration stockage
        self.create_storage_group(layout)
        
        # Configuration lots
        self.create_batches_group(layout)
        
        # Configuration Real-ESRGAN
        self.create_esrgan_group(layout)
        
        # Configuration sécurité
        self.create_security_group(layout)
        
        # Boutons
        self.create_buttons(layout)
        
        layout.addStretch()
        self.setWidget(content_widget)
        
        # Initialiser les disques
        self.refresh_drives()
    
    def create_network_group(self, parent_layout):
        """Crée le groupe de configuration réseau"""
        network_group = QGroupBox("Configuration Réseau")
        network_group.setMinimumWidth(400)
        network_layout = QGridLayout(network_group)
        network_layout.setSpacing(10)
        network_layout.setContentsMargins(15, 20, 15, 15)
        
        network_layout.addWidget(QLabel("Adresse IP:"), 0, 0)
        self.host_input = QLineEdit(config.HOST)
        self.host_input.setMaximumWidth(200)
        network_layout.addWidget(self.host_input, 0, 1)
        
        network_layout.addWidget(QLabel("Port:"), 1, 0)
        self.port_input = QSpinBox()
        self.port_input.setRange(1024, 65535)
        self.port_input.setValue(config.PORT)
        self.port_input.setMaximumWidth(100)
        network_layout.addWidget(self.port_input, 1, 1)
        
        network_layout.addWidget(QLabel("Clients maximum:"), 2, 0)
        self.max_clients_spin = QSpinBox()
        self.max_clients_spin.setRange(1, 1000)
        self.max_clients_spin.setValue(config.MAX_CLIENTS)
        self.max_clients_spin.setMaximumWidth(100)
        network_layout.addWidget(self.max_clients_spin, 2, 1)
        
        parent_layout.addWidget(network_group)
    
    def create_storage_group(self, parent_layout):
        """Crée le groupe de configuration stockage"""
        storage_group = QGroupBox("Configuration Stockage")
        storage_group.setMinimumWidth(400)
        storage_layout = QGridLayout(storage_group)
        storage_layout.setSpacing(10)
        storage_layout.setContentsMargins(15, 20, 15, 15)
        
        # Sélection du disque de travail
        storage_layout.addWidget(QLabel("Disque de travail:"), 0, 0)
        self.drive_combo = QComboBox()
        self.drive_combo.setMinimumWidth(200)
        self.drive_combo.currentTextChanged.connect(self.on_drive_changed)
        storage_layout.addWidget(self.drive_combo, 0, 1, 1, 2)
        
        # Bouton pour actualiser les disques
        refresh_drives_btn = QPushButton("Actualiser")
        refresh_drives_btn.setMaximumWidth(100)
        refresh_drives_btn.clicked.connect(self.refresh_drives)
        storage_layout.addWidget(refresh_drives_btn, 0, 3)
        
        # Informations sur l'espace disque
        self.drive_info_label = QLabel("Chargement des informations disque...")
        self.drive_info_label.setStyleSheet("font-size: 10px; color: #888; padding: 5px;")
        self.drive_info_label.setWordWrap(True)
        storage_layout.addWidget(self.drive_info_label, 1, 0, 1, 4)
        
        # Nettoyage automatique
        self.auto_cleanup_check = QCheckBox("Nettoyage automatique des fichiers temporaires")
        self.auto_cleanup_check.setChecked(config.AUTO_CLEANUP)
        storage_layout.addWidget(self.auto_cleanup_check, 2, 0, 1, 4)
        
        # Espace libre minimum
        storage_layout.addWidget(QLabel("Espace libre minimum (GB):"), 3, 0)
        self.min_free_space_spin = QSpinBox()
        self.min_free_space_spin.setRange(10, 1000)
        self.min_free_space_spin.setValue(config.MIN_FREE_SPACE_GB)
        self.min_free_space_spin.setMaximumWidth(100)
        storage_layout.addWidget(self.min_free_space_spin, 3, 1)
        
        # Bouton de nettoyage manuel
        cleanup_btn = QPushButton("Nettoyer fichiers temporaires")
        cleanup_btn.clicked.connect(self.manual_cleanup)
        cleanup_btn.setStyleSheet("background-color: #FF9800; color: white; padding: 8px;")
        cleanup_btn.setMaximumWidth(250)
        storage_layout.addWidget(cleanup_btn, 4, 0, 1, 2)
        
        parent_layout.addWidget(storage_group)
    
    def create_batches_group(self, parent_layout):
        """Crée le groupe de configuration lots"""
        batches_group = QGroupBox("Configuration Lots")
        batches_group.setMinimumWidth(400)
        batches_layout = QGridLayout(batches_group)
        batches_layout.setSpacing(10)
        batches_layout.setContentsMargins(15, 20, 15, 15)
        
        batches_layout.addWidget(QLabel("Taille des lots (images):"), 0, 0)
        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setRange(10, 200)
        self.batch_size_spin.setValue(config.BATCH_SIZE)
        self.batch_size_spin.setMaximumWidth(100)
        batches_layout.addWidget(self.batch_size_spin, 0, 1)
        
        batches_layout.addWidget(QLabel("Tentatives maximum:"), 1, 0)
        self.max_retries_spin = QSpinBox()
        self.max_retries_spin.setRange(1, 10)
        self.max_retries_spin.setValue(config.MAX_RETRIES)
        self.max_retries_spin.setMaximumWidth(100)
        batches_layout.addWidget(self.max_retries_spin, 1, 1)
        
        parent_layout.addWidget(batches_group)
    
    def create_esrgan_group(self, parent_layout):
        """Crée le groupe de configuration Real-ESRGAN"""
        esrgan_group = QGroupBox("Configuration Real-ESRGAN")
        esrgan_group.setMinimumWidth(400)
        esrgan_layout = QGridLayout(esrgan_group)
        esrgan_layout.setSpacing(10)
        esrgan_layout.setContentsMargins(15, 20, 15, 15)
        
        esrgan_layout.addWidget(QLabel("Modèle d'upscaling:"), 0, 0)
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "realesr-animevideov3",
            "RealESRGAN_x4plus_anime_6B",
            "RealESRGAN_x4plus"
        ])
        self.model_combo.setCurrentText(config.REALESRGAN_MODEL)
        self.model_combo.setMinimumWidth(200)
        esrgan_layout.addWidget(self.model_combo, 0, 1)
        
        esrgan_layout.addWidget(QLabel("Taille des tuiles (pixels):"), 1, 0)
        self.tile_size_spin = QSpinBox()
        self.tile_size_spin.setRange(128, 1024)
        self.tile_size_spin.setSingleStep(128)
        self.tile_size_spin.setValue(config.TILE_SIZE)
        self.tile_size_spin.setMaximumWidth(100)
        esrgan_layout.addWidget(self.tile_size_spin, 1, 1)
        
        parent_layout.addWidget(esrgan_group)
    
    def create_security_group(self, parent_layout):
        """Crée le groupe de configuration sécurité"""
        security_group = QGroupBox("Configuration Sécurité")
        security_group.setMinimumWidth(400)
        security_layout = QGridLayout(security_group)
        security_layout.setSpacing(10)
        security_layout.setContentsMargins(15, 20, 15, 15)
        
        self.encryption_check = QCheckBox("Activer le chiffrement des communications")
        self.encryption_check.setChecked(config.USE_ENCRYPTION)
        security_layout.addWidget(self.encryption_check, 0, 0, 1, 2)
        
        # Description du chiffrement
        encryption_desc = QLabel("Chiffre toutes les communications entre le serveur et les clients (recommandé pour WAN)")
        encryption_desc.setStyleSheet("font-size: 10px; color: #888; font-style: italic;")
        encryption_desc.setWordWrap(True)
        security_layout.addWidget(encryption_desc, 1, 0, 1, 2)
        
        parent_layout.addWidget(security_group)
    
    def create_buttons(self, parent_layout):
        """Crée les boutons de contrôle"""
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        
        save_config_btn = QPushButton("Sauvegarder Configuration")
        save_config_btn.clicked.connect(self.main_window.save_configuration)
        save_config_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 10px; font-weight: bold;")
        save_config_btn.setMinimumHeight(35)
        
        reset_config_btn = QPushButton("Réinitialiser")
        reset_config_btn.clicked.connect(self.main_window.reset_configuration)
        reset_config_btn.setStyleSheet("background-color: #f44336; color: white; padding: 10px; font-weight: bold;")
        reset_config_btn.setMinimumHeight(35)
        
        buttons_layout.addWidget(save_config_btn)
        buttons_layout.addWidget(reset_config_btn)
        buttons_layout.addStretch()
        
        parent_layout.addLayout(buttons_layout)
    
    def refresh_drives(self):
        """Actualise la liste des disques disponibles"""
        try:
            if not hasattr(self, 'drive_combo') or not hasattr(self, 'drive_info_label'):
                return
                
            self.drive_combo.clear()
            drives = config.get_available_drives()
            
            for mountpoint, info in drives.items():
                free_gb = info['free_gb']
                total_gb = info['total_gb']
                percent_free = (free_gb / total_gb) * 100
                
                display_text = f"{mountpoint} - {free_gb:.1f}GB libre ({percent_free:.1f}% libre)"
                self.drive_combo.addItem(display_text, mountpoint)
            
            current_index = self.drive_combo.findData(config.WORK_DRIVE)
            if current_index >= 0:
                self.drive_combo.setCurrentIndex(current_index)
            
            self.update_drive_info()
            
        except Exception as e:
            print(f"Erreur actualisation disques: {e}")
    
    def on_drive_changed(self):
        """Gestionnaire de changement de disque"""
        try:
            if not hasattr(self, 'drive_combo') or not hasattr(self, 'drive_info_label'):
                return
                
            current_data = self.drive_combo.currentData()
            if current_data:
                config.set_work_drive(current_data)
                self.update_drive_info()
                
        except Exception as e:
            print(f"Erreur changement disque: {e}")
    
    def update_drive_info(self):
        """Met à jour les informations du disque sélectionné"""
        try:
            if not hasattr(self, 'drive_info_label'):
                return
                
            drives = config.get_available_drives()
            current_drive = config.WORK_DRIVE
            
            if current_drive in drives:
                info = drives[current_drive]
                
                info_text = (
                    f"📁 Disque: {info['device']} ({info['fstype']}) | "
                    f"💾 Total: {info['total_gb']:.1f}GB | "
                    f"📊 Utilisé: {info['used_gb']:.1f}GB ({info['percent_used']:.1f}%) | "
                    f"✅ Libre: {info['free_gb']:.1f}GB"
                )
                
                if info['free_gb'] < config.MIN_FREE_SPACE_GB:
                    color = "#f44336"
                    status = "⚠️ ESPACE INSUFFISANT"
                elif info['free_gb'] < config.MIN_FREE_SPACE_GB * 2:
                    color = "#FF9800"
                    status = "⚠️ Espace limité"
                else:
                    color = "#4CAF50"
                    status = "✅ Espace suffisant"
                
                self.drive_info_label.setText(f"{status}\n{info_text}")
                self.drive_info_label.setStyleSheet(f"""
                    font-size: 11px; 
                    color: {color}; 
                    font-weight: bold; 
                    padding: 8px; 
                    border: 1px solid {color}; 
                    border-radius: 4px;
                """)
                
        except Exception as e:
            print(f"Erreur mise à jour info disque: {e}")
    
    def manual_cleanup(self):
        """Nettoyage manuel des fichiers temporaires"""
        try:
            reply = QMessageBox.question(
                self, "Nettoyage", 
                "Supprimer tous les fichiers temporaires?\n"
                "Cette action est irréversible et supprimera:\n"
                "- Toutes les frames extraites\n"
                "- Toutes les frames upscalées\n"
                "- Tous les fichiers audio temporaires",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                success = config.cleanup_temp_files()
                
                if success:
                    QMessageBox.information(self, "Succès", "Fichiers temporaires supprimés")
                    self.refresh_drives()
                else:
                    QMessageBox.warning(self, "Erreur", "Erreur lors du nettoyage")
                    
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur nettoyage: {str(e)}")