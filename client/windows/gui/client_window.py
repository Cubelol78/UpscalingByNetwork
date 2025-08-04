# UpscalingByNetwork/client/windows/gui/client_window.py
"""
Interface graphique principale du client Windows
Interface moderne avec monitoring temps réel et gestion des paramètres
"""

import sys
import asyncio
import time
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import qasync
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QTabWidget, QGroupBox, QGridLayout, QLabel, QPushButton, QLineEdit,
    QSpinBox, QTextEdit, QProgressBar, QSystemTrayIcon, QMenu, QAction,
    QMessageBox, QFrame, QSplitter, QCheckBox, QComboBox, QStyle,
    QHeaderView, QTableWidget, QTableWidgetItem, QSlider, QStatusBar,
    QListWidget, QListWidgetItem
)
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QThread, QSize
from PyQt5.QtGui import QFont, QIcon, QPixmap, QPalette, QColor

# Import conditionnel du client distribué
try:
    from core.distributed_client import DistributedClient
except ImportError:
    # Fallback si le module n'existe pas encore
    DistributedClient = None

class ClientWindow(QMainWindow):
    """Interface graphique principale du client"""
    
    # Signaux pour communication inter-threads
    connection_changed = pyqtSignal(bool, str)
    batch_received = pyqtSignal(str, dict)
    batch_progress = pyqtSignal(str, float, int, int)
    batch_completed = pyqtSignal(str, bool, float)
    error_occurred = pyqtSignal(str)
    stats_updated = pyqtSignal(dict)
    
    def __init__(self):
        super().__init__()
        
        # Client distribué
        self.client: Optional["DistributedClient"] = None
        
        # Configuration par défaut
        self.config = {
            'server_host': 'localhost',
            'server_port': 8888,
            'auto_connect': False,
            'auto_request_batches': True,
            'minimize_to_tray': True,
            'notifications': True,
            'processing_settings': {
                'model': 'realesr-animevideov3',
                'scale': 4,
                'tile_size': 0
            }
        }
        
        # État de l'interface
        self.connected = False
        self.processing = False
        self.current_batch = None
        self.start_time = None
        
        # Interface
        self.setup_ui()
        self.setup_tray()
        self.setup_timers()
        self.setup_styles()
        self.setup_client()
        self.setup_connections()
        
        # État initial
        self.update_ui_state()
        
        self.setWindowTitle("UpscalingByNetwork - Client Distribué")
        self.setGeometry(200, 200, 1000, 700)
        self.setMinimumSize(800, 600)
    
    def set_server_config(self, host: str, port: int):
        """Configure les paramètres du serveur"""
        self.config['server_host'] = host
        self.config['server_port'] = port
        self.server_host_input.setText(host)
        self.server_port_input.setValue(port)
    
    def setup_ui(self):
        """Configure l'interface utilisateur"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principal
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Barre de statut rapide
        self.setup_status_bar(main_layout)
        
        # Onglets principaux
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # Onglet Connexion
        self.setup_connection_tab()
        
        # Onglet Traitement
        self.setup_processing_tab()
        
        # Onglet Statistiques
        self.setup_statistics_tab()
        
        # Onglet Configuration
        self.setup_configuration_tab()
        
        # Onglet Logs
        self.setup_logs_tab()
        
        # Barre de statut
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Client déconnecté")
    
    def setup_status_bar(self, main_layout):
        """Configure la barre de statut rapide"""
        status_frame = QFrame()
        status_frame.setFrameStyle(QFrame.StyledPanel)
        status_frame.setMaximumHeight(80)
        main_layout.addWidget(status_frame)
        
        status_layout = QHBoxLayout(status_frame)
        
        # État de connexion
        connection_group = QGroupBox("Connexion")
        connection_layout = QGridLayout(connection_group)
        
        self.connection_status_label = QLabel("Déconnecté")
        self.connection_status_label.setStyleSheet("color: red; font-weight: bold;")
        connection_layout.addWidget(self.connection_status_label, 0, 0)
        
        self.server_info_label = QLabel("Aucun serveur")
        self.server_info_label.setStyleSheet("color: #666; font-size: 10px;")
        connection_layout.addWidget(self.server_info_label, 1, 0)
        
        status_layout.addWidget(connection_group)
        
        # État de traitement
        processing_group = QGroupBox("Traitement")
        processing_layout = QGridLayout(processing_group)
        
        self.processing_status_label = QLabel("Inactif")
        processing_layout.addWidget(self.processing_status_label, 0, 0)
        
        self.current_batch_label = QLabel("Aucun lot")
        self.current_batch_label.setStyleSheet("color: #666; font-size: 10px;")
        processing_layout.addWidget(self.current_batch_label, 1, 0)
        
        status_layout.addWidget(processing_group)
        
        # Statistiques rapides
        stats_group = QGroupBox("Statistiques")
        stats_layout = QGridLayout(stats_group)
        
        self.batches_processed_label = QLabel("Lots: 0")
        stats_layout.addWidget(self.batches_processed_label, 0, 0)
        
        self.images_processed_label = QLabel("Images: 0")
        stats_layout.addWidget(self.images_processed_label, 0, 1)
        
        self.uptime_label = QLabel("Uptime: 00:00:00")
        stats_layout.addWidget(self.uptime_label, 1, 0, 1, 2)
        
        status_layout.addWidget(stats_group)
        status_layout.addStretch()
    
    def setup_connection_tab(self):
        """Configure l'onglet de connexion"""
        connection_widget = QWidget()
        self.tabs.addTab(connection_widget, "🔗 Connexion")
        
        layout = QVBoxLayout(connection_widget)
        
        # Configuration serveur
        server_group = QGroupBox("Configuration Serveur")
        server_layout = QGridLayout(server_group)
        
        server_layout.addWidget(QLabel("Adresse serveur:"), 0, 0)
        self.server_host_input = QLineEdit(self.config['server_host'])
        server_layout.addWidget(self.server_host_input, 0, 1)
        
        server_layout.addWidget(QLabel("Port:"), 0, 2)
        self.server_port_input = QSpinBox()
        self.server_port_input.setRange(1024, 65535)
        self.server_port_input.setValue(self.config['server_port'])
        server_layout.addWidget(self.server_port_input, 0, 3)
        
        # Boutons de connexion
        buttons_layout = QHBoxLayout()
        
        self.connect_btn = QPushButton("Se connecter")
        self.connect_btn.clicked.connect(self.toggle_connection)
        buttons_layout.addWidget(self.connect_btn)
        
        self.test_connection_btn = QPushButton("Test Connexion")
        self.test_connection_btn.clicked.connect(self.test_connection)
        buttons_layout.addWidget(self.test_connection_btn)
        
        buttons_layout.addStretch()
        
        server_layout.addLayout(buttons_layout, 1, 0, 1, 4)
        
        layout.addWidget(server_group)
        
        # Options de connexion
        options_group = QGroupBox("Options")
        options_layout = QGridLayout(options_group)
        
        self.auto_connect_check = QCheckBox("Connexion automatique au démarrage")
        self.auto_connect_check.setChecked(self.config['auto_connect'])
        options_layout.addWidget(self.auto_connect_check, 0, 0, 1, 2)
        
        self.auto_request_check = QCheckBox("Demander automatiquement des lots")
        self.auto_request_check.setChecked(self.config['auto_request_batches'])
        options_layout.addWidget(self.auto_request_check, 1, 0, 1, 2)
        
        layout.addWidget(options_group)
        
        # Journal de connexion
        log_group = QGroupBox("Journal de Connexion")
        log_layout = QVBoxLayout(log_group)
        
        self.connection_log = QTextEdit()
        self.connection_log.setMaximumHeight(200)
        self.connection_log.setReadOnly(True)
        log_layout.addWidget(self.connection_log)
        
        layout.addWidget(log_group)
        layout.addStretch()
    
    def setup_processing_tab(self):
        """Configure l'onglet de traitement"""
        processing_widget = QWidget()
        self.tabs.addTab(processing_widget, "⚙️ Traitement")
        
        layout = QVBoxLayout(processing_widget)
        
        # Paramètres de traitement
        settings_group = QGroupBox("Paramètres d'Upscaling")
        settings_layout = QGridLayout(settings_group)
        
        settings_layout.addWidget(QLabel("Modèle:"), 0, 0)
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "realesr-animevideov3",
            "realesrgan-x4plus",
            "realesrgan-x4plus-anime",
            "RealESRNet_x4plus"
        ])
        self.model_combo.setCurrentText(self.config['processing_settings']['model'])
        settings_layout.addWidget(self.model_combo, 0, 1)
        
        settings_layout.addWidget(QLabel("Facteur d'échelle:"), 0, 2)
        self.scale_combo = QComboBox()
        self.scale_combo.addItems(["2", "3", "4"])
        self.scale_combo.setCurrentText(str(self.config['processing_settings']['scale']))
        settings_layout.addWidget(self.scale_combo, 0, 3)
        
        settings_layout.addWidget(QLabel("Taille de tuile:"), 1, 0)
        self.tile_size_slider = QSlider(Qt.Horizontal)
        self.tile_size_slider.setRange(0, 512)
        self.tile_size_slider.setValue(self.config['processing_settings']['tile_size'])
        self.tile_size_slider.valueChanged.connect(self.update_tile_size_label)
        settings_layout.addWidget(self.tile_size_slider, 1, 1, 1, 2)
        
        self.tile_size_label = QLabel("Auto")
        settings_layout.addWidget(self.tile_size_label, 1, 3)
        
        # Bouton d'application des paramètres
        apply_settings_btn = QPushButton("Appliquer les Paramètres")
        apply_settings_btn.clicked.connect(self.apply_processing_settings)
        settings_layout.addWidget(apply_settings_btn, 2, 0, 1, 4)
        
        layout.addWidget(settings_group)
        
        # État du traitement actuel
        current_group = QGroupBox("Traitement Actuel")
        current_layout = QGridLayout(current_group)
        
        current_layout.addWidget(QLabel("Lot actuel:"), 0, 0)
        self.current_batch_info_label = QLabel("Aucun")
        current_layout.addWidget(self.current_batch_info_label, 0, 1)
        
        current_layout.addWidget(QLabel("Progression:"), 1, 0)
        self.batch_progress_bar = QProgressBar()
        self.batch_progress_bar.setVisible(False)
        current_layout.addWidget(self.batch_progress_bar, 1, 1)
        
        self.batch_progress_label = QLabel("")
        current_layout.addWidget(self.batch_progress_label, 2, 0, 1, 2)
        
        layout.addWidget(current_group)
        
        # Historique des lots traités
        history_group = QGroupBox("Historique des Lots")
        history_layout = QVBoxLayout(history_group)
        
        self.batch_history_list = QListWidget()
        history_layout.addWidget(self.batch_history_list)
        
        layout.addWidget(history_group)
    
    def setup_statistics_tab(self):
        """Configure l'onglet de statistiques"""
        stats_widget = QWidget()
        self.tabs.addTab(stats_widget, "📊 Statistiques")
        
        layout = QVBoxLayout(stats_widget)
        
        # Statistiques générales
        general_group = QGroupBox("Statistiques Générales")
        general_layout = QGridLayout(general_group)
        
        self.total_batches_label = QLabel("Lots traités: 0")
        general_layout.addWidget(self.total_batches_label, 0, 0)
        
        self.total_images_label = QLabel("Images traitées: 0")
        general_layout.addWidget(self.total_images_label, 0, 1)
        
        self.avg_time_label = QLabel("Temps moyen/lot: 0s")
        general_layout.addWidget(self.avg_time_label, 1, 0)
        
        self.success_rate_label = QLabel("Taux de réussite: 100%")
        general_layout.addWidget(self.success_rate_label, 1, 1)
        
        layout.addWidget(general_group)
        
        # Statistiques système
        system_group = QGroupBox("Informations Système")
        system_layout = QGridLayout(system_group)
        
        self.cpu_usage_label = QLabel("CPU: 0%")
        system_layout.addWidget(self.cpu_usage_label, 0, 0)
        
        self.memory_usage_label = QLabel("RAM: 0%")
        system_layout.addWidget(self.memory_usage_label, 0, 1)
        
        self.gpu_usage_label = QLabel("GPU: N/A")
        system_layout.addWidget(self.gpu_usage_label, 1, 0)
        
        self.disk_usage_label = QLabel("Disque: 0%")
        system_layout.addWidget(self.disk_usage_label, 1, 1)
        
        layout.addWidget(system_group)
        
        # Graphiques de performance (placeholder)
        performance_group = QGroupBox("Performance en Temps Réel")
        performance_layout = QVBoxLayout(performance_group)
        
        self.performance_placeholder = QLabel("Graphiques de performance\n(À implémenter)")
        self.performance_placeholder.setAlignment(Qt.AlignCenter)
        self.performance_placeholder.setStyleSheet("color: #666; font-size: 14px;")
        performance_layout.addWidget(self.performance_placeholder)
        
        layout.addWidget(performance_group)
        layout.addStretch()
    
    def setup_configuration_tab(self):
        """Configure l'onglet de configuration"""
        config_widget = QWidget()
        self.tabs.addTab(config_widget, "⚙️ Configuration")
        
        layout = QVBoxLayout(config_widget)
        
        # Configuration générale
        general_group = QGroupBox("Configuration Générale")
        general_layout = QGridLayout(general_group)
        
        self.minimize_to_tray_check = QCheckBox("Minimiser vers la barre système")
        self.minimize_to_tray_check.setChecked(self.config['minimize_to_tray'])
        general_layout.addWidget(self.minimize_to_tray_check, 0, 0)
        
        self.notifications_check = QCheckBox("Activer les notifications")
        self.notifications_check.setChecked(self.config['notifications'])
        general_layout.addWidget(self.notifications_check, 0, 1)
        
        layout.addWidget(general_group)
        
        # Chemins des outils
        paths_group = QGroupBox("Chemins des Outils")
        paths_layout = QGridLayout(paths_group)
        
        paths_layout.addWidget(QLabel("Real-ESRGAN:"), 0, 0)
        self.realesrgan_path_input = QLineEdit()
        paths_layout.addWidget(self.realesrgan_path_input, 0, 1)
        
        browse_realesrgan_btn = QPushButton("Parcourir")
        browse_realesrgan_btn.clicked.connect(self.browse_realesrgan_path)
        paths_layout.addWidget(browse_realesrgan_btn, 0, 2)
        
        layout.addWidget(paths_group)
        
        # Boutons de gestion de la configuration
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        self.save_config_btn = QPushButton("Sauvegarder Configuration")
        self.save_config_btn.clicked.connect(self.save_configuration)
        buttons_layout.addWidget(self.save_config_btn)
        
        self.load_config_btn = QPushButton("Charger Configuration")
        self.load_config_btn.clicked.connect(self.load_configuration)
        buttons_layout.addWidget(self.load_config_btn)
        
        self.reset_config_btn = QPushButton("Réinitialiser")
        self.reset_config_btn.clicked.connect(self.reset_configuration)
        buttons_layout.addWidget(self.reset_config_btn)
        
        layout.addLayout(buttons_layout)
        layout.addStretch()
    
    def setup_logs_tab(self):
        """Configure l'onglet des logs"""
        logs_widget = QWidget()
        self.tabs.addTab(logs_widget, "📋 Logs")
        
        layout = QVBoxLayout(logs_widget)
        
        # Zone de texte pour les logs
        self.logs_text = QTextEdit()
        self.logs_text.setReadOnly(True)
        self.logs_text.setFont(QFont("Consolas", 9))
        layout.addWidget(self.logs_text)
        
        # Contrôles des logs
        controls_layout = QHBoxLayout()
        
        self.clear_logs_btn = QPushButton("Effacer")
        self.clear_logs_btn.clicked.connect(self.logs_text.clear)
        controls_layout.addWidget(self.clear_logs_btn)
        
        self.auto_scroll_check = QCheckBox("Défilement automatique")
        self.auto_scroll_check.setChecked(True)
        controls_layout.addWidget(self.auto_scroll_check)
        
        controls_layout.addStretch()
        
        self.export_logs_btn = QPushButton("Exporter Logs")
        self.export_logs_btn.clicked.connect(self.export_logs)
        controls_layout.addWidget(self.export_logs_btn)
        
        layout.addLayout(controls_layout)
    
    def setup_tray(self):
        """Configure l'icône système"""
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = QSystemTrayIcon(self)
            self.tray_icon.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
            
            # Menu contextuel
            tray_menu = QMenu()
            
            show_action = QAction("Afficher", self)
            show_action.triggered.connect(self.show)
            tray_menu.addAction(show_action)
            
            connect_action = QAction("Se connecter", self)
            connect_action.triggered.connect(self.toggle_connection)
            tray_menu.addAction(connect_action)
            
            tray_menu.addSeparator()
            
            quit_action = QAction("Quitter", self)
            quit_action.triggered.connect(self.close)
            tray_menu.addAction(quit_action)
            
            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.show()
    
    def setup_timers(self):
        """Configure les timers de mise à jour"""
        # Mise à jour de l'interface
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_ui_state)
        self.update_timer.start(1000)  # 1 seconde
        
        # Mise à jour des statistiques
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.update_statistics)
        self.stats_timer.start(5000)  # 5 secondes
    
    def setup_styles(self):
        """Configure les styles de l'interface"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #cccccc;
                border-radius: 5px;
                margin-top: 1ex;
                padding-top: 5px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
            QProgressBar {
                border: 2px solid #cccccc;
                border-radius: 4px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 2px;
            }
        """)
    
    def setup_client(self):
        """Configure le client distribué"""
        if DistributedClient:
            self.client = DistributedClient()
            
            # Configuration des callbacks
            self.client.on_connected = self.on_client_connected
            self.client.on_disconnected = self.on_client_disconnected
            self.client.on_batch_received = self.on_client_batch_received
            self.client.on_batch_progress = self.on_client_batch_progress
            self.client.on_batch_completed = self.on_client_batch_completed
            self.client.on_error = self.on_client_error
    
    def setup_connections(self):
        """Configure les connexions de signaux"""
        self.connection_changed.connect(self.handle_connection_changed)
        self.batch_received.connect(self.handle_batch_received)
        self.batch_progress.connect(self.handle_batch_progress)
        self.batch_completed.connect(self.handle_batch_completed)
        self.error_occurred.connect(self.handle_error)
        self.stats_updated.connect(self.handle_stats_updated)
    
    def update_ui_state(self):
        """Met à jour l'état de l'interface"""
        if self.client:
            stats = self.client.get_client_stats()
            self.connected = stats['connected']
            self.processing = stats['processing']
            self.current_batch = stats['current_batch']
        
        # Mise à jour du bouton de connexion
        if self.connected:
            self.connect_btn.setText("Se déconnecter")
            self.connect_btn.setStyleSheet("background-color: #f44336;")
            self.connection_status_label.setText("Connecté")
            self.connection_status_label.setStyleSheet("color: green; font-weight: bold;")
            self.server_info_label.setText(f"{self.config['server_host']}:{self.config['server_port']}")
        else:
            self.connect_btn.setText("Se connecter")
            self.connect_btn.setStyleSheet("background-color: #4CAF50;")
            self.connection_status_label.setText("Déconnecté")
            self.connection_status_label.setStyleSheet("color: red; font-weight: bold;")
            self.server_info_label.setText("Aucun serveur")
        
        # Mise à jour du statut de traitement
        if self.processing and self.current_batch:
            self.processing_status_label.setText("En cours")
            self.processing_status_label.setStyleSheet("color: blue; font-weight: bold;")
            self.current_batch_label.setText(f"Lot: {self.current_batch['batch_id']}")
            self.current_batch_info_label.setText(f"Lot: {self.current_batch['batch_id']}")
        else:
            if self.connected:
                self.processing_status_label.setText("En attente")
                self.processing_status_label.setStyleSheet("color: orange; font-weight: bold;")
            else:
                self.processing_status_label.setText("Inactif")
                self.processing_status_label.setStyleSheet("color: gray; font-weight: bold;")
            
            self.current_batch_label.setText("Aucun lot")
            self.current_batch_info_label.setText("Aucun")
        
        # Mise à jour de la barre de progression
        if self.processing and self.current_batch:
            progress = self.current_batch.get('progress', 0)
            self.batch_progress_bar.setValue(int(progress * 100))
            self.batch_progress_bar.setVisible(True)
        else:
            self.batch_progress_bar.setVisible(False)
        
        # Mise à jour de l'uptime
        if self.connected and self.start_time:
            uptime_seconds = (time.time() - self.start_time)
            hours = int(uptime_seconds // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            seconds = int(uptime_seconds % 60)
            self.uptime_label.setText(f"Uptime: {hours:02d}:{minutes:02d}:{seconds:02d}")
        else:
            self.uptime_label.setText("Uptime: 00:00:00")
    
    def update_statistics(self):
        """Met à jour les statistiques"""
        if self.client:
            stats = self.client.get_client_stats()
            
            # Statistiques générales
            self.batches_processed_label.setText(f"Lots: {stats['total_batches_processed']}")
            self.images_processed_label.setText(f"Images: {stats['total_images_processed']}")
            self.total_batches_label.setText(f"Lots traités: {stats['total_batches_processed']}")
            self.total_images_label.setText(f"Images traitées: {stats['total_images_processed']}")
            
            # Statistiques système si disponibles
            if 'system_info' in stats:
                system_info = stats['system_info']
                self.cpu_usage_label.setText(f"CPU: {system_info.get('cpu_percent', 0):.1f}%")
                self.memory_usage_label.setText(f"RAM: {system_info.get('memory_percent', 0):.1f}%")
                self.disk_usage_label.setText(f"Disque: {system_info.get('disk_percent', 0):.1f}%")
    
    async def toggle_connection(self):
        """Bascule l'état de connexion"""
        if self.connected:
            await self.disconnect_from_server()
        else:
            await self.connect_to_server()
    
    async def connect_to_server(self):
        """Se connecte au serveur"""
        if not self.client:
            self.log_message("Client non initialisé", "error")
            return
        
        host = self.server_host_input.text().strip()
        port = self.server_port_input.value()
        
        if not host:
            QMessageBox.warning(self, "Erreur", "Veuillez saisir l'adresse du serveur")
            return
        
        self.config['server_host'] = host
        self.config['server_port'] = port
        
        self.log_message(f"Connexion au serveur {host}:{port}...")
        
        success = await self.client.connect_to_server(host, port)
        if success:
            self.start_time = time.time()
            self.log_message("Connexion établie", "success")
        else:
            self.log_message("Échec de la connexion", "error")
    
    async def disconnect_from_server(self):
        """Se déconnecte du serveur"""
        if self.client:
            await self.client.disconnect()
            self.start_time = None
            self.log_message("Déconnecté du serveur")
    
    async def test_connection(self):
        """Test la connexion au serveur"""
        host = self.server_host_input.text().strip()
        port = self.server_port_input.value()
        
        if not host:
            QMessageBox.warning(self, "Erreur", "Veuillez saisir l'adresse du serveur")
            return
        
        self.log_message(f"Test de connexion vers {host}:{port}...")
        
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            sock.close()
            
            if result == 0:
                self.log_message("Serveur accessible", "success")
                QMessageBox.information(self, "Test", "Le serveur est accessible")
            else:
                self.log_message("Serveur inaccessible", "error")
                QMessageBox.warning(self, "Test", "Le serveur n'est pas accessible")
                
        except Exception as e:
            self.log_message(f"Erreur test connexion: {e}", "error")
            QMessageBox.critical(self, "Erreur", f"Erreur lors du test:\n{e}")
    
    def update_tile_size_label(self, value):
        """Met à jour le label de la taille de tuile"""
        if value == 0:
            self.tile_size_label.setText("Auto")
        else:
            self.tile_size_label.setText(f"{value}px")
    
    def apply_processing_settings(self):
        """Applique les paramètres de traitement"""
        if not self.client:
            return
        
        model = self.model_combo.currentText()
        scale = int(self.scale_combo.currentText())
        tile_size = self.tile_size_slider.value()
        
        self.config['processing_settings'] = {
            'model': model,
            'scale': scale,
            'tile_size': tile_size
        }
        
        self.client.set_processing_settings(model, scale, tile_size)
        self.log_message(f"Paramètres appliqués: {model}, échelle {scale}, tuile {tile_size}")
    
    def browse_realesrgan_path(self):
        """Ouvre un dialogue pour sélectionner Real-ESRGAN"""
        from PyQt5.QtWidgets import QFileDialog
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Sélectionner Real-ESRGAN",
            "",
            "Exécutables (*.exe);;Tous les fichiers (*)"
        )
        
        if file_path:
            self.realesrgan_path_input.setText(file_path)
    
    def save_configuration(self):
        """Sauvegarde la configuration"""
        try:
            # Collecte de la configuration actuelle
            config_data = {
                'server_host': self.server_host_input.text(),
                'server_port': self.server_port_input.value(),
                'auto_connect': self.auto_connect_check.isChecked(),
                'auto_request_batches': self.auto_request_check.isChecked(),
                'minimize_to_tray': self.minimize_to_tray_check.isChecked(),
                'notifications': self.notifications_check.isChecked(),
                'processing_settings': {
                    'model': self.model_combo.currentText(),
                    'scale': int(self.scale_combo.currentText()),
                    'tile_size': self.tile_size_slider.value()
                },
                'realesrgan_path': self.realesrgan_path_input.text()
            }
            
            config_file = Path("client_config.json")
            with open(config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            self.config.update(config_data)
            
            QMessageBox.information(self, "Configuration", "Configuration sauvegardée avec succès")
            self.log_message("Configuration sauvegardée")
            
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur lors de la sauvegarde:\n{e}")
            self.log_message(f"Erreur sauvegarde config: {e}", "error")
    
    def load_configuration(self):
        """Charge la configuration"""
        try:
            config_file = Path("client_config.json")
            if config_file.exists():
                with open(config_file, 'r') as f:
                    config_data = json.load(f)
                
                # Application de la configuration à l'interface
                self.server_host_input.setText(config_data.get('server_host', 'localhost'))
                self.server_port_input.setValue(config_data.get('server_port', 8888))
                self.auto_connect_check.setChecked(config_data.get('auto_connect', False))
                self.auto_request_check.setChecked(config_data.get('auto_request_batches', True))
                self.minimize_to_tray_check.setChecked(config_data.get('minimize_to_tray', True))
                self.notifications_check.setChecked(config_data.get('notifications', True))
                
                processing_settings = config_data.get('processing_settings', {})
                self.model_combo.setCurrentText(processing_settings.get('model', 'realesr-animevideov3'))
                self.scale_combo.setCurrentText(str(processing_settings.get('scale', 4)))
                self.tile_size_slider.setValue(processing_settings.get('tile_size', 0))
                
                self.realesrgan_path_input.setText(config_data.get('realesrgan_path', ''))
                
                self.config.update(config_data)
                
                QMessageBox.information(self, "Configuration", "Configuration chargée avec succès")
                self.log_message("Configuration chargée")
            else:
                QMessageBox.warning(self, "Configuration", "Aucun fichier de configuration trouvé")
                
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur lors du chargement:\n{e}")
            self.log_message(f"Erreur chargement config: {e}", "error")
    
    def reset_configuration(self):
        """Remet la configuration par défaut"""
        reply = QMessageBox.question(
            self,
            "Confirmation",
            "Voulez-vous vraiment remettre la configuration par défaut?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Restaurer les valeurs par défaut
            self.server_host_input.setText("localhost")
            self.server_port_input.setValue(8888)
            self.auto_connect_check.setChecked(False)
            self.auto_request_check.setChecked(True)
            self.minimize_to_tray_check.setChecked(True)
            self.notifications_check.setChecked(True)
            self.model_combo.setCurrentText("realesr-animevideov3")
            self.scale_combo.setCurrentText("4")
            self.tile_size_slider.setValue(0)
            self.realesrgan_path_input.clear()
            
            self.log_message("Configuration réinitialisée")
    
    def export_logs(self):
        """Exporte les logs"""
        from PyQt5.QtWidgets import QFileDialog
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Exporter les logs",
            f"client_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Fichiers texte (*.txt);;Tous les fichiers (*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.logs_text.toPlainText())
                
                QMessageBox.information(self, "Export", "Logs exportés avec succès")
                
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Erreur lors de l'export:\n{e}")
    
    def log_message(self, message: str, level: str = "info"):
        """Ajoute un message aux logs"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        level_colors = {
            "info": "#000000",
            "success": "#008000",
            "warning": "#FF8C00",
            "error": "#FF0000"
        }
        
        color = level_colors.get(level, "#000000")
        formatted_message = f'<span style="color: {color};">[{timestamp}] {message}</span><br>'
        
        self.logs_text.append(formatted_message)
        self.connection_log.append(f"[{timestamp}] {message}")
        
        if self.auto_scroll_check.isChecked():
            scrollbar = self.logs_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
    
    # === Callbacks du client ===
    
    async def on_client_connected(self, host: str, port: int):
        """Callback appelé lors de la connexion"""
        self.connection_changed.emit(True, f"{host}:{port}")
    
    async def on_client_disconnected(self):
        """Callback appelé lors de la déconnexion"""
        self.connection_changed.emit(False, "")
    
    async def on_client_batch_received(self, batch_id: str, batch_info: dict):
        """Callback appelé lors de la réception d'un lot"""
        self.batch_received.emit(batch_id, batch_info)
    
    async def on_client_batch_progress(self, batch_id: str, progress: float, current: int, total: int):
        """Callback appelé lors de la progression d'un lot"""
        self.batch_progress.emit(batch_id, progress, current, total)
    
    async def on_client_batch_completed(self, batch_id: str, success: bool, processing_time: float):
        """Callback appelé lors de la completion d'un lot"""
        self.batch_completed.emit(batch_id, success, processing_time)
    
    async def on_client_error(self, error_message: str):
        """Callback appelé lors d'une erreur"""
        self.error_occurred.emit(error_message)
    
    # === Gestionnaires de signaux ===
    
    def handle_connection_changed(self, connected: bool, server_info: str):
        """Gère les changements d'état de connexion"""
        if connected:
            self.log_message(f"Connecté au serveur {server_info}", "success")
        else:
            self.log_message("Déconnecté du serveur", "warning")
    
    def handle_batch_received(self, batch_id: str, batch_info: dict):
        """Gère la réception d'un nouveau lot"""
        self.log_message(f"Nouveau lot reçu: {batch_id}")
        
        # Ajouter à l'historique
        item = QListWidgetItem(f"[{datetime.now().strftime('%H:%M:%S')}] {batch_id} - Reçu")
        self.batch_history_list.addItem(item)
        self.batch_history_list.scrollToBottom()
    
    def handle_batch_progress(self, batch_id: str, progress: float, current: int, total: int):
        """Gère la progression d'un lot"""
        self.batch_progress_label.setText(f"Progression: {current}/{total} images ({progress*100:.1f}%)")
    
    def handle_batch_completed(self, batch_id: str, success: bool, processing_time: float):
        """Gère la completion d'un lot"""
        status = "Réussi" if success else "Échec"
        self.log_message(f"Lot {batch_id} terminé: {status} ({processing_time:.1f}s)", 
                         "success" if success else "error")
        
        # Mettre à jour l'historique
        item = QListWidgetItem(f"[{datetime.now().strftime('%H:%M:%S')}] {batch_id} - {status} ({processing_time:.1f}s)")
        self.batch_history_list.addItem(item)
        self.batch_history_list.scrollToBottom()
        
        # Notification système si activée
        if self.config['notifications'] and hasattr(self, 'tray_icon'):
            self.tray_icon.showMessage(
                "UpscalingByNetwork",
                f"Lot terminé: {status}",
                QSystemTrayIcon.Information,
                3000
            )
    
    def handle_error(self, error_message: str):
        """Gère les erreurs"""
        self.log_message(f"Erreur: {error_message}", "error")
        
        # Notification système pour les erreurs critiques
        if hasattr(self, 'tray_icon'):
            self.tray_icon.showMessage(
                "UpscalingByNetwork - Erreur",
                error_message,
                QSystemTrayIcon.Critical,
                5000
            )
    
    def handle_stats_updated(self, stats: dict):
        """Gère la mise à jour des statistiques"""
        pass  # Géré par update_statistics()
    
    def closeEvent(self, event):
        """Gère la fermeture de la fenêtre"""
        if self.config.get('minimize_to_tray', True) and hasattr(self, 'tray_icon'):
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "UpscalingByNetwork",
                "Le client continue de fonctionner en arrière-plan",
                QSystemTrayIcon.Information,
                2000
            )
        else:
            if self.connected:
                reply = QMessageBox.question(
                    self,
                    "Confirmation",
                    "Le client est connecté. Voulez-vous vraiment quitter?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                
                if reply == QMessageBox.Yes:
                    if self.client:
                        asyncio.create_task(self.client.disconnect())
                    event.accept()
                else:
                    event.ignore()
            else:
                event.accept()