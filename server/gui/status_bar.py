"""
Barre d'état pour l'interface principale avec logique simplifiée des boutons
"""

from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                            QPushButton, QProgressBar, QGroupBox, QFrame)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from pathlib import Path

from utils.config import config
from gui.widgets.loading_widget import InlineLoadingIndicator
from gui.themes import get_button_style, get_status_label_style, Colors

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
        self.server_status_label.setStyleSheet(f"{get_status_label_style('offline')} font-size: 12px;")
        self.server_port_label = QLabel(f"Port: {config.PORT}")
        self.server_port_label.setStyleSheet(f"font-size: 11px; color: {Colors.TEXT_PRIMARY};")
        
        server_layout.addWidget(self.server_status_label)
        server_layout.addWidget(self.server_port_label)
        server_layout.addStretch()
        
        # Statistiques clients
        clients_group = QGroupBox("Clients")
        clients_group.setMinimumWidth(140)
        clients_layout = QVBoxLayout(clients_group)
        clients_layout.setSpacing(5)
        
        self.clients_count_label = QLabel("Connectés: 0")
        self.clients_count_label.setStyleSheet(f"font-size: 11px; color: {Colors.TEXT_PRIMARY};")
        self.clients_processing_label = QLabel("En traitement: 0")
        self.clients_processing_label.setStyleSheet(f"font-size: 11px; color: {Colors.TEXT_PRIMARY};")
        
        clients_layout.addWidget(self.clients_count_label)
        clients_layout.addWidget(self.clients_processing_label)
        clients_layout.addStretch()
        
        # Statistiques lots
        batches_group = QGroupBox("Lots")
        batches_group.setMinimumWidth(140)
        batches_layout = QVBoxLayout(batches_group)
        batches_layout.setSpacing(5)
        
        self.batches_pending_label = QLabel("En attente: 0")
        self.batches_pending_label.setStyleSheet(f"font-size: 11px; color: {Colors.TEXT_PRIMARY};")
        self.batches_completed_label = QLabel("Terminés: 0")
        self.batches_completed_label.setStyleSheet(f"font-size: 11px; color: {Colors.TEXT_PRIMARY};")
        
        batches_layout.addWidget(self.batches_pending_label)
        batches_layout.addWidget(self.batches_completed_label)
        batches_layout.addStretch()
        
        # Job actuel
        job_group = QGroupBox("Job Actuel")
        job_group.setMinimumWidth(250)
        job_layout = QVBoxLayout(job_group)
        job_layout.setSpacing(5)
        
        self.current_job_label = QLabel("Aucun")
        self.current_job_label.setStyleSheet("font-size: 11px; color: #e0e0e0;")
        self.current_job_label.setWordWrap(True)
        self.job_progress = QProgressBar()
        self.job_progress.setMinimumHeight(20)
        
        job_layout.addWidget(self.current_job_label)
        job_layout.addWidget(self.job_progress)
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
                background-color: #0d7377;
                color: white;
                font-weight: bold;
                border-radius: 5px;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #14a085;
            }
        """)
        
        self.start_job_btn = QPushButton("Nouveau Job")
        self.start_job_btn.clicked.connect(self.main_window.start_new_job)
        self.start_job_btn.setMinimumHeight(30)
        self.start_job_btn.setEnabled(False)
        
        # Statut processeur natif
        self.native_status_label = QLabel("Processeur: Vérification...")
        self.native_status_label.setStyleSheet("font-size: 10px; color: #888888;")
        self.native_status_label.setWordWrap(True)

        # Indicateur de chargement pour les opérations
        self.operation_indicator = InlineLoadingIndicator(size=20)
        self.operation_indicator.hide()

        controls_layout.addWidget(self.server_control_btn)
        controls_layout.addWidget(self.start_job_btn)
        controls_layout.addWidget(self.operation_indicator)
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
        """Met à jour la barre de statut avec les statistiques"""
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
        
        # Job actuel
        if stats['current_job']:
            job_info = stats['current_job']
            self.current_job_label.setText(job_info['input_file'])
            self.job_progress.setValue(int(job_info['progress']))
        else:
            self.current_job_label.setText("Aucun")
            self.job_progress.setValue(0)
        
        # Statut du processeur natif
        if 'native_processor' in stats:
            native = stats['native_processor']
            if native['available']:
                if native['processing']:
                    batch_info = f" (lot: {native['current_batch'][:8]})" if native['current_batch'] else ""
                    self.native_status_label.setText(f"🔄 Traitement natif actif{batch_info}")
                    self.native_status_label.setStyleSheet("font-size: 10px; color: #4CAF50; font-weight: bold;")
                else:
                    self.native_status_label.setText("✅ Processeur natif prêt")
                    self.native_status_label.setStyleSheet("font-size: 10px; color: #2196F3;")
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
        self.current_job_label.setText("Aucun")
        self.job_progress.setValue(0)

    def show_operation_status(self, message: str, operation_type: str = "generic"):
        """Affiche un indicateur de chargement pour une opération en cours"""
        # Désactiver les boutons pendant l'opération
        self.server_control_btn.setEnabled(False)
        self.start_job_btn.setEnabled(False)

        # Afficher l'indicateur avec le message
        self.operation_indicator.start(message)

        # Mettre à jour le statut selon le type d'opération
        if operation_type == "starting":
            self.server_status_label.setText("● Démarrage...")
            self.server_status_label.setStyleSheet("color: #FFA726; font-weight: bold; font-size: 12px;")
        elif operation_type == "stopping":
            self.server_status_label.setText("● Arrêt...")
            self.server_status_label.setStyleSheet("color: #FFA726; font-weight: bold; font-size: 12px;")

    def hide_operation_status(self):
        """Masque l'indicateur de chargement"""
        # Arrêter l'indicateur
        self.operation_indicator.stop()

        # Réactiver les boutons
        self.server_control_btn.setEnabled(True)
        # Le bouton start_job sera réactivé par update_button_states si le serveur est en cours