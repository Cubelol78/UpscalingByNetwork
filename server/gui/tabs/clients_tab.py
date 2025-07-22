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
                    self.clients_table.setItem(row, 0, QTableWidgetItem(client['mac_address'][:17]))
                    self.clients_table.setItem(row, 1, QTableWidgetItem(client['ip_address']))
                    self.clients_table.setItem(row, 2, QTableWidgetItem(client['hostname']))
                    self.clients_table.setItem(row, 3, QTableWidgetItem(client['platform']))
                    
                    status_item = QTableWidgetItem(client['status'])
                    if client['is_online']:
                        status_item.setBackground(QColor(144, 238, 144))
                    else:
                        status_item.setBackground(QColor(255, 182, 193))
                    self.clients_table.setItem(row, 4, status_item)
                    
                    self.clients_table.setItem(row, 5, QTableWidgetItem(client['current_batch'] or "Aucun"))
                    self.clients_table.setItem(row, 6, QTableWidgetItem(str(client['batches_completed'])))
                    self.clients_table.setItem(row, 7, QTableWidgetItem(f"{client['success_rate']:.1f}%"))
                    self.clients_table.setItem(row, 8, QTableWidgetItem(f"{client['average_batch_time']:.1f}s"))
                    self.clients_table.setItem(row, 9, QTableWidgetItem(format_duration(client['connection_time'])))
    
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