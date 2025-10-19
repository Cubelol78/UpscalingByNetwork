"""
Onglet jobs et lots
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QSplitter, QLabel,
                            QTableWidget, QTableWidgetItem)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from pathlib import Path

from utils.file_utils import format_duration

class JobsTab(QWidget):
    """Onglet jobs et lots"""
    
    def __init__(self, server, main_window):
        super().__init__()
        self.server = server
        self.main_window = main_window
        self.setup_ui()
    
    def setup_ui(self):
        """Configuration de l'interface"""
        layout = QVBoxLayout(self)
        
        # Splitter vertical
        splitter = QSplitter(Qt.Vertical)
        
        # Partie haute - Jobs
        jobs_widget = self.create_jobs_section()
        
        # Partie basse - Lots du job sélectionné
        batches_widget = self.create_batches_section()
        
        splitter.addWidget(jobs_widget)
        splitter.addWidget(batches_widget)
        splitter.setSizes([300, 400])
        
        layout.addWidget(splitter)
    
    def create_jobs_section(self):
        """Crée la section des jobs"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        jobs_label = QLabel("Jobs")
        jobs_label.setFont(QFont("Arial", 12, QFont.Bold))
        
        self.jobs_table = QTableWidget()
        self.jobs_table.setColumnCount(8)
        self.jobs_table.setHorizontalHeaderLabels([
            "ID", "Fichier", "Status", "Progression", 
            "Lots total", "Terminés", "Temps", "Créé le"
        ])
        
        # Connexion pour la sélection
        self.jobs_table.selectionModel().selectionChanged.connect(
            self.on_job_selection_changed
        )
        
        layout.addWidget(jobs_label)
        layout.addWidget(self.jobs_table)
        
        return widget
    
    def create_batches_section(self):
        """Crée la section des lots"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        batches_label = QLabel("Lots du job sélectionné")
        batches_label.setFont(QFont("Arial", 12, QFont.Bold))
        
        self.batches_table = QTableWidget()
        self.batches_table.setColumnCount(8)
        self.batches_table.setHorizontalHeaderLabels([
            "ID", "Frames", "Status", "Client", 
            "Progression", "Tentatives", "Temps", "Erreur"
        ])
        
        layout.addWidget(batches_label)
        layout.addWidget(self.batches_table)
        
        return widget
    
    def update_tab(self):
        """Met à jour l'onglet jobs"""
        self.update_jobs_table()
        # La table des lots sera mise à jour par la sélection
    
    def update_jobs_table(self):
        """Met à jour le tableau des jobs"""
        jobs = list(self.server.jobs.values())
        self.jobs_table.setRowCount(len(jobs))

        for row, job in enumerate(jobs):
            # Job ID with tooltip showing full UUID
            job_id_item = QTableWidgetItem(job.id[:8] + "...")
            job_id_tooltip = f"<b>Full Job ID:</b> {job.id}<br>"
            job_id_tooltip += f"<b>Status:</b> {job.status.value}<br>"
            job_id_tooltip += f"<b>Created:</b> {job.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
            if job.started_at:
                job_id_tooltip += f"<br><b>Started:</b> {job.started_at.strftime('%Y-%m-%d %H:%M:%S')}"
            if job.completed_at:
                job_id_tooltip += f"<br><b>Completed:</b> {job.completed_at.strftime('%Y-%m-%d %H:%M:%S')}"
            job_id_item.setToolTip(job_id_tooltip)
            self.jobs_table.setItem(row, 0, job_id_item)

            # File name with tooltip showing full path
            file_name = Path(job.input_video_path).name
            file_item = QTableWidgetItem(file_name)
            file_tooltip = f"<b>Input Path:</b> {job.input_video_path}<br>"
            file_tooltip += f"<b>Output Path:</b> {job.output_video_path}<br>"
            file_tooltip += f"<b>Total Frames:</b> {job.total_frames}<br>"
            file_tooltip += f"<b>Frame Rate:</b> {job.frame_rate:.2f} fps"
            if job.has_any_audio():
                file_tooltip += f"<br><b>Audio Tracks:</b> {len(job.audio_tracks)}"
            if job.has_any_subtitles():
                file_tooltip += f"<br><b>Subtitle Tracks:</b> {len(job.subtitle_tracks)}"
            file_item.setToolTip(file_tooltip)
            self.jobs_table.setItem(row, 1, file_item)

            # Status with tooltip
            status_item = QTableWidgetItem(job.status.value)
            status_tooltip = f"<b>Status:</b> {job.status.value}"
            if job.error_message:
                status_tooltip += f"<br><b>Error:</b> {job.error_message}"
            status_item.setToolTip(status_tooltip)
            self.jobs_table.setItem(row, 2, status_item)

            # Progress with tooltip
            progress_item = QTableWidgetItem(f"{job.progress:.1f}%")
            progress_tooltip = f"<b>Progress:</b> {job.progress:.2f}%<br>"
            progress_tooltip += f"<b>Completed:</b> {job.completed_batches}/{len(job.batches)} batches"
            if job.failed_batches > 0:
                progress_tooltip += f"<br><b>Failed Batches:</b> {job.failed_batches}"
            if job.estimated_remaining_time:
                progress_tooltip += f"<br><b>Estimated Time Remaining:</b> {format_duration(job.estimated_remaining_time)}"
            progress_item.setToolTip(progress_tooltip)
            self.jobs_table.setItem(row, 3, progress_item)

            # Total batches with tooltip
            total_batches_item = QTableWidgetItem(str(len(job.batches)))
            total_batches_item.setToolTip(f"Total Batches: {len(job.batches)}")
            self.jobs_table.setItem(row, 4, total_batches_item)

            # Completed batches with tooltip
            completed_item = QTableWidgetItem(str(job.completed_batches))
            completed_tooltip = f"<b>Completed:</b> {job.completed_batches}<br>"
            completed_tooltip += f"<b>Failed:</b> {job.failed_batches}<br>"
            completed_tooltip += f"<b>Remaining:</b> {len(job.batches) - job.completed_batches - job.failed_batches}"
            completed_item.setToolTip(completed_tooltip)
            self.jobs_table.setItem(row, 5, completed_item)

            # Processing time with tooltip
            processing_time = job.processing_time or 0
            time_item = QTableWidgetItem(format_duration(processing_time))
            time_tooltip = f"<b>Processing Time:</b> {format_duration(processing_time)}"
            if job.estimated_remaining_time:
                time_tooltip += f"<br><b>Est. Remaining:</b> {format_duration(job.estimated_remaining_time)}"
            time_item.setToolTip(time_tooltip)
            self.jobs_table.setItem(row, 6, time_item)

            # Created time with tooltip showing full datetime
            created_item = QTableWidgetItem(job.created_at.strftime('%H:%M:%S'))
            created_item.setToolTip(f"Created: {job.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
            self.jobs_table.setItem(row, 7, created_item)
    
    def on_job_selection_changed(self):
        """Gestionnaire de changement de sélection de job"""
        selected_rows = self.jobs_table.selectionModel().selectedRows()
        if not selected_rows:
            self.batches_table.setRowCount(0)
            return
        
        row = selected_rows[0].row()
        if row < len(self.server.jobs):
            job = list(self.server.jobs.values())[row]
            self.update_batches_for_job(job)
    
    def update_batches_for_job(self, job):
        """Met à jour les lots pour un job donné"""
        job_batches = [self.server.batches[batch_id] for batch_id in job.batches
                      if batch_id in self.server.batches]

        self.batches_table.setRowCount(len(job_batches))

        for row, batch in enumerate(job_batches):
            # Batch ID with tooltip showing full UUID
            batch_id_item = QTableWidgetItem(batch.id[:8] + "...")
            batch_id_tooltip = f"<b>Full Batch ID:</b> {batch.id}<br>"
            batch_id_tooltip += f"<b>Job ID:</b> {batch.job_id}<br>"
            batch_id_tooltip += f"<b>Status:</b> {batch.status.value}<br>"
            batch_id_tooltip += f"<b>Created:</b> {batch.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
            if batch.assigned_at:
                batch_id_tooltip += f"<br><b>Assigned:</b> {batch.assigned_at.strftime('%Y-%m-%d %H:%M:%S')}"
            if batch.started_at:
                batch_id_tooltip += f"<br><b>Started:</b> {batch.started_at.strftime('%Y-%m-%d %H:%M:%S')}"
            if batch.completed_at:
                batch_id_tooltip += f"<br><b>Completed:</b> {batch.completed_at.strftime('%Y-%m-%d %H:%M:%S')}"
            batch_id_item.setToolTip(batch_id_tooltip)
            self.batches_table.setItem(row, 0, batch_id_item)

            # Frame range with tooltip showing frame count
            frame_range_item = QTableWidgetItem(f"{batch.frame_start}-{batch.frame_end}")
            frame_range_tooltip = f"<b>Frame Range:</b> {batch.frame_start} to {batch.frame_end}<br>"
            frame_range_tooltip += f"<b>Total Frames:</b> {batch.frame_count}<br>"
            frame_range_tooltip += f"<b>Progress:</b> {batch.progress:.1f}%"
            if batch.estimated_time:
                frame_range_tooltip += f"<br><b>Estimated Time:</b> {format_duration(batch.estimated_time)}"
            frame_range_item.setToolTip(frame_range_tooltip)
            self.batches_table.setItem(row, 1, frame_range_item)

            # Status with tooltip
            status_item = QTableWidgetItem(batch.status.value)
            status_tooltip = f"<b>Status:</b> {batch.status.value}<br>"
            status_tooltip += f"<b>Retry Count:</b> {batch.retry_count}"
            if batch.error_message:
                status_tooltip += f"<br><b>Error:</b> {batch.error_message}"
            status_item.setToolTip(status_tooltip)
            self.batches_table.setItem(row, 2, status_item)

            # Assigned client with tooltip showing full MAC
            client_display = batch.assigned_client[:8] + "..." if batch.assigned_client and len(batch.assigned_client) > 8 else (batch.assigned_client or "Aucun")
            client_item = QTableWidgetItem(client_display)
            if batch.assigned_client:
                client_tooltip = f"<b>Full MAC Address:</b> {batch.assigned_client}<br>"
                client_tooltip += f"<b>Assigned At:</b> {batch.assigned_at.strftime('%Y-%m-%d %H:%M:%S') if batch.assigned_at else 'N/A'}"
                client_item.setToolTip(client_tooltip)
            else:
                client_item.setToolTip("No client assigned yet")
            self.batches_table.setItem(row, 3, client_item)

            # Progress with tooltip
            progress_item = QTableWidgetItem(f"{batch.progress:.1f}%")
            progress_tooltip = f"<b>Progress:</b> {batch.progress:.2f}%<br>"
            progress_tooltip += f"<b>Status:</b> {batch.status.value}"
            progress_item.setToolTip(progress_tooltip)
            self.batches_table.setItem(row, 4, progress_item)

            # Retry count with tooltip
            retry_item = QTableWidgetItem(str(batch.retry_count))
            retry_tooltip = f"<b>Retry Count:</b> {batch.retry_count}<br>"
            retry_tooltip += f"<b>Status:</b> {batch.status.value}"
            if batch.error_message:
                retry_tooltip += f"<br><b>Last Error:</b> {batch.error_message}"
            retry_item.setToolTip(retry_tooltip)
            self.batches_table.setItem(row, 5, retry_item)

            # Processing time with tooltip
            processing_time = batch.processing_time or 0
            time_item = QTableWidgetItem(format_duration(processing_time))
            time_tooltip = f"<b>Processing Time:</b> {format_duration(processing_time)}"
            if batch.estimated_time:
                time_tooltip += f"<br><b>Estimated Time:</b> {format_duration(batch.estimated_time)}"
            time_item.setToolTip(time_tooltip)
            self.batches_table.setItem(row, 6, time_item)

            # Error message with tooltip showing full error
            error_message = batch.error_message or ""
            if error_message and len(error_message) > 50:
                error_display = error_message[:50] + "..."
            else:
                error_display = error_message
            error_item = QTableWidgetItem(error_display)
            if error_message:
                error_tooltip = f"<b>Full Error Message:</b><br>{error_message}<br><br>"
                error_tooltip += f"<b>Retry Count:</b> {batch.retry_count}<br>"
                error_tooltip += f"<b>Status:</b> {batch.status.value}"
                error_item.setToolTip(error_tooltip)
            else:
                error_item.setToolTip("No error")
            self.batches_table.setItem(row, 7, error_item)