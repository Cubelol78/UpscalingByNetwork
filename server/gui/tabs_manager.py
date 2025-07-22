"""
Gestionnaire des onglets de l'interface principale
"""

from PyQt5.QtWidgets import QTabWidget
from gui.tabs.overview_tab import OverviewTab
from gui.tabs.clients_tab import ClientsTab
from gui.tabs.jobs_tab import JobsTab
from gui.tabs.performance_tab import PerformanceTab
from gui.tabs.logs_tab import LogsTab
from gui.tabs.config_tab import ConfigTab

class TabsManager(QTabWidget):
    """Gestionnaire des onglets principaux"""
    
    def __init__(self, server, main_window):
        super().__init__()
        self.server = server
        self.main_window = main_window
        
        self.setup_tabs()
    
    def setup_tabs(self):
        """Configuration des onglets"""
        # Onglet Vue d'ensemble
        self.overview_tab = OverviewTab(self.server, self.main_window)
        self.addTab(self.overview_tab, "Vue d'ensemble")
        
        # Onglet Clients
        self.clients_tab = ClientsTab(self.server, self.main_window)
        self.addTab(self.clients_tab, "Clients")
        
        # Onglet Jobs & Lots
        self.jobs_tab = JobsTab(self.server, self.main_window)
        self.addTab(self.jobs_tab, "Jobs & Lots")
        
        # Onglet Performance
        self.performance_tab = PerformanceTab(self.server, self.main_window)
        self.addTab(self.performance_tab, "Performance")
        
        # Onglet Logs
        self.logs_tab = LogsTab(self.server, self.main_window)
        self.addTab(self.logs_tab, "Logs")
        
        # Onglet Configuration
        self.config_tab = ConfigTab(self.server, self.main_window)
        self.addTab(self.config_tab, "Configuration")
    
    def update_current_tab(self, stats):
        """Met à jour l'onglet actuellement visible"""
        current_tab = self.currentIndex()
        
        if current_tab == 0:  # Vue d'ensemble
            self.overview_tab.update_tab(stats)
        elif current_tab == 1:  # Clients
            self.clients_tab.update_tab()
        elif current_tab == 2:  # Jobs & Lots
            self.jobs_tab.update_tab()
    
    def update_performance_charts(self):
        """Met à jour les graphiques de performance"""
        if self.currentIndex() == 3:  # Onglet Performance
            self.performance_tab.update_charts()
        
        # Mise à jour des graphiques dans l'onglet vue d'ensemble aussi
        if self.currentIndex() == 0:
            self.overview_tab.update_charts()