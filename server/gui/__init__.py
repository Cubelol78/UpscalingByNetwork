# UpscalingByNetwork/server/gui/__init__.py
"""
Module d'interface graphique pour le serveur
"""

# Import conditionnel des widgets principaux
try:
    from .main_window import MainWindow
    GUI_AVAILABLE = True
except ImportError:
    MainWindow = None
    GUI_AVAILABLE = False

__all__ = ['MainWindow', 'GUI_AVAILABLE']