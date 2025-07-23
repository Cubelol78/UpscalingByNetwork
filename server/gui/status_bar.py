"""
Barre d'état pour l'interface principale avec logique simplifiée des boutons - VERSION CORRIGÉE
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
        self.update_button_states()  # État initial
    
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
        
        # Job actuel - VERSION AMÉLIORÉE
        job_group = QGroupBox("Job Actuel")
        job_group.setMinimumWidth(280)
        job_layout = QVBoxLayout(job_group)
        job_layout.setSpacing(5)
        
        self.current_job_label = QLabel("Aucun")
        self.current_job_label.setStyleSheet("font-size: 11px; font-weight: bold;")
        self.current_job_label.setWordWrap(True)
        
        # Barre de progression avec pourcentage
        progress_layout = QHBoxLayout()
        self.job_progress = QProgressBar()
        self.job_progress.setMinimumHeight(20)
        self.job_progress.setRange(0, 100)
        self.job_progress.setValue(0)
        self.job_progress.setFormat("%p%")  # Affiche le pourcentage
        
        # Label avec détails de progression
        self.progress_details_label = QLabel("0/0 lots")
        self.progress_details_label.setStyleSheet("font-size: 10px; color: #888;")
        
        progress_layout.addWidget(self.job_progress, 1)
        progress_layout.addWidget(self.progress_details_label)
        
        job_layout.addWidget(self.current_job_label)
        job_layout.addLayout(progress_layout)
        job_layout.addStretch()
        
        # Contrôles serveur - LOGIQUE SIMPLIFIÉE
        controls_group = QGroupBox("Contrôles Serveur")
        controls_group.setMinimumWidth(160)
        controls_layout = QVBoxLayout(controls_group)
        controls_layout.setSpacing(8)
        
        # Un seul bouton qui change selon l'état
        self.server_control_btn = QPushButton("Démarrer Serveur")
        self.server_control_btn.clicked.connect(self.toggle_server)
        self.server_control_btn.setMinimumHeight(35)
        self.server_control_btn.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                border-radius: 5px;
                padding: 8px;
            }
        """)
        
        self.start_job_btn = QPushButton("Nouveau Job")
        self.start_job_btn.clicked.connect(self.main_window.start_new_job)
        self.start_job_btn.setMinimumHeight(30)
        self.start_job_btn.setEnabled(False)
        
        # Statut processeur natif
        self.native_status_label = QLabel("Processeur: Vérification...")
        self.native_status_label.setStyleSheet("font-size: 10px; color: #888;")
        self.native_status_label.setWordWrap(True)
        
        controls_layout.addWidget(self.server_control_btn)
        controls_layout.addWidget(self.start_job_btn)
        controls_layout.addWidget(self.native_status_label)
        controls_layout.addStretch()
        
        # Ajout des groupes au layout
        layout.addWidget(server_group)
        layout.addWidget(clients_group)
        layout.addWidget(batches_group)
        layout.addWidget(job_group)
        layout.addWidget(controls_group)
        layout.addStretch()
    
    def toggle_server(self):
        """Bascule l'état du serveur (démarrer/arrêter)"""
        if self.server.running:
            self.main_window.stop_server()
        else:
            self.main_window.start_server()
    
    def update_button_states(self):
        """Met à jour l'état et l'apparence des boutons selon l'état du serveur"""
        if self.server.running:
            # Serveur en cours - Bouton d'arrêt
            self.server_control_btn.setText("Arrêter Serveur")
            self.server_control_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f44336;
                    color: white;
                    font-weight: bold;
                    border-radius: 5px;
                    padding: 8px;
                }
                QPushButton:hover {
                    background-color: #d32f2f;
                }
            """)
            self.start_job_btn.setEnabled(True)
            
            # Statut serveur
            self.server_status_label.setText("● En ligne")
            self.server_status_label.setStyleSheet("color: #4CAF50; font-weight: bold; font-size: 12px;")
            
        else:
            # Serveur arrêté - Bouton de démarrage
            self.server_control_btn.setText("Démarrer Serveur")
            self.server_control_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    font-weight: bold;
                    border-radius: 5px;
                    padding: 8px;
                }
                QPushButton:hover {
                    background-color: #388E3C;
                }
            """)
            self.start_job_btn.setEnabled(False)
            
            # Statut serveur
            self.server_status_label.setText("● Arrêté")
            self.server_status_label.setStyleSheet("color: #f44336; font-weight: bold; font-size: 12px;")
    
    def update_status(self, stats):
        """Met à jour la barre de statut avec les statistiques - VERSION AMÉLIORÉE"""
        # Mise à jour des boutons
        self.update_button_states()
        
        # Mise à jour du port
        self.server_port_label.setText(f"Port: {config.PORT}")
        
        # Statistiques clients
        self.clients_count_label.setText(f"Connectés: {stats['clients']['online']}")
        self.clients_processing_label.setText(f"En traitement: {stats['clients']['processing']}")
        
        # Statistiques lots
        self.batches_pending_label.setText(f"En attente: {stats['batches']['pending']}")
        self.batches_completed_label.setText(f"Terminés: {stats['batches']['completed']}")
        
        # Job actuel - LOGIQUE AMÉLIORÉE
        current_job_data = stats.get('current_job', {})
        
        if current_job_data and current_job_data.get('id'):
            # Il y a un job actuel
            job_name = current_job_data.get('input_file', 'Job en cours')
            job_status = current_job_data.get('status', 'unknown')
            progress = current_job_data.get('progress', 0)
            
            # Mise à jour du nom avec statut
            status_emoji = {
                'extracting': '📤',
                'processing': '⚙️',
                'assembling': '🎬',
                'completed': '✅',
                'failed': '❌'
            }.get(job_status, '🔄')
            
            self.current_job_label.setText(f"{status_emoji} {job_name}")
            
            # Mise à jour de la barre de progression
            self.job_progress.setValue(int(progress))
            
            # Détails de progression avec lots
            if 'total_batches' in current_job_data and 'completed_batches' in current_job_data:
                total_batches = current_job_data['total_batches']
                completed_batches = current_job_data['completed_batches']
                self.progress_details_label.setText(f"{completed_batches}/{total_batches} lots")
            else:
                self.progress_details_label.setText(f"{progress:.1f}%")
            
            # Couleur de la barre selon le statut
            if job_status == 'completed':
                self.job_progress.setStyleSheet("QProgressBar::chunk { background-color: #4CAF50; }")
            elif job_status == 'failed':
                self.job_progress.setStyleSheet("QProgressBar::chunk { background-color: #f44336; }")
            elif job_status == 'processing':
                self.job_progress.setStyleSheet("QProgressBar::chunk { background-color: #2196F3; }")
            else:
                self.job_progress.setStyleSheet("QProgressBar::chunk { background-color: #FF9800; }")
        else:
            # Aucun job actuel
            self.current_job_label.setText("Aucun job actif")
            self.job_progress.setValue(0)
            self.progress_details_label.setText("0/0 lots")
            self.job_progress.setStyleSheet("")  # Style par défaut
        
        # Statut du processeur natif
        native_stats = stats.get('native_processor', {})
        if native_stats:
            if native_stats.get('available', False):
                if native_stats.get('processing', False):
                    current_batch = native_stats.get('current_batch', '')
                    batch_info = f" (lot: {current_batch[:8]})" if current_batch else ""
                    self.native_status_label.setText(f"🔄 Traitement natif actif{batch_info}")
                    self.native_status_label.setStyleSheet("font-size: 10px; color: #4CAF50; font-weight: bold;")
                else:
                    self.native_status_label.setText("✅ Processeur natif prêt")
                    self.native_status_label.setStyleSheet("font-size: 10px; color: #2196F3;")
            else:
                executable_path = native_stats.get('executable_path', '')
                if executable_path:
                    self.native_status_label.setText(f"❌ Real-ESRGAN: {Path(executable_path).name}")
                else:
                    self.native_status_label.setText("❌ Real-ESRGAN non disponible")
                self.native_status_label.setStyleSheet("font-size: 10px; color: #FF9800;")
    
    def update_status_stopped(self):
        """Met à jour la barre de statut quand le serveur est arrêté"""
        # Mise à jour des boutons
        self.update_button_states()
        
        # Remise à zéro des statistiques
        self.clients_count_label.setText("Connectés: 0")
        self.clients_processing_label.setText("En traitement: 0")
        self.batches_pending_label.setText("En attente: 0")
        self.batches_completed_label.setText("Terminés: 0")
        self.current_job_label.setText("Aucun job actif")
        self.job_progress.setValue(0)
        self.progress_details_label.setText("0/0 lots")
        self.job_progress.setStyleSheet("")  # Style par défaut