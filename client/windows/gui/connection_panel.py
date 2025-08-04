"""
Panneaux spécialisés pour l'interface client Windows
UpscalingByNetwork/client/windows/gui/connection_panel.py
"""

import time
import socket
import qasync
from typing import Dict, Any, Optional
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QGridLayout,
    QLabel, QPushButton, QLineEdit, QSpinBox, QTextEdit, QProgressBar,
    QCheckBox, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QFrame, QMessageBox, QFormLayout, QSlider
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QColor

class ConnectionPanel(QWidget):
    """Onglet de gestion de la connexion au serveur"""
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setup_ui()
        
        # Données de connexion
        self.connection_stats = {}
        self.last_ping_time = 0
        
        # Timer pour ping automatique
        self.ping_timer = QTimer()
        self.ping_timer.timeout.connect(self.auto_ping)
        self.ping_timer.start(30000)  # Ping toutes les 30 secondes
    
    def setup_ui(self):
        """Configure l'interface du panneau"""
        layout = QVBoxLayout(self)
        
        # Splitter principal
        main_splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(main_splitter)
        
        # Partie gauche: Configuration de connexion
        left_widget = self.create_connection_config()
        main_splitter.addWidget(left_widget)
        
        # Partie droite: Statut et diagnostics
        right_widget = self.create_connection_status()
        main_splitter.addWidget(right_widget)
        
        main_splitter.setSizes([400, 600])
    
    def create_connection_config(self):
        """Crée la section de configuration de connexion"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Configuration serveur
        server_group = QGroupBox("Configuration du serveur")
        server_layout = QFormLayout(server_group)
        
        self.host_input = QLineEdit()
        self.host_input.setText(self.main_window.config['server_host'])
        self.host_input.setPlaceholderText("IP ou nom d'hôte du serveur")
        server_layout.addRow("Adresse serveur:", self.host_input)
        
        self.port_input = QSpinBox()
        self.port_input.setRange(1024, 65535)
        self.port_input.setValue(self.main_window.config['server_port'])
        server_layout.addRow("Port:", self.port_input)
        
        # Bouton de test de connexion
        test_layout = QHBoxLayout()
        self.test_connection_btn = QPushButton("Tester la connexion")
        self.test_connection_btn.clicked.connect(self.test_connection)
        test_layout.addWidget(self.test_connection_btn)
        
        self.ping_btn = QPushButton("Ping")
        self.ping_btn.clicked.connect(self.ping_server)
        test_layout.addWidget(self.ping_btn)
        
        test_layout.addStretch()
        server_layout.addRow("Tests:", test_layout)
        
        layout.addWidget(server_group)
        
        # Options de connexion
        options_group = QGroupBox("Options de connexion")
        options_layout = QFormLayout(options_group)
        
        self.auto_connect_check = QCheckBox("Connexion automatique au démarrage")
        self.auto_connect_check.setChecked(self.main_window.config.get('auto_connect', False))
        options_layout.addRow(self.auto_connect_check)
        
        self.auto_reconnect_check = QCheckBox("Reconnexion automatique")
        self.auto_reconnect_check.setChecked(True)
        options_layout.addRow(self.auto_reconnect_check)
        
        self.connection_timeout_spin = QSpinBox()
        self.connection_timeout_spin.setRange(5, 60)
        self.connection_timeout_spin.setValue(30)
        self.connection_timeout_spin.setSuffix(" secondes")
        options_layout.addRow("Timeout connexion:", self.connection_timeout_spin)
        
        self.heartbeat_interval_spin = QSpinBox()
        self.heartbeat_interval_spin.setRange(10, 300)
        self.heartbeat_interval_spin.setValue(30)
        self.heartbeat_interval_spin.setSuffix(" secondes")
        options_layout.addRow("Intervalle heartbeat:", self.heartbeat_interval_spin)
        
        layout.addWidget(options_group)
        
        # Contrôles de connexion
        controls_group = QGroupBox("Contrôles")
        controls_layout = QVBoxLayout(controls_group)
        
        connect_layout = QHBoxLayout()
        
        self.connect_btn = QPushButton("Se connecter")
        self.connect_btn.clicked.connect(self.connect_to_server)
        self.connect_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                font-size: 14px;
                padding: 12px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        connect_layout.addWidget(self.connect_btn)
        
        self.disconnect_btn = QPushButton("Se déconnecter")
        self.disconnect_btn.clicked.connect(self.disconnect_from_server)
        self.disconnect_btn.setEnabled(False)
        self.disconnect_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                font-size: 14px;
                padding: 12px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)
        connect_layout.addWidget(self.disconnect_btn)
        
        controls_layout.addLayout(connect_layout)
        
        # Bouton de sauvegarde de configuration
        save_config_btn = QPushButton("Sauvegarder la configuration")
        save_config_btn.clicked.connect(self.save_connection_config)
        controls_layout.addWidget(save_config_btn)
        
        layout.addWidget(controls_group)
        
        layout.addStretch()
        return widget
    
    def create_connection_status(self):
        """Crée la section de statut de connexion"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Statut de connexion actuel
        status_group = QGroupBox("Statut de la connexion")
        status_layout = QGridLayout(status_group)
        
        self.status_labels = {}
        status_items = [
            ("État:", "state"),
            ("Serveur:", "server"),
            ("Temps de connexion:", "uptime"),
            ("Dernière activité:", "last_activity"),
            ("Ping:", "ping"),
            ("Qualité connexion:", "quality")
        ]
        
        for i, (label, key) in enumerate(status_items):
            row, col = i // 2, (i % 2) * 2
            
            status_layout.addWidget(QLabel(label), row, col)
            
            value_label = QLabel("-")
            value_label.setStyleSheet("font-weight: bold;")
            status_layout.addWidget(value_label, row, col + 1)
            
            self.status_labels[key] = value_label
        
        layout.addWidget(status_group)
        
        # Informations du client
        client_group = QGroupBox("Informations du client")
        client_layout = QGridLayout(client_group)
        
        self.client_labels = {}
        client_items = [
            ("Adresse MAC:", "mac"),
            ("ID Client:", "client_id"),
            ("Version:", "version"),
            ("Capacités:", "capabilities")
        ]
        
        for i, (label, key) in enumerate(client_items):
            client_layout.addWidget(QLabel(label), i, 0)
            
            value_label = QLabel("-")
            client_layout.addWidget(value_label, i, 1)
            
            self.client_labels[key] = value_label
        
        layout.addWidget(client_group)
        
        # Statistiques de performance réseau
        network_group = QGroupBox("Performance réseau")
        network_layout = QVBoxLayout(network_group)
        
        # Graphique de ping (simplifié)
        ping_frame = QFrame()
        ping_frame.setFrameStyle(QFrame.StyledPanel)
        ping_frame.setMinimumHeight(100)
        ping_frame.setStyleSheet("background-color: white;")
        
        ping_layout = QVBoxLayout(ping_frame)
        self.ping_graph_label = QLabel("Graphique de ping")
        self.ping_graph_label.setAlignment(Qt.AlignCenter)
        self.ping_graph_label.setStyleSheet("color: #666; font-style: italic;")
        ping_layout.addWidget(self.ping_graph_label)
        
        network_layout.addWidget(ping_frame)
        
        # Statistiques réseau
        network_stats_layout = QGridLayout()
        
        self.network_labels = {}
        network_items = [
            ("Ping min:", "ping_min"),
            ("Ping max:", "ping_max"),
            ("Ping moyen:", "ping_avg"),
            ("Perte de paquets:", "packet_loss"),
            ("Bande passante:", "bandwidth"),
            ("Latence:", "latency")
        ]
        
        for i, (label, key) in enumerate(network_items):
            row, col = i // 3, (i % 3) * 2
            
            network_stats_layout.addWidget(QLabel(label), row, col)
            
            value_label = QLabel("-")
            value_label.setStyleSheet("font-size: 10px;")
            network_stats_layout.addWidget(value_label, row, col + 1)
            
            self.network_labels[key] = value_label
        
        network_layout.addLayout(network_stats_layout)
        layout.addWidget(network_group)
        
        # Journal de connexion
        log_group = QGroupBox("Journal de connexion")
        log_layout = QVBoxLayout(log_group)
        
        self.connection_log = QTextEdit()
        self.connection_log.setMaximumHeight(150)
        self.connection_log.setReadOnly(True)
        self.connection_log.setFont(QFont("Consolas", 8))
        self.connection_log.setStyleSheet("""
            QTextEdit {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
            }
        """)
        log_layout.addWidget(self.connection_log)
        
        layout.addWidget(log_group)
        
        return widget
    
    @qasync.asyncSlot()
    async def connect_to_server(self):
        """Se connecte au serveur"""
        try:
            host = self.host_input.text().strip()
            port = self.port_input.value()
            
            if not host:
                QMessageBox.warning(self, "Erreur", "Veuillez saisir l'adresse du serveur")
                return
            
            self.log_connection(f"Tentative de connexion à {host}:{port}...")
            
            self.connect_btn.setEnabled(False)
            self.connect_btn.setText("Connexion...")
            
            success = await self.main_window.client.connect_to_server(host, port)
            
            if success:
                self.connect_btn.setText("Connecté")
                self.disconnect_btn.setEnabled(True)
                self.log_connection("✅ Connexion établie avec succès")
            else:
                self.connect_btn.setText("Se connecter")
                self.connect_btn.setEnabled(True)
                self.log_connection("❌ Échec de la connexion")
                
        except Exception as e:
            self.connect_btn.setText("Se connecter")
            self.connect_btn.setEnabled(True)
            self.log_connection(f"❌ Erreur de connexion: {e}")
    
    @qasync.asyncSlot()
    async def disconnect_from_server(self):
        """Se déconnecte du serveur"""
        try:
            self.log_connection("Déconnexion en cours...")
            
            await self.main_window.client.disconnect()
            
            self.connect_btn.setText("Se connecter")
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)
            
            self.log_connection("🔌 Déconnecté du serveur")
            
        except Exception as e:
            self.log_connection(f"❌ Erreur de déconnexion: {e}")
    
    def test_connection(self):
        """Teste la connexion au serveur (sans authentification complète)"""
        try:
            host = self.host_input.text().strip()
            port = self.port_input.value()
            
            if not host:
                QMessageBox.warning(self, "Erreur", "Veuillez saisir l'adresse du serveur")
                return
            
            self.test_connection_btn.setEnabled(False)
            self.test_connection_btn.setText("Test en cours...")
            
            # Test de connexion TCP simple
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            
            try:
                result = sock.connect_ex((host, port))
                sock.close()
                
                if result == 0:
                    self.log_connection(f"✅ Test de connexion réussi pour {host}:{port}")
                    QMessageBox.information(self, "Test de connexion", "Connexion possible au serveur")
                else:
                    self.log_connection(f"❌ Test de connexion échoué pour {host}:{port}")
                    QMessageBox.warning(self, "Test de connexion", "Impossible de se connecter au serveur")
                    
            except Exception as e:
                self.log_connection(f"❌ Erreur test de connexion: {e}")
                QMessageBox.critical(self, "Erreur", f"Erreur de test de connexion:\n{e}")
            
        finally:
            self.test_connection_btn.setEnabled(True)
            self.test_connection_btn.setText("Tester la connexion")
    
    def ping_server(self):
        """Effectue un ping vers le serveur"""
        try:
            host = self.host_input.text().strip()
            
            if not host:
                QMessageBox.warning(self, "Erreur", "Veuillez saisir l'adresse du serveur")
                return
            
            import subprocess
            import platform
            
            # Commande ping selon l'OS
            if platform.system().lower() == "windows":
                cmd = ["ping", "-n", "4", host]
            else:
                cmd = ["ping", "-c", "4", host]
            
            self.ping_btn.setEnabled(False)
            self.ping_btn.setText("Ping...")
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                
                if result.returncode == 0:
                    # Extraction du temps de ping (simplifié)
                    output = result.stdout
                    if "time=" in output or "temps=" in output:
                        # Analyse basique du résultat ping
                        lines = output.split('\n')
                        ping_times = []
                        
                        for line in lines:
                            if "time=" in line or "temps=" in line:
                                try:
                                    # Extraction du temps (format variable selon l'OS)
                                    import re
                                    match = re.search(r'time[=<](\d+(?:\.\d+)?)ms', line)
                                    if match:
                                        ping_times.append(float(match.group(1)))
                                except:
                                    pass
                        
                        if ping_times:
                            avg_ping = sum(ping_times) / len(ping_times)
                            self.last_ping_time = avg_ping
                            self.log_connection(f"🏓 Ping vers {host}: {avg_ping:.1f}ms")
                            self.status_labels["ping"].setText(f"{avg_ping:.1f}ms")
                        else:
                            self.log_connection(f"🏓 Ping vers {host}: succès")
                    else:
                        self.log_connection(f"🏓 Ping vers {host}: succès")
                else:
                    self.log_connection(f"❌ Ping vers {host}: échec")
                    
            except subprocess.TimeoutExpired:
                self.log_connection(f"⏱️ Ping vers {host}: timeout")
            except Exception as e:
                self.log_connection(f"❌ Erreur ping: {e}")
            
        finally:
            self.ping_btn.setEnabled(True)
            self.ping_btn.setText("Ping")
    
    def auto_ping(self):
        """Ping automatique si connecté"""
        if (self.main_window.client and 
            self.main_window.client.connected and 
            self.host_input.text().strip()):
            self.ping_server()
    
    def save_connection_config(self):
        """Sauvegarde la configuration de connexion"""
        config_update = {
            'server_host': self.host_input.text().strip(),
            'server_port': self.port_input.value(),
            'auto_connect': self.auto_connect_check.isChecked()
        }
        
        self.main_window.update_client_config(config_update)
        
        QMessageBox.information(self, "Configuration", "Configuration de connexion sauvegardée")
        self.log_connection("💾 Configuration sauvegardée")
    
    def update_data(self, stats: Dict[str, Any]):
        """Met à jour les données du panneau"""
        if not self.main_window.client:
            return
        
        client = self.main_window.client
        
        # Mise à jour du statut
        if client.connected:
            self.status_labels["state"].setText("Connecté")
            self.status_labels["state"].setStyleSheet("color: green; font-weight: bold;")
            self.status_labels["server"].setText(f"{client.server_host}:{client.server_port}")
            
            # Temps de connexion
            if hasattr(client, 'connection_start_time'):
                uptime = time.time() - client.connection_start_time
                hours = int(uptime // 3600)
                minutes = int((uptime % 3600) // 60)
                self.status_labels["uptime"].setText(f"{hours:02d}:{minutes:02d}")
            
            # Dernière activité
            if hasattr(client, 'last_activity'):
                elapsed = time.time() - client.last_activity
                if elapsed < 60:
                    self.status_labels["last_activity"].setText(f"{int(elapsed)}s")
                else:
                    self.status_labels["last_activity"].setText(f"{int(elapsed//60)}m")
            
            # Ping
            if self.last_ping_time > 0:
                self.status_labels["ping"].setText(f"{self.last_ping_time:.1f}ms")
                
                # Qualité de connexion basée sur le ping
                if self.last_ping_time < 50:
                    quality = "Excellente"
                    color = "green"
                elif self.last_ping_time < 100:
                    quality = "Bonne"
                    color = "orange"
                else:
                    quality = "Moyenne"
                    color = "red"
                
                self.status_labels["quality"].setText(quality)
                self.status_labels["quality"].setStyleSheet(f"color: {color}; font-weight: bold;")
        else:
            self.status_labels["state"].setText("Déconnecté")
            self.status_labels["state"].setStyleSheet("color: red; font-weight: bold;")
            self.status_labels["server"].setText("-")
            self.status_labels["uptime"].setText("-")
            self.status_labels["last_activity"].setText("-")
            self.status_labels["ping"].setText("-")
            self.status_labels["quality"].setText("-")
        
        # Informations du client
        if hasattr(client, 'mac_address'):
            self.client_labels["mac"].setText(client.mac_address)
        
        if hasattr(client, 'client_id'):
            client_id = client.client_id[:8] + "..." if len(client.client_id) > 8 else client.client_id
            self.client_labels["client_id"].setText(client_id)
        
        self.client_labels["version"].setText("1.0.0")
        
        # Capacités
        capabilities = []
        if hasattr(client, 'upscaler') and client.upscaler.is_available():
            capabilities.append("Real-ESRGAN")
        
        self.client_labels["capabilities"].setText(", ".join(capabilities) if capabilities else "Aucune")
    
    def log_connection(self, message: str):
        """Ajoute un message au journal de connexion"""
        timestamp = time.strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        
        self.connection_log.append(log_entry)
        
        # Limitation du nombre de lignes
        document = self.connection_log.document()
        if document.blockCount() > 100:
            cursor = self.connection_log.textCursor()
            cursor.movePosition(cursor.Start)
            cursor.select(cursor.BlockUnderCursor)
            cursor.removeSelectedText()