# client/windows/gui/main_window.py
"""
Fenêtre principale du client Windows d'upscaling distribué
"""

import sys
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QProgressBar,
    QGroupBox, QTabWidget, QStatusBar, QMenuBar, QAction,
    QSystemTrayIcon, QMenu, QMessageBox, QSpinBox, QCheckBox,
    QComboBox, QFileDialog, QSplitter, QFrame
)
from PyQt5.QtCore import (
    QTimer, QThread, pyqtSignal, QSettings, Qt, QSize
)
from PyQt5.QtGui import QIcon, QFont, QPixmap, QPalette

class ConnectionTab(QWidget):
    """Onglet de gestion de la connexion au serveur"""
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Configuration serveur
        server_group = QGroupBox("Configuration du serveur")
        server_layout = QGridLayout()
        
        server_layout.addWidget(QLabel("Adresse du serveur:"), 0, 0)
        self.server_host = QLineEdit("localhost")
        server_layout.addWidget(self.server_host, 0, 1)
        
        server_layout.addWidget(QLabel("Port:"), 1, 0)
        self.server_port = QSpinBox()
        self.server_port.setRange(1024, 65535)
        self.server_port.setValue(8765)
        server_layout.addWidget(self.server_port, 1, 1)
        
        # Boutons de connexion
        self.connect_btn = QPushButton("Se connecter")
        self.connect_btn.clicked.connect(self.toggle_connection)
        server_layout.addWidget(self.connect_btn, 2, 0, 1, 2)
        
        server_group.setLayout(server_layout)
        layout.addWidget(server_group)
        
        # Statut de connexion
        status_group = QGroupBox("Statut de connexion")
        status_layout = QVBoxLayout()
        
        self.connection_status = QLabel("Non connecté")
        self.connection_status.setStyleSheet("color: red; font-weight: bold;")
        status_layout.addWidget(self.connection_status)
        
        self.server_info = QTextEdit()
        self.server_info.setMaximumHeight(100)
        self.server_info.setReadOnly(True)
        status_layout.addWidget(self.server_info)
        
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def toggle_connection(self):
        """Gère la connexion/déconnexion au serveur"""
        if hasattr(self.main_window, 'client') and self.main_window.client:
            if self.main_window.client.connected:
                self.main_window.disconnect_from_server()
            else:
                host = self.server_host.text().strip()
                port = self.server_port.value()
                self.main_window.connect_to_server(host, port)
    
    def update_connection_status(self, connected: bool, info: str = ""):
        """Met à jour le statut de connexion"""
        if connected:
            self.connection_status.setText("Connecté")
            self.connection_status.setStyleSheet("color: green; font-weight: bold;")
            self.connect_btn.setText("Se déconnecter")
        else:
            self.connection_status.setText("Non connecté")
            self.connection_status.setStyleSheet("color: red; font-weight: bold;")
            self.connect_btn.setText("Se connecter")
        
        if info:
            self.server_info.setText(info)

