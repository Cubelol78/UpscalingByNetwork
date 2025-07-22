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
            self.jobs_table.setItem(row, 0, QTableWidgetItem(job.id[:8]))
            self.jobs_table.setItem(row, 1, QTableWidgetItem(Path(job.input_video_path).name))
            self.jobs_table.setItem(row, 2, QTableWidgetItem(job.status.value))
            self.jobs_table.setItem(row, 3, QTableWidgetItem(f"{job.progress:.1f}%"))
            self.jobs_table.setItem(row, 4, QTableWidgetItem(str(len(job.batches))))
            self.jobs_table.setItem(row, 5, QTableWidgetItem(str(job.completed_batches)))
            
            processing_time = job.processing_time or 0
            self.jobs_table.setItem(row, 6, QTableWidgetItem(format_duration(processing_time)))
            self.jobs_table.setItem(row, 7, QTableWidgetItem(job.created_at.strftime('%H:%M:%S')))
    
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
            self.batches_table.setItem(row, 0, QTableWidgetItem(batch.id[:8]))
            self.batches_table.setItem(row, 1, QTableWidgetItem(f"{batch.frame_start}-{batch.frame_end}"))
            self.batches_table.setItem(row, 2, QTableWidgetItem(batch.status.value))
            self.batches_table.setItem(row, 3, QTableWidgetItem(batch.assigned_client or "Aucun"))
            self.batches_table.setItem(row, 4, QTableWidgetItem(f"{batch.progress:.1f}%"))
            self.batches_table.setItem(row, 5, QTableWidgetItem(str(batch.retry_count)))
            
            processing_time = batch.processing_time or 0
            self.batches_table.setItem(row, 6, QTableWidgetItem(format_duration(processing_time)))
            self.batches_table.setItem(row, 7, QTableWidgetItem(batch.error_message or ""))