"""
Panneau de surveillance des clients et performances
UpscalingByNetwork/server/gui/monitoring_panel.py
"""

import time
from typing import Dict, Any
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QGridLayout,
    QLabel, QTableWidget, QTableWidgetItem, QProgressBar, QPushButton,
    QSplitter, QFrame, QHeaderView, QAbstractItemView, QTextEdit,
    QScrollArea, QComboBox, QCheckBox, QSpinBox
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QPalette, QColor

class MonitoringPanel(QWidget):
    """Panneau de surveillance en temps réel"""
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setup_ui()
        
        # Données de monitoring
        self.last_stats = {}
        self.last_clients = {}
        
        # Timer pour graphiques en temps réel
        self.chart_timer = QTimer()
        self.chart_timer.timeout.connect(self.update_charts)
        self.chart_timer.start(2000)  # Mise à jour toutes les 2 secondes
        
        # Historique pour graphiques
        self.performance_history = []
        self.max_history_points = 100
    
    def setup_ui(self):
        """Configure l'interface du panneau"""
        layout = QVBoxLayout(self)
        
        # Splitter principal
        main_splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(main_splitter)
        
        # Partie gauche: Vue d'ensemble et graphiques
        left_widget = self.create_left_panel()
        main_splitter.addWidget(left_widget)
        
        # Partie droite: Détails clients
        right_widget = self.create_right_panel()
        main_splitter.addWidget(right_widget)
        
        # Proportions
        main_splitter.setSizes([600, 800])
    
    def create_left_panel(self):
        """Crée le panneau gauche avec vue d'ensemble"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Vue d'ensemble du serveur
        overview_group = self.create_server_overview()
        layout.addWidget(overview_group)
        
        # Graphiques de performance
        performance_group = self.create_performance_charts()
        layout.addWidget(performance_group)
        
        # Alertes et notifications
        alerts_group = self.create_alerts_panel()
        layout.addWidget(alerts_group)
        
        return widget
    
    def create_server_overview(self):
        """Crée la vue d'ensemble du serveur"""
        group = QGroupBox("Vue d'ensemble du serveur")
        layout = QGridLayout(group)
        
        # Métriques principales
        metrics = [
            ("Clients connectés", "clients_connected"),
            ("Clients actifs", "clients_active"),
            ("Jobs en cours", "jobs_active"),
            ("Lots en attente", "batches_pending"),
            ("Lots en traitement", "batches_processing"),
            ("Lots terminés", "batches_completed"),
            ("Débit (img/min)", "throughput"),
            ("Charge CPU", "cpu_usage")
        ]
        
        self.overview_labels = {}
        
        for i, (label, key) in enumerate(metrics):
            row, col = i // 2, (i % 2) * 2
            
            layout.addWidget(QLabel(f"{label}:"), row, col)
            
            value_label = QLabel("0")
            value_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #0078d4;")
            layout.addWidget(value_label, row, col + 1)
            
            self.overview_labels[key] = value_label
        
        return group
    
    def create_performance_charts(self):
        """Crée les graphiques de performance"""
        group = QGroupBox("Graphiques de performance")
        layout = QVBoxLayout(group)
        
        # Placeholder pour graphiques
        # Dans une vraie implémentation, on utiliserait matplotlib ou pyqtgraph
        
        chart_widget = QWidget()
        chart_widget.setMinimumHeight(200)
        chart_widget.setStyleSheet("""
            QWidget {
                background-color: white;
                border: 1px solid #d0d0d0;
                border-radius: 4px;
            }
        """)
        
        chart_layout = QVBoxLayout(chart_widget)
        
        self.chart_label = QLabel("Graphiques de performance en temps réel")
        self.chart_label.setAlignment(Qt.AlignCenter)
        self.chart_label.setStyleSheet("color: #666; font-style: italic;")
        chart_layout.addWidget(self.chart_label)
        
        # Contrôles des graphiques
        controls_layout = QHBoxLayout()
        
        self.chart_type_combo = QComboBox()
        self.chart_type_combo.addItems([
            "Débit (images/minute)",
            "Clients actifs",
            "Charge CPU",
            "Utilisation réseau"
        ])
        controls_layout.addWidget(QLabel("Affichage:"))
        controls_layout.addWidget(self.chart_type_combo)
        
        controls_layout.addStretch()
        
        reset_chart_btn = QPushButton("Réinitialiser")
        reset_chart_btn.clicked.connect(self.reset_charts)
        controls_layout.addWidget(reset_chart_btn)
        
        layout.addWidget(chart_widget)
        layout.addLayout(controls_layout)
        
        return group
    
    def create_alerts_panel(self):
        """Crée le panneau d'alertes"""
        group = QGroupBox("Alertes et notifications")
        layout = QVBoxLayout(group)
        
        self.alerts_text = QTextEdit()
        self.alerts_text.setMaximumHeight(120)
        self.alerts_text.setReadOnly(True)
        self.alerts_text.setStyleSheet("""
            QTextEdit {
                background-color: #fff8dc;
                border: 1px solid #ddd;
                font-family: Consolas, monospace;
                font-size: 10px;
            }
        """)
        layout.addWidget(self.alerts_text)
        
        # Contrôles d'alertes
        controls_layout = QHBoxLayout()
        
        clear_alerts_btn = QPushButton("Effacer")
        clear_alerts_btn.clicked.connect(self.clear_alerts)
        controls_layout.addWidget(clear_alerts_btn)
        
        self.enable_alerts_check = QCheckBox("Alertes activées")
        self.enable_alerts_check.setChecked(True)
        controls_layout.addWidget(self.enable_alerts_check)
        
        controls_layout.addStretch()
        layout.addLayout(controls_layout)
        
        return group
    
    def create_right_panel(self):
        """Crée le panneau droit avec détails clients"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Tableau des clients
        clients_group = self.create_clients_table()
        layout.addWidget(clients_group)
        
        # Détails du client sélectionné
        details_group = self.create_client_details()
        layout.addWidget(details_group)
        
        return widget
    
    def create_clients_table(self):
        """Crée le tableau des clients connectés"""
        group = QGroupBox("Clients connectés")
        layout = QVBoxLayout(group)
        
        # Contrôles du tableau
        controls_layout = QHBoxLayout()
        
        refresh_btn = QPushButton("Actualiser")
        refresh_btn.clicked.connect(self.refresh_clients_table)
        controls_layout.addWidget(refresh_btn)
        
        disconnect_btn = QPushButton("Déconnecter")
        disconnect_btn.clicked.connect(self.disconnect_selected_client)
        controls_layout.addWidget(disconnect_btn)
        
        controls_layout.addStretch()
        
        self.auto_refresh_check = QCheckBox("Actualisation auto")
        self.auto_refresh_check.setChecked(True)
        controls_layout.addWidget(self.auto_refresh_check)
        
        layout.addLayout(controls_layout)
        
        # Tableau
        self.clients_table = QTableWidget()
        self.clients_table.setColumnCount(8)
        self.clients_table.setHorizontalHeaderLabels([
            "Adresse MAC", "Statut", "Lot actuel", "Progression", 
            "Lots traités", "Taux succès", "Vitesse", "Dernière activité"
        ])
        
        # Configuration du tableau
        header = self.clients_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # MAC
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Statut
        header.setSectionResizeMode(3, QHeaderView.Fixed)             # Progression
        header.resizeSection(3, 120)  # Largeur fixe pour la barre de progression
        
        self.clients_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.clients_table.itemSelectionChanged.connect(self.on_client_selected)
        
        layout.addWidget(self.clients_table)
        
        return group
    
    def create_client_details(self):
        """Crée le panneau de détails d'un client"""
        group = QGroupBox("Détails du client")
        layout = QVBoxLayout(group)
        
        # Informations générales
        info_layout = QGridLayout()
        
        self.detail_labels = {}
        details = [
            ("MAC:", "mac"),
            ("IP:", "ip"),
            ("Statut:", "status"),
            ("Connecté depuis:", "connected_since"),
            ("Lots traités:", "batches_completed"),
            ("Lots échoués:", "batches_failed"),
            ("Temps total:", "total_time"),
            ("Vitesse moyenne:", "avg_speed")
        ]
        
        for i, (label, key) in enumerate(details):
            row, col = i // 2, (i % 2) * 2
            
            info_layout.addWidget(QLabel(label), row, col)
            
            value_label = QLabel("-")
            value_label.setStyleSheet("font-weight: bold;")
            info_layout.addWidget(value_label, row, col + 1)
            
            self.detail_labels[key] = value_label
        
        layout.addLayout(info_layout)
        
        # Informations système
        system_group = QGroupBox("Informations système")
        system_layout = QGridLayout(system_group)
        
        self.system_labels = {}
        system_info = [
            ("OS:", "os"),
            ("CPU:", "cpu"),
            ("RAM:", "ram"),
            ("GPU:", "gpu"),
            ("Charge CPU:", "cpu_load"),
            ("Utilisation RAM:", "ram_usage")
        ]
        
        for i, (label, key) in enumerate(system_info):
            row, col = i // 2, (i % 2) * 2
            
            system_layout.addWidget(QLabel(label), row, col)
            
            value_label = QLabel("-")
            system_layout.addWidget(value_label, row, col + 1)
            
            self.system_labels[key] = value_label
        
        layout.addWidget(system_group)
        
        # Actions client
        actions_layout = QHBoxLayout()
        
        ping_btn = QPushButton("Ping")
        ping_btn.clicked.connect(self.ping_client)
        actions_layout.addWidget(ping_btn)
        
        reset_stats_btn = QPushButton("Réinitialiser stats")
        reset_stats_btn.clicked.connect(self.reset_client_stats)
        actions_layout.addWidget(reset_stats_btn)
        
        actions_layout.addStretch()
        layout.addLayout(actions_layout)
        
        return group
    
    def update_data(self, stats: Dict[str, Any], clients: Dict[str, Any]):
        """Met à jour les données du panneau"""
        self.last_stats = stats
        self.last_clients = clients
        
        # Mise à jour vue d'ensemble
        self.update_overview(stats)
        
        # Mise à jour tableau clients
        if self.auto_refresh_check.isChecked():
            self.update_clients_table(clients)
        
        # Vérification d'alertes
        self.check_alerts(stats, clients)
        
        # Ajout aux données de performance
        self.add_performance_data(stats)
    
    def update_overview(self, stats: Dict[str, Any]):
        """Met à jour la vue d'ensemble"""
        try:
            self.overview_labels["clients_connected"].setText(str(stats.get('active_clients', 0)))
            
            # Calcul des clients actifs (en traitement)
            active_clients = sum(1 for client in self.last_clients.values() 
                               if client.get('status') == 'processing')
            self.overview_labels["clients_active"].setText(str(active_clients))
            
            self.overview_labels["jobs_active"].setText(str(stats.get('total_jobs', 0)))
            
            # Calcul des lots par statut
            pending_batches = sum(1 for batch in getattr(self.main_window.server, 'batches', {}).values()
                                if getattr(batch, 'status', None) and batch.status.value == 'pending')
            processing_batches = sum(1 for batch in getattr(self.main_window.server, 'batches', {}).values()
                                   if getattr(batch, 'status', None) and batch.status.value == 'processing')
            
            self.overview_labels["batches_pending"].setText(str(pending_batches))
            self.overview_labels["batches_processing"].setText(str(processing_batches))
            self.overview_labels["batches_completed"].setText(str(stats.get('completed_batches', 0)))
            
            # Calcul du débit (images par minute)
            total_time = stats.get('uptime', 1)
            if total_time > 0:
                # Estimation basée sur le nombre de lots complétés * taille moyenne des lots
                completed_images = stats.get('completed_batches', 0) * 50  # 50 images par lot en moyenne
                throughput = (completed_images / total_time) * 60  # par minute
                self.overview_labels["throughput"].setText(f"{throughput:.1f}")
            else:
                self.overview_labels["throughput"].setText("0")
            
            # Charge CPU (simulée)
            import psutil
            cpu_usage = psutil.cpu_percent()
            self.overview_labels["cpu_usage"].setText(f"{cpu_usage:.1f}%")
            
        except Exception as e:
            print(f"Erreur mise à jour overview: {e}")
    
    def update_clients_table(self, clients: Dict[str, Any]):
        """Met à jour le tableau des clients"""
        try:
            self.clients_table.setRowCount(len(clients))
            
            for row, (mac, client_data) in enumerate(clients.items()):
                # Adresse MAC
                self.clients_table.setItem(row, 0, QTableWidgetItem(mac))
                
                # Statut
                status = client_data.get('status', 'unknown')
                status_item = QTableWidgetItem(status.title())
                
                # Couleur selon le statut
                if status == 'processing':
                    status_item.setBackground(QColor(144, 238, 144))  # Vert clair
                elif status == 'idle':
                    status_item.setBackground(QColor(173, 216, 230))  # Bleu clair
                elif status == 'error':
                    status_item.setBackground(QColor(255, 182, 193))  # Rouge clair
                
                self.clients_table.setItem(row, 1, status_item)
                
                # Lot actuel
                current_batch = client_data.get('current_batch_id', 'Aucun')
                if current_batch and current_batch != 'Aucun':
                    # Affichage court de l'ID
                    short_id = current_batch.split('_')[-1] if '_' in current_batch else current_batch[:8]
                    self.clients_table.setItem(row, 2, QTableWidgetItem(short_id))
                else:
                    self.clients_table.setItem(row, 2, QTableWidgetItem('Aucun'))
                
                # Barre de progression
                progress = client_data.get('current_progress', 0)
                progress_bar = QProgressBar()
                progress_bar.setValue(int(progress))
                progress_bar.setStyleSheet("""
                    QProgressBar {
                        border: 1px solid #d0d0d0;
                        border-radius: 3px;
                        text-align: center;
                    }
                    QProgressBar::chunk {
                        background-color: #0078d4;
                        border-radius: 2px;
                    }
                """)
                self.clients_table.setCellWidget(row, 3, progress_bar)
                
                # Lots traités
                batches_completed = client_data.get('batches_completed', 0)
                self.clients_table.setItem(row, 4, QTableWidgetItem(str(batches_completed)))
                
                # Taux de succès
                success_rate = client_data.get('success_rate', 100.0)
                self.clients_table.setItem(row, 5, QTableWidgetItem(f"{success_rate:.1f}%"))
                
                # Vitesse moyenne
                avg_time = client_data.get('average_processing_time', 0)
                if avg_time > 0:
                    speed = f"{60/avg_time:.1f} img/min"
                else:
                    speed = "N/A"
                self.clients_table.setItem(row, 6, QTableWidgetItem(speed))
                
                # Dernière activité
                last_activity = client_data.get('last_activity', 0)
                if last_activity > 0:
                    elapsed = time.time() - last_activity
                    if elapsed < 60:
                        activity_text = f"{int(elapsed)}s"
                    elif elapsed < 3600:
                        activity_text = f"{int(elapsed//60)}m"
                    else:
                        activity_text = f"{int(elapsed//3600)}h"
                else:
                    activity_text = "N/A"
                
                self.clients_table.setItem(row, 7, QTableWidgetItem(activity_text))
            
        except Exception as e:
            print(f"Erreur mise à jour tableau clients: {e}")
    
    def on_client_selected(self):
        """Gestion de la sélection d'un client"""
        current_row = self.clients_table.currentRow()
        if current_row >= 0:
            mac_item = self.clients_table.item(current_row, 0)
            if mac_item:
                mac_address = mac_item.text()
                self.update_client_details(mac_address)
    
    def update_client_details(self, mac_address: str):
        """Met à jour les détails du client sélectionné"""
        try:
            if mac_address not in self.last_clients:
                return
            
            client_data = self.last_clients[mac_address]
            
            # Informations générales
            self.detail_labels["mac"].setText(mac_address)
            self.detail_labels["ip"].setText(client_data.get('ip_address', 'N/A'))
            self.detail_labels["status"].setText(client_data.get('status', 'unknown').title())
            
            # Temps de connexion
            connected_at = client_data.get('connected_at', 0)
            if connected_at > 0:
                elapsed = time.time() - connected_at
                hours = int(elapsed // 3600)
                minutes = int((elapsed % 3600) // 60)
                self.detail_labels["connected_since"].setText(f"{hours}h {minutes}m")
            else:
                self.detail_labels["connected_since"].setText("N/A")
            
            self.detail_labels["batches_completed"].setText(str(client_data.get('batches_completed', 0)))
            self.detail_labels["batches_failed"].setText(str(client_data.get('batches_failed', 0)))
            
            # Temps total de traitement
            total_time = client_data.get('total_processing_time', 0)
            if total_time > 0:
                hours = int(total_time // 3600)
                minutes = int((total_time % 3600) // 60)
                self.detail_labels["total_time"].setText(f"{hours}h {minutes}m")
            else:
                self.detail_labels["total_time"].setText("0")
            
            # Vitesse moyenne
            avg_time = client_data.get('average_processing_time', 0)
            if avg_time > 0:
                self.detail_labels["avg_speed"].setText(f"{60/avg_time:.1f} img/min")
            else:
                self.detail_labels["avg_speed"].setText("N/A")
            
            # Informations système
            system_info = client_data.get('system_info', {})
            self.system_labels["os"].setText(system_info.get('os', 'N/A'))
            self.system_labels["cpu"].setText(system_info.get('cpu', 'N/A'))
            self.system_labels["ram"].setText(f"{system_info.get('ram_gb', 0)} GB")
            self.system_labels["gpu"].setText(system_info.get('gpu', 'N/A'))
            
            # Charge système actuelle
            current_load = system_info.get('current_load', {})
            self.system_labels["cpu_load"].setText(f"{current_load.get('cpu_percent', 0):.1f}%")
            self.system_labels["ram_usage"].setText(f"{current_load.get('memory_percent', 0):.1f}%")
            
        except Exception as e:
            print(f"Erreur mise à jour détails client: {e}")
    
    def check_alerts(self, stats: Dict[str, Any], clients: Dict[str, Any]):
        """Vérifie et affiche les alertes"""
        if not self.enable_alerts_check.isChecked():
            return
        
        try:
            # Vérification clients déconnectés
            for mac, client_data in clients.items():
                if client_data.get('is_stale', False):
                    self.add_alert(f"⚠️ Client {mac} sans activité depuis longtemps", "warning")
                
                # Vérification taux d'échec élevé
                success_rate = client_data.get('success_rate', 100)
                if success_rate < 80:
                    self.add_alert(f"❌ Client {mac} taux d'échec élevé: {success_rate:.1f}%", "error")
            
            # Vérification charge serveur
            active_clients = stats.get('active_clients', 0)
            if active_clients == 0 and stats.get('total_batches', 0) > 0:
                self.add_alert("⏰ Aucun client disponible, lots en attente", "warning")
            
        except Exception as e:
            print(f"Erreur vérification alertes: {e}")
    
    def add_alert(self, message: str, level: str = "info"):
        """Ajoute une alerte"""
        timestamp = time.strftime("%H:%M:%S")
        
        # Couleur selon le niveau
        color = {
            "info": "#0078d4",
            "warning": "#ff8c00", 
            "error": "#dc3545"
        }.get(level, "#000000")
        
        formatted_message = f'<span style="color: {color};">[{timestamp}] {message}</span>'
        self.alerts_text.append(formatted_message)
        
        # Limiter le nombre de lignes
        document = self.alerts_text.document()
        if document.blockCount() > 50:
            cursor = self.alerts_text.textCursor()
            cursor.movePosition(cursor.Start)
            cursor.select(cursor.BlockUnderCursor)
            cursor.removeSelectedText()
    
    def add_performance_data(self, stats: Dict[str, Any]):
        """Ajoute des données pour les graphiques de performance"""
        current_time = time.time()
        
        data_point = {
            'timestamp': current_time,
            'throughput': stats.get('completed_batches', 0) * 50 / max(stats.get('uptime', 1), 1) * 60,
            'active_clients': stats.get('active_clients', 0),
            'cpu_usage': 0,  # À implémenter
            'network_usage': 0  # À implémenter
        }
        
        self.performance_history.append(data_point)
        
        # Limiter l'historique
        if len(self.performance_history) > self.max_history_points:
            self.performance_history.pop(0)
    
    def update_charts(self):
        """Met à jour les graphiques"""
        # Placeholder pour mise à jour des graphiques
        if self.performance_history:
            latest = self.performance_history[-1]
            chart_type = self.chart_type_combo.currentText()
            
            if "Débit" in chart_type:
                value = latest['throughput']
                self.chart_label.setText(f"Débit actuel: {value:.1f} images/minute")
            elif "Clients" in chart_type:
                value = latest['active_clients']
                self.chart_label.setText(f"Clients actifs: {value}")
    
    def refresh_clients_table(self):
        """Actualise manuellement le tableau des clients"""
        if self.last_clients:
            self.update_clients_table(self.last_clients)
    
    def disconnect_selected_client(self):
        """Déconnecte le client sélectionné"""
        current_row = self.clients_table.currentRow()
        if current_row >= 0:
            mac_item = self.clients_table.item(current_row, 0)
            if mac_item:
                mac_address = mac_item.text()
                # Ici on appellerait la méthode de déconnexion du serveur
                self.add_alert(f"Déconnexion forcée du client {mac_address}", "warning")
    
    def ping_client(self):
        """Envoie un ping au client sélectionné"""
        current_row = self.clients_table.currentRow()
        if current_row >= 0:
            mac_item = self.clients_table.item(current_row, 0)
            if mac_item:
                mac_address = mac_item.text()
                self.add_alert(f"Ping envoyé au client {mac_address}", "info")
    
    def reset_client_stats(self):
        """Réinitialise les statistiques du client sélectionné"""
        current_row = self.clients_table.currentRow()
        if current_row >= 0:
            mac_item = self.clients_table.item(current_row, 0)
            if mac_item:
                mac_address = mac_item.text()
                self.add_alert(f"Statistiques réinitialisées pour {mac_address}", "info")
    
    def reset_charts(self):
        """Réinitialise les graphiques"""
        self.performance_history.clear()
        self.chart_label.setText("Graphiques réinitialisés")
    
    def clear_alerts(self):
        """Efface toutes les alertes"""
        self.alerts_text.clear()