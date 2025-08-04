# UpscalingByNetwork/server/gui/server_window.py
"""
Interface graphique principale du serveur distribué
Version complète avec gestion des lots et monitoring temps réel
"""

import sys
import asyncio
import time
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
import qasync
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QTabWidget, QGroupBox, QGridLayout, QLabel, QPushButton, QFileDialog,
    QTableWidget, QTableWidgetItem, QProgressBar, QTextEdit, QSpinBox,
    QLineEdit, QComboBox, QCheckBox, QSlider, QSplitter, QFrame,
    QScrollArea, QMessageBox, QSystemTrayIcon, QMenu, QAction, QStyle,
    QHeaderView, QStatusBar, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import QTimer, Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QFont, QIcon, QPixmap, QPalette, QColor, QPainter

# Import conditionnel du serveur distribué
try:
    from core.distributed_server import DistributedServer
except ImportError:
    # Fallback si le module n'existe pas encore
    DistributedServer = None

class BatchStatusWidget(QWidget):
    """Widget d'affichage du statut d'un lot"""
    
    def __init__(self, batch_id: str, total_images: int):
        super().__init__()
        self.batch_id = batch_id
        self.total_images = total_images
        self.processed_images = 0
        self.status = "pending"  # pending, processing, completed, error
        self.client_mac = None
        
        self.setup_ui()
    
    def setup_ui(self):
        """Configure l'interface du widget de lot"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # En-tête du lot
        header_layout = QHBoxLayout()
        
        self.batch_label = QLabel(f"Lot {self.batch_id}")
        self.batch_label.setFont(QFont("Arial", 10, QFont.Bold))
        header_layout.addWidget(self.batch_label)
        
        self.status_label = QLabel("En attente")
        self.status_label.setStyleSheet("color: orange;")
        header_layout.addStretch()
        header_layout.addWidget(self.status_label)
        
        layout.addLayout(header_layout)
        
        # Barre de progression
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(self.total_images)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # Informations détaillées
        self.info_label = QLabel(f"0/{self.total_images} images")
        self.info_label.setStyleSheet("color: #666; font-size: 9px;")
        layout.addWidget(self.info_label)
        
        # Style du widget
        self.setMaximumHeight(80)
        self.setStyleSheet("""
            BatchStatusWidget {
                border: 1px solid #ddd;
                border-radius: 5px;
                background-color: #f9f9f9;
                margin: 2px;
            }
        """)
    
    def update_status(self, status: str, processed: int = None, client_mac: str = None):
        """Met à jour le statut du lot"""
        self.status = status
        if processed is not None:
            self.processed_images = processed
        if client_mac:
            self.client_mac = client_mac
        
        # Mise à jour de l'affichage
        status_colors = {
            "pending": ("En attente", "color: orange;"),
            "processing": ("En cours", "color: blue;"),
            "completed": ("Terminé", "color: green;"),
            "error": ("Erreur", "color: red;")
        }
        
        if status in status_colors:
            text, style = status_colors[status]
            self.status_label.setText(text)
            self.status_label.setStyleSheet(style)
        
        # Mise à jour de la progression
        if processed is not None:
            self.progress_bar.setValue(processed)
            self.info_label.setText(f"{processed}/{self.total_images} images")
            
            if client_mac:
                self.info_label.setText(f"{processed}/{self.total_images} images - {client_mac[:8]}...")

class ServerWindow(QMainWindow):
    """Interface graphique principale du serveur"""
    
    # Signaux pour communication inter-threads
    client_connected = pyqtSignal(str, str)  # mac, hostname
    client_disconnected = pyqtSignal(str)  # mac
    batch_assigned = pyqtSignal(str, str)  # batch_id, client_mac
    batch_progress = pyqtSignal(str, int)  # batch_id, processed_count
    batch_completed = pyqtSignal(str, bool)  # batch_id, success
    job_started = pyqtSignal(str)  # job_id
    job_completed = pyqtSignal(str, bool)  # job_id, success
    
    def __init__(self):
        super().__init__()
        
        # Serveur distribué
        self.server: Optional["DistributedServer"] = None
        self.server_running = False
        
        # Configuration
        self.config = {
            'host': '0.0.0.0',
            'port': 8888,
            'max_clients': 50,
            'batch_size': 50,
            'auto_start': False,
            'minimize_to_tray': True
        }
        
        # Données d'état
        self.connected_clients: Dict[str, Dict] = {}
        self.active_batches: Dict[str, BatchStatusWidget] = {}
        self.current_job = None
        
        # Interface
        self.setup_ui()
        self.setup_tray()
        self.setup_timers()
        self.setup_styles()
        
        # État initial
        self.update_ui_state()
        
        self.setWindowTitle("UpscalingByNetwork - Serveur Distribué")
        self.setGeometry(100, 100, 1400, 900)
        self.setMinimumSize(1200, 700)
    
    def set_server_config(self, host: str, port: int):
        """Configure les paramètres du serveur"""
        self.config['host'] = host
        self.config['port'] = port
        self.host_input.setText(host)
        self.port_input.setValue(port)
    
    def setup_ui(self):
        """Configure l'interface utilisateur"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principal
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Barre de statut du serveur
        self.setup_server_status_bar(main_layout)
        
        # Onglets principaux
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # Onglet Surveillance
        self.setup_monitoring_tab()
        
        # Onglet Gestion des Jobs
        self.setup_job_management_tab()
        
        # Onglet Configuration
        self.setup_configuration_tab()
        
        # Onglet Logs
        self.setup_logs_tab()
        
        # Barre de statut
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Serveur arrêté")
    
    def setup_server_status_bar(self, main_layout):
        """Configure la barre de statut du serveur"""
        status_frame = QFrame()
        status_frame.setFrameStyle(QFrame.StyledPanel)
        status_frame.setMaximumHeight(80)
        main_layout.addWidget(status_frame)
        
        status_layout = QHBoxLayout(status_frame)
        
        # Contrôles du serveur
        server_group = QGroupBox("Contrôle Serveur")
        server_layout = QGridLayout(server_group)
        
        server_layout.addWidget(QLabel("Adresse:"), 0, 0)
        self.host_input = QLineEdit(self.config['host'])
        server_layout.addWidget(self.host_input, 0, 1)
        
        server_layout.addWidget(QLabel("Port:"), 0, 2)
        self.port_input = QSpinBox()
        self.port_input.setRange(1024, 65535)
        self.port_input.setValue(self.config['port'])
        server_layout.addWidget(self.port_input, 0, 3)
        
        self.start_stop_btn = QPushButton("Démarrer le Serveur")
        self.start_stop_btn.clicked.connect(self.toggle_server)
        server_layout.addWidget(self.start_stop_btn, 1, 0, 1, 2)
        
        self.server_status_label = QLabel("Arrêté")
        self.server_status_label.setStyleSheet("color: red; font-weight: bold;")
        server_layout.addWidget(self.server_status_label, 1, 2, 1, 2)
        
        status_layout.addWidget(server_group)
        
        # Statistiques rapides
        stats_group = QGroupBox("Statistiques")
        stats_layout = QGridLayout(stats_group)
        
        self.clients_count_label = QLabel("Clients: 0")
        stats_layout.addWidget(self.clients_count_label, 0, 0)
        
        self.batches_count_label = QLabel("Lots: 0")
        stats_layout.addWidget(self.batches_count_label, 0, 1)
        
        self.jobs_count_label = QLabel("Jobs: 0")
        stats_layout.addWidget(self.jobs_count_label, 1, 0)
        
        self.uptime_label = QLabel("Uptime: 00:00:00")
        stats_layout.addWidget(self.uptime_label, 1, 1)
        
        status_layout.addWidget(stats_group)
        status_layout.addStretch()
    
    def setup_monitoring_tab(self):
        """Configure l'onglet de surveillance"""
        monitoring_widget = QWidget()
        self.tabs.addTab(monitoring_widget, "🖥️ Surveillance")
        
        layout = QHBoxLayout(monitoring_widget)
        
        # Splitter pour diviser l'espace
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)
        
        # Panel gauche - Clients connectés
        clients_group = QGroupBox("Clients Connectés")
        clients_layout = QVBoxLayout(clients_group)
        
        self.clients_table = QTableWidget()
        self.clients_table.setColumnCount(5)
        self.clients_table.setHorizontalHeaderLabels([
            "Adresse MAC", "Nom d'hôte", "IP", "Lots traités", "Statut"
        ])
        self.clients_table.horizontalHeader().setStretchLastSection(True)
        clients_layout.addWidget(self.clients_table)
        
        splitter.addWidget(clients_group)
        
        # Panel droit - Lots actifs
        batches_group = QGroupBox("Lots Actifs")
        batches_layout = QVBoxLayout(batches_group)
        
        # Scroll area pour les lots
        self.batches_scroll = QScrollArea()
        self.batches_scroll.setWidgetResizable(True)
        self.batches_widget = QWidget()
        self.batches_layout = QVBoxLayout(self.batches_widget)
        self.batches_layout.addStretch()
        self.batches_scroll.setWidget(self.batches_widget)
        
        batches_layout.addWidget(self.batches_scroll)
        splitter.addWidget(batches_group)
        
        # Ratio des panels
        splitter.setSizes([600, 800])
    
    def setup_job_management_tab(self):
        """Configure l'onglet de gestion des jobs"""
        job_widget = QWidget()
        self.tabs.addTab(job_widget, "🎬 Gestion des Jobs")
        
        layout = QVBoxLayout(job_widget)
        
        # Nouveau job
        new_job_group = QGroupBox("Nouveau Job")
        new_job_layout = QGridLayout(new_job_group)
        
        new_job_layout.addWidget(QLabel("Fichier vidéo:"), 0, 0)
        self.video_path_input = QLineEdit()
        new_job_layout.addWidget(self.video_path_input, 0, 1)
        
        self.browse_video_btn = QPushButton("Parcourir")
        self.browse_video_btn.clicked.connect(self.browse_video_file)
        new_job_layout.addWidget(self.browse_video_btn, 0, 2)
        
        new_job_layout.addWidget(QLabel("Facteur d'échelle:"), 1, 0)
        self.scale_factor_combo = QComboBox()
        self.scale_factor_combo.addItems(["2", "3", "4"])
        self.scale_factor_combo.setCurrentText("4")
        new_job_layout.addWidget(self.scale_factor_combo, 1, 1)
        
        new_job_layout.addWidget(QLabel("Modèle:"), 1, 2)
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "realesr-animevideov3",
            "realesrgan-x4plus",
            "realesrgan-x4plus-anime"
        ])
        new_job_layout.addWidget(self.model_combo, 1, 3)
        
        self.create_job_btn = QPushButton("Créer le Job")
        self.create_job_btn.clicked.connect(self.create_new_job)
        self.create_job_btn.setEnabled(False)
        new_job_layout.addWidget(self.create_job_btn, 2, 0, 1, 4)
        
        layout.addWidget(new_job_group)
        
        # Jobs actifs
        active_jobs_group = QGroupBox("Jobs Actifs")
        active_jobs_layout = QVBoxLayout(active_jobs_group)
        
        self.jobs_table = QTableWidget()
        self.jobs_table.setColumnCount(6)
        self.jobs_table.setHorizontalHeaderLabels([
            "ID", "Fichier", "Progression", "Lots total", "Lots traités", "Statut"
        ])
        self.jobs_table.horizontalHeader().setStretchLastSection(True)
        active_jobs_layout.addWidget(self.jobs_table)
        
        layout.addWidget(active_jobs_group)
    
    def setup_configuration_tab(self):
        """Configure l'onglet de configuration"""
        config_widget = QWidget()
        self.tabs.addTab(config_widget, "⚙️ Configuration")
        
        layout = QVBoxLayout(config_widget)
        
        # Configuration serveur
        server_config_group = QGroupBox("Configuration Serveur")
        server_config_layout = QGridLayout(server_config_group)
        
        server_config_layout.addWidget(QLabel("Clients maximum:"), 0, 0)
        self.max_clients_spin = QSpinBox()
        self.max_clients_spin.setRange(1, 1000)
        self.max_clients_spin.setValue(self.config['max_clients'])
        server_config_layout.addWidget(self.max_clients_spin, 0, 1)
        
        server_config_layout.addWidget(QLabel("Taille des lots:"), 1, 0)
        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setRange(10, 200)
        self.batch_size_spin.setValue(self.config['batch_size'])
        server_config_layout.addWidget(self.batch_size_spin, 1, 1)
        
        self.auto_start_check = QCheckBox("Démarrage automatique")
        self.auto_start_check.setChecked(self.config['auto_start'])
        server_config_layout.addWidget(self.auto_start_check, 2, 0, 1, 2)
        
        layout.addWidget(server_config_group)
        
        # Chemins des exécutables
        paths_group = QGroupBox("Chemins des Exécutables")
        paths_layout = QGridLayout(paths_group)
        
        paths_layout.addWidget(QLabel("FFmpeg:"), 0, 0)
        self.ffmpeg_path_input = QLineEdit()
        paths_layout.addWidget(self.ffmpeg_path_input, 0, 1)
        
        paths_layout.addWidget(QLabel("Real-ESRGAN:"), 1, 0)
        self.realesrgan_path_input = QLineEdit()
        paths_layout.addWidget(self.realesrgan_path_input, 1, 1)
        
        layout.addWidget(paths_group)
        
        # Boutons de sauvegarde
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        self.save_config_btn = QPushButton("Sauvegarder Configuration")
        self.save_config_btn.clicked.connect(self.save_configuration)
        buttons_layout.addWidget(self.save_config_btn)
        
        self.load_config_btn = QPushButton("Charger Configuration")
        self.load_config_btn.clicked.connect(self.load_configuration)
        buttons_layout.addWidget(self.load_config_btn)
        
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
        """)
    
    def update_ui_state(self):
        """Met à jour l'état de l'interface"""
        # Mise à jour du bouton start/stop
        if self.server_running:
            self.start_stop_btn.setText("Arrêter le Serveur")
            self.start_stop_btn.setStyleSheet("background-color: #f44336;")
            self.server_status_label.setText("Démarré")
            self.server_status_label.setStyleSheet("color: green; font-weight: bold;")
            self.create_job_btn.setEnabled(True)
        else:
            self.start_stop_btn.setText("Démarrer le Serveur")
            self.start_stop_btn.setStyleSheet("background-color: #4CAF50;")
            self.server_status_label.setText("Arrêté")
            self.server_status_label.setStyleSheet("color: red; font-weight: bold;")
            self.create_job_btn.setEnabled(False)
        
        # Mise à jour des statistiques rapides
        self.clients_count_label.setText(f"Clients: {len(self.connected_clients)}")
        self.batches_count_label.setText(f"Lots: {len(self.active_batches)}")
    
    def update_statistics(self):
        """Met à jour les statistiques détaillées"""
        if self.server_running:
            # Calcul de l'uptime
            # TODO: Implémenter le calcul d'uptime
            pass
    
    def toggle_server(self):
        """Démarre ou arrête le serveur"""
        if self.server_running:
            self.stop_server()
        else:
            self.start_server()
    
    def start_server(self):
        """Démarre le serveur"""
        try:
            host = self.host_input.text()
            port = self.port_input.value()
            
            # TODO: Démarrer le serveur distribué
            # self.server = DistributedServer()
            # await self.server.start(host, port)
            
            self.server_running = True
            self.log_message(f"Serveur démarré sur {host}:{port}")
            
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de démarrer le serveur:\n{e}")
    
    def stop_server(self):
        """Arrête le serveur"""
        try:
            # TODO: Arrêter le serveur distribué
            # if self.server:
            #     await self.server.stop()
            
            self.server_running = False
            self.connected_clients.clear()
            self.active_batches.clear()
            self.update_clients_table()
            self.update_batches_display()
            
            self.log_message("Serveur arrêté")
            
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur lors de l'arrêt:\n{e}")
    
    def browse_video_file(self):
        """Ouvre un dialogue pour sélectionner un fichier vidéo"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Sélectionner un fichier vidéo",
            "",
            "Fichiers vidéo (*.mp4 *.avi *.mkv *.mov *.wmv *.flv);;Tous les fichiers (*)"
        )
        
        if file_path:
            self.video_path_input.setText(file_path)
    
    def create_new_job(self):
        """Crée un nouveau job d'upscaling"""
        video_path = self.video_path_input.text()
        if not video_path or not Path(video_path).exists():
            QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un fichier vidéo valide")
            return
        
        scale_factor = int(self.scale_factor_combo.currentText())
        model = self.model_combo.currentText()
        
        # TODO: Créer le job dans le serveur distribué
        job_id = f"job_{int(time.time())}"
        self.log_message(f"Création du job {job_id}: {Path(video_path).name}")
        
        # Réinitialiser le formulaire
        self.video_path_input.clear()
    
    def update_clients_table(self):
        """Met à jour le tableau des clients"""
        self.clients_table.setRowCount(len(self.connected_clients))
        
        for i, (mac, client_info) in enumerate(self.connected_clients.items()):
            self.clients_table.setItem(i, 0, QTableWidgetItem(mac))
            self.clients_table.setItem(i, 1, QTableWidgetItem(client_info.get('hostname', 'Inconnu')))
            self.clients_table.setItem(i, 2, QTableWidgetItem(client_info.get('ip', 'Inconnu')))
            self.clients_table.setItem(i, 3, QTableWidgetItem(str(client_info.get('batches_processed', 0))))
            self.clients_table.setItem(i, 4, QTableWidgetItem(client_info.get('status', 'Connecté')))
    
    def update_batches_display(self):
        """Met à jour l'affichage des lots"""
        # Supprimer les widgets existants (sauf le stretch)
        while self.batches_layout.count() > 1:
            child = self.batches_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Ajouter les widgets de lots actifs
        for batch_id, batch_widget in self.active_batches.items():
            self.batches_layout.insertWidget(self.batches_layout.count() - 1, batch_widget)
    
    def add_batch(self, batch_id: str, total_images: int):
        """Ajoute un nouveau lot à l'affichage"""
        batch_widget = BatchStatusWidget(batch_id, total_images)
        self.active_batches[batch_id] = batch_widget
        self.update_batches_display()
    
    def update_batch_progress(self, batch_id: str, processed: int, client_mac: str = None):
        """Met à jour la progression d'un lot"""
        if batch_id in self.active_batches:
            self.active_batches[batch_id].update_status("processing", processed, client_mac)
    
    def complete_batch(self, batch_id: str, success: bool):
        """Marque un lot comme terminé"""
        if batch_id in self.active_batches:
            status = "completed" if success else "error"
            self.active_batches[batch_id].update_status(status)
    
    def log_message(self, message: str):
        """Ajoute un message aux logs"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        
        self.logs_text.append(formatted_message)
        
        if self.auto_scroll_check.isChecked():
            scrollbar = self.logs_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
    
    def save_configuration(self):
        """Sauvegarde la configuration"""
        config_data = {
            'host': self.host_input.text(),
            'port': self.port_input.value(),
            'max_clients': self.max_clients_spin.value(),
            'batch_size': self.batch_size_spin.value(),
            'auto_start': self.auto_start_check.isChecked(),
            'ffmpeg_path': self.ffmpeg_path_input.text(),
            'realesrgan_path': self.realesrgan_path_input.text()
        }
        
        try:
            config_file = Path("server_config.json")
            with open(config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            QMessageBox.information(self, "Configuration", "Configuration sauvegardée avec succès")
            
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur lors de la sauvegarde:\n{e}")
    
    def load_configuration(self):
        """Charge la configuration"""
        try:
            config_file = Path("server_config.json")
            if config_file.exists():
                with open(config_file, 'r') as f:
                    config_data = json.load(f)
                
                # Appliquer la configuration à l'interface
                self.host_input.setText(config_data.get('host', '0.0.0.0'))
                self.port_input.setValue(config_data.get('port', 8888))
                self.max_clients_spin.setValue(config_data.get('max_clients', 50))
                self.batch_size_spin.setValue(config_data.get('batch_size', 50))
                self.auto_start_check.setChecked(config_data.get('auto_start', False))
                self.ffmpeg_path_input.setText(config_data.get('ffmpeg_path', ''))
                self.realesrgan_path_input.setText(config_data.get('realesrgan_path', ''))
                
                QMessageBox.information(self, "Configuration", "Configuration chargée avec succès")
            else:
                QMessageBox.warning(self, "Configuration", "Aucun fichier de configuration trouvé")
                
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur lors du chargement:\n{e}")
    
    def export_logs(self):
        """Exporte les logs vers un fichier"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Exporter les logs",
            f"server_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Fichiers texte (*.txt);;Tous les fichiers (*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.logs_text.toPlainText())
                
                QMessageBox.information(self, "Export", "Logs exportés avec succès")
                
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Erreur lors de l'export:\n{e}")
    
    def closeEvent(self, event):
        """Gère la fermeture de la fenêtre"""
        if self.config.get('minimize_to_tray', True) and hasattr(self, 'tray_icon'):
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "UpscalingByNetwork",
                "Le serveur continue de fonctionner en arrière-plan",
                QSystemTrayIcon.Information,
                2000
            )
        else:
            if self.server_running:
                reply = QMessageBox.question(
                    self,
                    "Confirmation",
                    "Le serveur est en cours d'exécution. Voulez-vous vraiment quitter?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                
                if reply == QMessageBox.Yes:
                    self.stop_server()
                    event.accept()
                else:
                    event.ignore()
            else:
                event.accept()