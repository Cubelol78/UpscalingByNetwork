"""
Interface graphique pour le serveur d'upscaling distribué
"""

import sys
import os
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QTabWidget, QLabel, QPushButton, QTableWidget, 
                            QTableWidgetItem, QProgressBar, QPlainTextEdit, QGroupBox,
                            QGridLayout, QFileDialog, QMessageBox, QSplitter,
                            QFrame, QScrollArea, QComboBox, QSpinBox, QCheckBox,
                            QSlider, QApplication, QHeaderView)
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QThread, pyqtSlot
from PyQt5.QtGui import QFont, QPixmap, QIcon, QPalette, QColor
import pyqtgraph as pg
from datetime import datetime
from pathlib import Path
import json
import asyncio

from config.settings import config
from utils.logger import get_logger
from utils.file_utils import format_file_size, format_duration
from utils.performance_monitor import performance_monitor

class MainWindow(QMainWindow):
    """Fenêtre principale du serveur"""
    
    def __init__(self, server):
        super().__init__()
        self.server = server
        self.logger = get_logger(__name__)
        
        # Configuration de la fenêtre
        self.setWindowTitle("Distributed Upscaling Server v1.0")
        self.setGeometry(100, 100, 1400, 900)
        self.setMinimumSize(1200, 800)
        
        # Initialisation de l'interface
        self.setup_ui()
        self.setup_timers()
        self.setup_connections()
        
        # Démarrage du monitoring
        performance_monitor.start_monitoring()
        
        self.logger.info("Interface graphique initialisée")
    
    # =============================================================================
    # CONFIGURATION DE L'INTERFACE
    # =============================================================================
    
    def setup_ui(self):
        """Configuration de l'interface utilisateur"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(15)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Barre d'état en haut
        self.create_status_bar()
        layout.addWidget(self.status_frame)
        
        # Onglets principaux
        main_tabs = self.create_main_layout()
        layout.addWidget(main_tabs, 1)
    
    def create_status_bar(self):
        """Crée la barre d'état principale"""
        self.status_frame = QFrame()
        self.status_frame.setFrameStyle(QFrame.Box)
        self.status_frame.setMinimumHeight(120)
        self.status_frame.setMaximumHeight(140)
        
        layout = QHBoxLayout(self.status_frame)
        layout.setSpacing(15)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Statut du serveur
        server_group = QGroupBox("Serveur")
        server_group.setMinimumWidth(120)
        server_layout = QVBoxLayout(server_group)
        server_layout.setSpacing(5)
        
        self.server_status_label = QLabel("● Démarré")
        self.server_status_label.setStyleSheet("color: green; font-weight: bold; font-size: 12px;")
        self.server_port_label = QLabel(f"Port: {config.PORT}")
        self.server_port_label.setStyleSheet("font-size: 11px;")
        
        server_layout.addWidget(self.server_status_label)
        server_layout.addWidget(self.server_port_label)
        server_layout.addStretch()
        
        # Statistiques clients
        clients_group = QGroupBox("Clients")
        clients_group.setMinimumWidth(140)
        clients_layout = QVBoxLayout(clients_group)
        clients_layout.setSpacing(5)
        
        self.clients_count_label = QLabel("Connectés: 0")
        self.clients_count_label.setStyleSheet("font-size: 11px;")
        self.clients_processing_label = QLabel("En traitement: 0")
        self.clients_processing_label.setStyleSheet("font-size: 11px;")
        
        clients_layout.addWidget(self.clients_count_label)
        clients_layout.addWidget(self.clients_processing_label)
        clients_layout.addStretch()
        
        # Statistiques lots
        batches_group = QGroupBox("Lots")
        batches_group.setMinimumWidth(140)
        batches_layout = QVBoxLayout(batches_group)
        batches_layout.setSpacing(5)
        
        self.batches_pending_label = QLabel("En attente: 0")
        self.batches_pending_label.setStyleSheet("font-size: 11px;")
        self.batches_completed_label = QLabel("Terminés: 0")
        self.batches_completed_label.setStyleSheet("font-size: 11px;")
        
        batches_layout.addWidget(self.batches_pending_label)
        batches_layout.addWidget(self.batches_completed_label)
        batches_layout.addStretch()
        
        # Job actuel
        job_group = QGroupBox("Job Actuel")
        job_group.setMinimumWidth(250)
        job_layout = QVBoxLayout(job_group)
        job_layout.setSpacing(5)
        
        self.current_job_label = QLabel("Aucun")
        self.current_job_label.setStyleSheet("font-size: 11px;")
        self.current_job_label.setWordWrap(True)
        self.job_progress = QProgressBar()
        self.job_progress.setMinimumHeight(20)
        
        job_layout.addWidget(self.current_job_label)
        job_layout.addWidget(self.job_progress)
        job_layout.addStretch()
        
        # Boutons de contrôle
        controls_group = QGroupBox("Contrôles")
        controls_group.setMinimumWidth(140)
        controls_layout = QVBoxLayout(controls_group)
        controls_layout.setSpacing(8)
        
        self.start_job_btn = QPushButton("Nouveau Job")
        self.start_job_btn.clicked.connect(self.start_new_job)
        self.start_job_btn.setMinimumHeight(25)
        
        self.stop_server_btn = QPushButton("Arrêter Serveur")
        self.stop_server_btn.clicked.connect(self.stop_server)
        self.stop_server_btn.setStyleSheet("background-color: #d32f2f; color: white;")
        self.stop_server_btn.setMinimumHeight(25)
        
        controls_layout.addWidget(self.start_job_btn)
        controls_layout.addWidget(self.stop_server_btn)
        controls_layout.addStretch()
        
        # Ajout des groupes au layout
        layout.addWidget(server_group)
        layout.addWidget(clients_group)
        layout.addWidget(batches_group)
        layout.addWidget(job_group)
        layout.addWidget(controls_group)
        layout.addStretch()
    
    def create_main_layout(self):
        """Crée le layout principal avec les onglets"""
        self.tab_widget = QTabWidget()
        
        # Onglet Vue d'ensemble
        self.overview_tab = self.create_overview_tab()
        self.tab_widget.addTab(self.overview_tab, "Vue d'ensemble")
        
        # Onglet Clients
        self.clients_tab = self.create_clients_tab()
        self.tab_widget.addTab(self.clients_tab, "Clients")
        
        # Onglet Jobs & Lots
        self.jobs_tab = self.create_jobs_tab()
        self.tab_widget.addTab(self.jobs_tab, "Jobs & Lots")
        
        # Onglet Performance
        self.performance_tab = self.create_performance_tab()
        self.tab_widget.addTab(self.performance_tab, "Performance")
        
        # Onglet Logs
        self.logs_tab = self.create_logs_tab()
        self.tab_widget.addTab(self.logs_tab, "Logs")
        
        # Onglet Configuration
        self.config_tab = self.create_config_tab()
        self.tab_widget.addTab(self.config_tab, "Configuration")
        
        return self.tab_widget
    
    # =============================================================================
    # CRÉATION DES ONGLETS
    # =============================================================================
    
    def create_overview_tab(self):
        """Crée l'onglet vue d'ensemble"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Splitter horizontal
        splitter = QSplitter(Qt.Horizontal)
        
        # Partie gauche - Graphiques
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        # Graphique temps réel des clients
        self.clients_chart = pg.PlotWidget(title="Clients connectés")
        self.clients_chart.setLabel('left', 'Nombre', size='10pt')
        self.clients_chart.setLabel('bottom', 'Temps', size='10pt')
        self.clients_chart.showGrid(x=True, y=True, alpha=0.3)
        self.clients_chart.setMinimumHeight(220)
        self.clients_chart.setBackground('black')
        self.clients_chart.getAxis('left').setTextPen('white')
        self.clients_chart.getAxis('bottom').setTextPen('white')
        
        # Graphique des lots
        self.batches_chart = pg.PlotWidget(title="Progression des lots")
        self.batches_chart.setLabel('left', 'Lots', size='10pt')
        self.batches_chart.setLabel('bottom', 'Temps', size='10pt')
        self.batches_chart.showGrid(x=True, y=True, alpha=0.3)
        self.batches_chart.setMinimumHeight(220)
        self.batches_chart.setBackground('black')
        self.batches_chart.getAxis('left').setTextPen('white')
        self.batches_chart.getAxis('bottom').setTextPen('white')
        
        left_layout.addWidget(self.clients_chart)
        left_layout.addWidget(self.batches_chart)
        
        # Partie droite - Informations détaillées
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # Informations système
        system_group = QGroupBox("Système")
        system_layout = QGridLayout(system_group)
        system_layout.setSpacing(8)
        system_layout.setContentsMargins(10, 15, 10, 10)
        
        system_layout.addWidget(QLabel("Utilisation:"), 0, 0)
        
        self.cpu_usage_label = QLabel("CPU: 0%")
        self.cpu_usage_label.setStyleSheet("font-weight: bold; color: #4CAF50;")
        
        self.memory_usage_label = QLabel("RAM: 0%")
        self.memory_usage_label.setStyleSheet("font-weight: bold; color: #2196F3;")
        
        self.disk_usage_label = QLabel("Disque: 0%")
        self.disk_usage_label.setStyleSheet("font-weight: bold; color: #FF9800;")
        
        self.uptime_label = QLabel("Uptime: 0s")
        self.uptime_label.setStyleSheet("font-weight: bold; color: #9C27B0;")
        
        system_layout.addWidget(self.cpu_usage_label, 1, 0)
        system_layout.addWidget(self.memory_usage_label, 2, 0)
        system_layout.addWidget(self.disk_usage_label, 3, 0)
        system_layout.addWidget(self.uptime_label, 4, 0)
        
        # Statistiques de performance
        perf_group = QGroupBox("Performance")
        perf_layout = QGridLayout(perf_group)
        perf_layout.setSpacing(8)
        perf_layout.setContentsMargins(10, 15, 10, 10)
        
        self.avg_batch_time_label = QLabel("Temps moyen/lot: N/A")
        self.avg_batch_time_label.setStyleSheet("font-size: 11px;")
        
        self.processing_rate_label = QLabel("Taux de traitement: N/A")
        self.processing_rate_label.setStyleSheet("font-size: 11px;")
        
        self.total_processed_label = QLabel("Total traité: 0")
        self.total_processed_label.setStyleSheet("font-size: 11px; font-weight: bold;")
        
        perf_layout.addWidget(self.avg_batch_time_label, 0, 0)
        perf_layout.addWidget(self.processing_rate_label, 1, 0)
        perf_layout.addWidget(self.total_processed_label, 2, 0)
        
        # Top clients
        top_clients_group = QGroupBox("Top Clients")
        top_clients_layout = QVBoxLayout(top_clients_group)
        top_clients_layout.setContentsMargins(10, 15, 10, 10)
        
        self.top_clients_table = QTableWidget(5, 3)
        self.top_clients_table.setHorizontalHeaderLabels(["Client", "Lots", "Taux"])
        self.top_clients_table.horizontalHeader().setStretchLastSection(True)
        self.top_clients_table.setAlternatingRowColors(True)
        self.top_clients_table.setMinimumHeight(180)
        
        self.top_clients_table.setStyleSheet("""
            QTableWidget {
                gridline-color: #444;
                font-size: 10px;
            }
            QHeaderView::section {
                background-color: #555;
                padding: 5px;
                border: 1px solid #666;
                font-weight: bold;
            }
        """)
        
        top_clients_layout.addWidget(self.top_clients_table)
        
        right_layout.addWidget(system_group)
        right_layout.addWidget(perf_group)
        right_layout.addWidget(top_clients_group)
        right_layout.addStretch()
        
        # Assemblage
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([800, 400])
        
        layout.addWidget(splitter)
        return widget
    
    def create_clients_tab(self):
        """Crée l'onglet clients"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Barre d'outils
        toolbar_layout = QHBoxLayout()
        
        refresh_btn = QPushButton("Actualiser")
        refresh_btn.clicked.connect(self.refresh_clients)
        
        disconnect_btn = QPushButton("Déconnecter Client")
        disconnect_btn.clicked.connect(self.disconnect_selected_client)
        disconnect_btn.setEnabled(False)
        
        toolbar_layout.addWidget(refresh_btn)
        toolbar_layout.addWidget(disconnect_btn)
        toolbar_layout.addStretch()
        
        # Tableau des clients
        self.clients_table = QTableWidget()
        self.clients_table.setColumnCount(10)
        self.clients_table.setHorizontalHeaderLabels([
            "MAC", "IP", "Hostname", "Platform", "Status", 
            "Lot actuel", "Lots terminés", "Taux succès", 
            "Temps moy.", "Connexion"
        ])
        
        # Configuration du tableau
        header = self.clients_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        
        self.clients_table.selectionModel().selectionChanged.connect(
            lambda: disconnect_btn.setEnabled(
                len(self.clients_table.selectionModel().selectedRows()) > 0
            )
        )
        
        layout.addLayout(toolbar_layout)
        layout.addWidget(self.clients_table)
        
        return widget
    
    def create_jobs_tab(self):
        """Crée l'onglet jobs et lots"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Splitter vertical
        splitter = QSplitter(Qt.Vertical)
        
        # Partie haute - Jobs
        jobs_widget = QWidget()
        jobs_layout = QVBoxLayout(jobs_widget)
        
        jobs_label = QLabel("Jobs")
        jobs_label.setFont(QFont("Arial", 12, QFont.Bold))
        
        self.jobs_table = QTableWidget()
        self.jobs_table.setColumnCount(8)
        self.jobs_table.setHorizontalHeaderLabels([
            "ID", "Fichier", "Status", "Progression", 
            "Lots total", "Terminés", "Temps", "Créé le"
        ])
        
        jobs_layout.addWidget(jobs_label)
        jobs_layout.addWidget(self.jobs_table)
        
        # Partie basse - Lots du job sélectionné
        batches_widget = QWidget()
        batches_layout = QVBoxLayout(batches_widget)
        
        batches_label = QLabel("Lots du job sélectionné")
        batches_label.setFont(QFont("Arial", 12, QFont.Bold))
        
        self.batches_table = QTableWidget()
        self.batches_table.setColumnCount(8)
        self.batches_table.setHorizontalHeaderLabels([
            "ID", "Frames", "Status", "Client", 
            "Progression", "Tentatives", "Temps", "Erreur"
        ])
        
        batches_layout.addWidget(batches_label)
        batches_layout.addWidget(self.batches_table)
        
        # Assemblage
        splitter.addWidget(jobs_widget)
        splitter.addWidget(batches_widget)
        splitter.setSizes([300, 400])
        
        layout.addWidget(splitter)
        return widget
    
    def create_performance_tab(self):
        """Crée l'onglet performance"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Graphiques de performance
        charts_layout = QGridLayout()
        
        # CPU Usage
        self.cpu_chart = pg.PlotWidget(title="Utilisation CPU")
        self.cpu_chart.setLabel('left', 'Pourcentage')
        self.cpu_chart.setLabel('bottom', 'Temps')
        self.cpu_chart.showGrid(x=True, y=True)
        
        # Memory Usage
        self.memory_chart = pg.PlotWidget(title="Utilisation Mémoire")
        self.memory_chart.setLabel('left', 'Pourcentage')
        self.memory_chart.setLabel('bottom', 'Temps')
        self.memory_chart.showGrid(x=True, y=True)
        
        # Network I/O
        self.network_chart = pg.PlotWidget(title="Trafic Réseau")
        self.network_chart.setLabel('left', 'MB/s')
        self.network_chart.setLabel('bottom', 'Temps')
        self.network_chart.showGrid(x=True, y=True)
        
        # Processing Rate
        self.rate_chart = pg.PlotWidget(title="Taux de Traitement")
        self.rate_chart.setLabel('left', 'Lots/min')
        self.rate_chart.setLabel('bottom', 'Temps')
        self.rate_chart.showGrid(x=True, y=True)
        
        charts_layout.addWidget(self.cpu_chart, 0, 0)
        charts_layout.addWidget(self.memory_chart, 0, 1)
        charts_layout.addWidget(self.network_chart, 1, 0)
        charts_layout.addWidget(self.rate_chart, 1, 1)
        
        layout.addLayout(charts_layout)
        return widget
    
    def create_logs_tab(self):
        """Crée l'onglet logs"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Barre d'outils
        toolbar_layout = QHBoxLayout()
        
        clear_btn = QPushButton("Effacer")
        clear_btn.clicked.connect(self.clear_logs)
        
        save_btn = QPushButton("Sauvegarder")
        save_btn.clicked.connect(self.save_logs)
        
        level_combo = QComboBox()
        level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        level_combo.setCurrentText("INFO")
        level_combo.currentTextChanged.connect(self.change_log_level)
        
        toolbar_layout.addWidget(QLabel("Niveau:"))
        toolbar_layout.addWidget(level_combo)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(clear_btn)
        toolbar_layout.addWidget(save_btn)
        
        # Zone de texte pour les logs
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(config.LOG_MAX_LINES)
        
        # Police monospace pour les logs
        font = QFont("Consolas", 9)
        font.setStyleHint(QFont.Monospace)
        self.log_text.setFont(font)
        
        layout.addLayout(toolbar_layout)
        layout.addWidget(self.log_text)
        
        return widget
    
    def create_config_tab(self):
        """Crée l'onglet configuration"""
        widget = QScrollArea()
        widget.setWidgetResizable(True)
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(15)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Configuration stockage
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
        
        # Informations sur l'espace disque - INITIALISATION CORRECTE
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
        
        # Configuration serveur
        server_group = QGroupBox("Configuration Serveur")
        server_group.setMinimumWidth(400)
        server_layout = QGridLayout(server_group)
        server_layout.setSpacing(10)
        server_layout.setContentsMargins(15, 20, 15, 15)
        
        server_layout.addWidget(QLabel("Host:"), 0, 0)
        self.host_input = QLabel(config.HOST)
        self.host_input.setStyleSheet("font-weight: bold;")
        server_layout.addWidget(self.host_input, 0, 1)
        
        server_layout.addWidget(QLabel("Port:"), 1, 0)
        self.port_input = QLabel(str(config.PORT))
        self.port_input.setStyleSheet("font-weight: bold;")
        server_layout.addWidget(self.port_input, 1, 1)
        
        server_layout.addWidget(QLabel("Clients maximum:"), 2, 0)
        self.max_clients_spin = QSpinBox()
        self.max_clients_spin.setRange(1, 1000)
        self.max_clients_spin.setValue(config.MAX_CLIENTS)
        self.max_clients_spin.setMaximumWidth(100)
        server_layout.addWidget(self.max_clients_spin, 2, 1)
        
        # Configuration lots
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
        
        # Configuration Real-ESRGAN
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
        
        # Configuration sécurité
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
        
        # Boutons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        
        save_config_btn = QPushButton("Sauvegarder Configuration")
        save_config_btn.clicked.connect(self.save_configuration)
        save_config_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 10px; font-weight: bold;")
        save_config_btn.setMinimumHeight(35)
        
        reset_config_btn = QPushButton("Réinitialiser")
        reset_config_btn.clicked.connect(self.reset_configuration)
        reset_config_btn.setStyleSheet("background-color: #f44336; color: white; padding: 10px; font-weight: bold;")
        reset_config_btn.setMinimumHeight(35)
        
        buttons_layout.addWidget(save_config_btn)
        buttons_layout.addWidget(reset_config_btn)
        buttons_layout.addStretch()
        
        # Ajout au layout avec espacements appropriés
        layout.addWidget(storage_group)
        layout.addSpacing(10)
        layout.addWidget(server_group)
        layout.addSpacing(10)
        layout.addWidget(batches_group)
        layout.addSpacing(10)
        layout.addWidget(esrgan_group)
        layout.addSpacing(10)
        layout.addWidget(security_group)
        layout.addSpacing(15)
        layout.addLayout(buttons_layout)
        layout.addStretch()
        
        widget.setWidget(content_widget)
        
        # IMPORTANT: Initialiser les disques après création de tous les widgets
        self.refresh_drives()
        
        return widget
    
    # =============================================================================
    # CONFIGURATION ET CONNEXIONS
    # =============================================================================
    
    def setup_timers(self):
        """Configure les timers pour les mises à jour"""
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_interface)
        self.update_timer.start(config.GUI_UPDATE_INTERVAL)
        
        self.performance_timer = QTimer()
        self.performance_timer.timeout.connect(self.update_performance_charts)
        self.performance_timer.start(5000)
    
    def setup_connections(self):
        """Configure les connexions de signaux"""
        self.jobs_table.selectionModel().selectionChanged.connect(
            self.on_job_selection_changed
        )
    
    # =============================================================================
    # MISE À JOUR DE L'INTERFACE
    # =============================================================================
    
    def update_interface(self):
        """Met à jour l'interface avec les données du serveur"""
        try:
            stats = self.server.get_statistics()
            self.update_status_bar(stats)
            
            current_tab = self.tab_widget.currentIndex()
            if current_tab == 0:
                self.update_overview_tab(stats)
            elif current_tab == 1:
                self.update_clients_tab()
            elif current_tab == 2:
                self.update_jobs_tab()
            
        except Exception as e:
            self.logger.error(f"Erreur mise à jour interface: {e}")
    
    def update_status_bar(self, stats):
        """Met à jour la barre de statut"""
        if stats['server']['running']:
            self.server_status_label.setText("● En ligne")
            self.server_status_label.setStyleSheet("color: green; font-weight: bold; font-size: 12px;")
        else:
            self.server_status_label.setText("● Hors ligne")
            self.server_status_label.setStyleSheet("color: red; font-weight: bold; font-size: 12px;")
        
        self.clients_count_label.setText(f"Connectés: {stats['clients']['online']}")
        self.clients_processing_label.setText(f"En traitement: {stats['clients']['processing']}")
        
        self.batches_pending_label.setText(f"En attente: {stats['batches']['pending']}")
        self.batches_completed_label.setText(f"Terminés: {stats['batches']['completed']}")
        
        if stats['current_job']:
            job_info = stats['current_job']
            self.current_job_label.setText(job_info['input_file'])
            self.job_progress.setValue(int(job_info['progress']))
        else:
            self.current_job_label.setText("Aucun")
            self.job_progress.setValue(0)
    
    def update_overview_tab(self, stats):
        """Met à jour l'onglet vue d'ensemble"""
        self.update_top_clients()
        
        perf_stats = performance_monitor.get_current_stats()
        if 'cpu_usage' in perf_stats:
            self.cpu_usage_label.setText(f"CPU: {perf_stats['cpu_usage']['current']:.1f}%")
        if 'memory_usage' in perf_stats:
            self.memory_usage_label.setText(f"RAM: {perf_stats['memory_usage']['current']:.1f}%")
        
        uptime = stats['server']['uptime']
        self.uptime_label.setText(f"Uptime: {format_duration(uptime)}")
    
    def update_clients_tab(self):
        """Met à jour l'onglet clients"""
        if hasattr(self.server, 'client_manager'):
            clients_stats = self.server.client_manager.get_all_clients_stats()
            self.clients_table.setRowCount(len(clients_stats))
            
            for row, client in enumerate(clients_stats):
                if client:
                    self.clients_table.setItem(row, 0, QTableWidgetItem(client['mac_address'][:17]))
                    self.clients_table.setItem(row, 1, QTableWidgetItem(client['ip_address']))
                    self.clients_table.setItem(row, 2, QTableWidgetItem(client['hostname']))
                    self.clients_table.setItem(row, 3, QTableWidgetItem(client['platform']))
                    
                    status_item = QTableWidgetItem(client['status'])
                    if client['is_online']:
                        status_item.setBackground(QColor(144, 238, 144))
                    else:
                        status_item.setBackground(QColor(255, 182, 193))
                    self.clients_table.setItem(row, 4, status_item)
                    
                    self.clients_table.setItem(row, 5, QTableWidgetItem(client['current_batch'] or "Aucun"))
                    self.clients_table.setItem(row, 6, QTableWidgetItem(str(client['batches_completed'])))
                    self.clients_table.setItem(row, 7, QTableWidgetItem(f"{client['success_rate']:.1f}%"))
                    self.clients_table.setItem(row, 8, QTableWidgetItem(f"{client['average_batch_time']:.1f}s"))
                    self.clients_table.setItem(row, 9, QTableWidgetItem(format_duration(client['connection_time'])))
    
    def update_jobs_tab(self):
        """Met à jour l'onglet jobs"""
        jobs = list(self.server.jobs.values())
        self.jobs_table.setRowCount(len(jobs))
        
        for row, job in enumerate(jobs):
            self.jobs_table.setItem(row, 0, QTableWidgetItem(job.id[:8]))
            self.jobs_table.setItem(row, 1, QTableWidgetItem(Path(job.input_video_path).name))
            self.jobs_table.setItem(row, 2, QTableWidgetItem(job.status.value))
            self.jobs_table.setItem(row, 3, QTableWidgetItem(f"{job.progress:.1f}%"))
            self.jobs_table.setItem(row, 4, QTableWidgetItem(str(len(job.batches))))
            self.jobs_table.setItem(row, 5, QTableWidgetItem(str(job.completed_batches)))
            
            processing_time = job.processing_time or 0
            self.jobs_table.setItem(row, 6, QTableWidgetItem(format_duration(processing_time)))
            self.jobs_table.setItem(row, 7, QTableWidgetItem(job.created_at.strftime('%H:%M:%S')))
    
    def update_top_clients(self):
        """Met à jour le tableau des top clients"""
        clients = list(self.server.clients.values())
        clients.sort(key=lambda c: c.batches_completed, reverse=True)
        
        for row in range(min(5, len(clients))):
            client = clients[row]
            self.top_clients_table.setItem(row, 0, QTableWidgetItem(client.hostname or client.mac_address[:8]))
            self.top_clients_table.setItem(row, 1, QTableWidgetItem(str(client.batches_completed)))
            self.top_clients_table.setItem(row, 2, QTableWidgetItem(f"{client.success_rate:.1f}%"))
    
    def update_performance_charts(self):
        """Met à jour les graphiques de performance"""
        try:
            performance_monitor.add_server_metrics(self.server)
            
            timestamps_cpu, cpu_data = performance_monitor.get_time_series_data('cpu_usage', 60)
            timestamps_mem, memory_data = performance_monitor.get_time_series_data('memory_usage', 60)
            
            if timestamps_cpu and cpu_data:
                self.cpu_chart.clear()
                self.cpu_chart.plot(timestamps_cpu, cpu_data, pen='r')
            
            if timestamps_mem and memory_data:
                self.memory_chart.clear()
                self.memory_chart.plot(timestamps_mem, memory_data, pen='b')
            
        except Exception as e:
            self.logger.error(f"Erreur mise à jour graphiques performance: {e}")
    
    # =============================================================================
    # GESTION DU STOCKAGE
    # =============================================================================
    
    def refresh_drives(self):
        """Actualise la liste des disques disponibles"""
        try:
            # Vérifier que le widget existe avant de continuer
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
            self.logger.error(f"Erreur actualisation disques: {e}")
    
    def on_drive_changed(self):
        """Gestionnaire de changement de disque"""
        try:
            # Vérifier que les widgets existent
            if not hasattr(self, 'drive_combo') or not hasattr(self, 'drive_info_label'):
                return
                
            current_data = self.drive_combo.currentData()
            if current_data:
                config.set_work_drive(current_data)
                self.update_drive_info()
                self.logger.info(f"Disque de travail changé: {current_data}")
                
        except Exception as e:
            self.logger.error(f"Erreur changement disque: {e}")
    
    def update_drive_info(self):
        """Met à jour les informations du disque sélectionné"""
        try:
            # Vérifier que le widget existe
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
                    color = "#f44336"  # Rouge - insuffisant
                    status = "⚠️ ESPACE INSUFFISANT"
                elif info['free_gb'] < config.MIN_FREE_SPACE_GB * 2:
                    color = "#FF9800"  # Orange - limite
                    status = "⚠️ Espace limité"
                else:
                    color = "#4CAF50"  # Vert - OK
                    status = "✅ Espace suffisant"
                
                self.drive_info_label.setText(f"{status}\n{info_text}")
                self.drive_info_label.setStyleSheet(f"""
                    font-size: 11px; 
                    color: {color}; 
                    font-weight: bold; 
                    padding: 8px; 
                    border: 1px solid {color}; 
                    border-radius: 4px; 
                    background-color: rgba({color[1:3]}, {color[3:5]}, {color[5:7]}, 0.1);
                """.replace("#", ""))
                
                # Tooltip avec plus de détails
                work_dir = Path(config.TEMP_DIR).parent
                tooltip_text = f"""
Dossier de travail: {work_dir}
Dossier temporaire: {config.TEMP_DIR}
Dossier de sortie: {config.OUTPUT_DIR}
Espace libre minimum configuré: {config.MIN_FREE_SPACE_GB} GB
                """.strip()
                self.drive_info_label.setToolTip(tooltip_text)
                
            else:
                self.drive_info_label.setText("❌ Informations disque non disponibles")
                self.drive_info_label.setStyleSheet("font-size: 11px; color: #f44336; font-weight: bold; padding: 8px;")
                
        except Exception as e:
            self.logger.error(f"Erreur mise à jour info disque: {e}")
            if hasattr(self, 'drive_info_label'):
                self.drive_info_label.setText("❌ Erreur lecture disque")
                self.drive_info_label.setStyleSheet("font-size: 11px; color: #f44336; font-weight: bold; padding: 8px;")
    
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
            self.logger.error(f"Erreur nettoyage manuel: {e}")
            QMessageBox.critical(self, "Erreur", f"Erreur nettoyage: {str(e)}")
    
    def check_space_before_job(self, video_path: str) -> bool:
        """Vérifie l'espace disque avant de créer un job"""
        try:
            space_info = config.check_space_requirements(video_path)
            
            if 'error' in space_info:
                QMessageBox.critical(self, "Erreur", f"Impossible d'analyser la vidéo:\n{space_info['error']}")
                return False
            
            msg = QMessageBox()
            msg.setWindowTitle("Estimation espace disque requis")
            msg.setIcon(QMessageBox.Information if space_info['sufficient_space'] else QMessageBox.Warning)
            
            details_text = f"""
Fichier vidéo: {Path(video_path).name}
Taille: {space_info['video_size_gb']:.2f} GB
Frames estimées: {space_info['estimated_frames']:,}

Espace requis:
• Frames originales: {space_info['frames_space_gb']:.1f} GB
• Frames upscalées: {space_info['upscaled_space_gb']:.1f} GB  
• Fichiers temporaires: {space_info['temp_space_gb']:.1f} GB
• Vidéo de sortie: {space_info['output_space_gb']:.1f} GB

Total requis: {space_info['total_required_gb']:.1f} GB
Espace disponible: {space_info['available_space_gb']:.1f} GB
Disque de travail: {space_info['work_drive']}
"""
            
            if space_info['sufficient_space']:
                msg.setText("✅ Espace disque suffisant")
                msg.setInformativeText("Le job peut être créé.")
                msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
                msg.setDefaultButton(QMessageBox.Ok)
            else:
                msg.setText("⚠️ Espace disque insuffisant")
                msg.setInformativeText(
                    f"Il manque {space_info['total_required_gb'] - space_info['available_space_gb']:.1f} GB.\n"
                    "Voulez-vous continuer quand même?"
                )
                msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                msg.setDefaultButton(QMessageBox.No)
            
            msg.setDetailedText(details_text)
            result = msg.exec_()
            
            if space_info['sufficient_space']:
                return result == QMessageBox.Ok
            else:
                return result == QMessageBox.Yes
                
        except Exception as e:
            self.logger.error(f"Erreur vérification espace: {e}")
            QMessageBox.warning(self, "Erreur", f"Impossible de vérifier l'espace disque:\n{str(e)}")
            return True
    
    # =============================================================================
    # ACTIONS UTILISATEUR
    # =============================================================================
    
    def start_new_job(self):
        """Démarre un nouveau job avec vérification de l'espace"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Sélectionner une vidéo", "",
            "Vidéos (*.mp4 *.avi *.mov *.mkv);;Tous les fichiers (*)"
        )
        
        if file_path:
            if self.check_space_before_job(file_path):
                self.start_job_async(file_path)
    
    def start_job_async(self, file_path):
        """Démarre un job de manière asynchrone"""
        try:
            from models.job import Job
            from models.batch import Batch
            import uuid
            
            job = Job(
                input_video_path=file_path,
                output_video_path=str(Path(file_path).with_suffix('_upscaled.mp4'))
            )
            
            self.server.jobs[job.id] = job
            self.server.current_job = job.id
            
            for i in range(5):
                batch = Batch(
                    job_id=job.id,
                    frame_start=i*50,
                    frame_end=(i+1)*50-1,
                    frame_paths=[f"frame_{j:06d}.png" for j in range(i*50, (i+1)*50)]
                )
                self.server.batches[batch.id] = batch
                job.batches.append(batch.id)
            
            job.total_frames = 250
            job.start()
            
            QMessageBox.information(self, "Succès", f"Job créé avec succès!\n{job.total_frames} frames à traiter")
            
        except Exception as e:
            self.logger.error(f"Erreur création job: {e}")
            QMessageBox.critical(self, "Erreur", f"Erreur lors de la création du job:\n{str(e)}")
    
    def stop_server(self):
        """Arrête le serveur"""
        reply = QMessageBox.question(
            self, "Confirmation", "Êtes-vous sûr de vouloir arrêter le serveur?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                asyncio.create_task(self.server.stop())
            except:
                pass
            QApplication.quit()
    
    def refresh_clients(self):
        """Actualise la liste des clients"""
        self.update_clients_tab()
    
    def disconnect_selected_client(self):
        """Déconnecte le client sélectionné"""
        selected_rows = self.clients_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        
        row = selected_rows[0].row()
        mac_address = self.clients_table.item(row, 0).text()
        
        reply = QMessageBox.question(
            self, "Confirmation", f"Déconnecter le client {mac_address}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if hasattr(self.server, 'client_manager'):
                success = self.server.client_manager.disconnect_client(mac_address)
                if success:
                    QMessageBox.information(self, "Succès", "Client déconnecté")
                else:
                    QMessageBox.warning(self, "Erreur", "Impossible de déconnecter le client")
    
    def on_job_selection_changed(self):
        """Gestionnaire de changement de sélection de job"""
        selected_rows = self.jobs_table.selectionModel().selectedRows()
        if not selected_rows:
            self.batches_table.setRowCount(0)
            return
        
        row = selected_rows[0].row()
        if row < len(self.server.jobs):
            job = list(self.server.jobs.values())[row]
            self.update_batches_for_job(job)
    
    def update_batches_for_job(self, job):
        """Met à jour les lots pour un job donné"""
        job_batches = [self.server.batches[batch_id] for batch_id in job.batches 
                      if batch_id in self.server.batches]
        
        self.batches_table.setRowCount(len(job_batches))
        
        for row, batch in enumerate(job_batches):
            self.batches_table.setItem(row, 0, QTableWidgetItem(batch.id[:8]))
            self.batches_table.setItem(row, 1, QTableWidgetItem(f"{batch.frame_start}-{batch.frame_end}"))
            self.batches_table.setItem(row, 2, QTableWidgetItem(batch.status.value))
            self.batches_table.setItem(row, 3, QTableWidgetItem(batch.assigned_client or "Aucun"))
            self.batches_table.setItem(row, 4, QTableWidgetItem(f"{batch.progress:.1f}%"))
            self.batches_table.setItem(row, 5, QTableWidgetItem(str(batch.retry_count)))
            
            processing_time = batch.processing_time or 0
            self.batches_table.setItem(row, 6, QTableWidgetItem(format_duration(processing_time)))
            self.batches_table.setItem(row, 7, QTableWidgetItem(batch.error_message or ""))
    
    # =============================================================================
    # GESTION DES LOGS
    # =============================================================================
    
    def clear_logs(self):
        """Efface les logs"""
        self.log_text.clear()
    
    def save_logs(self):
        """Sauvegarde les logs"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Sauvegarder les logs", "server_logs.txt",
            "Fichiers texte (*.txt);;Tous les fichiers (*)"
        )
        
        if file_path:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self.log_text.toPlainText())
            QMessageBox.information(self, "Succès", "Logs sauvegardés")
    
    def change_log_level(self, level):
        """Change le niveau de logging"""
        import logging
        numeric_level = getattr(logging, level.upper())
        logging.getLogger().setLevel(numeric_level)
    
    # =============================================================================
    # GESTION DE LA CONFIGURATION
    # =============================================================================
    
    def save_configuration(self):
        """Sauvegarde la configuration"""
        try:
            config.AUTO_CLEANUP = self.auto_cleanup_check.isChecked()
            config.MIN_FREE_SPACE_GB = self.min_free_space_spin.value()
            config.MAX_CLIENTS = self.max_clients_spin.value()
            config.BATCH_SIZE = self.batch_size_spin.value()
            config.MAX_RETRIES = self.max_retries_spin.value()
            config.REALESRGAN_MODEL = self.model_combo.currentText()
            config.TILE_SIZE = self.tile_size_spin.value()
            config.USE_ENCRYPTION = self.encryption_check.isChecked()
            
            QMessageBox.information(self, "Succès", 
                f"Configuration sauvegardée\n"
                f"Disque de travail: {config.WORK_DRIVE}\n"
                f"Dossiers: {Path(config.TEMP_DIR).parent}")
            
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur lors de la sauvegarde:\n{str(e)}")
    
    def reset_configuration(self):
        """Remet la configuration par défaut"""
        reply = QMessageBox.question(
            self, "Confirmation", "Remettre la configuration par défaut?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.auto_cleanup_check.setChecked(True)
            self.min_free_space_spin.setValue(50)
            self.max_clients_spin.setValue(50)
            self.batch_size_spin.setValue(50)
            self.max_retries_spin.setValue(3)
            self.model_combo.setCurrentText("realesr-animevideov3")
            self.tile_size_spin.setValue(256)
            self.encryption_check.setChecked(True)
            
            config.WORK_DRIVE = config.get_best_drive()
            config.update_paths()
            config.create_directories()
            self.refresh_drives()
    
    # =============================================================================
    # ÉVÉNEMENTS DE LA FENÊTRE
    # =============================================================================
    
    def closeEvent(self, event):
        """Gestionnaire de fermeture de l'application"""
        reply = QMessageBox.question(
            self, "Confirmation", "Êtes-vous sûr de vouloir quitter?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            performance_monitor.stop_monitoring()
            
            if self.server.running:
                try:
                    asyncio.create_task(self.server.stop())
                except:
                    pass
            
            event.accept()
        else:
            event.ignore()