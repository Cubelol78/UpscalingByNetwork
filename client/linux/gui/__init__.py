"""
GUI components for the Linux client
"""

try:
    from .main_window import ClientMainWindow
    from .connection_panel import ConnectionPanel
    from .processing_panel import ProcessingPanel
    from .settings_panel import SettingsPanel

    GUI_AVAILABLE = True

    __all__ = [
        "ClientMainWindow",
        "ConnectionPanel",
        "ProcessingPanel",
        "SettingsPanel",
        "GUI_AVAILABLE",
    ]
except ImportError:
    GUI_AVAILABLE = False
    __all__ = ["GUI_AVAILABLE"]
