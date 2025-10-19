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
        self.cpu_chart.setLabel('left', 'Pourcentage', color='#e0e0e0')
        self.cpu_chart.setLabel('bottom', 'Temps', color='#e0e0e0')
        self.cpu_chart.showGrid(x=True, y=True, alpha=0.3)
        self.cpu_chart.setBackground('#2b2b2b')
        self.cpu_chart.getAxis('left').setTextPen('#e0e0e0')
        self.cpu_chart.getAxis('bottom').setTextPen('#e0e0e0')
        self.cpu_chart.getAxis('left').setPen('#555555')
        self.cpu_chart.getAxis('bottom').setPen('#555555')

        # Memory Usage
        self.memory_chart = pg.PlotWidget(title="Utilisation Mémoire")
        self.memory_chart.setLabel('left', 'Pourcentage', color='#e0e0e0')
        self.memory_chart.setLabel('bottom', 'Temps', color='#e0e0e0')
        self.memory_chart.showGrid(x=True, y=True, alpha=0.3)
        self.memory_chart.setBackground('#2b2b2b')
        self.memory_chart.getAxis('left').setTextPen('#e0e0e0')
        self.memory_chart.getAxis('bottom').setTextPen('#e0e0e0')
        self.memory_chart.getAxis('left').setPen('#555555')
        self.memory_chart.getAxis('bottom').setPen('#555555')

        # Network I/O
        self.network_chart = pg.PlotWidget(title="Trafic Réseau")
        self.network_chart.setLabel('left', 'MB/s', color='#e0e0e0')
        self.network_chart.setLabel('bottom', 'Temps', color='#e0e0e0')
        self.network_chart.showGrid(x=True, y=True, alpha=0.3)
        self.network_chart.setBackground('#2b2b2b')
        self.network_chart.getAxis('left').setTextPen('#e0e0e0')
        self.network_chart.getAxis('bottom').setTextPen('#e0e0e0')
        self.network_chart.getAxis('left').setPen('#555555')
        self.network_chart.getAxis('bottom').setPen('#555555')

        # Processing Rate
        self.rate_chart = pg.PlotWidget(title="Taux de Traitement")
        self.rate_chart.setLabel('left', 'Lots/min', color='#e0e0e0')
        self.rate_chart.setLabel('bottom', 'Temps', color='#e0e0e0')
        self.rate_chart.showGrid(x=True, y=True, alpha=0.3)
        self.rate_chart.setBackground('#2b2b2b')
        self.rate_chart.getAxis('left').setTextPen('#e0e0e0')
        self.rate_chart.getAxis('bottom').setTextPen('#e0e0e0')
        self.rate_chart.getAxis('left').setPen('#555555')
        self.rate_chart.getAxis('bottom').setPen('#555555')
        
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
                self.cpu_chart.plot(timestamps_cpu, cpu_data, pen=pg.mkPen(color='#f44336', width=2))

            # Memory Usage
            timestamps_mem, memory_data = performance_monitor.get_time_series_data('memory_usage', 60)
            if timestamps_mem and memory_data:
                self.memory_chart.clear()
                self.memory_chart.plot(timestamps_mem, memory_data, pen=pg.mkPen(color='#2196F3', width=2))

            # Network I/O
            timestamps_net, network_data = performance_monitor.get_time_series_data('network_io', 60)
            if timestamps_net and network_data:
                self.network_chart.clear()
                # Conversion en MB/s (les données sont en bytes)
                network_mbps = [x / (1024*1024) if isinstance(x, (int, float)) else 0 for x in network_data]
                self.network_chart.plot(timestamps_net, network_mbps, pen=pg.mkPen(color='#4CAF50', width=2))

            # Processing Rate
            timestamps_rate, rate_data = performance_monitor.get_time_series_data('processing_rate', 60)
            if timestamps_rate and rate_data:
                self.rate_chart.clear()
                self.rate_chart.plot(timestamps_rate, rate_data, pen=pg.mkPen(color='#FF9800', width=2))
                
        except Exception as e:
            print(f"Erreur mise à jour graphiques performance: {e}")