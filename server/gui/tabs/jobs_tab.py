"""
Onglet jobs et lots - VERSION CORRIGÉE
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QSplitter, QLabel,
                            QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QHBoxLayout)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor
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
        
        # Titre avec bouton de rafraîchissement
        header_layout = QHBoxLayout()
        jobs_label = QLabel("Jobs")
        jobs_label.setFont(QFont("Arial", 12, QFont.Bold))
        
        refresh_btn = QPushButton("Actualiser")
        refresh_btn.clicked.connect(self.refresh_data)
        refresh_btn.setMaximumWidth(100)
        
        header_layout.addWidget(jobs_label)
        header_layout.addStretch()
        header_layout.addWidget(refresh_btn)
        
        self.jobs_table = QTableWidget()
        self.jobs_table.setColumnCount(8)
        self.jobs_table.setHorizontalHeaderLabels([
            "ID", "Fichier", "Status", "Progression", 
            "Lots total", "Terminés", "Temps", "Créé le"
        ])
        
        # Configuration du tableau
        header = self.jobs_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        
        # Connexion pour la sélection
        self.jobs_table.selectionModel().selectionChanged.connect(
            self.on_job_selection_changed
        )
        
        layout.addLayout(header_layout)
        layout.addWidget(self.jobs_table)
        
        return widget
    
    def create_batches_section(self):
        """Crée la section des lots"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        batches_label = QLabel("Lots du job sélectionné")
        batches_label.setFont(QFont("Arial", 12, QFont.Bold))
        
        self.batches_table = QTableWidget()
        self.batches_table.setColumnCount(9)
        self.batches_table.setHorizontalHeaderLabels([
            "ID", "Frames", "Status", "Client", 
            "Progression", "Tentatives", "Temps", "Créé", "Erreur"
        ])
        
        # Configuration du tableau
        header = self.batches_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        
        layout.addWidget(batches_label)
        layout.addWidget(self.batches_table)
        
        return widget
    
    def refresh_data(self):
        """Actualise les données manuellement"""
        self.update_tab()
    
    def update_tab(self):
        """Met à jour l'onglet jobs"""
        self.update_jobs_table()
        # La table des lots sera mise à jour par la sélection si il y en a une
        if self.jobs_table.currentRow() >= 0:
            self.on_job_selection_changed()
    
    def update_jobs_table(self):
        """Met à jour le tableau des jobs"""
        jobs = list(self.server.jobs.values())
        self.jobs_table.setRowCount(len(jobs))
        
        for row, job in enumerate(jobs):
            # ID (8 premiers caractères)
            id_item = QTableWidgetItem(job.id[:8])
            id_item.setToolTip(job.id)  # Tooltip avec l'ID complet
            self.jobs_table.setItem(row, 0, id_item)
            
            # Fichier
            filename = Path(job.input_video_path).name if job.input_video_path else "N/A"
            self.jobs_table.setItem(row, 1, QTableWidgetItem(filename))
            
            # Status avec couleur
            status_item = QTableWidgetItem(job.status.value)
            if job.status.value == "completed":
                status_item.setBackground(QColor(144, 238, 144))  # Vert clair
            elif job.status.value == "failed":
                status_item.setBackground(QColor(255, 182, 193))  # Rouge clair
            elif job.status.value in ["processing", "extracting", "assembling"]:
                status_item.setBackground(QColor(255, 255, 144))  # Jaune clair
            self.jobs_table.setItem(row, 2, status_item)
            
            # Progression
            progress_item = QTableWidgetItem(f"{job.progress:.1f}%")
            self.jobs_table.setItem(row, 3, progress_item)
            
            # Lots total
            self.jobs_table.setItem(row, 4, QTableWidgetItem(str(len(job.batches))))
            
            # Terminés
            completed_count = job.completed_batches
            self.jobs_table.setItem(row, 5, QTableWidgetItem(str(completed_count)))
            
            # Temps de traitement
            processing_time = job.processing_time or 0
            if processing_time > 0:
                time_str = format_duration(processing_time)
            else:
                time_str = "En cours..." if job.status.value in ["processing", "extracting", "assembling"] else "N/A"
            self.jobs_table.setItem(row, 6, QTableWidgetItem(time_str))
            
            # Créé le
            created_str = job.created_at.strftime('%H:%M:%S')
            self.jobs_table.setItem(row, 7, QTableWidgetItem(created_str))
        
        # Message si aucun job
        if len(jobs) == 0:
            self.jobs_table.setRowCount(1)
            no_jobs_item = QTableWidgetItem("Aucun job - Créez un nouveau job pour commencer")
            no_jobs_item.setBackground(QColor(240, 240, 240))
            self.jobs_table.setItem(0, 0, no_jobs_item)
            for col in range(1, 8):
                self.jobs_table.setItem(0, col, QTableWidgetItem(""))
    
    def on_job_selection_changed(self):
        """Gestionnaire de changement de sélection de job"""
        selected_rows = self.jobs_table.selectionModel().selectedRows()
        if not selected_rows:
            self.batches_table.setRowCount(0)
            return
        
        row = selected_rows[0].row()
        jobs_list = list(self.server.jobs.values())
        
        if row < len(jobs_list):
            job = jobs_list[row]
            self.update_batches_for_job(job)
        else:
            # Cas où il n'y a pas de vrais jobs (message "Aucun job")
            self.batches_table.setRowCount(0)
    
    def update_batches_for_job(self, job):
        """Met à jour les lots pour un job donné"""
        # Récupérer tous les lots du job
        job_batches = []
        for batch_id in job.batches:
            if batch_id in self.server.batches:
                job_batches.append(self.server.batches[batch_id])
        
        self.batches_table.setRowCount(len(job_batches))
        
        for row, batch in enumerate(job_batches):
            # ID (8 premiers caractères)
            id_item = QTableWidgetItem(batch.id[:8])
            id_item.setToolTip(batch.id)  # Tooltip avec l'ID complet
            self.batches_table.setItem(row, 0, id_item)
            
            # Frames (début-fin)
            frames_str = f"{batch.frame_start}-{batch.frame_end} ({len(batch.frame_paths)})"
            self.batches_table.setItem(row, 1, QTableWidgetItem(frames_str))
            
            # Status avec couleur
            status_item = QTableWidgetItem(batch.status.value)
            if batch.status.value == "completed":
                status_item.setBackground(QColor(144, 238, 144))  # Vert clair
            elif batch.status.value == "failed":
                status_item.setBackground(QColor(255, 182, 193))  # Rouge clair
            elif batch.status.value in ["processing", "assigned"]:
                status_item.setBackground(QColor(255, 255, 144))  # Jaune clair
            elif batch.status.value == "duplicate":
                status_item.setBackground(QColor(173, 216, 230))  # Bleu clair
            self.batches_table.setItem(row, 2, status_item)
            
            # Client assigné
            client_name = "Aucun"
            if batch.assigned_client:
                if batch.assigned_client == "SERVER_NATIVE":
                    client_name = "Serveur (natif)"
                else:
                    # Essayer de récupérer le nom du client
                    if batch.assigned_client in self.server.clients:
                        client = self.server.clients[batch.assigned_client]
                        client_name = client.hostname or batch.assigned_client[:8]
                    else:
                        client_name = batch.assigned_client[:8]
            self.batches_table.setItem(row, 3, QTableWidgetItem(client_name))
            
            # Progression
            progress_item = QTableWidgetItem(f"{batch.progress:.1f}%")
            self.batches_table.setItem(row, 4, progress_item)
            
            # Tentatives
            retry_str = f"{batch.retry_count}"
            if batch.retry_count > 0:
                retry_str += f" (max {3})"  # Utilisation de la constante MAX_RETRIES
            self.batches_table.setItem(row, 5, QTableWidgetItem(retry_str))
            
            # Temps de traitement
            processing_time = batch.processing_time or 0
            if processing_time > 0:
                time_str = format_duration(processing_time)
            else:
                time_str = "En cours..." if batch.status.value == "processing" else "N/A"
            self.batches_table.setItem(row, 6, QTableWidgetItem(time_str))
            
            # Créé le
            created_str = batch.created_at.strftime('%H:%M:%S')
            self.batches_table.setItem(row, 7, QTableWidgetItem(created_str))
            
            # Erreur (tronquée si trop longue)
            error_msg = batch.error_message or ""
            if len(error_msg) > 50:
                error_msg = error_msg[:47] + "..."
            error_item = QTableWidgetItem(error_msg)
            if batch.error_message:
                error_item.setToolTip(batch.error_message)  # Tooltip avec l'erreur complète
                error_item.setBackground(QColor(255, 182, 193))  # Rouge clair pour les erreurs
            self.batches_table.setItem(row, 8, error_item)
        
        # Message si aucun lot
        if len(job_batches) == 0:
            self.batches_table.setRowCount(1)
            no_batches_item = QTableWidgetItem("Aucun lot pour ce job")
            no_batches_item.setBackground(QColor(240, 240, 240))
            self.batches_table.setItem(0, 0, no_batches_item)
            for col in range(1, 9):
                self.batches_table.setItem(0, col, QTableWidgetItem(""))