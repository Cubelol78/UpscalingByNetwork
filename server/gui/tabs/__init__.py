# gui/tabs/__init__.py - Fichier d'initialisation des onglets

from .overview_tab import OverviewTab
from .config_tab import ConfigTab
from .clients_tab import ClientsTab
from .jobs_tab import JobsTab
from .performance_tab import PerformanceTab
from .logs_tab import LogsTab

__all__ = [
    'OverviewTab',
    'ConfigTab',
    'ClientsTab',
    'JobsTab', 
    'PerformanceTab',
    'LogsTab'
]