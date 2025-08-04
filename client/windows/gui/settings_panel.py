# UpscalingByNetwork/client/windows/gui/settings_panel.py

import sys
import asyncio
import time
from pathlib import Path
from typing import Optional, Dict, Any
import qasync
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QTabWidget, QGroupBox, QGridLayout, QLabel, QPushButton, QLineEdit,
    QSpinBox, QTextEdit, QProgressBar, QSystemTrayIcon, QMenu, QAction,
    QMessageBox, QFrame, QSplitter, QCheckBox, QComboBox, QStyle,
    QHeaderView, QTableWidget, QTableWidgetItem, QFormLayout
)
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QThread
from PyQt5.QtGui import QFont, QIcon, QPixmap, QPalette, QColor

from ..core.distributed_client import DistributedClient
from .connection_panel import ConnectionPanel
from .processing_panel import ProcessingPanel
from .settings_panel import SettingsPanel

class SettingsPanel(QWidget):
    """Onglet des paramètres et configuration"""
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setup_ui()
    
    def setup_ui(self):
        """Configure l'interface du panneau"""
        layout = QVBoxLayout(self)
        
        # Onglets de paramètres
        settings_tabs = QTabWidget()
        layout.addWidget(settings_tabs)
        
        # Onglet Général
        general_tab = self.create_general_settings()
        settings_tabs.addTab(general_tab, "Général")
        
        # Onglet Performance
        performance_tab = self.create_performance_settings()
        settings_tabs.addTab(performance_tab, "Performance")
        
        # Onglet Sécurité
        security_tab = self.create_security_settings()
        settings_tabs.addTab(security_tab, "Sécurité")
        
        # Onglet Avancé
        advanced_tab = self.create_advanced_settings()
        settings_tabs.addTab(advanced_tab, "Avancé")
        
        # Boutons de contrôle
        buttons_layout = QHBoxLayout()
        
        save_btn = QPushButton("Sauvegarder")
        save_btn.clicked.connect(self.save_settings)
        save_btn.setStyleSheet("QPushButton { background-color: #28a745; }")
        buttons_layout.addWidget(save_btn)
        
        reset_btn = QPushButton("Réinitialiser")
        reset_btn.clicked.connect(self.reset_settings)
        buttons_layout.addWidget(reset_btn)
        
        buttons_layout.addStretch()
        
        apply_btn = QPushButton("Appliquer")
        apply_btn.clicked.connect(self.apply_settings)
        buttons_layout.addWidget(apply_btn)
        
        layout.addLayout(buttons_layout)
    
    def create_general_settings(self):
        """Crée les paramètres généraux"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Interface utilisateur
        ui_group = QGroupBox("Interface utilisateur")
        ui_layout = QFormLayout(ui_group)
        
        self.minimize_to_tray_check = QCheckBox("Réduire dans la barre système")
        self.minimize_to_tray_check.setChecked(self.main_window.config.get('minimize_to_tray', True))
        ui_layout.addRow(self.minimize_to_tray_check)
        
        self.notifications_check = QCheckBox("Notifications")
        self.notifications_check.setChecked(self.main_window.config.get('notifications', True))
        ui_layout.addRow(self.notifications_check)
        
        self.auto_start_check = QCheckBox("Démarrage automatique avec Windows")
        ui_layout.addRow(self.auto_start_check)
        
        layout.addWidget(ui_group)
        
        # Comportement
        behavior_group = QGroupBox("Comportement")
        behavior_layout = QFormLayout(behavior_group)
        
        self.auto_start_processing_check = QCheckBox("Démarrer le traitement automatiquement")
        self.auto_start_processing_check.setChecked(self.main_window.config.get('auto_start_processing', True))
        behavior_layout.addRow(self.auto_start_processing_check)
        
        self.confirm_exit_check = QCheckBox("Confirmer avant de quitter")
        self.confirm_exit_check.setChecked(True)
        behavior_layout.addRow(self.confirm_exit_check)
        
        layout.addWidget(behavior_group)
        
        layout.addStretch()
        return widget
    
    def create_performance_settings(self):
        """Crée les paramètres de performance"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Real-ESRGAN
        realesrgan_group = QGroupBox("Configuration Real-ESRGAN")
        realesrgan_layout = QFormLayout(realesrgan_group)
        
        self.tile_size_spin = QSpinBox()
        self.tile_size_spin.setRange(128, 1024)
        self.tile_size_spin.setValue(256)
        self.tile_size_spin.setSuffix(" pixels")
        realesrgan_layout.addRow("Taille des tuiles:", self.tile_size_spin)
        
        self.gpu_id_spin = QSpinBox()
        self.gpu_id_spin.setRange(0, 8)
        self.gpu_id_spin.setValue(0)
        realesrgan_layout.addRow("ID GPU:", self.gpu_id_spin)
        
        layout.addWidget(realesrgan_group)
        
        # Traitement
        processing_group = QGroupBox("Traitement")
        processing_layout = QFormLayout(processing_group)
        
        self.max_concurrent_spin = QSpinBox()
        self.max_concurrent_spin.setRange(1, 4)
        self.max_concurrent_spin.setValue(self.main_window.config.get('max_concurrent_batches', 1))
        processing_layout.addRow("Lots simultanés max:", self.max_concurrent_spin)
        
        self.cpu_threads_spin = QSpinBox()
        self.cpu_threads_spin.setRange(1, 16)
        self.cpu_threads_spin.setValue(4)
        processing_layout.addRow("Threads CPU:", self.cpu_threads_spin)
        
        layout.addWidget(processing_group)
        
        layout.addStretch()
        return widget
    
    def create_security_settings(self):
        """Crée les paramètres de sécurité"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Chiffrement
        encryption_group = QGroupBox("Chiffrement")
        encryption_layout = QFormLayout(encryption_group)
        
        self.encryption_enabled_check = QCheckBox("Activer le chiffrement")
        self.encryption_enabled_check.setChecked(True)
        encryption_layout.addRow(self.encryption_enabled_check)
        
        self.verify_server_check = QCheckBox("Vérifier l'identité du serveur")
        self.verify_server_check.setChecked(True)
        encryption_layout.addRow(self.verify_server_check)
        
        layout.addWidget(encryption_group)
        
        layout.addStretch()
        return widget
    
    def create_advanced_settings(self):
        """Crée les paramètres avancés"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Logs
        logs_group = QGroupBox("Journalisation")
        logs_layout = QFormLayout(logs_group)
        
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["Debug", "Info", "Warning", "Error"])
        self.log_level_combo.setCurrentText("Info")
        logs_layout.addRow("Niveau de log:", self.log_level_combo)
        
        self.log_to_file_check = QCheckBox("Sauvegarder les logs dans un fichier")
        self.log_to_file_check.setChecked(True)
        logs_layout.addRow(self.log_to_file_check)
        
        layout.addWidget(logs_group)
        
        # Réseau
        network_group = QGroupBox("Réseau")
        network_layout = QFormLayout(network_group)
        
        self.connection_timeout_spin = QSpinBox()
        self.connection_timeout_spin.setRange(5, 120)
        self.connection_timeout_spin.setValue(30)
        self.connection_timeout_spin.setSuffix(" secondes")
        network_layout.addRow("Timeout connexion:", self.connection_timeout_spin)
        
        self.retry_attempts_spin = QSpinBox()
        self.retry_attempts_spin.setRange(1, 10)
        self.retry_attempts_spin.setValue(3)
        network_layout.addRow("Tentatives de reconnexion:", self.retry_attempts_spin)
        
        layout.addWidget(network_group)
        
        layout.addStretch()
        return widget
    
    def save_settings(self):
        """Sauvegarde tous les paramètres"""
        config_update = {
            'minimize_to_tray': self.minimize_to_tray_check.isChecked(),
            'notifications': self.notifications_check.isChecked(),
            'auto_start_processing': self.auto_start_processing_check.isChecked(),
            'max_concurrent_batches': self.max_concurrent_spin.value()
        }
        
        self.main_window.update_client_config(config_update)
        
        QMessageBox.information(self, "Paramètres", "Paramètres sauvegardés avec succès")
        
        # Log dans l'interface principale
        self.main_window.log_message("💾 Paramètres sauvegardés")
    
    def reset_settings(self):
        """Remet les paramètres par défaut"""
        reply = QMessageBox.question(
            self, "Réinitialisation",
            "Voulez-vous vraiment réinitialiser tous les paramètres ?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Remise des valeurs par défaut
            self.minimize_to_tray_check.setChecked(True)
            self.notifications_check.setChecked(True)
            self.auto_start_processing_check.setChecked(True)
            self.max_concurrent_spin.setValue(1)
            self.tile_size_spin.setValue(256)
            self.gpu_id_spin.setValue(0)
            self.cpu_threads_spin.setValue(4)
            
            QMessageBox.information(self, "Réinitialisation", "Paramètres réinitialisés")
    
    def apply_settings(self):
        """Applique les paramètres sans sauvegarder"""
        # Application immédiate de certains paramètres
        self.main_window.config['notifications'] = self.notifications_check.isChecked()
        
        QMessageBox.information(self, "Paramètres", "Paramètres appliqués temporairement")