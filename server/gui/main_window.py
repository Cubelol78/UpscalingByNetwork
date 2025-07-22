"""
Interface graphique pour le serveur d'upscaling distribué - Classe principale
"""

import sys
import os
import threading
import asyncio
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QTabWidget, QLabel, QPushButton, QTableWidget, 
                            QTableWidgetItem, QProgressBar, QPlainTextEdit, QGroupBox,
                            QGridLayout, QFileDialog, QMessageBox, QSplitter,
                            QFrame, QScrollArea, QComboBox, QSpinBox, QCheckBox,
                            QSlider, QApplication, QHeaderView, QLineEdit)
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QThread, pyqtSlot
from PyQt5.QtGui import QFont, QPixmap, QIcon, QPalette, QColor
import pyqtgraph as pg
from datetime import datetime
from pathlib import Path
import json

from config.settings import config
from utils.logger import get_logger
from utils.file_utils import format_file_size, format_duration
from utils.performance_monitor import performance_monitor

# Import des modules de l'interface
from gui.status_bar import StatusBarWidget
from gui.tabs_manager import TabsManager
from gui.server_control import ServerControlMixin
from gui.configuration import ConfigurationMixin

class MainWindow(QMainWindow, ServerControlMixin, ConfigurationMixin):
    """Fenêtre principale du serveur"""
    
    def __init__(self, server):
        super().__init__()
        self.server = server
        self.logger = get_logger(__name__)
        self.server_thread = None
        
        # Configuration de la fenêtre
        self.setWindowTitle("Distributed Upscaling Server v1.0")
        self.setGeometry(100, 100, 1400, 900)
        self.setMinimumSize(1200, 800)
        
        # Initialisation de l'interface
        self.setup_ui()
        self.setup_timers()
        self.setup_connections()
        
        # Chargement de la configuration sauvegardée dans l'interface
        # (après que tous les widgets soient créés)
        self.load_saved_configuration()
        
        # Démarrage du monitoring
        performance_monitor.start_monitoring()
        
        self.logger.info("Interface graphique initialisée avec configuration chargée")
    
    def setup_ui(self):
        """Configuration de l'interface utilisateur"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(15)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Barre d'état en haut
        self.status_bar = StatusBarWidget(self.server, self)
        layout.addWidget(self.status_bar)
        
        # Gestionnaire d'onglets
        self.tabs_manager = TabsManager(self.server, self)
        layout.addWidget(self.tabs_manager, 1)
    
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
        pass
    
    def update_interface(self):
        """Met à jour l'interface avec les données du serveur"""
        try:
            if self.server.running:
                stats = self.server.get_statistics()
                self.status_bar.update_status(stats)
                self.tabs_manager.update_current_tab(stats)
            else:
                # Serveur arrêté - mise à jour basique
                self.status_bar.update_status_stopped()
            
        except Exception as e:
            self.logger.error(f"Erreur mise à jour interface: {e}")
    
    def update_performance_charts(self):
        """Met à jour les graphiques de performance"""
        try:
            if not self.server.running:
                return
                
            performance_monitor.add_server_metrics(self.server)
            self.tabs_manager.update_performance_charts()
            
        except Exception as e:
            self.logger.error(f"Erreur mise à jour graphiques performance: {e}")
    
    def start_new_job(self):
        """Démarre un nouveau job"""
        if not self.server.running:
            QMessageBox.warning(self, "Erreur", "Le serveur doit être démarré pour créer un job")
            return
            
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Sélectionner une vidéo", "",
            "Vidéos (*.mp4 *.avi *.mov *.mkv);;Tous les fichiers (*)"
        )
        
        if file_path:
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