class ProcessingTab(QWidget):
    """Onglet de traitement et de suivi des tâches"""
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Informations de traitement
        processing_group = QGroupBox("Traitement en cours")
        processing_layout = QGridLayout()
        
        processing_layout.addWidget(QLabel("Lot actuel:"), 0, 0)
        self.current_batch = QLabel("Aucun")
        processing_layout.addWidget(self.current_batch, 0, 1)
        
        processing_layout.addWidget(QLabel("Fichier vidéo:"), 1, 0)
        self.current_video = QLabel("Aucun")
        processing_layout.addWidget(self.current_video, 1, 1)
        
        processing_layout.addWidget(QLabel("Progression:"), 2, 0)
        self.progress_bar = QProgressBar()
        processing_layout.addWidget(self.progress_bar, 2, 1)
        
        processing_group.setLayout(processing_layout)
        layout.addWidget(processing_group)
        
        # Statistiques
        stats_group = QGroupBox("Statistiques")
        stats_layout = QGridLayout()
        
        stats_layout.addWidget(QLabel("Lots traités:"), 0, 0)
        self.batches_processed = QLabel("0")
        stats_layout.addWidget(self.batches_processed, 0, 1)
        
        stats_layout.addWidget(QLabel("Images traitées:"), 1, 0)
        self.images_processed = QLabel("0")
        stats_layout.addWidget(self.images_processed, 1, 1)
        
        stats_layout.addWidget(QLabel("Temps de traitement:"), 2, 0)
        self.processing_time = QLabel("0s")
        stats_layout.addWidget(self.processing_time, 2, 1)
        
        stats_layout.addWidget(QLabel("FPS moyen:"), 3, 0)
        self.average_fps = QLabel("0")
        stats_layout.addWidget(self.average_fps, 3, 1)
        
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)
        
        # Contrôles
        controls_group = QGroupBox("Contrôles")
        controls_layout = QHBoxLayout()
        
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.clicked.connect(self.toggle_processing)
        controls_layout.addWidget(self.pause_btn)
        
        self.reset_stats_btn = QPushButton("Reset stats")
        self.reset_stats_btn.clicked.connect(self.reset_statistics)
        controls_layout.addWidget(self.reset_stats_btn)
        
        controls_group.setLayout(controls_layout)
        layout.addWidget(controls_group)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def toggle_processing(self):
        """Gère la pause/reprise du traitement"""
        # TODO: Implémenter la pause/reprise
        pass
    
    def reset_statistics(self):
        """Remet à zéro les statistiques"""
        self.batches_processed.setText("0")
        self.images_processed.setText("0")
        self.processing_time.setText("0s")
        self.average_fps.setText("0")
    
    def update_processing_info(self, batch_id: str, video_name: str, progress: int):
        """Met à jour les informations de traitement"""
        self.current_batch.setText(batch_id if batch_id else "Aucun")
        self.current_video.setText(video_name if video_name else "Aucun")
        self.progress_bar.setValue(progress)
    
    def update_statistics(self, stats: Dict[str, Any]):
        """Met à jour les statistiques"""
        self.batches_processed.setText(str(stats.get('batches_processed', 0)))
        self.images_processed.setText(str(stats.get('images_processed', 0)))
        self.processing_time.setText(f"{stats.get('processing_time', 0):.1f}s")
        self.average_fps.setText(f"{stats.get('average_fps', 0):.2f}")

class ConfigTab(QWidget):
    """Onglet de configuration du client"""
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Configuration matérielle
        hardware_group = QGroupBox("Configuration matérielle")
        hardware_layout = QGridLayout()
        
        hardware_layout.addWidget(QLabel("Utilisation GPU:"), 0, 0)
        self.gpu_enabled = QCheckBox("Activer le GPU")
        self.gpu_enabled.setChecked(True)
        hardware_layout.addWidget(self.gpu_enabled, 0, 1)
        
        hardware_layout.addWidget(QLabel("Nombre de threads:"), 1, 0)
        self.thread_count = QSpinBox()
        self.thread_count.setRange(1, 16)
        self.thread_count.setValue(4)
        hardware_layout.addWidget(self.thread_count, 1, 1)
        
        hardware_layout.addWidget(QLabel("Mémoire GPU (MB):"), 2, 0)
        self.gpu_memory = QSpinBox()
        self.gpu_memory.setRange(512, 16384)
        self.gpu_memory.setValue(4096)
        hardware_layout.addWidget(self.gpu_memory, 2, 1)
        
        hardware_group.setLayout(hardware_layout)
        layout.addWidget(hardware_group)
        
        # Configuration de traitement
        processing_group = QGroupBox("Configuration de traitement")
        processing_layout = QGridLayout()
        
        processing_layout.addWidget(QLabel("Modèle Real-ESRGAN:"), 0, 0)
        self.realesrgan_model = QComboBox()
        self.realesrgan_model.addItems([
            "RealESRGAN_x4plus",
            "RealESRNet_x4plus",
            "RealESRGAN_x4plus_anime_6B",
            "RealESRGAN_x2plus"
        ])
        processing_layout.addWidget(self.realesrgan_model, 0, 1)
        
        processing_layout.addWidget(QLabel("Format de sortie:"), 1, 0)
        self.output_format = QComboBox()
        self.output_format.addItems(["png", "jpg", "webp"])
        processing_layout.addWidget(self.output_format, 1, 1)
        
        processing_group.setLayout(processing_layout)
        layout.addWidget(processing_group)
        
        # Boutons de configuration
        buttons_layout = QHBoxLayout()
        
        self.save_config_btn = QPushButton("Sauvegarder")
        self.save_config_btn.clicked.connect(self.save_configuration)
        buttons_layout.addWidget(self.save_config_btn)
        
        self.load_config_btn = QPushButton("Charger")
        self.load_config_btn.clicked.connect(self.load_configuration)
        buttons_layout.addWidget(self.load_config_btn)
        
        self.test_realesrgan_btn = QPushButton("Tester Real-ESRGAN")
        self.test_realesrgan_btn.clicked.connect(self.test_realesrgan)
        buttons_layout.addWidget(self.test_realesrgan_btn)
        
        layout.addLayout(buttons_layout)
        layout.addStretch()
        self.setLayout(layout)
    
    def save_configuration(self):
        """Sauvegarde la configuration"""
        # TODO: Implémenter la sauvegarde
        QMessageBox.information(self, "Configuration", "Configuration sauvegardée")
    
    def load_configuration(self):
        """Charge la configuration"""
        # TODO: Implémenter le chargement
        QMessageBox.information(self, "Configuration", "Configuration chargée")
    
    def test_realesrgan(self):
        """Test la disponibilité de Real-ESRGAN"""
        # TODO: Implémenter le test
        QMessageBox.information(self, "Test Real-ESRGAN", "Test en cours...")

