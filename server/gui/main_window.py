# server/gui/main_window.py - Corrections pour mise à jour interface

"""
Interface graphique pour le serveur d'upscaling distribué - CORRIGÉE
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
from utils.file_utils import format_duration
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
        # Timer principal - plus fréquent pour les mises à jour critiques
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_interface)
        self.update_timer.start(500)  # 500ms au lieu de 1000ms pour plus de réactivité
        
        # Timer pour les graphiques de performance
        self.performance_timer = QTimer()
        self.performance_timer.timeout.connect(self.update_performance_charts)
        self.performance_timer.start(5000)
        
        # Timer spécial pour les jobs/lots - mise à jour plus fréquente
        self.jobs_timer = QTimer()
        self.jobs_timer.timeout.connect(self.update_jobs_display)
        self.jobs_timer.start(1000)  # Chaque seconde pour les jobs
    
    def setup_connections(self):
        """Configure les connexions de signaux"""
        pass
    
    def update_interface(self):
        """Met à jour l'interface avec les données du serveur"""
        try:
            if self.server.running:
                stats = self.server.get_statistics()
                self.status_bar.update_status(stats)
                
                # Mise à jour de l'onglet actuel seulement
                current_tab_index = self.tabs_manager.currentIndex()
                if current_tab_index == 0:  # Vue d'ensemble
                    self.tabs_manager.overview_tab.update_tab(stats)
                elif current_tab_index == 1:  # Clients
                    self.tabs_manager.clients_tab.update_tab()
            else:
                # Serveur arrêté - mise à jour basique
                self.status_bar.update_status_stopped()
            
        except Exception as e:
            self.logger.error(f"Erreur mise à jour interface: {e}")
    
    def update_jobs_display(self):
        """Met à jour spécifiquement l'affichage des jobs et lots"""
        try:
            if not self.server.running:
                return
            
            # Mise à jour forcée de l'onglet Jobs & Lots s'il est visible
            current_tab_index = self.tabs_manager.currentIndex()
            if current_tab_index == 2:  # Jobs & Lots
                self.tabs_manager.jobs_tab.update_tab()
            
            # Force la mise à jour de la barre de statut pour les jobs
            if hasattr(self, 'status_bar'):
                stats = self.server.get_statistics()
                self.status_bar.update_status(stats)
                
        except Exception as e:
            self.logger.debug(f"Erreur mise à jour jobs: {e}")
    
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
        """Démarre un job de manière asynchrone - VERSION CORRIGÉE"""
        try:
            # Vérifier que le fichier vidéo existe
            if not os.path.exists(file_path):
                QMessageBox.critical(self, "Erreur", f"Le fichier vidéo n'existe pas:\n{file_path}")
                return
            
            # Créer le job via le processeur vidéo dans un thread
            def create_job_thread():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    try:
                        job = loop.run_until_complete(self.server.video_processor.create_job_from_video(file_path))
                        
                        if job:
                            # Démarrer l'extraction des frames
                            success = loop.run_until_complete(self.server.video_processor.extract_frames(job))
                            
                            if success:
                                # Ajouter le job au serveur et le marquer comme actuel
                                self.server.jobs[job.id] = job
                                self.server.current_job = job.id
                                
                                # Notification de succès dans le thread principal - CORRECTION
                                from PyQt5.QtCore import QMetaObject, Qt
                                QMetaObject.invokeMethod(self, "show_job_success", Qt.QueuedConnection,
                                                       Q_ARG(str, Path(file_path).name),
                                                       Q_ARG(str, Path(job.output_video_path).name),
                                                       Q_ARG(int, job.total_frames),
                                                       Q_ARG(int, len(job.batches)))
                            else:
                                QMetaObject.invokeMethod(self, "show_job_error", Qt.QueuedConnection,
                                                       Q_ARG(str, "Erreur lors de l'extraction des frames"))
                        else:
                            QMetaObject.invokeMethod(self, "show_job_error", Qt.QueuedConnection,
                                                   Q_ARG(str, "Impossible de créer le job à partir du fichier vidéo"))
                    finally:
                        loop.close()
                        
                except Exception as e:
                    self.logger.error(f"Erreur création job: {e}")
                    from PyQt5.QtCore import QMetaObject, Qt, Q_ARG
                    QMetaObject.invokeMethod(self, "show_job_error", Qt.QueuedConnection,
                                           Q_ARG(str, f"Erreur lors de la création du job:\n{str(e)}"))
            
            # Lancer dans un thread séparé
            thread = threading.Thread(target=create_job_thread, daemon=True)
            thread.start()
            
        except Exception as e:
            self.logger.error(f"Erreur start_job_async: {e}")
            QMessageBox.critical(self, "Erreur", f"Erreur lors de la création du job:\n{str(e)}")
    
    @pyqtSlot(str, str, int, int)
    def show_job_success(self, input_name, output_name, frames, batches):
        """Affiche le message de succès pour un job"""
        QMessageBox.information(self, "Succès", 
            f"Job créé avec succès!\n"
            f"Fichier d'entrée: {input_name}\n"
            f"Fichier de sortie: {output_name}\n"
            f"{frames} frames extraites\n"
            f"{batches} lots créés")
    
    @pyqtSlot(str)
    def show_job_error(self, error_message):
        """Affiche le message d'erreur pour un job"""
        QMessageBox.critical(self, "Erreur", error_message)
    
    @pyqtSlot(str, str, int, int)
    def show_job_success(self, input_name, output_name, frames, batches):
        """Affiche le message de succès pour un job"""
        QMessageBox.information(self, "Succès", 
            f"Job créé avec succès!\n"
            f"Fichier d'entrée: {input_name}\n"
            f"Fichier de sortie: {output_name}\n"
            f"{frames} frames extraites\n"
            f"{batches} lots créés")
    
    @pyqtSlot(str)
    def show_job_error(self, error_message):
        """Affiche le message d'erreur pour un job"""
        QMessageBox.critical(self, "Erreur", error_message)
    
    def closeEvent(self, event):
        """Gestionnaire de fermeture de l'application"""
        reply = QMessageBox.question(
            self, "Confirmation", "Êtes-vous sûr de vouloir quitter?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Arrêter les timers
            if hasattr(self, 'update_timer'):
                self.update_timer.stop()
            if hasattr(self, 'performance_timer'):
                self.performance_timer.stop()
            if hasattr(self, 'jobs_timer'):
                self.jobs_timer.stop()
            
            performance_monitor.stop_monitoring()
            
            if self.server.running:
                try:
                    self.server.stop_sync()
                except Exception as e:
                    self.logger.error(f"Erreur arrêt serveur lors fermeture: {e}")
            
            event.accept()
        else:
            event.ignore()