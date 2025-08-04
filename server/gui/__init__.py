# UpscalingByNetwork/server/gui/__init__.py
"""
Module d'interface graphique pour le serveur
"""

# Import conditionnel des widgets principaux
try:
    from .server_window import ServerWindow
    GUI_AVAILABLE = True
except ImportError:
    ServerWindow = None
    GUI_AVAILABLE = False

__all__ = ['ServerWindow', 'GUI_AVAILABLE']