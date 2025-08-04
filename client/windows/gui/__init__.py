# UpscalingByNetwork/client/windows/gui/__init__.py
"""
Interface graphique pour le client Windows
"""

try:
    from .client_window import ClientWindow
    GUI_AVAILABLE = True
except ImportError:
    ClientWindow = None
    GUI_AVAILABLE = False

__all__ = ['ClientWindow', 'GUI_AVAILABLE']