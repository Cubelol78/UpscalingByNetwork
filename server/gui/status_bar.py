"""
Barre d'état pour l'interface principale
"""

from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, 
                            QPushButton, QProgressBar, QGroupBox, QFrame)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from pathlib import Path

from config.settings import config

class StatusBarWidget(QFrame):
    """Widget de la barre d'état principale"""
    
    def __init__(self, server, main_window):
        super().__init__()
        self.server = server
        self.main_window = main_window
        
        self.setFrameStyle(QFrame.Box)
        self.setMinimumHeight(120)
        self.setMaximumHeight(140)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Configuration de l'interface de la barre d'état"""
        layout = QHBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Statut du serveur
        server_group = QGroupBox("Serveur")
        server_group.setMinimumWidth(120)
        server_layout = QVBoxLayout(server_group)
        server_layout.setSpacing(5)
        
        self.server_status_label = QLabel("● Arrêté")
        self.server_status_label.setStyleSheet("color: red; font-weight: bold; font-size: 12px;")
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
        
        self.start_server_btn = QPushButton("Démarrer Serveur")
        self.start_server_btn.clicked.connect(self.main_window.start_server)
        self.start_server_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        self.start_server_btn.setMinimumHeight(25)
        
        self.stop_server_btn = QPushButton("Arrêter Serveur")
        self.stop_server_btn.clicked.connect(self.main_window.stop_server)
        self.stop_server_btn.setStyleSheet("background-color: #d32f2f; color: white;")
        self.stop_server_btn.setMinimumHeight(25)
        self.stop_server_btn.setEnabled(False)
        
        self.start_job_btn = QPushButton("Nouveau Job")
        self.start_job_btn.clicked.connect(self.main_window.start_new_job)
        self.start_job_btn.setMinimumHeight(25)
        self.start_job_btn.setEnabled(False)
        
        controls_layout.addWidget(self.start_server_btn)
        controls_layout.addWidget(self.stop_server_btn)
        controls_layout.addWidget(self.start_job_btn)
        controls_layout.addStretch()
        
        # Ajout des groupes au layout
        layout.addWidget(server_group)
        layout.addWidget(clients_group)
        layout.addWidget(batches_group)
        layout.addWidget(job_group)
        layout.addWidget(controls_group)
        layout.addStretch()
    
    def update_status(self, stats):
        """Met à jour la barre de statut avec les statistiques"""
        # Statut serveur
        if self.server.running:
            self.server_status_label.setText("● En ligne")
            self.server_status_label.setStyleSheet("color: green; font-weight: bold; font-size: 12px;")
        else:
            self.server_status_label.setText("● Arrêté")
            self.server_status_label.setStyleSheet("color: red; font-weight: bold; font-size: 12px;")
        
        self.server_port_label.setText(f"Port: {config.PORT}")
        
        # Statistiques clients
        self.clients_count_label.setText(f"Connectés: {stats['clients']['online']}")
        self.clients_processing_label.setText(f"En traitement: {stats['clients']['processing']}")
        
        # Statistiques lots
        self.batches_pending_label.setText(f"En attente: {stats['batches']['pending']}")
        self.batches_completed_label.setText(f"Terminés: {stats['batches']['completed']}")
        
        # Job actuel
        if stats['current_job']:
            job_info = stats['current_job']
            self.current_job_label.setText(job_info['input_file'])
            self.job_progress.setValue(int(job_info['progress']))
        else:
            self.current_job_label.setText("Aucun")
            self.job_progress.setValue(0)
    
    def update_status_stopped(self):
        """Met à jour la barre de statut quand le serveur est arrêté"""
        self.server_status_label.setText("● Arrêté")
        self.server_status_label.setStyleSheet("color: red; font-weight: bold; font-size: 12px;")
        
        self.clients_count_label.setText("Connectés: 0")
        self.clients_processing_label.setText("En traitement: 0")
        self.batches_pending_label.setText("En attente: 0")
        self.batches_completed_label.setText("Terminés: 0")
        self.current_job_label.setText("Aucun")
        self.job_progress.setValue(0)
    
    def set_server_running(self, running):
        """Met à jour l'état des boutons selon l'état du serveur"""
        self.start_server_btn.setEnabled(not running)
        self.stop_server_btn.setEnabled(running)
        self.start_job_btn.setEnabled(running)