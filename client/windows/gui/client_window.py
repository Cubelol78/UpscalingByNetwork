"""
Interface graphique principale du client Windows
UpscalingByNetwork/client/windows/gui/client_window.py
"""

import sys
import asyncio
import time
from pathlib import Path
from typing import Optional, Dict, Any
import qasync
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QTabWidget, QGroupBox, QGridLayout, QLabel, QPushButton, QLineEdit,
    QSpinBox, QTextEdit, QProgressBar, QSystemTrayIcon, QMenu, QAction,
    QMessageBox, QFrame, QSplitter, QCheckBox, QComboBox, QStyle,
    QHeaderView, QTableWidget, QTableWidgetItem
)
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QThread
from PyQt5.QtGui import QFont, QIcon, QPixmap, QPalette, QColor

from ..core.distributed_client import DistributedClient
from .connection_panel import ConnectionPanel
from .processing_panel import ProcessingPanel
from .settings_panel import SettingsPanel

class ClientWindow(QMainWindow):
    """Interface graphique principale du client"""
    
    # Signaux pour communication inter-threads
    connection_changed = pyqtSignal(bool, str)
    batch_received = pyqtSignal(str, int)
    progress_updated = pyqtSignal(str, float, int)
    batch_completed = pyqtSignal(str, float, int)
    error_occurred = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        
        # Client distribué
        self.client: Optional[DistributedClient] = None
        
        # Configuration par défaut
        self.config = {
            'server_host': 'localhost',
            'server_port': 8888,
            'auto_connect': False,
            'minimize_to_tray': True,
            'notifications': True,
            'max_concurrent_batches': 1,
            'auto_start_processing': True
        }
        
        # Interface
        self.setup_ui()
        self.setup_tray()
        self.setup_timers()
        self.setup_styles()
        self.setup_client()
        
        # État initial
        self.update_ui_state()
        
        self.setWindowTitle("UpscalingByNetwork - Client Distribué")
        self.setGeometry(200, 200, 1000, 700)
    
    def setup_ui(self):
        """Configure l'interface utilisateur"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principal
        main_layout = QVBoxLayout(central_widget)
        
        # Barre de statut rapide
        self.setup_status_bar(main_layout)
        
        # Onglets principaux
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # Onglet Connexion
        self.connection_tab = ConnectionPanel(self)
        self.tabs.addTab(self.connection_tab, "🔌 Connexion")
        
        # Onglet Traitement
        self.processing_tab = ProcessingPanel(self)
        self.tabs.addTab(self.processing_tab, "⚡ Traitement")
        
        # Onglet Paramètres
        self.settings_tab = SettingsPanel(self)
        self.tabs.addTab(self.settings_tab, "⚙️ Paramètres")
        
        # Onglet Logs
        self.logs_tab = self.create_logs_tab()
        self.tabs.addTab(self.logs_tab, "📋 Logs")
        
        # Barre de statut
        self.statusBar().showMessage("Client démarré - Non connecté")
    
    def setup_status_bar(self, layout):
        """Crée la barre de statut rapide"""
        status_frame = QFrame()
        status_frame.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        status_frame.setMaximumHeight(70)
        
        status_layout = QHBoxLayout(status_frame)
        
        # Statut de connexion
        conn_group = QGroupBox("Connexion")
        conn_layout = QGridLayout(conn_group)
        
        self.connection_status_label = QLabel("Déconnecté")
        self.connection_status_label.setStyleSheet("color: red; font-weight: bold;")
        conn_layout.addWidget(QLabel("Statut:"), 0, 0)
        conn_layout.addWidget(self.connection_status_label, 0, 1)
        
        self.server_info_label = QLabel("-")
        conn_layout.addWidget(QLabel("Serveur:"), 1, 0)
        conn_layout.addWidget(self.server_info_label, 1, 1)
        
        status_layout.addWidget(conn_group)
        
        # Statut du traitement
        proc_group = QGroupBox("Traitement")
        proc_layout = QGridLayout(proc_group)
        
        self.processing_status_label = QLabel("Inactif")
        proc_layout.addWidget(QLabel("État:"), 0, 0)
        proc_layout.addWidget(self.processing_status_label, 0, 1)
        
        self.current_batch_label = QLabel("Aucun")
        proc_layout.addWidget(QLabel("Lot:"), 1, 0)
        proc_layout.addWidget(self.current_batch_label, 1, 1)
        
        status_layout.addWidget(proc_group)
        
        # Statistiques
        stats_group = QGroupBox("Statistiques")
        stats_layout = QGridLayout(stats_group)
        
        self.batches_completed_label = QLabel("0")
        stats_layout.addWidget(QLabel("Lots traités:"), 0, 0)
        stats_layout.addWidget(self.batches_completed_label, 0, 1)
        
        self.images_processed_label = QLabel("0")
        stats_layout.addWidget(QLabel("Images:"), 1, 0)
        stats_layout.addWidget(self.images_processed_label, 1, 1)
        
        self.uptime_label = QLabel("00:00:00")
        stats_layout.addWidget(QLabel("Durée:"), 0, 2)
        stats_layout.addWidget(self.uptime_label, 0, 3)
        
        status_layout.addWidget(stats_group)
        
        # Contrôles rapides
        controls_group = QGroupBox("Contrôles")
        controls_layout = QVBoxLayout(controls_group)
        
        self.quick_connect_btn = QPushButton("Connexion Rapide")
        self.quick_connect_btn.clicked.connect(self.quick_connect_toggle)
        self.quick_connect_btn.setMinimumHeight(30)
        controls_layout.addWidget(self.quick_connect_btn)
        
        self.emergency_stop_btn = QPushButton("Arrêt d'urgence")
        self.emergency_stop_btn.clicked.connect(self.emergency_stop)
        self.emergency_stop_btn.setStyleSheet("QPushButton { background-color: #dc3545; }")
        self.emergency_stop_btn.setEnabled(False)
        controls_layout.addWidget(self.emergency_stop_btn)
        
        status_layout.addWidget(controls_group)
        
        layout.addWidget(status_frame)
    
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
        
        # Niveau de log
        controls_layout.addWidget(QLabel("Niveau:"))
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["Debug", "Info", "Warning", "Error"])
        self.log_level_combo.setCurrentText("Info")
        controls_layout.addWidget(self.log_level_combo)
        
        controls_layout.addStretch()
        layout.addLayout(controls_layout)
        
        # Zone de logs
        self.logs_text = QTextEdit()
        self.logs_text.setReadOnly(True)
        self.logs_text.setFont(QFont("Consolas", 9))
        self.logs_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #404040;
            }
        """)
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
            
            connect_action = QAction("Se connecter", self)
            connect_action.triggered.connect(self.quick_connect_toggle)
            tray_menu.addAction(connect_action)
            
            tray_menu.addSeparator()
            
            quit_action = QAction("Quitter", self)
            quit_action.triggered.connect(self.quit_application)
            tray_menu.addAction(quit_action)
            
            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.activated.connect(self.tray_activated)
            
            # Icône
            icon = self.style().standardIcon(QStyle.SP_DesktopIcon)
            self.tray_icon.setIcon(icon)
            self.setWindowIcon(icon)
            
            self.tray_icon.show()
    
    def setup_timers(self):
        """Configure les timers"""
        # Timer principal de mise à jour
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_ui)
        self.update_timer.start(1000)  # Chaque seconde
        
        # Timer pour uptime
        self.start_time = time.time()
    
    def setup_styles(self):
        """Configure les styles CSS"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            
            QTabWidget::pane {
                border: 1px solid #c0c0c0;
                background-color: white;
                border-radius: 4px;
            }
            
            QTabBar::tab {
                background-color: #e0e0e0;
                padding: 10px 20px;
                margin-right: 2px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: bold;
            }
            
            QTabBar::tab:selected {
                background-color: white;
                border-bottom: 3px solid #0078d4;
            }
            
            QTabBar::tab:hover {
                background-color: #f0f0f0;
            }
            
            QGroupBox {
                font-weight: bold;
                border: 2px solid #d0d0d0;
                border-radius: 8px;
                margin: 8px;
                padding-top: 15px;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px 0 8px;
                background-color: white;
            }
            
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 11px;
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
            
            QLabel {
                color: #333333;
            }
            
            QLineEdit, QSpinBox {
                padding: 8px;
                border: 2px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
            }
            
            QLineEdit:focus, QSpinBox:focus {
                border-color: #0078d4;
            }
            
            QProgressBar {
                border: 2px solid #e0e0e0;
                border-radius: 6px;
                text-align: center;
                font-weight: bold;
                height: 25px;
            }
            
            QProgressBar::chunk {
                background-color: #28a745;
                border-radius: 4px;
                margin: 2px;
            }
        """)
    
    def setup_client(self):
        """Configure le client distribué"""
        self.client = DistributedClient()
        
        # Connexion des callbacks
        self.client.on_connection_changed = self.on_connection_changed
        self.client.on_batch_received = self.on_batch_received
        self.client.on_progress_update = self.on_progress_update
        self.client.on_batch_completed = self.on_batch_completed
        self.client.on_error = self.on_error
        
        # Connexion des signaux
        self.connection_changed.connect(self.update_connection_status)
        self.batch_received.connect(self.update_batch_received)
        self.progress_updated.connect(self.update_progress)
        self.batch_completed.connect(self.update_batch_completed)
        self.error_occurred.connect(self.show_error)
    
    def on_connection_changed(self, connected: bool, info: str):
        """Callback changement de connexion"""
        self.connection_changed.emit(connected, info)
    
    def on_batch_received(self, batch_id: str, frame_count: int):
        """Callback réception de lot"""
        self.batch_received.emit(batch_id, frame_count)
    
    def on_progress_update(self, batch_id: str, progress: float, current_frame: int):
        """Callback mise à jour progression"""
        self.progress_updated.emit(batch_id, progress, current_frame)
    
    def on_batch_completed(self, batch_id: str, processing_time: float, frames_processed: int):
        """Callback lot terminé"""
        self.batch_completed.emit(batch_id, processing_time, frames_processed)
    
    def on_error(self, error_message: str):
        """Callback erreur"""
        self.error_occurred.emit(error_message)
    
    def update_connection_status(self, connected: bool, info: str):
        """Met à jour le statut de connexion"""
        if connected:
            self.connection_status_label.setText("Connecté")
            self.connection_status_label.setStyleSheet("color: green; font-weight: bold;")
            self.server_info_label.setText(info)
            self.quick_connect_btn.setText("Se déconnecter")
            self.emergency_stop_btn.setEnabled(True)
            
            if self.config.get('notifications', True):
                self.tray_icon.showMessage(
                    "UpscalingByNetwork",
                    f"Connecté au serveur",
                    QSystemTrayIcon.Information,
                    3000
                )
        else:
            self.connection_status_label.setText("Déconnecté")
            self.connection_status_label.setStyleSheet("color: red; font-weight: bold;")
            self.server_info_label.setText("-")
            self.quick_connect_btn.setText("Se connecter")
            self.emergency_stop_btn.setEnabled(False)
            self.processing_status_label.setText("Inactif")
            self.current_batch_label.setText("Aucun")
    
    def update_batch_received(self, batch_id: str, frame_count: int):
        """Met à jour l'interface pour un nouveau lot"""
        short_id = batch_id.split('_')[-1] if '_' in batch_id else batch_id[:8]
        self.current_batch_label.setText(short_id)
        self.processing_status_label.setText("En cours")
        
        self.log_message(f"Nouveau lot reçu: {short_id} ({frame_count} images)")
        
        if self.config.get('notifications', True):
            self.tray_icon.showMessage(
                "Nouveau lot",
                f"Traitement de {frame_count} images",
                QSystemTrayIcon.Information,
                2000
            )
    
    def update_progress(self, batch_id: str, progress: float, current_frame: int):
        """Met à jour la progression"""
        # Les onglets individuels gèrent leur propre mise à jour
        pass
    
    def update_batch_completed(self, batch_id: str, processing_time: float, frames_processed: int):
        """Met à jour l'interface pour un lot terminé"""
        self.current_batch_label.setText("Aucun")
        self.processing_status_label.setText("Inactif")
        
        # Mise à jour des statistiques
        if self.client:
            stats = self.client.get_stats()
            self.batches_completed_label.setText(str(stats['batches_completed']))
            self.images_processed_label.setText(str(stats['images_processed']))
        
        self.log_message(f"Lot terminé en {processing_time:.1f}s ({frames_processed} images)")
        
        if self.config.get('notifications', True):
            self.tray_icon.showMessage(
                "Lot terminé",
                f"Traité en {processing_time:.1f}s",
                QSystemTrayIcon.Information,
                2000
            )
    
    def show_error(self, error_message: str):
        """Affiche une erreur"""
        self.log_message(f"ERREUR: {error_message}", "error")
        
        if not self.isMinimized():
            QMessageBox.critical(self, "Erreur", error_message)
    
    @qasync.asyncSlot()
    async def quick_connect_toggle(self):
        """Connexion/déconnexion rapide"""
        if self.client and self.client.connected:
            await self.client.disconnect()
        else:
            host = self.config['server_host']
            port = self.config['server_port']
            await self.client.connect_to_server(host, port)
    
    @qasync.asyncSlot()
    async def emergency_stop(self):
        """Arrêt d'urgence"""
        if self.client:
            await self.client.disconnect()
        
        self.log_message("ARRÊT D'URGENCE activé", "warning")
        
        QMessageBox.information(
            self, 
            "Arrêt d'urgence", 
            "Le client a été déconnecté et tout traitement a été arrêté."
        )
    
    def update_ui(self):
        """Mise à jour périodique de l'interface"""
        # Mise à jour de l'uptime
        uptime = time.time() - self.start_time
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        seconds = int(uptime % 60)
        self.uptime_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        
        # Mise à jour des statistiques si client connecté
        if self.client and self.client.connected:
            stats = self.client.get_stats()
            self.batches_completed_label.setText(str(stats['batches_completed']))
            self.images_processed_label.setText(str(stats['images_processed']))
            
            # Mise à jour des onglets
            self.processing_tab.update_data(stats)
            self.connection_tab.update_data(stats)
    
    def update_ui_state(self):
        """Met à jour l'état général de l'interface"""
        connected = self.client and self.client.connected
        
        # Mise à jour de la barre de statut
        if connected:
            self.statusBar().showMessage("Client connecté et opérationnel")
        else:
            self.statusBar().showMessage("Client démarré - Non connecté")
    
    def log_message(self, message: str, level: str = "info"):
        """Ajoute un message aux logs"""
        timestamp = time.strftime("%H:%M:%S")
        
        # Couleur selon le niveau
        colors = {
            "debug": "#888888",
            "info": "#ffffff",
            "warning": "#ffa500",
            "error": "#ff4444"
        }
        
        color = colors.get(level, "#ffffff")
        
        # Icône selon le niveau
        icons = {
            "debug": "🐛",
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌"
        }
        
        icon = icons.get(level, "ℹ️")
        
        formatted_message = f'<span style="color: {color};">[{timestamp}] {icon} {message}</span>'
        self.logs_text.append(formatted_message)
        
        # Auto-scroll si activé
        if self.auto_scroll_check.isChecked():
            scrollbar = self.logs_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        
        # Limitation du nombre de lignes
        document = self.logs_text.document()
        if document.blockCount() > 1000:
            cursor = self.logs_text.textCursor()
            cursor.movePosition(cursor.Start)
            cursor.select(cursor.BlockUnderCursor)
            cursor.removeSelectedText()
    
    def clear_logs(self):
        """Efface les logs"""
        self.logs_text.clear()
        self.log_message("Logs effacés")
    
    def save_logs(self):
        """Sauvegarde les logs"""
        from PyQt5.QtWidgets import QFileDialog
        
        filename, _ = QFileDialog.getSaveFileName(
            self, "Sauvegarder les logs", 
            f"client_logs_{time.strftime('%Y%m%d_%H%M%S')}.txt",
            "Fichiers texte (*.txt)"
        )
        
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    # Extraction du texte sans HTML
                    plain_text = self.logs_text.toPlainText()
                    f.write(plain_text)
                
                self.log_message(f"Logs sauvegardés: {filename}")
                QMessageBox.information(self, "Sauvegarde", "Logs sauvegardés avec succès")
            except Exception as e:
                self.log_message(f"Erreur sauvegarde logs: {e}", "error")
    
    def tray_activated(self, reason):
        """Gestion des clics sur l'icône système"""
        if reason == QSystemTrayIcon.DoubleClick:
            if self.isVisible():
                self.hide()
            else:
                self.show()
                self.activateWindow()
                self.raise_()
    
    def closeEvent(self, event):
        """Gestion de la fermeture"""
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
        self.log_message("Fermeture de l'application...")
        
        if self.client and self.client.connected:
            await self.client.disconnect()
        
        QApplication.quit()
    
    def get_client_config(self) -> Dict[str, Any]:
        """Retourne la configuration du client"""
        return self.config.copy()
    
    def update_client_config(self, new_config: Dict[str, Any]):
        """Met à jour la configuration du client"""
        self.config.update(new_config)
        
        # Application de certains changements immédiatement
        if 'notifications' in new_config:
            # Pas d'action spéciale nécessaire
            pass

# Point d'entrée pour l'application client
if __name__ == "__main__":
    import qasync
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Permet de continuer avec l'icône système
    
    # Configuration de l'event loop asynchrone
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    # Fenêtre principale
    window = ClientWindow()
    window.show()
    
    try:
        with loop:
            loop.run_forever()
    except KeyboardInterrupt:
        pass