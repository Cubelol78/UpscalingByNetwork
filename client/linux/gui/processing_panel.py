"""
Processing panel for GUI
"""

try:
    from PyQt5.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QLabel,
        QTextEdit,
        QProgressBar,
    )
    from PyQt5.QtCore import QTimer

    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False


class ProcessingPanel(QWidget):
    """Processing status panel"""

    def __init__(self, client):
        if not PYQT_AVAILABLE:
            raise RuntimeError("PyQt5 not available")

        super().__init__()
        self.client = client
        self._create_ui()

        # Update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_stats)
        self.update_timer.start(1000)

    def _create_ui(self):
        """Create UI"""
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Processing status
        layout.addWidget(QLabel("Processing Status:"))

        self.status_label = QLabel("Idle")
        layout.addWidget(self.status_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        # Statistics
        layout.addWidget(QLabel("Statistics:"))
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        layout.addWidget(self.stats_text)

    def _update_stats(self):
        """Update statistics display"""
        if self.client.processor.is_processing:
            self.status_label.setText(
                f"Processing batch: {self.client.processor.current_batch_id}"
            )
            self.progress_bar.setRange(0, 0)  # Indeterminate
        else:
            self.status_label.setText("Idle")
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)

        # Display stats
        stats = self.client.processor.get_stats()
        perf_stats = stats.get("performance_stats", {})

        stats_text = f"""
Batches Processed: {perf_stats.get('batches_processed', 0)}
Total Frames: {perf_stats.get('total_frames_processed', 0)}
Average Time/Frame: {perf_stats.get('average_time_per_frame', 0):.2f}s
Errors: {perf_stats.get('errors_count', 0)}
Data Received: {perf_stats.get('data_received_mb', 0):.1f} MB
Data Sent: {perf_stats.get('data_sent_mb', 0):.1f} MB
        """

        self.stats_text.setText(stats_text.strip())
