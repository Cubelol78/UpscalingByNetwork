"""
Onglet performance
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QGridLayout
import pyqtgraph as pg

from utils.performance_monitor import performance_monitor

class PerformanceTab(QWidget):
    """Onglet performance"""
    
    def __init__(self, server, main_window):
        super().__init__()
        self.server = server
        self.main_window = main_window
        self.setup_ui()
    
    def setup_ui(self):
        """Configuration de l'interface"""
        layout = QVBoxLayout(self)
        
        # Graphiques de performance
        charts_layout = QGridLayout()
        
        # CPU Usage
        self.cpu_chart = pg.PlotWidget(title="Utilisation CPU")
        self.cpu_chart.setLabel('left', 'Pourcentage')
        self.cpu_chart.setLabel('bottom', 'Temps')
        self.cpu_chart.showGrid(x=True, y=True)
        self.cpu_chart.setBackground('black')
        
        # Memory Usage
        self.memory_chart = pg.PlotWidget(title="Utilisation Mémoire")
        self.memory_chart.setLabel('left', 'Pourcentage')
        self.memory_chart.setLabel('bottom', 'Temps')
        self.memory_chart.showGrid(x=True, y=True)
        self.memory_chart.setBackground('black')
        
        # Network I/O
        self.network_chart = pg.PlotWidget(title="Trafic Réseau")
        self.network_chart.setLabel('left', 'MB/s')
        self.network_chart.setLabel('bottom', 'Temps')
        self.network_chart.showGrid(x=True, y=True)
        self.network_chart.setBackground('black')
        
        # Processing Rate
        self.rate_chart = pg.PlotWidget(title="Taux de Traitement")
        self.rate_chart.setLabel('left', 'Lots/min')
        self.rate_chart.setLabel('bottom', 'Temps')
        self.rate_chart.showGrid(x=True, y=True)
        self.rate_chart.setBackground('black')
        
        charts_layout.addWidget(self.cpu_chart, 0, 0)
        charts_layout.addWidget(self.memory_chart, 0, 1)
        charts_layout.addWidget(self.network_chart, 1, 0)
        charts_layout.addWidget(self.rate_chart, 1, 1)
        
        layout.addLayout(charts_layout)
    
    def update_charts(self):
        """Met à jour les graphiques de performance"""
        try:
            # CPU Usage
            timestamps_cpu, cpu_data = performance_monitor.get_time_series_data('cpu_usage', 60)
            if timestamps_cpu and cpu_data:
                self.cpu_chart.clear()
                self.cpu_chart.plot(timestamps_cpu, cpu_data, pen='r')
            
            # Memory Usage
            timestamps_mem, memory_data = performance_monitor.get_time_series_data('memory_usage', 60)
            if timestamps_mem and memory_data:
                self.memory_chart.clear()
                self.memory_chart.plot(timestamps_mem, memory_data, pen='b')
            
            # Network I/O
            timestamps_net, network_data = performance_monitor.get_time_series_data('network_io', 60)
            if timestamps_net and network_data:
                self.network_chart.clear()
                # Conversion en MB/s (les données sont en bytes)
                network_mbps = [x / (1024*1024) if isinstance(x, (int, float)) else 0 for x in network_data]
                self.network_chart.plot(timestamps_net, network_mbps, pen='g')
            
            # Processing Rate
            timestamps_rate, rate_data = performance_monitor.get_time_series_data('processing_rate', 60)
            if timestamps_rate and rate_data:
                self.rate_chart.clear()
                self.rate_chart.plot(timestamps_rate, rate_data, pen='y')
                
        except Exception as e:
            print(f"Erreur mise à jour graphiques performance: {e}")