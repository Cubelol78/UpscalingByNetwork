"""
Onglet clients
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                            QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from utils.file_utils import format_duration

class ClientsTab(QWidget):
    """Onglet clients"""
    
    def __init__(self, server, main_window):
        super().__init__()
        self.server = server
        self.main_window = main_window
        self.setup_ui()
    
    def setup_ui(self):
        """Configuration de l'interface"""
        layout = QVBoxLayout(self)
        
        # Barre d'outils
        toolbar_layout = QHBoxLayout()
        
        refresh_btn = QPushButton("Actualiser")
        refresh_btn.clicked.connect(self.refresh_clients)
        
        self.disconnect_btn = QPushButton("Déconnecter Client")
        self.disconnect_btn.clicked.connect(self.disconnect_selected_client)
        self.disconnect_btn.setEnabled(False)
        
        toolbar_layout.addWidget(refresh_btn)
        toolbar_layout.addWidget(self.disconnect_btn)
        toolbar_layout.addStretch()
        
        # Tableau des clients
        self.clients_table = QTableWidget()
        self.clients_table.setColumnCount(10)
        self.clients_table.setHorizontalHeaderLabels([
            "MAC", "IP", "Hostname", "Platform", "Status", 
            "Lot actuel", "Lots terminés", "Taux succès", 
            "Temps moy.", "Connexion"
        ])
        
        # Configuration du tableau
        header = self.clients_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        
        self.clients_table.selectionModel().selectionChanged.connect(
            lambda: self.disconnect_btn.setEnabled(
                len(self.clients_table.selectionModel().selectedRows()) > 0
            )
        )
        
        layout.addLayout(toolbar_layout)
        layout.addWidget(self.clients_table)
    
    def update_tab(self):
        """Met à jour l'onglet clients"""
        if hasattr(self.server, 'client_manager'):
            clients_stats = self.server.client_manager.get_all_clients_stats()
            self.clients_table.setRowCount(len(clients_stats))

            for row, client in enumerate(clients_stats):
                if client:
                    # MAC address with tooltip showing full MAC and hardware info
                    mac_item = QTableWidgetItem(client['mac_address'][:17])
                    mac_tooltip = f"<b>Full MAC Address:</b> {client['mac_address']}"
                    if client.get('gpu_info'):
                        mac_tooltip += f"<br><b>GPU:</b> {client['gpu_info']}"
                    if client.get('cpu_info'):
                        mac_tooltip += f"<br><b>CPU:</b> {client['cpu_info']}"
                    mac_item.setToolTip(mac_tooltip)
                    self.clients_table.setItem(row, 0, mac_item)

                    # IP address with tooltip
                    ip_item = QTableWidgetItem(client['ip_address'])
                    ip_item.setToolTip(f"IP Address: {client['ip_address']}")
                    self.clients_table.setItem(row, 1, ip_item)

                    # Hostname with tooltip
                    hostname_item = QTableWidgetItem(client['hostname'])
                    hostname_item.setToolTip(f"Hostname: {client['hostname']}<br>Platform: {client['platform']}")
                    self.clients_table.setItem(row, 2, hostname_item)

                    # Platform with tooltip
                    platform_item = QTableWidgetItem(client['platform'])
                    platform_item.setToolTip(f"Platform: {client['platform']}")
                    self.clients_table.setItem(row, 3, platform_item)

                    # Status with rich tooltip
                    status_item = QTableWidgetItem(client['status'])
                    status_tooltip = f"<b>Status:</b> {client['status']}<br>"
                    status_tooltip += f"<b>Connected At:</b> {client['connected_at']}<br>"
                    status_tooltip += f"<b>Last Heartbeat:</b> {client['last_heartbeat']}<br>"
                    status_tooltip += f"<b>Connection Time:</b> {format_duration(client['connection_time'])}"
                    status_item.setToolTip(status_tooltip)
                    if client['is_online']:
                        status_item.setBackground(QColor(13, 115, 119))  # Dark teal for online
                        status_item.setForeground(QColor(255, 255, 255))  # White text
                    else:
                        status_item.setBackground(QColor(244, 67, 54))  # Red for offline
                        status_item.setForeground(QColor(255, 255, 255))  # White text
                    self.clients_table.setItem(row, 4, status_item)

                    # Current batch with tooltip
                    batch_display = client['current_batch'][:8] + "..." if client['current_batch'] and len(client['current_batch']) > 8 else (client['current_batch'] or "Aucun")
                    batch_item = QTableWidgetItem(batch_display)
                    if client['current_batch']:
                        batch_item.setToolTip(f"Full Batch ID: {client['current_batch']}")
                    else:
                        batch_item.setToolTip("No batch currently assigned")
                    self.clients_table.setItem(row, 5, batch_item)

                    # Batches completed with tooltip
                    completed_item = QTableWidgetItem(str(client['batches_completed']))
                    completed_tooltip = f"<b>Batches Completed:</b> {client['batches_completed']}<br>"
                    completed_tooltip += f"<b>Batches Failed:</b> {client['batches_failed']}<br>"
                    completed_tooltip += f"<b>Total Batches:</b> {client['batches_completed'] + client['batches_failed']}"
                    completed_item.setToolTip(completed_tooltip)
                    self.clients_table.setItem(row, 6, completed_item)

                    # Success rate with tooltip
                    success_item = QTableWidgetItem(f"{client['success_rate']:.1f}%")
                    success_tooltip = f"<b>Success Rate:</b> {client['success_rate']:.2f}%<br>"
                    success_tooltip += f"<b>Successful:</b> {client['batches_completed']}<br>"
                    success_tooltip += f"<b>Failed:</b> {client['batches_failed']}"
                    success_item.setToolTip(success_tooltip)
                    self.clients_table.setItem(row, 7, success_item)

                    # Average batch time with tooltip
                    avg_time_item = QTableWidgetItem(f"{client['average_batch_time']:.1f}s")
                    avg_time_item.setToolTip(f"Average Batch Processing Time: {client['average_batch_time']:.2f} seconds")
                    self.clients_table.setItem(row, 8, avg_time_item)

                    # Connection time with tooltip
                    conn_time_item = QTableWidgetItem(format_duration(client['connection_time']))
                    conn_time_item.setToolTip(f"Total Connection Time: {format_duration(client['connection_time'])}")
                    self.clients_table.setItem(row, 9, conn_time_item)
    
    def refresh_clients(self):
        """Actualise la liste des clients"""
        self.update_tab()
    
    def disconnect_selected_client(self):
        """Déconnecte le client sélectionné"""
        selected_rows = self.clients_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        
        row = selected_rows[0].row()
        mac_address = self.clients_table.item(row, 0).text()
        
        reply = QMessageBox.question(
            self, "Confirmation", f"Déconnecter le client {mac_address}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if hasattr(self.server, 'client_manager'):
                success = self.server.client_manager.disconnect_client(mac_address)
                if success:
                    QMessageBox.information(self, "Succès", "Client déconnecté")
                    self.refresh_clients()
                else:
                    QMessageBox.warning(self, "Erreur", "Impossible de déconnecter le client")