class LogTab(QWidget):
    """Onglet d'affichage des logs"""
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Zone de logs
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_text)
        
        # Contrôles de logs
        controls_layout = QHBoxLayout()
        
        self.clear_logs_btn = QPushButton("Effacer")
        self.clear_logs_btn.clicked.connect(self.clear_logs)
        controls_layout.addWidget(self.clear_logs_btn)
        
        self.save_logs_btn = QPushButton("Sauvegarder")
        self.save_logs_btn.clicked.connect(self.save_logs)
        controls_layout.addWidget(self.save_logs_btn)
        
        self.auto_scroll = QCheckBox("Auto-scroll")
        self.auto_scroll.setChecked(True)
        controls_layout.addWidget(self.auto_scroll)
        
        controls_layout.addStretch()
        layout.addLayout(controls_layout)
        
        self.setLayout(layout)
    
    def add_log(self, message: str):
        """Ajoute un message de log"""
        self.log_text.append(message)
        if self.auto_scroll.isChecked():
            self.log_text.moveCursor(self.log_text.textCursor().End)
    
    def clear_logs(self):
        """Efface tous les logs"""
        self.log_text.clear()
    
    def save_logs(self):
        """Sauvegarde les logs dans un fichier"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Sauvegarder les logs", "client_logs.txt", "Text Files (*.txt)"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.toPlainText())
                QMessageBox.information(self, "Logs", f"Logs sauvegardés dans {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de sauvegarder: {e}")

class MainWindow(QMainWindow):
    """Fenêtre principale du client d'upscaling distribué"""
    
    def __init__(self):
        super().__init__()
        self.client = None
        self.settings = QSettings("UpscalingByNetwork", "Client")
        self.system_tray = None
        
        self.setup_ui()
        self.setup_system_tray()
        self.setup_timers()
        self.load_settings()
        
        # Configuration du logging GUI
        self.setup_logging_handler()
    
    def setup_ui(self):
        """Initialise l'interface utilisateur"""
        self.setWindowTitle("Client d'Upscaling Distribué")
        self.setMinimumSize(800, 600)
        self.resize(1000, 700)
        
        # Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principal
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        # Titre et logo
        header_layout = QHBoxLayout()
        title_label = QLabel("Client d'Upscaling Distribué")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        # Indicateur de statut
        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("color: red; font-size: 20px;")
        header_layout.addWidget(self.status_indicator)
        
        main_layout.addLayout(header_layout)
        
        # Onglets
        self.tab_widget = QTabWidget()
        
        # Création des onglets
        self.connection_tab = ConnectionTab(self)
        self.processing_tab = ProcessingTab(self)
        self.config_tab = ConfigTab(self)
        self.log_tab = LogTab(self)
        
        self.tab_widget.addTab(self.connection_tab, "Connexion")
        self.tab_widget.addTab(self.processing_tab, "Traitement")
        self.tab_widget.addTab(self.config_tab, "Configuration")
        self.tab_widget.addTab(self.log_tab, "Logs")
        
        main_layout.addWidget(self.tab_widget)
        
        # Barre de statut
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Client démarré - Non connecté")
        
        # Menu
        self.setup_menu()
    
    def setup_menu(self):
        """Configure la barre de menu"""
        menubar = self.menuBar()
        
        # Menu Fichier
        file_menu = menubar.addMenu('Fichier')
        
        connect_action = QAction('Se connecter', self)
        connect_action.triggered.connect(self.connection_tab.toggle_connection)
        file_menu.addAction(connect_action)
        
        file_menu.addSeparator()
        
        quit_action = QAction('Quitter', self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)
        
        # Menu Options
        options_menu = menubar.addMenu('Options')
        
        settings_action = QAction('Paramètres', self)
        settings_action.triggered.connect(lambda: self.tab_widget.setCurrentWidget(self.config_tab))
        options_menu.addAction(settings_action)
        
        # Menu Aide
        help_menu = menubar.addMenu('Aide')
        
        about_action = QAction('À propos', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def setup_system_tray(self):
        """Configure l'icône de la barre système"""
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.system_tray = QSystemTrayIcon(self)
            
            # Menu contextuel
            tray_menu = QMenu()
            
            show_action = tray_menu.addAction("Afficher")
            show_action.triggered.connect(self.show)
            
            tray_menu.addSeparator()
            
            quit_action = tray_menu.addAction("Quitter")
            quit_action.triggered.connect(self.close)
            
            self.system_tray.setContextMenu(tray_menu)
            self.system_tray.activated.connect(self.on_tray_activated)
            
            # Icône par défaut (vous pouvez ajouter une vraie icône)
            self.system_tray.setToolTip("Client d'Upscaling Distribué")
            self.system_tray.show()
    
    def setup_timers(self):
        """Configure les timers pour les mises à jour"""
        # Timer pour les mises à jour de statut
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(1000)  # Mise à jour chaque seconde
        
        # Timer pour les statistiques
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.update_statistics)
        self.stats_timer.start(5000)  # Mise à jour toutes les 5 secondes
    
    def setup_logging_handler(self):
        """Configure le gestionnaire de logs pour l'interface"""
        class GuiLogHandler(logging.Handler):
            def __init__(self, log_widget):
                super().__init__()
                self.log_widget = log_widget
            
            def emit(self, record):
                msg = self.format(record)
                self.log_widget.add_log(msg)
        
        # Ajout du handler GUI au logger racine
        gui_handler = GuiLogHandler(self.log_tab)
        gui_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logging.getLogger().addHandler(gui_handler)
    
    def connect_to_server(self, host: str, port: int):
        """Connecte le client au serveur"""
        try:
            # TODO: Implémenter la connexion réelle
            self.log_tab.add_log(f"Tentative de connexion à {host}:{port}")
            
            # Simulation de connexion réussie
            self.connection_tab.update_connection_status(True, f"Connecté à {host}:{port}")
            self.status_indicator.setStyleSheet("color: green; font-size: 20px;")
            self.status_bar.showMessage(f"Connecté à {host}:{port}")
            
        except Exception as e:
            self.log_tab.add_log(f"Erreur de connexion: {e}")
            QMessageBox.critical(self, "Erreur de connexion", str(e))
    
    def disconnect_from_server(self):
        """Déconnecte le client du serveur"""
        try:
            # TODO: Implémenter la déconnexion réelle
            self.log_tab.add_log("Déconnexion du serveur")
            
            self.connection_tab.update_connection_status(False, "Déconnecté")
            self.status_indicator.setStyleSheet("color: red; font-size: 20px;")
            self.status_bar.showMessage("Non connecté")
            
        except Exception as e:
            self.log_tab.add_log(f"Erreur de déconnexion: {e}")
    
    def update_status(self):
        """Met à jour le statut de l'application"""
        # TODO: Implémenter la mise à jour du statut réel
        pass
    
    def update_statistics(self):
        """Met à jour les statistiques"""
        # TODO: Implémenter la mise à jour des statistiques réelles
        pass
    
    def on_tray_activated(self, reason):
        """Gère les clics sur l'icône de la barre système"""
        if reason == QSystemTrayIcon.DoubleClick:
            if self.isVisible():
                self.hide()
            else:
                self.show()
                self.raise_()
                self.activateWindow()
    
    def show_about(self):
        """Affiche la boîte de dialogue À propos"""
        QMessageBox.about(self, "À propos", 
            "Client d'Upscaling Distribué\n\n"
            "Version 1.0\n"
            "Système de traitement d'images distribué\n"
            "utilisant Real-ESRGAN pour l'upscaling.")
    
    def load_settings(self):
        """Charge les paramètres sauvegardés"""
        try:
            # Géométrie de la fenêtre
            geometry = self.settings.value("geometry")
            if geometry:
                self.restoreGeometry(geometry)
            
            # Configuration de connexion
            host = self.settings.value("server/host", "localhost")
            port = self.settings.value("server/port", 8765, type=int)
            
            self.connection_tab.server_host.setText(host)
            self.connection_tab.server_port.setValue(port)
            
            # Configuration matérielle
            gpu_enabled = self.settings.value("hardware/gpu_enabled", True, type=bool)
            thread_count = self.settings.value("hardware/thread_count", 4, type=int)
            gpu_memory = self.settings.value("hardware/gpu_memory", 4096, type=int)
            
            self.config_tab.gpu_enabled.setChecked(gpu_enabled)
            self.config_tab.thread_count.setValue(thread_count)
            self.config_tab.gpu_memory.setValue(gpu_memory)
            
            # Configuration de traitement
            model = self.settings.value("processing/realesrgan_model", "RealESRGAN_x4plus")
            output_format = self.settings.value("processing/output_format", "png")
            
            model_index = self.config_tab.realesrgan_model.findText(model)
            if model_index >= 0:
                self.config_tab.realesrgan_model.setCurrentIndex(model_index)
            
            format_index = self.config_tab.output_format.findText(output_format)
            if format_index >= 0:
                self.config_tab.output_format.setCurrentIndex(format_index)
                
        except Exception as e:
            self.log_tab.add_log(f"Erreur lors du chargement des paramètres: {e}")
    
    def save_settings(self):
        """Sauvegarde les paramètres actuels"""
        try:
            # Géométrie de la fenêtre
            self.settings.setValue("geometry", self.saveGeometry())
            
            # Configuration de connexion
            self.settings.setValue("server/host", self.connection_tab.server_host.text())
            self.settings.setValue("server/port", self.connection_tab.server_port.value())
            
            # Configuration matérielle
            self.settings.setValue("hardware/gpu_enabled", self.config_tab.gpu_enabled.isChecked())
            self.settings.setValue("hardware/thread_count", self.config_tab.thread_count.value())
            self.settings.setValue("hardware/gpu_memory", self.config_tab.gpu_memory.value())
            
            # Configuration de traitement
            self.settings.setValue("processing/realesrgan_model", self.config_tab.realesrgan_model.currentText())
            self.settings.setValue("processing/output_format", self.config_tab.output_format.currentText())
            
        except Exception as e:
            self.log_tab.add_log(f"Erreur lors de la sauvegarde des paramètres: {e}")
    
    def closeEvent(self, event):
        """Gère la fermeture de l'application"""
        if self.system_tray and self.system_tray.isVisible():
            QMessageBox.information(self, "Application",
                "L'application continuera de fonctionner en arrière-plan. "
                "Pour la fermer complètement, utilisez 'Quitter' dans le menu contextuel.")
            self.hide()
            event.ignore()
        else:
            self.save_settings()
            event.accept()
    
    def set_client(self, client):
        """Définit l'instance du client"""
        self.client = client
        # TODO: Connecter les signaux du client aux méthodes de l'interface