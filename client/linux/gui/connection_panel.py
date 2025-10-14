"""
Connection panel for GUI
"""

try:
    from PyQt5.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QTextEdit,
        QSpinBox,
    )
    from PyQt5.QtCore import QTimer
    import asyncio

    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False


class ConnectionPanel(QWidget):
    """Connection control panel"""

    def __init__(self, client):
        if not PYQT_AVAILABLE:
            raise RuntimeError("PyQt5 not available")

        super().__init__()
        self.client = client
        self._create_ui()

    def _create_ui(self):
        """Create UI"""
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Connection settings
        settings_layout = QHBoxLayout()
        layout.addLayout(settings_layout)

        settings_layout.addWidget(QLabel("Host:"))
        self.host_input = QLineEdit()
        self.host_input.setText(self.client.config.get("server.host"))
        settings_layout.addWidget(self.host_input)

        settings_layout.addWidget(QLabel("Port:"))
        self.port_input = QSpinBox()
        self.port_input.setRange(1024, 65535)
        self.port_input.setValue(self.client.config.get("server.port"))
        settings_layout.addWidget(self.port_input)

        # Connect button
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self._on_connect_clicked)
        settings_layout.addWidget(self.connect_button)

        # Status log
        layout.addWidget(QLabel("Connection Status:"))
        self.status_log = QTextEdit()
        self.status_log.setReadOnly(True)
        layout.addWidget(self.status_log)

    def _on_connect_clicked(self):
        """Handle connect button click"""
        if self.client.is_connected:
            asyncio.create_task(self._disconnect())
        else:
            asyncio.create_task(self._connect())

    async def _connect(self):
        """Connect to server"""
        host = self.host_input.text()
        port = self.port_input.value()

        self.status_log.append(f"Connecting to {host}:{port}...")
        self.connect_button.setEnabled(False)

        try:
            result = await self.client.connect(host, port)
            if result:
                self.status_log.append("Connected successfully")
                self.connect_button.setText("Disconnect")
            else:
                self.status_log.append("Connection failed")
        finally:
            self.connect_button.setEnabled(True)

    async def _disconnect(self):
        """Disconnect from server"""
        self.status_log.append("Disconnecting...")
        self.connect_button.setEnabled(False)

        try:
            await self.client.disconnect()
            self.status_log.append("Disconnected")
            self.connect_button.setText("Connect")
        finally:
            self.connect_button.setEnabled(True)
