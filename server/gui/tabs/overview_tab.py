"""
Onglet vue d'ensemble
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
                            QGroupBox, QGridLayout, QLabel, QTableWidget,
                            QTableWidgetItem, QHeaderView)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor
import pyqtgraph as pg

from utils.performance_monitor import performance_monitor
from utils.file_utils import format_duration

class OverviewTab(QWidget):
    """Onglet vue d'ensemble"""
    
    def __init__(self, server, main_window):
        super().__init__()
        self.server = server
        self.main_window = main_window
        self.setup_ui()
    
    def setup_ui(self):
        """Configuration de l'interface"""
        layout = QVBoxLayout(self)
        
        # Splitter horizontal
        splitter = QSplitter(Qt.Horizontal)
        
        # Partie gauche - Graphiques
        left_widget = self.create_charts_section()
        
        # Partie droite - Informations détaillées
        right_widget = self.create_info_section()
        
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([800, 400])
        
        layout.addWidget(splitter)
    
    def create_charts_section(self):
        """Crée la section des graphiques"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Graphique temps réel des clients
        self.clients_chart = pg.PlotWidget(title="Clients connectés")
        self.clients_chart.setLabel('left', 'Nombre', size='10pt')
        self.clients_chart.setLabel('bottom', 'Temps', size='10pt')
        self.clients_chart.showGrid(x=True, y=True, alpha=0.3)
        self.clients_chart.setMinimumHeight(220)
        self.clients_chart.setBackground('black')
        self.clients_chart.getAxis('left').setTextPen('white')
        self.clients_chart.getAxis('bottom').setTextPen('white')
        
        # Graphique des lots
        self.batches_chart = pg.PlotWidget(title="Progression des lots")
        self.batches_chart.setLabel('left', 'Lots', size='10pt')
        self.batches_chart.setLabel('bottom', 'Temps', size='10pt')
        self.batches_chart.showGrid(x=True, y=True, alpha=0.3)
        self.batches_chart.setMinimumHeight(220)
        self.batches_chart.setBackground('black')
        self.batches_chart.getAxis('left').setTextPen('white')
        self.batches_chart.getAxis('bottom').setTextPen('white')
        
        layout.addWidget(self.clients_chart)
        layout.addWidget(self.batches_chart)
        
        return widget
    
    def create_info_section(self):
        """Crée la section des informations"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Informations système
        system_group = QGroupBox("Système")
        system_layout = QGridLayout(system_group)
        system_layout.setSpacing(8)
        system_layout.setContentsMargins(10, 15, 10, 10)
        
        system_layout.addWidget(QLabel("Utilisation:"), 0, 0)
        
        self.cpu_usage_label = QLabel("CPU: 0%")
        self.cpu_usage_label.setStyleSheet("font-weight: bold; color: #4CAF50;")
        
        self.memory_usage_label = QLabel("RAM: 0%")
        self.memory_usage_label.setStyleSheet("font-weight: bold; color: #2196F3;")
        
        self.disk_usage_label = QLabel("Disque: 0%")
        self.disk_usage_label.setStyleSheet("font-weight: bold; color: #FF9800;")
        
        self.uptime_label = QLabel("Uptime: 0s")
        self.uptime_label.setStyleSheet("font-weight: bold; color: #9C27B0;")
        
        system_layout.addWidget(self.cpu_usage_label, 1, 0)
        system_layout.addWidget(self.memory_usage_label, 2, 0)
        system_layout.addWidget(self.disk_usage_label, 3, 0)
        system_layout.addWidget(self.uptime_label, 4, 0)
        
        # Statistiques de performance
        perf_group = QGroupBox("Performance")
        perf_layout = QGridLayout(perf_group)
        perf_layout.setSpacing(8)
        perf_layout.setContentsMargins(10, 15, 10, 10)
        
        self.avg_batch_time_label = QLabel("Temps moyen/lot: N/A")
        self.avg_batch_time_label.setStyleSheet("font-size: 11px;")
        
        self.processing_rate_label = QLabel("Taux de traitement: N/A")
        self.processing_rate_label.setStyleSheet("font-size: 11px;")
        
        self.total_processed_label = QLabel("Total traité: 0")
        self.total_processed_label.setStyleSheet("font-size: 11px; font-weight: bold;")
        
        perf_layout.addWidget(self.avg_batch_time_label, 0, 0)
        perf_layout.addWidget(self.processing_rate_label, 1, 0)
        perf_layout.addWidget(self.total_processed_label, 2, 0)
        
        # Top clients
        top_clients_group = QGroupBox("Top Clients")
        top_clients_layout = QVBoxLayout(top_clients_group)
        top_clients_layout.setContentsMargins(10, 15, 10, 10)
        
        self.top_clients_table = QTableWidget(5, 3)
        self.top_clients_table.setHorizontalHeaderLabels(["Client", "Lots", "Taux"])
        self.top_clients_table.horizontalHeader().setStretchLastSection(True)
        self.top_clients_table.setAlternatingRowColors(True)
        self.top_clients_table.setMinimumHeight(180)
        
        self.top_clients_table.setStyleSheet("""
            QTableWidget {
                gridline-color: #444;
                font-size: 10px;
            }
            QHeaderView::section {
                background-color: #555;
                padding: 5px;
                border: 1px solid #666;
                font-weight: bold;
            }
        """)
        
        top_clients_layout.addWidget(self.top_clients_table)
        
        layout.addWidget(system_group)
        layout.addWidget(perf_group)
        layout.addWidget(top_clients_group)
        layout.addStretch()
        
        return widget
    
    def update_tab(self, stats):
        """Met à jour l'onglet avec les statistiques"""
        self.update_top_clients()
        
        perf_stats = performance_monitor.get_current_stats()
        if 'cpu_usage' in perf_stats:
            self.cpu_usage_label.setText(f"CPU: {perf_stats['cpu_usage']['current']:.1f}%")
        if 'memory_usage' in perf_stats:
            self.memory_usage_label.setText(f"RAM: {perf_stats['memory_usage']['current']:.1f}%")
        
        uptime = stats['server']['uptime']
        self.uptime_label.setText(f"Uptime: {format_duration(uptime)}")
    
    def update_top_clients(self):
        """Met à jour le tableau des top clients"""
        clients = list(self.server.clients.values())
        clients.sort(key=lambda c: c.batches_completed, reverse=True)
        
        for row in range(min(5, len(clients))):
            client = clients[row]
            self.top_clients_table.setItem(row, 0, QTableWidgetItem(client.hostname or client.mac_address[:8]))
            self.top_clients_table.setItem(row, 1, QTableWidgetItem(str(client.batches_completed)))
            self.top_clients_table.setItem(row, 2, QTableWidgetItem(f"{client.success_rate:.1f}%"))
    
    def update_charts(self):
        """Met à jour les graphiques"""
        try:
            # Mise à jour du graphique des clients
            timestamps_clients, clients_data = performance_monitor.get_time_series_data('client_count', 60)
            if timestamps_clients and clients_data:
                self.clients_chart.clear()
                self.clients_chart.plot(timestamps_clients, clients_data, pen='g')
            
            # Mise à jour du graphique des lots
            timestamps_batches, batches_data = performance_monitor.get_time_series_data('batch_queue_size', 60)
            if timestamps_batches and batches_data:
                self.batches_chart.clear()
                self.batches_chart.plot(timestamps_batches, batches_data, pen='y')
                
        except Exception as e:
            print(f"Erreur mise à jour graphiques overview: {e}")