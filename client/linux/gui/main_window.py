"""
Main window for the GUI client
"""

try:
    from PyQt5.QtWidgets import (
        QMainWindow,
        QWidget,
        QVBoxLayout,
        QTabWidget,
        QStatusBar,
        QLabel,
    )
    from PyQt5.QtCore import QTimer

    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False


if PYQT_AVAILABLE:
    from .connection_panel import ConnectionPanel
    from .processing_panel import ProcessingPanel
    from .settings_panel import SettingsPanel


class ClientMainWindow(QMainWindow):
    """Main application window"""

    def __init__(self, client):
        if not PYQT_AVAILABLE:
            raise RuntimeError("PyQt5 not available")

        super().__init__()
        self.client = client
        self.setWindowTitle("Distributed Upscaling Client")
        self.setMinimumSize(800, 600)

        # Create UI
        self._create_ui()

        # Update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_status)
        self.update_timer.start(1000)

    def _create_ui(self):
        """Create user interface"""
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout()
        central_widget.setLayout(layout)

        # Tab widget
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # Tabs
        self.connection_panel = ConnectionPanel(self.client)
        self.processing_panel = ProcessingPanel(self.client)
        self.settings_panel = SettingsPanel(self.client)

        tabs.addTab(self.connection_panel, "Connection")
        tabs.addTab(self.processing_panel, "Processing")
        tabs.addTab(self.settings_panel, "Settings")

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.status_label = QLabel("Disconnected")
        self.status_bar.addWidget(self.status_label)

    def _update_status(self):
        """Update status display"""
        if self.client.is_connected:
            self.status_label.setText("Connected")
        else:
            self.status_label.setText("Disconnected")

    def closeEvent(self, event):
        """Handle close event"""
        # Cleanup
        event.accept()
