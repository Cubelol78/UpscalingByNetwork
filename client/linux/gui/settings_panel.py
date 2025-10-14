"""
Settings panel for GUI
"""

try:
    from PyQt5.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QFormLayout,
        QCheckBox,
        QSpinBox,
        QComboBox,
        QPushButton,
    )

    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False


class SettingsPanel(QWidget):
    """Settings configuration panel"""

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

        # Settings form
        form = QFormLayout()
        layout.addLayout(form)

        # Use GPU
        self.use_gpu_check = QCheckBox()
        self.use_gpu_check.setChecked(self.client.config.get("processing.use_gpu"))
        form.addRow("Use GPU:", self.use_gpu_check)

        # Tile size
        self.tile_size_spin = QSpinBox()
        self.tile_size_spin.setRange(64, 512)
        self.tile_size_spin.setValue(self.client.config.get("processing.tile_size"))
        form.addRow("Tile Size:", self.tile_size_spin)

        # Model
        self.model_combo = QComboBox()
        self.model_combo.addItems(
            [
                "RealESRGAN_x4plus",
                "RealESRGAN_x4plus_anime_6B",
                "realesr-animevideov3",
            ]
        )
        current_model = self.client.config.get("processing.realesrgan_model")
        index = self.model_combo.findText(current_model)
        if index >= 0:
            self.model_combo.setCurrentIndex(index)
        form.addRow("Model:", self.model_combo)

        # Save button
        self.save_button = QPushButton("Save Settings")
        self.save_button.clicked.connect(self._on_save_clicked)
        layout.addWidget(self.save_button)

        layout.addStretch()

    def _on_save_clicked(self):
        """Handle save button click"""
        self.client.config.set("processing.use_gpu", self.use_gpu_check.isChecked())
        self.client.config.set("processing.tile_size", self.tile_size_spin.value())
        self.client.config.set(
            "processing.realesrgan_model", self.model_combo.currentText()
        )

        self.save_button.setText("Saved!")
        QTimer.singleShot(2000, lambda: self.save_button.setText("Save Settings"))
