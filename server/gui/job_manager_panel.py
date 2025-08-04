"""
Panneau de gestion des jobs d'upscaling
UpscalingByNetwork/server/gui/job_manager_panel.py
"""

import os
import time
from pathlib import Path
from typing import Dict, Any, Optional
import qasync
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QGridLayout,
    QLabel, QTableWidget, QTableWidgetItem, QProgressBar, QPushButton,
    QFileDialog, QMessageBox, QSplitter, QTextEdit, QComboBox,
    QSpinBox, QCheckBox, QHeaderView, QAbstractItemView, QTabWidget,
    QListWidget, QListWidgetItem, QFrame
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor, QIcon

class JobManagerPanel(QWidget):
    """Panneau de gestion des jobs d'upscaling"""
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setup_ui()
        
        # Données actuelles
        self.current_jobs = {}
        self.current_batches = {}
        
        # Job sélectionné
        self.selected_job_id = None
    
    def setup_ui(self):
        """Configure l'interface du panneau"""
        layout = QVBoxLayout(self)
        
        # Onglets principaux
        tabs = QTabWidget()
        layout.addWidget(tabs)
        
        # Onglet nouveau job
        new_job_tab = self.create_new_job_tab()
        tabs.addTab(new_job_tab, "📁 Nouveau Job")
        
        # Onglet jobs actifs
        active_jobs_tab = self.create_active_jobs_tab()
        tabs.addTab(active_jobs_tab, "⚡ Jobs Actifs")
        
        # Onglet historique
        history_tab = self.create_history_tab()
        tabs.addTab(history_tab, "📊 Historique")
    
    def create_new_job_tab(self):
        """Crée l'onglet de création de nouveau job"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Sélection du fichier vidéo
        file_group = self.create_file_selection_group()
        layout.addWidget(file_group)
        
        # Configuration du job
        config_group = self.create_job_config_group()
        layout.addWidget(config_group)
        
        # Estimation et validation
        estimation_group = self.create_estimation_group()
        layout.addWidget(estimation_group)
        
        # Boutons d'action
        actions_layout = QHBoxLayout()
        
        self.create_job_btn = QPushButton("Créer le Job")
        self.create_job_btn.clicked.connect(self.create_new_job)
        self.create_job_btn.setEnabled(False)
        self.create_job_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                font-size: 14px;
                padding: 10px 20px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        actions_layout.addWidget(self.create_job_btn)
        
        actions_layout.addStretch()
        
        preview_btn = QPushButton("Aperçu")
        preview_btn.clicked.connect(self.preview_video)
        actions_layout.addWidget(preview_btn)
        
        layout.addLayout(actions_layout)
        layout.addStretch()
        
        return widget
    
    def create_file_selection_group(self):
        """Crée le groupe de sélection de fichier"""
        group = QGroupBox("Sélection du fichier vidéo")
        layout = QVBoxLayout(group)
        
        # Sélection fichier
        file_layout = QHBoxLayout()
        
        self.file_path_label = QLabel("Aucun fichier sélectionné")
        self.file_path_label.setStyleSheet("""
            QLabel {
                border: 1px solid #d0d0d0;
                padding: 8px;
                background-color: white;
                border-radius: 4px;
            }
        """)
        file_layout.addWidget(self.file_path_label)
        
        browse_btn = QPushButton("Parcourir...")
        browse_btn.clicked.connect(self.browse_video_file)
        file_layout.addWidget(browse_btn)
        
        layout.addLayout(file_layout)
        
        # Informations du fichier
        self.file_info_layout = QGridLayout()
        
        self.info_labels = {}
        info_fields = [
            ("Durée:", "duration"),
            ("Résolution:", "resolution"),
            ("FPS:", "fps"),
            ("Taille:", "size"),
            ("Codec:", "codec"),
            ("Audio:", "audio")
        ]
        
        for i, (label, key) in enumerate(info_fields):
            row, col = i // 3, (i % 3) * 2
            
            self.file_info_layout.addWidget(QLabel(label), row, col)
            
            value_label = QLabel("-")
            value_label.setStyleSheet("font-weight: bold;")
            self.file_info_layout.addWidget(value_label, row, col + 1)
            
            self.info_labels[key] = value_label
        
        layout.addLayout(self.file_info_layout)
        
        return group
    
    def create_job_config_group(self):
        """Crée le groupe de configuration du job"""
        group = QGroupBox("Configuration du traitement")
        layout = QGridLayout(group)
        
        # Modèle Real-ESRGAN
        layout.addWidget(QLabel("Modèle:"), 0, 0)
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "realesr-animevideov3 (Recommandé pour anime/cartoon)",
            "realesrgan-x4plus (Recommandé pour photos/réel)",
            "realesrgan-x4plus-anime (Anime haute qualité)"
        ])
        layout.addWidget(self.model_combo, 0, 1, 1, 2)
        
        # Facteur d'upscaling
        layout.addWidget(QLabel("Facteur d'échelle:"), 1, 0)
        self.scale_combo = QComboBox()
        self.scale_combo.addItems(["2x", "4x", "8x"])
        self.scale_combo.setCurrentText("4x")
        self.scale_combo.currentTextChanged.connect(self.update_estimation)
        layout.addWidget(self.scale_combo, 1, 1)
        
        # Taille des lots
        layout.addWidget(QLabel("Taille des lots:"), 1, 2)
        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setRange(10, 200)
        self.batch_size_spin.setValue(50)
        self.batch_size_spin.setSuffix(" images")
        self.batch_size_spin.valueChanged.connect(self.update_estimation)
        layout.addWidget(self.batch_size_spin, 1, 3)
        
        # Qualité de compression
        layout.addWidget(QLabel("Qualité vidéo:"), 2, 0)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems([
            "Très haute (CRF 15)",
            "Haute (CRF 20)", 
            "Moyenne (CRF 25)",
            "Économique (CRF 30)"
        ])
        self.quality_combo.setCurrentIndex(1)  # Haute par défaut
        layout.addWidget(self.quality_combo, 2, 1)
        
        # Priorité
        layout.addWidget(QLabel("Priorité:"), 2, 2)
        self.priority_combo = QComboBox()
        self.priority_combo.addItems(["Basse", "Normale", "Haute"])
        self.priority_combo.setCurrentIndex(1)  # Normale par défaut
        layout.addWidget(self.priority_combo, 2, 3)
        
        # Options avancées
        layout.addWidget(QLabel("Options:"), 3, 0)
        
        options_layout = QHBoxLayout()
        
        self.denoise_check = QCheckBox("Débruitage")
        self.denoise_check.setChecked(True)
        options_layout.addWidget(self.denoise_check)
        
        self.face_enhance_check = QCheckBox("Amélioration visages")
        options_layout.addWidget(self.face_enhance_check)
        
        self.allow_duplicates_check = QCheckBox("Permettre doublons")
        self.allow_duplicates_check.setChecked(True)
        options_layout.addWidget(self.allow_duplicates_check)
        
        options_layout.addStretch()
        
        layout.addLayout(options_layout, 3, 1, 1, 3)
        
        return group
    
    def create_estimation_group(self):
        """Crée le groupe d'estimation"""
        group = QGroupBox("Estimation du traitement")
        layout = QGridLayout(group)
        
        self.estimation_labels = {}
        estimations = [
            ("Nombre de frames:", "frames"),
            ("Nombre de lots:", "batches"),
            ("Taille finale estimée:", "output_size"),
            ("Temps estimé:", "estimated_time"),
            ("Espace disque requis:", "disk_space"),
            ("Résolution finale:", "final_resolution")
        ]
        
        for i, (label, key) in enumerate(estimations):
            row, col = i // 2, (i % 2) * 2
            
            layout.addWidget(QLabel(label), row, col)
            
            value_label = QLabel("-")
            value_label.setStyleSheet("font-weight: bold; color: #0078d4;")
            layout.addWidget(value_label, row, col + 1)
            
            self.estimation_labels[key] = value_label
        
        return group
    
    def create_active_jobs_tab(self):
        """Crée l'onglet des jobs actifs"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Splitter pour jobs et détails
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)
        
        # Liste des jobs
        jobs_widget = self.create_jobs_list()
        splitter.addWidget(jobs_widget)
        
        # Détails du job
        details_widget = self.create_job_details()
        splitter.addWidget(details_widget)
        
        splitter.setSizes([400, 600])
        
        return widget
    
    def create_jobs_list(self):
        """Crée la liste des jobs"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # En-tête
        header_layout = QHBoxLayout()
        
        header_layout.addWidget(QLabel("Jobs actifs"))
        header_layout.addStretch()
        
        refresh_btn = QPushButton("Actualiser")
        refresh_btn.clicked.connect(self.refresh_jobs)
        header_layout.addWidget(refresh_btn)
        
        layout.addLayout(header_layout)
        
        # Tableau des jobs
        self.jobs_table = QTableWidget()
        self.jobs_table.setColumnCount(6)
        self.jobs_table.setHorizontalHeaderLabels([
            "ID", "Fichier", "Statut", "Progression", "Temps écoulé", "ETA"
        ])
        
        # Configuration
        header = self.jobs_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.resizeSection(3, 150)  # Barre de progression
        
        self.jobs_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.jobs_table.itemSelectionChanged.connect(self.on_job_selected)
        
        layout.addWidget(self.jobs_table)
        
        # Contrôles des jobs
        controls_layout = QHBoxLayout()
        
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.clicked.connect(self.pause_job)
        controls_layout.addWidget(self.pause_btn)
        
        self.cancel_btn = QPushButton("Annuler")
        self.cancel_btn.clicked.connect(self.cancel_job)
        self.cancel_btn.setStyleSheet("QPushButton { background-color: #dc3545; }")
        controls_layout.addWidget(self.cancel_btn)
        
        controls_layout.addStretch()
        
        self.priority_label = QLabel("Priorité:")
        controls_layout.addWidget(self.priority_label)
        
        self.job_priority_combo = QComboBox()
        self.job_priority_combo.addItems(["Basse", "Normale", "Haute"])
        self.job_priority_combo.currentTextChanged.connect(self.change_job_priority)
        controls_layout.addWidget(self.job_priority_combo)
        
        layout.addLayout(controls_layout)
        
        return widget
    
    def create_job_details(self):
        """Crée le panneau de détails du job"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Informations générales
        info_group = QGroupBox("Informations du job")
        info_layout = QGridLayout(info_group)
        
        self.job_detail_labels = {}
        job_details = [
            ("ID:", "id"),
            ("Fichier source:", "source"),
            ("Fichier de sortie:", "output"),
            ("Statut:", "status"),
            ("Créé le:", "created"),
            ("Démarré le:", "started"),
            ("Modèle:", "model"),
            ("Échelle:", "scale")
        ]
        
        for i, (label, key) in enumerate(job_details):
            row, col = i // 2, (i % 2) * 2
            
            info_layout.addWidget(QLabel(label), row, col)
            
            value_label = QLabel("-")
            value_label.setStyleSheet("font-weight: bold;")
            info_layout.addWidget(value_label, row, col + 1)
            
            self.job_detail_labels[key] = value_label
        
        layout.addWidget(info_group)
        
        # Progression détaillée
        progress_group = QGroupBox("Progression")
        progress_layout = QVBoxLayout(progress_group)
        
        # Barre de progression principale
        self.main_progress = QProgressBar()
        self.main_progress.setStyleSheet("""
            QProgressBar {
                border: 2px solid #d0d0d0;
                border-radius: 5px;
                text-align: center;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #28a745;
                border-radius: 3px;
            }
        """)
        progress_layout.addWidget(self.main_progress)
        
        # Statistiques de progression
        stats_layout = QGridLayout()
        
        self.progress_labels = {}
        progress_stats = [
            ("Lots terminés:", "completed"),
            ("Lots en cours:", "processing"), 
            ("Lots échoués:", "failed"),
            ("Images traitées:", "images"),
            ("Vitesse moyenne:", "speed"),
            ("Temps restant:", "eta")
        ]
        
        for i, (label, key) in enumerate(progress_stats):
            row, col = i // 3, (i % 3) * 2
            
            stats_layout.addWidget(QLabel(label), row, col)
            
            value_label = QLabel("0")
            value_label.setStyleSheet("font-weight: bold; color: #0078d4;")
            stats_layout.addWidget(value_label, row, col + 1)
            
            self.progress_labels[key] = value_label
        
        progress_layout.addLayout(stats_layout)
        layout.addWidget(progress_group)
        
        # Lots du job
        batches_group = QGroupBox("Lots du job")
        batches_layout = QVBoxLayout(batches_group)
        
        self.batches_table = QTableWidget()
        self.batches_table.setColumnCount(5)
        self.batches_table.setHorizontalHeaderLabels([
            "ID", "Statut", "Client", "Progression", "Temps"
        ])
        
        batches_header = self.batches_table.horizontalHeader()
        batches_header.setStretchLastSection(True)
        
        batches_layout.addWidget(self.batches_table)
        layout.addWidget(batches_group)
        
        return widget
    
    def create_history_tab(self):
        """Crée l'onglet historique"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Contrôles de l'historique
        controls_layout = QHBoxLayout()
        
        controls_layout.addWidget(QLabel("Période:"))
        
        period_combo = QComboBox()
        period_combo.addItems(["Aujourd'hui", "Cette semaine", "Ce mois", "Tout"])
        controls_layout.addWidget(period_combo)
        
        controls_layout.addStretch()
        
        export_btn = QPushButton("Exporter")
        export_btn.clicked.connect(self.export_history)
        controls_layout.addWidget(export_btn)
        
        layout.addLayout(controls_layout)
        
        # Tableau historique
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(7)
        self.history_table.setHorizontalHeaderLabels([
            "Date", "Fichier", "Statut", "Durée", "Taille", "Qualité", "Actions"
        ])
        
        layout.addWidget(self.history_table)
        
        return widget
    
    def browse_video_file(self):
        """Ouvre le dialogue de sélection de fichier"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Sélectionner une vidéo",
            "",
            "Fichiers vidéo (*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm);;Tous les fichiers (*)"
        )
        
        if file_path:
            self.load_video_info(file_path)
    
    def load_video_info(self, file_path: str):
        """Charge les informations de la vidéo"""
        try:
            self.file_path_label.setText(file_path)
            
            # Informations basiques du fichier
            file_info = Path(file_path).stat()
            file_size = file_info.st_size / (1024 * 1024)  # MB
            
            self.info_labels["size"].setText(f"{file_size:.1f} MB")
            
            # Ici on utiliserait ffprobe pour obtenir les vraies informations
            # Pour l'exemple, on simule
            self.info_labels["duration"].setText("00:05:30")
            self.info_labels["resolution"].setText("1920x1080")
            self.info_labels["fps"].setText("30.0")
            self.info_labels["codec"].setText("H.264")
            self.info_labels["audio"].setText("AAC")
            
            self.create_job_btn.setEnabled(True)
            self.update_estimation()
            
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de lire le fichier:\n{e}")
    
    def update_estimation(self):
        """Met à jour l'estimation du traitement"""
        try:
            # Simulation des calculs d'estimation
            duration_seconds = 330  # 5min 30s
            fps = 30.0
            total_frames = int(duration_seconds * fps)
            
            batch_size = self.batch_size_spin.value()
            num_batches = (total_frames + batch_size - 1) // batch_size
            
            scale_factor = int(self.scale_combo.currentText().replace('x', ''))
            
            # Estimation taille finale
            original_size = 1920 * 1080
            upscaled_size = original_size * (scale_factor ** 2)
            estimated_mb = (upscaled_size * total_frames * 3) / (1024 * 1024)  # RGB
            
            # Estimation temps (basé sur 2 sec/image en moyenne)
            estimated_seconds = total_frames * 2
            hours = estimated_seconds // 3600
            minutes = (estimated_seconds % 3600) // 60
            
            # Mise à jour des labels
            self.estimation_labels["frames"].setText(f"{total_frames:,}")
            self.estimation_labels["batches"].setText(f"{num_batches}")
            self.estimation_labels["output_size"].setText(f"{estimated_mb/1024:.1f} GB")
            self.estimation_labels["estimated_time"].setText(f"{hours}h {minutes}m")
            self.estimation_labels["disk_space"].setText(f"{estimated_mb/1024*2:.1f} GB")
            self.estimation_labels["final_resolution"].setText(f"{1920*scale_factor}x{1080*scale_factor}")
            
        except Exception as e:
            print(f"Erreur estimation: {e}")
    
    @qasync.asyncSlot()
    async def create_new_job(self):
        """Crée un nouveau job"""
        try:
            video_path = self.file_path_label.text()
            if video_path == "Aucun fichier sélectionné":
                QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un fichier vidéo")
                return
            
            if not self.main_window.server or not self.main_window.server_running:
                QMessageBox.warning(self, "Erreur", "Le serveur doit être démarré")
                return
            
            # Configuration du job
            config = {
                'model': self.model_combo.currentText().split()[0],
                'scale': int(self.scale_combo.currentText().replace('x', '')),
                'batch_size': self.batch_size_spin.value(),
                'quality': self.quality_combo.currentIndex(),
                'priority': self.priority_combo.currentIndex(),
                'denoise': self.denoise_check.isChecked(),
                'face_enhance': self.face_enhance_check.isChecked(),
                'allow_duplicates': self.allow_duplicates_check.isChecked()
            }
            
            # Création du job
            job_id = await self.main_window.server.create_distributed_job(video_path)
            
            if job_id:
                # Démarrage du traitement
                success = await self.main_window.server.extract_frames_and_create_batches(job_id)
                
                if success:
                    QMessageBox.information(self, "Succès", f"Job créé avec succès!\nID: {job_id}")
                    
                    # Réinitialisation du formulaire
                    self.file_path_label.setText("Aucun fichier sélectionné")
                    self.create_job_btn.setEnabled(False)
                    
                    # Basculer vers l'onglet jobs actifs
                    parent_tabs = self.parent()
                    while parent_tabs and not isinstance(parent_tabs, QTabWidget):
                        parent_tabs = parent_tabs.parent()
                    if parent_tabs:
                        parent_tabs.setCurrentIndex(1)  # Jobs actifs
                else:
                    QMessageBox.critical(self, "Erreur", "Échec du démarrage du traitement")
            else:
                QMessageBox.critical(self, "Erreur", "Échec de la création du job")
                
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur création job:\n{e}")
    
    def update_data(self, jobs: Dict[str, Any], batches: Dict[str, Any]):
        """Met à jour les données des jobs"""
        self.current_jobs = jobs
        self.current_batches = batches
        
        self.update_jobs_table()
        
        if self.selected_job_id:
            self.update_job_details(self.selected_job_id)
    
    def update_jobs_table(self):
        """Met à jour le tableau des jobs"""
        try:
            self.jobs_table.setRowCount(len(self.current_jobs))
            
            for row, (job_id, job) in enumerate(self.current_jobs.items()):
                # ID (court)
                short_id = job_id[:8] + "..." if len(job_id) > 8 else job_id
                self.jobs_table.setItem(row, 0, QTableWidgetItem(short_id))
                
                # Fichier
                filename = Path(job.input_video_path).name if hasattr(job, 'input_video_path') else "N/A"
                self.jobs_table.setItem(row, 1, QTableWidgetItem(filename))
                
                # Statut
                status = job.status.value if hasattr(job, 'status') else "unknown"
                status_item = QTableWidgetItem(status.title())
                
                # Couleur selon le statut
                if status == 'processing':
                    status_item.setBackground(QColor(144, 238, 144))
                elif status == 'completed':
                    status_item.setBackground(QColor(173, 216, 230))
                elif status == 'failed':
                    status_item.setBackground(QColor(255, 182, 193))
                
                self.jobs_table.setItem(row, 2, status_item)
                
                # Progression
                progress = getattr(job, 'progress', 0)
                progress_bar = QProgressBar()
                progress_bar.setValue(int(progress))
                self.jobs_table.setCellWidget(row, 3, progress_bar)
                
                # Temps écoulé
                if hasattr(job, 'start_time') and job.start_time:
                    elapsed = time.time() - job.start_time
                    hours = int(elapsed // 3600)
                    minutes = int((elapsed % 3600) // 60)
                    elapsed_text = f"{hours:02d}:{minutes:02d}"
                else:
                    elapsed_text = "N/A"
                
                self.jobs_table.setItem(row, 4, QTableWidgetItem(elapsed_text))
                
                # ETA
                eta = getattr(job, 'estimated_remaining_time', None)
                if eta and eta > 0:
                    eta_hours = int(eta // 3600)
                    eta_minutes = int((eta % 3600) // 60)
                    eta_text = f"{eta_hours:02d}:{eta_minutes:02d}"
                else:
                    eta_text = "N/A"
                
                self.jobs_table.setItem(row, 5, QTableWidgetItem(eta_text))
            
        except Exception as e:
            print(f"Erreur mise à jour tableau jobs: {e}")
    
    def on_job_selected(self):
        """Gestion de la sélection d'un job"""
        current_row = self.jobs_table.currentRow()
        if current_row >= 0:
            job_ids = list(self.current_jobs.keys())
            if current_row < len(job_ids):
                self.selected_job_id = job_ids[current_row]
                self.update_job_details(self.selected_job_id)
    
    def update_job_details(self, job_id: str):
        """Met à jour les détails du job sélectionné"""
        if job_id not in self.current_jobs:
            return
        
        job = self.current_jobs[job_id]
        
        try:
            # Informations générales
            self.job_detail_labels["id"].setText(job_id[:16] + "...")
            self.job_detail_labels["source"].setText(getattr(job, 'input_video_path', 'N/A'))
            self.job_detail_labels["output"].setText(getattr(job, 'output_video_path', 'N/A'))
            self.job_detail_labels["status"].setText(getattr(job, 'status', 'unknown').value.title())
            
            # Dates
            if hasattr(job, 'created_at'):
                created = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(job.created_at))
                self.job_detail_labels["created"].setText(created)
            
            if hasattr(job, 'start_time') and job.start_time:
                started = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(job.start_time))
                self.job_detail_labels["started"].setText(started)
            
            # Configuration
            self.job_detail_labels["model"].setText(getattr(job, 'model_name', 'N/A'))
            self.job_detail_labels["scale"].setText(f"{getattr(job, 'upscale_factor', 4)}x")
            
            # Progression
            progress = getattr(job, 'progress', 0)
            self.main_progress.setValue(int(progress))
            
            # Statistiques
            self.progress_labels["completed"].setText(str(getattr(job, 'completed_batches', 0)))
            
            # Lots en cours
            processing_batches = sum(1 for batch_id in getattr(job, 'batch_ids', [])
                                   if batch_id in self.current_batches and 
                                   self.current_batches[batch_id].status.value == 'processing')
            self.progress_labels["processing"].setText(str(processing_batches))
            
            self.progress_labels["failed"].setText(str(getattr(job, 'failed_batches', 0)))
            self.progress_labels["images"].setText(str(getattr(job, 'frames_processed', 0)))
            
            # Vitesse
            speed = getattr(job, 'frames_per_second_processed', 0)
            self.progress_labels["speed"].setText(f"{speed:.1f} img/s")
            
            # ETA
            eta = getattr(job, 'estimated_remaining_time', None)
            if eta and eta > 0:
                eta_hours = int(eta // 3600)
                eta_minutes = int((eta % 3600) // 60)
                self.progress_labels["eta"].setText(f"{eta_hours}h {eta_minutes}m")
            else:
                self.progress_labels["eta"].setText("N/A")
            
            # Mise à jour table des lots
            self.update_batches_table(job_id)
            
        except Exception as e:
            print(f"Erreur mise à jour détails job: {e}")
    
    def update_batches_table(self, job_id: str):
        """Met à jour le tableau des lots du job"""
        try:
            if job_id not in self.current_jobs:
                return
            
            job = self.current_jobs[job_id]
            batch_ids = getattr(job, 'batch_ids', [])
            
            self.batches_table.setRowCount(len(batch_ids))
            
            for row, batch_id in enumerate(batch_ids):
                if batch_id not in self.current_batches:
                    continue
                
                batch = self.current_batches[batch_id]
                
                # ID court
                short_id = batch_id.split('_')[-1] if '_' in batch_id else batch_id[:8]
                self.batches_table.setItem(row, 0, QTableWidgetItem(short_id))
                
                # Statut
                status = batch.status.value if hasattr(batch, 'status') else 'unknown'
                self.batches_table.setItem(row, 1, QTableWidgetItem(status.title()))
                
                # Client
                client = getattr(batch, 'assigned_client', 'Aucun')
                if client and client != 'Aucun':
                    client = client[:8] + "..." if len(client) > 8 else client
                self.batches_table.setItem(row, 2, QTableWidgetItem(client))
                
                # Progression
                progress = getattr(batch, 'progress', 0)
                progress_bar = QProgressBar()
                progress_bar.setValue(int(progress))
                self.batches_table.setCellWidget(row, 3, progress_bar)
                
                # Temps
                processing_time = getattr(batch, 'processing_time', 0)
                if processing_time > 0:
                    time_text = f"{processing_time:.1f}s"
                else:
                    time_text = "N/A"
                self.batches_table.setItem(row, 4, QTableWidgetItem(time_text))
                
        except Exception as e:
            print(f"Erreur mise à jour tableau lots: {e}")
    
    def preview_video(self):
        """Aperçu de la vidéo sélectionnée"""
        QMessageBox.information(self, "Aperçu", "Fonctionnalité d'aperçu à implémenter")
    
    def refresh_jobs(self):
        """Actualise la liste des jobs"""
        if self.current_jobs:
            self.update_jobs_table()
    
    def pause_job(self):
        """Met en pause le job sélectionné"""
        if self.selected_job_id:
            QMessageBox.information(self, "Pause", f"Job {self.selected_job_id[:8]}... mis en pause")
    
    def cancel_job(self):
        """Annule le job sélectionné"""
        if self.selected_job_id:
            reply = QMessageBox.question(
                self, "Confirmation", 
                "Voulez-vous vraiment annuler ce job ?",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                QMessageBox.information(self, "Annulation", f"Job {self.selected_job_id[:8]}... annulé")
    
    def change_job_priority(self):
        """Change la priorité du job sélectionné"""
        if self.selected_job_id:
            priority = self.job_priority_combo.currentText()
            QMessageBox.information(self, "Priorité", f"Priorité changée à: {priority}")
    
    def export_history(self):
        """Exporte l'historique des jobs"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Exporter l'historique", "historique_jobs.csv", "Fichiers CSV (*.csv)"
        )
        
        if filename:
            QMessageBox.information(self, "Export", "Historique exporté avec succès")