"""
Interface graphique principale du serveur distribué
UpscalingByNetwork/server/gui/server_window.py
"""

import sys
import asyncio
import time
from pathlib import Path
from typing import Dict, Any, Optional
import qasync
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QTabWidget, QGroupBox, QGridLayout, QLabel, QPushButton, QFileDialog,
    QTableWidget, QTableWidgetItem, QProgressBar, QTextEdit, QSpinBox,
    QLineEdit, QComboBox, QCheckBox, QSlider, QSplitter, QFrame,
    QScrollArea, QMessageBox, QSystemTrayIcon, QMenu, QAction, QStyle
)
from PyQt5.QtCore import QTimer, Qt, QThread, pyqtSignal, QRect
from PyQt5.QtGui import QFont, QIcon, QPixmap, QPalette, QColor, QPainter

from ..core.distributed_server import DistributedServer
from .monitoring_panel import MonitoringPanel
from .job_manager_panel import JobManagerPanel

class ServerWindow(QMainWindow):
    """Interface graphique principale du serveur"""
    
    def __init__(self):
        super().__init__()
        
        # Serveur distribué
        self.server: Optional[DistributedServer] = None
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
        
        # Interface
        self.setup_ui()
        self.setup_tray()
        self.setup_timers()
        self.setup_styles()
        
        # État initial
        self.update_ui_state()
        
        self.setWindowTitle("UpscalingByNetwork - Serveur Distribué")
        self.setGeometry(100, 100, 1400, 900)
    
    def setup_ui(self):
        """Configure l'interface utilisateur"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principal
        main_layout = QVBoxLayout(central_widget)
        
        # Barre de statut du serveur
        self.setup_server_status_bar(main_layout)
        
        # Onglets principaux
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # Onglet Surveillance
        self.monitoring_tab = MonitoringPanel(self)
        self.tabs.addTab(self.monitoring_tab, "🖥️ Surveillance")
        
        # Onglet Gestion des Jobs
        self.jobs_tab = JobManagerPanel(self)
        self.tabs.addTab(self.jobs_tab, "🎬 Gestion des Jobs")
        
        # Onglet Configuration
        self.config_tab = self.create_config_tab()
        self.tabs.addTab(self.config_tab, "⚙️ Configuration")
        
        # Onglet Logs
        self.logs_tab = self.create_logs_tab()
        self.tabs.addTab(self.logs_tab, "📋 Logs")
        
        # Barre de statut
        self.statusBar().showMessage("Serveur arrêté")
    
    def setup_server_status_bar(self, layout):
        """Crée la barre de statut du serveur"""
        status_frame = QFrame()
        status_frame.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        status_frame.setMaximumHeight(80)
        
        status_layout = QHBoxLayout(status_frame)
        
        # Statut du serveur
        server_group = QGroupBox("Statut du Serveur")
        server_layout = QGridLayout(server_group)
        
        self.server_status_label = QLabel("Arrêté")
        self.server_status_label.setStyleSheet("color: red; font-weight: bold; font-size: 14px;")
        server_layout.addWidget(QLabel("État:"), 0, 0)
        server_layout.addWidget(self.server_status_label, 0, 1)
        
        self.clients_count_label = QLabel("0")
        server_layout.addWidget(QLabel("Clients:"), 1, 0)
        server_layout.addWidget(self.clients_count_label, 1, 1)
        
        status_layout.addWidget(server_group)
        
        # Contrôles du serveur
        controls_group = QGroupBox("Contrôles")
        controls_layout = QHBoxLayout(controls_group)
        
        self.start_stop_btn = QPushButton("Démarrer le serveur")
        self.start_stop_btn.clicked.connect(self.toggle_server)
        self.start_stop_btn.setMinimumHeight(40)
        controls_layout.addWidget(self.start_stop_btn)
        
        self.restart_btn = QPushButton("Redémarrer")
        self.restart_btn.clicked.connect(self.restart_server)
        self.restart_btn.setEnabled(False)
        controls_layout.addWidget(self.restart_btn)
        
        status_layout.addWidget(controls_group)
        
        # Statistiques rapides
        stats_group = QGroupBox("Statistiques")
        stats_layout = QGridLayout(stats_group)
        
        self.jobs_count_label = QLabel("0")
        stats_layout.addWidget(QLabel("Jobs:"), 0, 0)
        stats_layout.addWidget(self.jobs_count_label, 0, 1)
        
        self.batches_count_label = QLabel("0")
        stats_layout.addWidget(QLabel("Lots:"), 1, 0)
        stats_layout.addWidget(self.batches_count_label, 1, 1)
        
        self.uptime_label = QLabel("00:00:00")
        stats_layout.addWidget(QLabel("Durée:"), 0, 2)
        stats_layout.addWidget(self.uptime_label, 0, 3)
        
        status_layout.addWidget(stats_group)
        
        layout.addWidget(status_frame)
    
    def create_config_tab(self):
        """Crée l'onglet de configuration"""
        config_widget = QWidget()
        layout = QVBoxLayout(config_widget)
        
        # Configuration réseau
        network_group = QGroupBox("Configuration Réseau")
        network_layout = QGridLayout(network_group)
        
        self.host_input = QLineEdit(self.config['host'])
        network_layout.addWidget(QLabel("Adresse IP:"), 0, 0)
        network_layout.addWidget(self.host_input, 0, 1)
        
        self.port_input = QSpinBox()
        self.port_input.setRange(1024, 65535)
        self.port_input.setValue(self.config['port'])
        network_layout.addWidget(QLabel("Port:"), 1, 0)
        network_layout.addWidget(self.port_input, 1, 1)
        
        self.max_clients_input = QSpinBox()
        self.max_clients_input.setRange(1, 200)
        self.max_clients_input.setValue(self.config['max_clients'])
        network_layout.addWidget(QLabel("Clients max:"), 2, 0)
        network_layout.addWidget(self.max_clients_input, 2, 1)
        
        layout.addWidget(network_group)
        
        # Configuration des lots
        batch_group = QGroupBox("Configuration des Lots")
        batch_layout = QGridLayout(batch_group)
        
        self.batch_size_input = QSpinBox()
        self.batch_size_input.setRange(10, 200)
        self.batch_size_input.setValue(self.config['batch_size'])
        batch_layout.addWidget(QLabel("Taille des lots:"), 0, 0)
        batch_layout.addWidget(self.batch_size_input, 0, 1)
        
        self.allow_duplicates_check = QCheckBox("Autoriser les doublons")
        self.allow_duplicates_check.setChecked(True)
        batch_layout.addWidget(self.allow_duplicates_check, 1, 0, 1, 2)
        
        self.server_processing_check = QCheckBox("Le serveur peut traiter")
        self.server_processing_check.setChecked(True)
        batch_layout.addWidget(self.server_processing_check, 2, 0, 1, 2)
        
        layout.addWidget(batch_group)
        
        # Configuration Real-ESRGAN
        realesrgan_group = QGroupBox("Configuration Real-ESRGAN")
        realesrgan_layout = QGridLayout(realesrgan_group)
        
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "realesr-animevideov3",
            "realesrgan-x4plus",
            "realesrgan-x4plus-anime"
        ])
        realesrgan_layout.addWidget(QLabel("Modèle:"), 0, 0)
        realesrgan_layout.addWidget(self.model_combo, 0, 1)
        
        self.scale_combo = QComboBox()
        self.scale_combo.addItems(["2", "4", "8"])
        self.scale_combo.setCurrentText("4")
        realesrgan_layout.addWidget(QLabel("Facteur d'échelle:"), 1, 0)
        realesrgan_layout.addWidget(self.scale_combo, 1, 1)
        
        self.tile_size_input = QSpinBox()
        self.tile_size_input.setRange(128, 1024)
        self.tile_size_input.setValue(256)
        realesrgan_layout.addWidget(QLabel("Taille tuile:"), 2, 0)
        realesrgan_layout.addWidget(self.tile_size_input, 2, 1)
        
        layout.addWidget(realesrgan_group)
        
        # Boutons de configuration
        buttons_layout = QHBoxLayout()
        
        save_config_btn = QPushButton("Sauvegarder")
        save_config_btn.clicked.connect(self.save_config)
        buttons_layout.addWidget(save_config_btn)
        
        load_config_btn = QPushButton("Charger")
        load_config_btn.clicked.connect(self.load_config)
        buttons_layout.addWidget(load_config_btn)
        
        reset_config_btn = QPushButton("Réinitialiser")
        reset_config_btn.clicked.connect(self.reset_config)
        buttons_layout.addWidget(reset_config_btn)
        
        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)
        
        layout.addStretch()
        return config_widget
    
    def create_logs_tab(self):
        """Crée l'onglet des logs"""
        logs_widget = QWidget()
        layout = QVBoxLayout(logs_widget)
        
        # Contrôles des logs
        controls_layout = QHBoxLayout()
        
        clear_logs_btn = QPushButton("Effacer")
        clear_logs_btn.clicked.connect(self.clear_logs)
        controls_layout.addWidget(clear_logs_btn)
        
        save_logs_btn = QPushButton("Sauvegarder")
        save_logs_btn.clicked.connect(self.save_logs)
        controls_layout.addWidget(save_logs_btn)
        
        self.auto_scroll_check = QCheckBox("Défilement auto")
        self.auto_scroll_check.setChecked(True)
        controls_layout.addWidget(self.auto_scroll_check)
        
        controls_layout.addStretch()
        layout.addLayout(controls_layout)
        
        # Zone de logs
        self.logs_text = QTextEdit()
        self.logs_text.setReadOnly(True)
        self.logs_text.setFont(QFont("Consolas", 9))
        layout.addWidget(self.logs_text)
        
        return logs_widget
    
    def setup_tray(self):
        """Configure l'icône système"""
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = QSystemTrayIcon(self)
            
            # Menu contextuel
            tray_menu = QMenu()
            
            show_action = QAction("Afficher", self)
            show_action.triggered.connect(self.show)
            tray_menu.addAction(show_action)
            
            tray_menu.addSeparator()
            
            start_action = QAction("Démarrer serveur", self)
            start_action.triggered.connect(self.start_server)
            tray_menu.addAction(start_action)
            
            stop_action = QAction("Arrêter serveur", self)
            stop_action.triggered.connect(self.stop_server)
            tray_menu.addAction(stop_action)
            
            tray_menu.addSeparator()
            
            quit_action = QAction("Quitter", self)
            quit_action.triggered.connect(self.quit_application)
            tray_menu.addAction(quit_action)
            
            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.activated.connect(self.tray_activated)
            
            # Icône (utiliser une icône par défaut si pas disponible)
            icon = self.style().standardIcon(QStyle.SP_ComputerIcon)
            self.tray_icon.setIcon(icon)
            self.setWindowIcon(icon)
            
            self.tray_icon.show()
    
    def setup_timers(self):
        """Configure les timers de mise à jour"""
        # Timer principal pour mise à jour UI
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_ui)
        self.update_timer.start(1000)  # Mise à jour chaque seconde
        
        # Timer pour logs
        self.logs_timer = QTimer()
        self.logs_timer.timeout.connect(self.update_logs)
        self.logs_timer.start(500)  # Logs plus fréquents
    
    def setup_styles(self):
        """Configure les styles CSS"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
            }
            
            QTabWidget::pane {
                border: 1px solid #c0c0c0;
                background-color: white;
            }
            
            QTabBar::tab {
                background-color: #e0e0e0;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            
            QTabBar::tab:selected {
                background-color: white;
                border-bottom: 2px solid #0078d4;
            }
            
            QGroupBox {
                font-weight: bold;
                border: 2px solid #c0c0c0;
                border-radius: 5px;
                margin: 5px;
                padding-top: 10px;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            
            QPushButton:hover {
                background-color: #106ebe;
            }
            
            QPushButton:pressed {
                background-color: #005a9e;
            }
            
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
            
            QTableWidget {
                gridline-color: #d0d0d0;
                selection-background-color: #0078d4;
            }
            
            QHeaderView::section {
                background-color: #f8f8f8;
                padding: 4px;
                border: 1px solid #d0d0d0;
                font-weight: bold;
            }
        """)
    
    @qasync.asyncSlot()
    async def toggle_server(self):
        """Démarre ou arrête le serveur"""
        if not self.server_running:
            await self.start_server()
        else:
            await self.stop_server()
    
    @qasync.asyncSlot()
    async def start_server(self):
        """Démarre le serveur"""
        try:
            if self.server_running:
                return
            
            # Récupération de la configuration
            host = self.host_input.text().strip()
            port = self.port_input.value()
            
            # Création du serveur
            self.server = DistributedServer(host, port)
            
            # Configuration des options
            self.server.batch_size = self.batch_size_input.value()
            self.server.server_can_process = self.server_processing_check.isChecked()
            
            # Démarrage asynchrone
            self.log_message("Démarrage du serveur...")
            
            # Démarrage en arrière-plan
            asyncio.create_task(self.server.start_server())
            
            self.server_running = True
            self.update_ui_state()
            
            self.log_message(f"Serveur démarré sur {host}:{port}")
            self.tray_icon.showMessage(
                "Serveur UpscalingByNetwork",
                f"Serveur démarré sur {host}:{port}",
                QSystemTrayIcon.Information,
                3000
            )
            
        except Exception as e:
            self.log_message(f"Erreur démarrage serveur: {e}")
            QMessageBox.critical(self, "Erreur", f"Impossible de démarrer le serveur:\n{e}")
    
    @qasync.asyncSlot()
    async def stop_server(self):
        """Arrête le serveur"""
        try:
            if not self.server_running or not self.server:
                return
            
            self.log_message("Arrêt du serveur...")
            
            await self.server.stop_server()
            
            self.server = None
            self.server_running = False
            self.update_ui_state()
            
            self.log_message("Serveur arrêté")
            self.tray_icon.showMessage(
                "Serveur UpscalingByNetwork",
                "Serveur arrêté",
                QSystemTrayIcon.Information,
                2000
            )
            
        except Exception as e:
            self.log_message(f"Erreur arrêt serveur: {e}")
    
    @qasync.asyncSlot()
    async def restart_server(self):
        """Redémarre le serveur"""
        await self.stop_server()
        await asyncio.sleep(1)
        await self.start_server()
    
    def update_ui_state(self):
        """Met à jour l'état de l'interface"""
        if self.server_running:
            self.server_status_label.setText("Démarré")
            self.server_status_label.setStyleSheet("color: green; font-weight: bold; font-size: 14px;")
            self.start_stop_btn.setText("Arrêter le serveur")
            self.restart_btn.setEnabled(True)
            self.statusBar().showMessage("Serveur en fonctionnement")
        else:
            self.server_status_label.setText("Arrêté")
            self.server_status_label.setStyleSheet("color: red; font-weight: bold; font-size: 14px;")
            self.start_stop_btn.setText("Démarrer le serveur")
            self.restart_btn.setEnabled(False)
            self.statusBar().showMessage("Serveur arrêté")
    
    def update_ui(self):
        """Met à jour l'interface utilisateur"""
        if self.server and self.server_running:
            # Mise à jour des statistiques
            stats = self.server.get_stats()
            clients_status = self.server.get_clients_status()
            
            self.clients_count_label.setText(str(stats.get('active_clients', 0)))
            self.jobs_count_label.setText(str(stats.get('total_jobs', 0)))
            self.batches_count_label.setText(str(stats.get('total_batches', 0)))
            
            # Uptime
            uptime = stats.get('uptime', 0)
            hours = int(uptime // 3600)
            minutes = int((uptime % 3600) // 60)
            seconds = int(uptime % 60)
            self.uptime_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
            
            # Mise à jour des onglets
            self.monitoring_tab.update_data(stats, clients_status)
            self.jobs_tab.update_data(self.server.jobs, self.server.batches)
        else:
            # Réinitialisation si serveur arrêté
            self.clients_count_label.setText("0")
            self.jobs_count_label.setText("0")
            self.batches_count_label.setText("0")
            self.uptime_label.setText("00:00:00")
    
    def update_logs(self):
        """Met à jour les logs"""
        # Cette méthode devrait récupérer les nouveaux logs
        # Pour l'instant, on simule avec le timestamp
        pass
    
    def log_message(self, message: str):
        """Ajoute un message aux logs"""
        timestamp = time.strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        
        self.logs_text.append(log_entry)
        
        if self.auto_scroll_check.isChecked():
            scrollbar = self.logs_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
    
    def clear_logs(self):
        """Efface les logs"""
        self.logs_text.clear()
    
    def save_logs(self):
        """Sauvegarde les logs"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Sauvegarder les logs", "logs.txt", "Fichiers texte (*.txt)"
        )
        
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.logs_text.toPlainText())
                
                QMessageBox.information(self, "Succès", "Logs sauvegardés avec succès")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Erreur sauvegarde logs:\n{e}")
    
    def save_config(self):
        """Sauvegarde la configuration"""
        self.config.update({
            'host': self.host_input.text(),
            'port': self.port_input.value(),
            'max_clients': self.max_clients_input.value(),
            'batch_size': self.batch_size_input.value()
        })
        
        # Ici on sauvegarderait dans un fichier de config
        QMessageBox.information(self, "Configuration", "Configuration sauvegardée")
    
    def load_config(self):
        """Charge la configuration"""
        # Ici on chargerait depuis un fichier de config
        QMessageBox.information(self, "Configuration", "Configuration chargée")
    
    def reset_config(self):
        """Remet la configuration par défaut"""
        reply = QMessageBox.question(
            self, "Réinitialisation", 
            "Voulez-vous vraiment réinitialiser la configuration ?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.host_input.setText('0.0.0.0')
            self.port_input.setValue(8888)
            self.max_clients_input.setValue(50)
            self.batch_size_input.setValue(50)
    
    def tray_activated(self, reason):
        """Gestion des clics sur l'icône système"""
        if reason == QSystemTrayIcon.DoubleClick:
            if self.isVisible():
                self.hide()
            else:
                self.show()
                self.activateWindow()
    
    def closeEvent(self, event):
        """Gestion de la fermeture de la fenêtre"""
        if self.config.get('minimize_to_tray', True) and self.tray_icon.isVisible():
            self.hide()
            event.ignore()
            
            if not hasattr(self, '_tray_message_shown'):
                self.tray_icon.showMessage(
                    "UpscalingByNetwork",
                    "L'application continue en arrière-plan",
                    QSystemTrayIcon.Information,
                    2000
                )
                self._tray_message_shown = True
        else:
            self.quit_application()
    
    @qasync.asyncSlot()
    async def quit_application(self):
        """Quitte l'application proprement"""
        if self.server_running:
            await self.stop_server()
        
        QApplication.quit()

# Point d'entrée pour l'application serveur
if __name__ == "__main__":
    import qasync
    
    app = QApplication(sys.argv)
    
    # Configuration de l'event loop asynchrone
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    # Fenêtre principale
    window = ServerWindow()
    window.show()
    
    try:
        with loop:
            loop.run_forever()
    except KeyboardInterrupt:
        pass