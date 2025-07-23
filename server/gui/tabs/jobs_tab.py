"""
Onglet jobs et lots avec support complet des sous-titres
Fichier: server/gui/tabs/jobs_tab.py
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QSplitter, QLabel,
                            QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, 
                            QHBoxLayout, QTextEdit, QGroupBox, QMessageBox)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor
from pathlib import Path

from utils.file_utils import format_duration

class JobsTab(QWidget):
    """Onglet jobs et lots avec informations détaillées et support sous-titres"""
    
    def __init__(self, server, main_window):
        super().__init__()
        self.server = server
        self.main_window = main_window
        self.current_selected_job = None
        self.setup_ui()
    
    def setup_ui(self):
        """Configuration de l'interface"""
        layout = QVBoxLayout(self)
        
        # Splitter principal vertical
        main_splitter = QSplitter(Qt.Vertical)
        
        # Partie haute - Jobs
        jobs_widget = self.create_jobs_section()
        
        # Splitter horizontal pour lots et détails
        bottom_splitter = QSplitter(Qt.Horizontal)
        
        # Partie basse gauche - Lots du job sélectionné
        batches_widget = self.create_batches_section()
        
        # Partie basse droite - Détails du job
        details_widget = self.create_job_details_section()
        
        bottom_splitter.addWidget(batches_widget)
        bottom_splitter.addWidget(details_widget)
        bottom_splitter.setSizes([600, 400])
        
        main_splitter.addWidget(jobs_widget)
        main_splitter.addWidget(bottom_splitter)
        main_splitter.setSizes([300, 500])
        
        layout.addWidget(main_splitter)
    
    def create_jobs_section(self):
        """Crée la section des jobs"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Titre avec boutons d'action
        header_layout = QHBoxLayout()
        jobs_label = QLabel("Jobs")
        jobs_label.setFont(QFont("Arial", 12, QFont.Bold))
        
        refresh_btn = QPushButton("Actualiser")
        refresh_btn.clicked.connect(self.refresh_data)
        refresh_btn.setMaximumWidth(100)
        
        # Bouton pour forcer l'assemblage (utile en cas de problème)
        force_assemble_btn = QPushButton("Forcer Assemblage")
        force_assemble_btn.clicked.connect(self.force_assemble_selected_job)
        force_assemble_btn.setMaximumWidth(120)
        force_assemble_btn.setStyleSheet("background-color: #FF9800; color: white;")
        
        header_layout.addWidget(jobs_label)
        header_layout.addStretch()
        header_layout.addWidget(refresh_btn)
        header_layout.addWidget(force_assemble_btn)
        
        self.jobs_table = QTableWidget()
        self.jobs_table.setColumnCount(10)
        self.jobs_table.setHorizontalHeaderLabels([
            "ID", "Fichier", "Status", "Progression", 
            "Lots total", "Terminés", "Audio", "Sous-titres", "Temps", "Créé le"
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
    
    def create_job_details_section(self):
        """Crée la section des détails du job"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        details_label = QLabel("Détails du job sélectionné")
        details_label.setFont(QFont("Arial", 12, QFont.Bold))
        
        # Zone de texte pour les détails généraux
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setMaximumHeight(200)
        self.details_text.setFont(QFont("Consolas", 9))
        self.details_text.setPlainText("Sélectionnez un job pour voir les détails")
        
        # Section sous-titres
        subtitles_group = QGroupBox("Sous-titres détectés")
        subtitles_layout = QVBoxLayout(subtitles_group)
        
        # Boutons d'action pour les sous-titres
        subtitle_actions_layout = QHBoxLayout()
        
        self.preview_subtitles_btn = QPushButton("Aperçu Sous-titres")
        self.preview_subtitles_btn.clicked.connect(self.preview_subtitles)
        self.preview_subtitles_btn.setEnabled(False)
        
        self.export_subtitles_btn = QPushButton("Exporter Sous-titres")
        self.export_subtitles_btn.clicked.connect(self.export_subtitles)
        self.export_subtitles_btn.setEnabled(False)
        
        subtitle_actions_layout.addWidget(self.preview_subtitles_btn)
        subtitle_actions_layout.addWidget(self.export_subtitles_btn)
        subtitle_actions_layout.addStretch()
        
        self.subtitles_table = QTableWidget()
        self.subtitles_table.setColumnCount(6)
        self.subtitles_table.setHorizontalHeaderLabels([
            "Langue", "Codec", "Titre", "Type", "État", "Fichier"
        ])
        self.subtitles_table.setMaximumHeight(150)
        
        # Configuration du tableau sous-titres
        sub_header = self.subtitles_table.horizontalHeader()
        sub_header.setStretchLastSection(True)
        sub_header.setSectionResizeMode(QHeaderView.ResizeToContents)
        
        subtitles_layout.addLayout(subtitle_actions_layout)
        subtitles_layout.addWidget(self.subtitles_table)
        
        layout.addWidget(details_label)
        layout.addWidget(self.details_text)
        layout.addWidget(subtitles_group)
        layout.addStretch()
        
        return widget
    
    def refresh_data(self):
        """Actualise les données manuellement"""
        self.update_tab()
    
    def update_tab(self):
        """Met à jour l'onglet jobs"""
        self.update_jobs_table()
        # La table des lots et détails seront mises à jour par la sélection si il y en a une
        if self.jobs_table.currentRow() >= 0:
            self.on_job_selection_changed()
    
    def update_jobs_table(self):
        """Met à jour le tableau des jobs avec informations sous-titres"""
        jobs = list(self.server.jobs.values())
        self.jobs_table.setRowCount(len(jobs))
        
        for row, job in enumerate(jobs):
            # ID (8 premiers caractères)
            id_item = QTableWidgetItem(job.id[:8])
            id_item.setToolTip(job.id)  # Tooltip avec l'ID complet
            self.jobs_table.setItem(row, 0, id_item)
            
            # Fichier
            filename = Path(job.input_video_path).name if job.input_video_path else "N/A"
            filename_item = QTableWidgetItem(filename)
            filename_item.setToolTip(job.input_video_path or "Chemin inconnu")
            self.jobs_table.setItem(row, 1, filename_item)
            
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
            
            # Audio
            audio_item = QTableWidgetItem("✅" if job.has_audio else "❌")
            audio_item.setToolTip("Audio présent" if job.has_audio else "Pas d'audio")
            self.jobs_table.setItem(row, 6, audio_item)
            
            # Sous-titres - logique améliorée
            subtitle_text, subtitle_tooltip = self._get_subtitle_display_info(job)
            subtitle_item = QTableWidgetItem(subtitle_text)
            subtitle_item.setToolTip(subtitle_tooltip)
            self.jobs_table.setItem(row, 7, subtitle_item)
            
            # Temps de traitement
            processing_time = job.processing_time or 0
            if processing_time > 0:
                time_str = format_duration(processing_time)
            else:
                time_str = "En cours..." if job.status.value in ["processing", "extracting", "assembling"] else "N/A"
            self.jobs_table.setItem(row, 8, QTableWidgetItem(time_str))
            
            # Créé le
            created_str = job.created_at.strftime('%d/%m %H:%M:%S')
            self.jobs_table.setItem(row, 9, QTableWidgetItem(created_str))
        
        # Message si aucun job
        if len(jobs) == 0:
            self.jobs_table.setRowCount(1)
            no_jobs_item = QTableWidgetItem("Aucun job - Créez un nouveau job pour commencer")
            no_jobs_item.setBackground(QColor(240, 240, 240))
            self.jobs_table.setItem(0, 0, no_jobs_item)
            for col in range(1, 10):
                self.jobs_table.setItem(0, col, QTableWidgetItem(""))
    
    def _get_subtitle_display_info(self, job) -> tuple:
        """Génère les informations d'affichage pour les sous-titres"""
        if not hasattr(job, 'has_subtitles') or not job.has_subtitles:
            return "❌", "Aucun sous-titre détecté"
        
        detected_count = 0
        extracted_count = 0
        
        # Nombre détecté
        if hasattr(job, 'subtitle_info') and job.subtitle_info:
            detected_count = job.subtitle_info.get('count', 0)
        
        # Nombre extrait
        if hasattr(job, 'subtitle_paths') and job.subtitle_paths:
            extracted_count = len(job.subtitle_paths)
        
        if detected_count == 0:
            return "❌", "Aucun sous-titre détecté"
        
        if extracted_count == 0:
            return f"🔍 {detected_count}", f"{detected_count} sous-titre(s) détecté(s) mais non extrait(s)"
        elif extracted_count == detected_count:
            return f"✅ {extracted_count}", f"{extracted_count} sous-titre(s) extrait(s) avec succès"
        else:
            return f"⚠️ {extracted_count}/{detected_count}", f"{extracted_count} sur {detected_count} sous-titre(s) extrait(s)"
    
    def on_job_selection_changed(self):
        """Gestionnaire de changement de sélection de job"""
        selected_rows = self.jobs_table.selectionModel().selectedRows()
        if not selected_rows:
            self.clear_job_details()
            return
        
        row = selected_rows[0].row()
        jobs_list = list(self.server.jobs.values())
        
        if row < len(jobs_list):
            job = jobs_list[row]
            self.current_selected_job = job
            self.update_batches_for_job(job)
            self.update_job_details(job)
        else:
            # Cas où il n'y a pas de vrais jobs (message "Aucun job")
            self.clear_job_details()
    
    def clear_job_details(self):
        """Efface les détails du job"""
        self.current_selected_job = None
        self.batches_table.setRowCount(0)
        self.details_text.setPlainText("Sélectionnez un job pour voir les détails")
        self.subtitles_table.setRowCount(0)
        self.preview_subtitles_btn.setEnabled(False)
        self.export_subtitles_btn.setEnabled(False)
    
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
                retry_str += f" (max 3)"
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
    
    def update_job_details(self, job):
        """Met à jour les détails du job sélectionné"""
        # Informations générales
        details = []
        details.append(f"=== JOB {job.id[:8]} ===")
        details.append(f"Fichier d'entrée: {Path(job.input_video_path).name if job.input_video_path else 'N/A'}")
        details.append(f"Fichier de sortie: {Path(job.output_video_path).name if job.output_video_path else 'N/A'}")
        details.append(f"Status: {job.status.value}")
        details.append(f"Progression: {job.progress:.1f}%")
        details.append("")
        
        # Informations techniques
        details.append("=== INFORMATIONS TECHNIQUES ===")
        details.append(f"Frames totales: {job.total_frames}")
        details.append(f"Framerate: {job.frame_rate:.3f} fps")
        details.append(f"Audio: {'Oui' if job.has_audio else 'Non'}")
        
        # Informations sous-titres
        subtitle_info = getattr(job, 'has_subtitles', False)
        details.append(f"Sous-titres: {'Oui' if subtitle_info else 'Non'}")
        
        if subtitle_info and hasattr(job, 'subtitle_info'):
            detected = job.subtitle_info.get('count', 0)
            extracted = len(getattr(job, 'subtitle_paths', []))
            details.append(f"  - Détectés: {detected}")
            details.append(f"  - Extraits: {extracted}")
        
        details.append("")
        
        # Informations de traitement
        details.append("=== TRAITEMENT ===")
        details.append(f"Lots totaux: {len(job.batches)}")
        details.append(f"Lots terminés: {job.completed_batches}")
        details.append(f"Lots échoués: {job.failed_batches}")
        
        if job.processing_time:
            details.append(f"Temps de traitement: {format_duration(job.processing_time)}")
        
        if job.estimated_remaining_time:
            details.append(f"Temps restant estimé: {format_duration(job.estimated_remaining_time)}")
        
        details.append("")
        details.append(f"Créé le: {job.created_at.strftime('%d/%m/%Y à %H:%M:%S')}")
        
        if job.error_message:
            details.append("")
            details.append("=== ERREUR ===")
            details.append(job.error_message)
        
        self.details_text.setPlainText("\n".join(details))
        
        # Mise à jour de la table des sous-titres
        self.update_subtitles_table(job)
    
    def update_subtitles_table(self, job):
        """Met à jour la table des sous-titres"""
        subtitle_paths = getattr(job, 'subtitle_paths', [])
        self.subtitles_table.setRowCount(len(subtitle_paths))
        
        for row, subtitle in enumerate(subtitle_paths):
            # Langue
            language = subtitle.get('language', 'unknown').upper()
            self.subtitles_table.setItem(row, 0, QTableWidgetItem(language))
            
            # Codec
            codec = subtitle.get('codec', 'unknown')
            self.subtitles_table.setItem(row, 1, QTableWidgetItem(codec))
            
            # Titre
            title = subtitle.get('title', '')
            self.subtitles_table.setItem(row, 2, QTableWidgetItem(title))
            
            # Type (défaut, forcé, etc.)
            type_info = []
            if subtitle.get('default', False):
                type_info.append("Défaut")
            if subtitle.get('forced', False):
                type_info.append("Forcé")
            type_str = ", ".join(type_info) if type_info else "Normal"
            self.subtitles_table.setItem(row, 3, QTableWidgetItem(type_str))
            
            # État
            file_path = subtitle.get('path', '')
            if file_path and Path(file_path).exists():
                state_item = QTableWidgetItem("✅ Extrait")
                state_item.setBackground(QColor(144, 238, 144))
            else:
                state_item = QTableWidgetItem("❌ Manquant")
                state_item.setBackground(QColor(255, 182, 193))
            self.subtitles_table.setItem(row, 4, state_item)
            
            # Fichier
            filename = Path(file_path).name if file_path else "N/A"
            file_item = QTableWidgetItem(filename)
            file_item.setToolTip(file_path)
            self.subtitles_table.setItem(row, 5, file_item)
        
        # Activation des boutons selon la disponibilité des sous-titres
        has_subtitles = len(subtitle_paths) > 0
        self.preview_subtitles_btn.setEnabled(has_subtitles)
        self.export_subtitles_btn.setEnabled(has_subtitles)
    
    def preview_subtitles(self):
        """Affiche un aperçu des sous-titres du job sélectionné"""
        if not self.current_selected_job:
            return
        
        try:
            # Utilisation de la méthode du VideoProcessor si disponible
            if hasattr(self.server, 'video_processor'):
                preview = self.server.video_processor.create_subtitle_preview(self.current_selected_job)
                if preview:
                    # Affichage dans une boîte de dialogue
                    dialog = QMessageBox(self)
                    dialog.setWindowTitle("Aperçu des sous-titres")
                    dialog.setText("Informations sur les sous-titres détectés:")
                    dialog.setDetailedText(preview)
                    dialog.setStyleSheet("QLabel { font-family: 'Consolas', monospace; }")
                    dialog.exec_()
                else:
                    QMessageBox.information(self, "Aperçu", "Aucune information de sous-titres disponible")
            else:
                # Fallback simple
                subtitle_info = getattr(self.current_selected_job, 'subtitle_paths', [])
                if subtitle_info:
                    preview_lines = [f"=== SOUS-TITRES ({len(subtitle_info)}) ==="]
                    for i, sub in enumerate(subtitle_info):
                        lang = sub.get('language', 'unknown').upper()
                        codec = sub.get('codec', 'unknown')
                        title = sub.get('title', '')
                        preview_lines.append(f"{i+1}. {lang} ({codec})")
                        if title:
                            preview_lines.append(f"   Titre: {title}")
                    
                    QMessageBox.information(self, "Aperçu des sous-titres", "\n".join(preview_lines))
                else:
                    QMessageBox.information(self, "Aperçu", "Aucun sous-titre disponible")
                    
        except Exception as e:
            QMessageBox.warning(self, "Erreur", f"Erreur lors de l'aperçu des sous-titres:\n{str(e)}")
    
    def export_subtitles(self):
        """Exporte les sous-titres du job sélectionné"""
        if not self.current_selected_job:
            return
        
        subtitle_paths = getattr(self.current_selected_job, 'subtitle_paths', [])
        if not subtitle_paths:
            QMessageBox.information(self, "Export", "Aucun sous-titre à exporter")
            return
        
        try:
            from PyQt5.QtWidgets import QFileDialog
            import shutil
            
            # Sélection du dossier de destination
            dest_dir = QFileDialog.getExistingDirectory(
                self, "Sélectionner le dossier de destination", 
                str(Path.home())
            )
            
            if not dest_dir:
                return
            
            dest_path = Path(dest_dir)
            job_name = Path(self.current_selected_job.input_video_path).stem
            copied_files = []
            
            for subtitle in subtitle_paths:
                source_path = Path(subtitle.get('path', ''))
                if source_path.exists():
                    # Nom de fichier avec langue
                    language = subtitle.get('language', 'unknown')
                    ext = source_path.suffix
                    dest_filename = f"{job_name}_{language}{ext}"
                    dest_file = dest_path / dest_filename
                    
                    # Copie du fichier
                    shutil.copy2(source_path, dest_file)
                    copied_files.append(dest_filename)
            
            if copied_files:
                files_list = "\n".join(copied_files)
                QMessageBox.information(
                    self, "Export réussi", 
                    f"Sous-titres exportés vers:\n{dest_dir}\n\nFichiers copiés:\n{files_list}"
                )
            else:
                QMessageBox.warning(self, "Export échoué", "Aucun fichier de sous-titres trouvé")
                
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'export", f"Erreur lors de l'export:\n{str(e)}")
    
    def force_assemble_selected_job(self):
        """Force l'assemblage du job sélectionné"""
        if not self.current_selected_job:
            QMessageBox.information(self, "Assemblage", "Aucun job sélectionné")
            return
        
        job = self.current_selected_job
        
        # Vérifications
        if job.status.value == "completed":
            QMessageBox.information(self, "Assemblage", "Ce job est déjà terminé")
            return
        
        if job.status.value == "assembling":
            QMessageBox.information(self, "Assemblage", "Ce job est déjà en cours d'assemblage")
            return
        
        # Vérifier qu'au moins quelques lots sont terminés
        completed_batches = sum(1 for batch_id in job.batches 
                              if batch_id in self.server.batches and 
                              self.server.batches[batch_id].status.value == "completed")
        
        if completed_batches == 0:
            QMessageBox.warning(self, "Assemblage", "Aucun lot terminé à assembler")
            return
        
        # Confirmation
        reply = QMessageBox.question(
            self, "Forcer l'assemblage",
            f"Forcer l'assemblage du job {job.id[:8]}?\n"
            f"{completed_batches}/{len(job.batches)} lots terminés\n\n"
            f"⚠️ Cette action peut créer une vidéo incomplète si tous les lots ne sont pas terminés.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                # Lancement de l'assemblage forcé
                import asyncio
                from models.job import JobStatus
                
                job.status = JobStatus.ASSEMBLING
                job.completed_batches = completed_batches
                
                # Lancement de l'assemblage en arrière-plan
                asyncio.create_task(self.server._assemble_video(job.id))
                
                QMessageBox.information(
                    self, "Assemblage lancé", 
                    f"Assemblage forcé démarré pour le job {job.id[:8]}\n"
                    f"Avec {completed_batches} lots terminés"
                )
                
                # Actualiser l'affichage
                self.refresh_data()
                
            except Exception as e:
                QMessageBox.critical(
                    self, "Erreur", 
                    f"Erreur lors du lancement de l'assemblage forcé:\n{str(e)}"
                )
    
    def get_job_summary_for_export(self, job) -> str:
        """Génère un résumé exportable du job"""
        lines = []
        lines.append(f"=== RAPPORT JOB {job.id} ===")
        lines.append(f"Date de création: {job.created_at.strftime('%d/%m/%Y %H:%M:%S')}")
        lines.append(f"Fichier source: {job.input_video_path}")
        lines.append(f"Fichier de sortie: {job.output_video_path}")
        lines.append(f"Status final: {job.status.value}")
        lines.append("")
        
        # Informations techniques
        lines.append("=== CARACTÉRISTIQUES VIDÉO ===")
        lines.append(f"Nombre de frames: {job.total_frames}")
        lines.append(f"Framerate: {job.frame_rate:.3f} fps")
        lines.append(f"Audio présent: {'Oui' if job.has_audio else 'Non'}")
        
        # Sous-titres détaillés
        if hasattr(job, 'has_subtitles') and job.has_subtitles:
            lines.append(f"Sous-titres: Oui")
            if hasattr(job, 'subtitle_info'):
                lines.append(f"  Pistes détectées: {job.subtitle_info.get('count', 0)}")
            if hasattr(job, 'subtitle_paths'):
                lines.append(f"  Pistes extraites: {len(job.subtitle_paths)}")
                lines.append("  Détail des pistes:")
                for i, sub in enumerate(job.subtitle_paths):
                    lang = sub.get('language', 'unknown').upper()
                    codec = sub.get('codec', 'unknown')
                    title = sub.get('title', '')
                    forced = " [FORCÉ]" if sub.get('forced') else ""
                    default = " [DÉFAUT]" if sub.get('default') else ""
                    lines.append(f"    {i+1}. {lang} ({codec}){forced}{default}")
                    if title:
                        lines.append(f"       Titre: {title}")
        else:
            lines.append(f"Sous-titres: Non")
        
        lines.append("")
        
        # Statistiques de traitement
        lines.append("=== TRAITEMENT ===")
        lines.append(f"Lots créés: {len(job.batches)}")
        lines.append(f"Lots terminés: {job.completed_batches}")
        lines.append(f"Lots échoués: {job.failed_batches}")
        lines.append(f"Taux de succès: {(job.completed_batches / len(job.batches) * 100):.1f}%")
        
        if job.processing_time:
            lines.append(f"Temps total de traitement: {format_duration(job.processing_time)}")
            frames_per_second = job.total_frames / job.processing_time if job.processing_time > 0 else 0
            lines.append(f"Performance: {frames_per_second:.2f} frames/seconde")
        
        lines.append("")
        
        # Détail des lots
        lines.append("=== DÉTAIL DES LOTS ===")
        for i, batch_id in enumerate(job.batches):
            if batch_id in self.server.batches:
                batch = self.server.batches[batch_id]
                status = batch.status.value
                client = batch.assigned_client or "Non assigné"
                if client == "SERVER_NATIVE":
                    client = "Serveur (processeur natif)"
                
                lines.append(f"Lot {i+1:3d}: {status:12s} | Client: {client:20s} | Frames: {len(batch.frame_paths):3d}")
                
                if batch.error_message:
                    lines.append(f"         Erreur: {batch.error_message}")
        
        return "\n".join(lines)
    
    def export_job_report(self):
        """Exporte un rapport détaillé du job sélectionné"""
        if not self.current_selected_job:
            QMessageBox.information(self, "Export", "Aucun job sélectionné")
            return
        
        try:
            from PyQt5.QtWidgets import QFileDialog
            
            # Nom de fichier par défaut
            job_name = Path(self.current_selected_job.input_video_path).stem
            default_filename = f"rapport_job_{job_name}_{self.current_selected_job.id[:8]}.txt"
            
            # Sélection du fichier de destination
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Exporter le rapport du job", default_filename,
                "Fichiers texte (*.txt);;Tous les fichiers (*)"
            )
            
            if not file_path:
                return
            
            # Génération et sauvegarde du rapport
            report_content = self.get_job_summary_for_export(self.current_selected_job)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(report_content)
            
            QMessageBox.information(
                self, "Export réussi", 
                f"Rapport du job exporté vers:\n{file_path}"
            )
            
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'export", f"Erreur lors de l'export du rapport:\n{str(e)}")
    
    def contextMenuEvent(self, event):
        """Menu contextuel pour actions avancées"""
        if self.current_selected_job:
            from PyQt5.QtWidgets import QMenu, QAction
            
            menu = QMenu(self)
            
            # Action d'export de rapport
            export_action = QAction("Exporter rapport détaillé", self)
            export_action.triggered.connect(self.export_job_report)
            menu.addAction(export_action)
            
            # Action de copie d'ID
            copy_id_action = QAction("Copier ID du job", self)
            copy_id_action.triggered.connect(lambda: self.copy_to_clipboard(self.current_selected_job.id))
            menu.addAction(copy_id_action)
            
            # Séparateur
            menu.addSeparator()
            
            # Actions selon le status
            if self.current_selected_job.status.value == "failed":
                retry_action = QAction("Remettre en traitement", self)
                retry_action.triggered.connect(self.retry_failed_job)
                menu.addAction(retry_action)
            
            if self.current_selected_job.status.value in ["processing", "extracting"]:
                cancel_action = QAction("Annuler le job", self)
                cancel_action.triggered.connect(self.cancel_job)
                menu.addAction(cancel_action)
            
            # Affichage du menu
            menu.exec_(event.globalPos())
    
    def copy_to_clipboard(self, text):
        """Copie un texte dans le presse-papiers"""
        try:
            from PyQt5.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            
            QMessageBox.information(self, "Copié", f"ID copié dans le presse-papiers:\n{text}")
        except Exception as e:
            QMessageBox.warning(self, "Erreur", f"Impossible de copier dans le presse-papiers:\n{str(e)}")
    
    def retry_failed_job(self):
        """Remet en traitement un job échoué"""
        if not self.current_selected_job:
            return
        
        job = self.current_selected_job
        
        if job.status.value != "failed":
            QMessageBox.information(self, "Retry", "Ce job n'est pas en échec")
            return
        
        reply = QMessageBox.question(
            self, "Recommencer le job",
            f"Remettre en traitement le job {job.id[:8]}?\n\n"
            f"Cela va:\n"
            f"- Remettre tous les lots échoués en attente\n"
            f"- Redémarrer le traitement des lots non terminés\n"
            f"- Conserver les lots déjà terminés",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                from models.job import JobStatus
                from models.batch import BatchStatus
                
                # Remettre le job en traitement
                job.status = JobStatus.PROCESSING
                job.error_message = ""
                
                # Remettre les lots échoués en attente
                reset_count = 0
                for batch_id in job.batches:
                    if batch_id in self.server.batches:
                        batch = self.server.batches[batch_id]
                        if batch.status in [BatchStatus.FAILED, BatchStatus.TIMEOUT]:
                            batch.reset()
                            reset_count += 1
                
                QMessageBox.information(
                    self, "Job relancé", 
                    f"Job {job.id[:8]} remis en traitement\n"
                    f"{reset_count} lots remis en attente"
                )
                
                # Actualiser l'affichage
                self.refresh_data()
                
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Erreur lors de la relance du job:\n{str(e)}")
    
    def cancel_job(self):
        """Annule un job en cours"""
        if not self.current_selected_job:
            return
        
        job = self.current_selected_job
        
        if job.status.value not in ["processing", "extracting", "assembling"]:
            QMessageBox.information(self, "Annulation", "Ce job n'est pas en cours de traitement")
            return
        
        reply = QMessageBox.question(
            self, "Annuler le job",
            f"Annuler le job {job.id[:8]}?\n\n"
            f"⚠️ Cette action est irréversible.\n"
            f"Le job sera marqué comme annulé et tous les lots en cours seront arrêtés.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                from models.job import JobStatus
                from models.batch import BatchStatus
                
                # Annuler le job
                job.cancel()
                
                # Libérer tous les lots en cours
                freed_count = 0
                for batch_id in job.batches:
                    if batch_id in self.server.batches:
                        batch = self.server.batches[batch_id]
                        if batch.status in [BatchStatus.ASSIGNED, BatchStatus.PROCESSING]:
                            # Libérer le client
                            if batch.assigned_client and batch.assigned_client in self.server.clients:
                                client = self.server.clients[batch.assigned_client]
                                client.current_batch = None
                                client.status = client.status  # Garder le status actuel
                            
                            # Marquer le lot comme annulé
                            batch.status = BatchStatus.FAILED
                            batch.error_message = "Job annulé par l'utilisateur"
                            freed_count += 1
                
                QMessageBox.information(
                    self, "Job annulé", 
                    f"Job {job.id[:8]} annulé avec succès\n"
                    f"{freed_count} lots libérés"
                )
                
                # Actualiser l'affichage
                self.refresh_data()
                
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Erreur lors de l'annulation du job:\n{str(e)}")
    
    def get_jobs_statistics(self) -> dict:
        """Retourne les statistiques générales des jobs"""
        jobs = list(self.server.jobs.values())
        
        if not jobs:
            return {
                'total_jobs': 0,
                'completed_jobs': 0,
                'failed_jobs': 0,
                'processing_jobs': 0,
                'total_frames': 0,
                'total_processing_time': 0,
                'average_fps': 0,
                'jobs_with_audio': 0,
                'jobs_with_subtitles': 0
            }
        
        stats = {
            'total_jobs': len(jobs),
            'completed_jobs': sum(1 for j in jobs if j.status.value == 'completed'),
            'failed_jobs': sum(1 for j in jobs if j.status.value == 'failed'),
            'processing_jobs': sum(1 for j in jobs if j.status.value in ['processing', 'extracting', 'assembling']),
            'total_frames': sum(j.total_frames for j in jobs),
            'total_processing_time': sum(j.processing_time or 0 for j in jobs),
            'jobs_with_audio': sum(1 for j in jobs if j.has_audio),
            'jobs_with_subtitles': sum(1 for j in jobs if getattr(j, 'has_subtitles', False))
        }
        
        # Calcul FPS moyen
        if stats['total_processing_time'] > 0:
            stats['average_fps'] = stats['total_frames'] / stats['total_processing_time']
        else:
            stats['average_fps'] = 0
        
        return stats
    

    # Ajoutez ces méthodes dans JobsTab pour améliorer l'affichage des infos audio

def _get_audio_display_info(self, job) -> tuple:
    """Génère les informations d'affichage pour les pistes audio"""
    if not job.has_audio:
        return "❌", "Aucun audio détecté"
    
    total_tracks = len(job.media_info.audio_tracks)
    extracted_tracks = len(job.get_extracted_audio_tracks()) if hasattr(job, 'get_extracted_audio_tracks') else 0
    
    if total_tracks == 0:
        return "❌", "Aucune piste audio détectée"
    
    if extracted_tracks == 0:
        return f"🔍 {total_tracks}", f"{total_tracks} piste(s) audio détectée(s) mais non extraite(s)"
    elif extracted_tracks == total_tracks:
        return f"✅ {extracted_tracks}", f"{extracted_tracks} piste(s) audio extraite(s) avec succès"
    else:
        return f"⚠️ {extracted_tracks}/{total_tracks}", f"{extracted_tracks} sur {total_tracks} piste(s) audio extraite(s)"

def update_jobs_table(self):
    """Met à jour le tableau des jobs avec informations audio améliorées"""
    jobs = list(self.server.jobs.values())
    self.jobs_table.setRowCount(len(jobs))
    
    for row, job in enumerate(jobs):
        # ID (8 premiers caractères)
        id_item = QTableWidgetItem(job.id[:8])
        id_item.setToolTip(job.id)
        self.jobs_table.setItem(row, 0, id_item)
        
        # Fichier
        filename = Path(job.input_video_path).name if job.input_video_path else "N/A"
        filename_item = QTableWidgetItem(filename)
        filename_item.setToolTip(job.input_video_path or "Chemin inconnu")
        self.jobs_table.setItem(row, 1, filename_item)
        
        # Status avec couleur
        status_item = QTableWidgetItem(job.status.value)
        if job.status.value == "completed":
            status_item.setBackground(QColor(144, 238, 144))
        elif job.status.value == "failed":
            status_item.setBackground(QColor(255, 182, 193))
        elif job.status.value in ["processing", "extracting", "assembling"]:
            status_item.setBackground(QColor(255, 255, 144))
        self.jobs_table.setItem(row, 2, status_item)
        
        # Progression
        progress_item = QTableWidgetItem(f"{job.progress:.1f}%")
        self.jobs_table.setItem(row, 3, progress_item)
        
        # Lots total
        self.jobs_table.setItem(row, 4, QTableWidgetItem(str(len(job.batches))))
        
        # Terminés
        completed_count = job.completed_batches
        self.jobs_table.setItem(row, 5, QTableWidgetItem(str(completed_count)))
        
        # Audio - logique améliorée avec multi-pistes
        audio_text, audio_tooltip = self._get_audio_display_info(job)
        audio_item = QTableWidgetItem(audio_text)
        audio_item.setToolTip(audio_tooltip)
        self.jobs_table.setItem(row, 6, audio_item)
        
        # Sous-titres - logique existante
        subtitle_text, subtitle_tooltip = self._get_subtitle_display_info(job)
        subtitle_item = QTableWidgetItem(subtitle_text)
        subtitle_item.setToolTip(subtitle_tooltip)
        self.jobs_table.setItem(row, 7, subtitle_item)
        
        # Temps de traitement
        processing_time = job.processing_time or 0
        if processing_time > 0:
            time_str = format_duration(processing_time)
        else:
            time_str = "En cours..." if job.status.value in ["processing", "extracting", "assembling"] else "N/A"
        self.jobs_table.setItem(row, 8, QTableWidgetItem(time_str))
        
        # Créé le
        created_str = job.created_at.strftime('%d/%m %H:%M:%S')
        self.jobs_table.setItem(row, 9, QTableWidgetItem(created_str))

def create_audio_details_section(self):
    """Crée une section détaillée pour les pistes audio"""
    audio_group = QGroupBox("Pistes audio détectées")
    audio_layout = QVBoxLayout(audio_group)
    
    # Boutons d'action pour l'audio
    audio_actions_layout = QHBoxLayout()
    
    self.preview_audio_btn = QPushButton("Aperçu Audio")
    self.preview_audio_btn.clicked.connect(self.preview_audio_tracks)
    self.preview_audio_btn.setEnabled(False)
    
    self.export_audio_btn = QPushButton("Exporter Audio")
    self.export_audio_btn.clicked.connect(self.export_audio_tracks)
    self.export_audio_btn.setEnabled(False)
    
    audio_actions_layout.addWidget(self.preview_audio_btn)
    audio_actions_layout.addWidget(self.export_audio_btn)
    audio_actions_layout.addStretch()
    
    # Tableau des pistes audio
    self.audio_table = QTableWidget()
    self.audio_table.setColumnCount(6)
    self.audio_table.setHorizontalHeaderLabels([
        "Langue", "Codec", "Canaux", "Titre", "État", "Fichier"
    ])
    self.audio_table.setMaximumHeight(150)
    
    # Configuration du tableau audio
    audio_header = self.audio_table.horizontalHeader()
    audio_header.setStretchLastSection(True)
    audio_header.setSectionResizeMode(QHeaderView.ResizeToContents)
    
    audio_layout.addLayout(audio_actions_layout)
    audio_layout.addWidget(self.audio_table)
    
    return audio_group

def update_job_details(self, job):
    """Met à jour les détails du job sélectionné avec infos audio"""
    # Informations générales existantes...
    details = []
    details.append(f"=== JOB {job.id[:8]} ===")
    details.append(f"Fichier d'entrée: {Path(job.input_video_path).name if job.input_video_path else 'N/A'}")
    details.append(f"Fichier de sortie: {Path(job.output_video_path).name if job.output_video_path else 'N/A'}")
    details.append(f"Status: {job.status.value}")
    details.append(f"Progression: {job.progress:.1f}%")
    details.append("")
    
    # Informations techniques avec audio détaillé
    details.append("=== INFORMATIONS TECHNIQUES ===")
    details.append(f"Frames totales: {job.total_frames}")
    details.append(f"Framerate: {job.frame_rate:.3f} fps")
    
    # Audio détaillé
    if job.has_audio and job.media_info.audio_tracks:
        details.append(f"Audio: Oui ({len(job.media_info.audio_tracks)} piste(s))")
        extracted_audio = job.get_extracted_audio_tracks() if hasattr(job, 'get_extracted_audio_tracks') else []
        details.append(f"  - Pistes détectées: {len(job.media_info.audio_tracks)}")
        details.append(f"  - Pistes extraites: {len(extracted_audio)}")
        
        # Détail des langues audio
        languages = job.audio_languages if hasattr(job, 'audio_languages') else []
        if languages:
            details.append(f"  - Langues: {', '.join(languages)}")
    else:
        details.append("Audio: Non")
    
    # Sous-titres (logique existante)
    subtitle_info = getattr(job, 'has_subtitles', False)
    details.append(f"Sous-titres: {'Oui' if subtitle_info else 'Non'}")
    
    if subtitle_info and hasattr(job, 'subtitle_info'):
        detected = job.subtitle_info.get('count', 0)
        extracted = len(getattr(job, 'subtitle_paths', []))
        details.append(f"  - Détectés: {detected}")
        details.append(f"  - Extraits: {extracted}")
    
    # ... reste des détails existants ...
    
    self.details_text.setPlainText("\n".join(details))
    
    # Mise à jour des tables audio et sous-titres
    self.update_audio_table(job)
    self.update_subtitles_table(job)

def update_audio_table(self, job):
    """Met à jour la table des pistes audio"""
    if not hasattr(job, 'media_info') or not job.media_info.audio_tracks:
        self.audio_table.setRowCount(0)
        self.preview_audio_btn.setEnabled(False)
        self.export_audio_btn.setEnabled(False)
        return
    
    audio_tracks = job.media_info.audio_tracks
    self.audio_table.setRowCount(len(audio_tracks))
    
    for row, track in enumerate(audio_tracks):
        # Langue
        language = track.get('language', 'unknown')
        if language != 'unknown':
            # Mapping des langues
            language_map = {
                'fr': 'Français', 'en': 'English', 'es': 'Español',
                'de': 'Deutsch', 'it': 'Italiano', 'ja': '日本語'
            }
            language_display = language_map.get(language.lower(), language.upper())
        else:
            language_display = 'Inconnu'
        self.audio_table.setItem(row, 0, QTableWidgetItem(language_display))
        
        # Codec
        codec = track.get('codec', 'unknown')
        self.audio_table.setItem(row, 1, QTableWidgetItem(codec))
        
        # Canaux
        channels = track.get('channels', 0)
        if channels > 0:
            if channels == 1:
                channel_desc = "Mono"
            elif channels == 2:
                channel_desc = "Stéréo"
            elif channels == 6:
                channel_desc = "5.1"
            elif channels == 8:
                channel_desc = "7.1"
            else:
                channel_desc = f"{channels}ch"
        else:
            channel_desc = "Inconnu"
        self.audio_table.setItem(row, 2, QTableWidgetItem(channel_desc))
        
        # Titre
        title = track.get('title', '')
        self.audio_table.setItem(row, 3, QTableWidgetItem(title))
        
        # État
        if track.get('extraction_success', False):
            state_item = QTableWidgetItem("✅ Extrait")
            state_item.setBackground(QColor(144, 238, 144))
        elif track.get('extraction_error'):
            state_item = QTableWidgetItem("❌ Erreur")
            state_item.setBackground(QColor(255, 182, 193))
        else:
            state_item = QTableWidgetItem("⏳ En attente")
            state_item.setBackground(QColor(255, 255, 144))
        self.audio_table.setItem(row, 4, state_item)
        
        # Fichier
        extraction_path = track.get('extraction_path', '')
        if extraction_path:
            filename = Path(extraction_path).name
            file_item = QTableWidgetItem(filename)
            file_item.setToolTip(extraction_path)
        else:
            file_item = QTableWidgetItem("N/A")
        self.audio_table.setItem(row, 5, file_item)
    
    # Activation des boutons selon la disponibilité des pistes audio
    has_audio = len(audio_tracks) > 0
    has_extracted_audio = any(track.get('extraction_success', False) for track in audio_tracks)
    
    self.preview_audio_btn.setEnabled(has_audio)
    self.export_audio_btn.setEnabled(has_extracted_audio)

def preview_audio_tracks(self):
    """Affiche un aperçu des pistes audio du job sélectionné"""
    if not self.current_selected_job:
        return
    
    try:
        job = self.current_selected_job
        
        if not hasattr(job, 'media_info') or not job.media_info.audio_tracks:
            QMessageBox.information(self, "Aperçu", "Aucune piste audio disponible")
            return
        
        preview_lines = []
        preview_lines.append(f"=== PISTES AUDIO - JOB {job.id[:8]} ===")
        preview_lines.append(f"Fichier source: {Path(job.input_video_path).name}")
        preview_lines.append(f"Pistes détectées: {len(job.media_info.audio_tracks)}")
        preview_lines.append("")
        
        for i, track in enumerate(job.media_info.audio_tracks):
            # Statut
            if track.get('extraction_success', False):
                status_icon = "✅"
                status_text = "Extrait"
            elif track.get('extraction_error'):
                status_icon = "❌"
                status_text = f"Erreur: {track['extraction_error']}"
            else:
                status_icon = "⏳"
                status_text = "En attente"
            
            # Informations de la piste
            language = track.get('language', 'unknown')
            codec = track.get('codec', 'unknown')
            channels = track.get('channels', 0)
            title = track.get('title', '')
            
            preview_lines.append(f"{i+1}. {status_icon} {language.upper()} - {codec}")
            
            if channels > 0:
                if channels == 1:
                    preview_lines.append(f"   Canaux: Mono")
                elif channels == 2:
                    preview_lines.append(f"   Canaux: Stéréo")
                elif channels == 6:
                    preview_lines.append(f"   Canaux: 5.1")
                elif channels == 8:
                    preview_lines.append(f"   Canaux: 7.1")
                else:
                    preview_lines.append(f"   Canaux: {channels}ch")
            
            if title:
                preview_lines.append(f"   Titre: {title}")
            
            if track.get('bitrate', 0) > 0:
                bitrate_kbps = track['bitrate'] // 1000
                preview_lines.append(f"   Bitrate: {bitrate_kbps} kbps")
            
            preview_lines.append(f"   Statut: {status_text}")
            preview_lines.append("")
        
        # Analyse de compatibilité
        if hasattr(job, 'get_audio_compatibility_report'):
            compat = job.get_audio_compatibility_report()
            if compat.get('problematic_tracks'):
                preview_lines.append("⚠️  CONVERSIONS NÉCESSAIRES:")
                for issue in compat['problematic_tracks']:
                    preview_lines.append(f"   - {issue['recommendation']}")
                preview_lines.append("")
        
        # Affichage dans une boîte de dialogue
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Aperçu des pistes audio")
        dialog.setText("Informations sur les pistes audio détectées:")
        dialog.setDetailedText("\n".join(preview_lines))
        dialog.setStyleSheet("QLabel { font-family: 'Consolas', monospace; }")
        dialog.exec_()
        
    except Exception as e:
        QMessageBox.warning(self, "Erreur", f"Erreur lors de l'aperçu des pistes audio:\n{str(e)}")

def export_audio_tracks(self):
    """Exporte les pistes audio du job sélectionné"""
    if not self.current_selected_job:
        return
    
    job = self.current_selected_job
    
    if not hasattr(job, 'media_info') or not job.media_info.audio_tracks:
        QMessageBox.information(self, "Export", "Aucune piste audio à exporter")
        return
    
    # Vérifier qu'il y a des pistes extraites
    extracted_tracks = [track for track in job.media_info.audio_tracks 
                       if track.get('extraction_success', False)]
    
    if not extracted_tracks:
        QMessageBox.information(self, "Export", "Aucune piste audio extraite à exporter")
        return
    
    try:
        from PyQt5.QtWidgets import QFileDialog
        import shutil
        
        # Sélection du dossier de destination
        dest_dir = QFileDialog.getExistingDirectory(
            self, "Sélectionner le dossier de destination", 
            str(Path.home())
        )
        
        if not dest_dir:
            return
        
        dest_path = Path(dest_dir)
        job_name = Path(job.input_video_path).stem
        copied_files = []
        
        for track in extracted_tracks:
            source_path = Path(track['extraction_path'])
            if source_path.exists():
                # Nom de fichier avec langue et format
                language = track.get('language', 'unknown')
                format_ext = track.get('extraction_format', 'aac')
                dest_filename = f"{job_name}_audio_{language}.{format_ext}"
                dest_file = dest_path / dest_filename
                
                # Copie du fichier
                shutil.copy2(source_path, dest_file)
                copied_files.append(dest_filename)
        
        if copied_files:
            files_list = "\n".join(copied_files)
            QMessageBox.information(
                self, "Export réussi", 
                f"Pistes audio exportées vers:\n{dest_dir}\n\nFichiers copiés:\n{files_list}"
            )
        else:
            QMessageBox.warning(self, "Export échoué", "Aucun fichier audio trouvé")
            
    except Exception as e:
        QMessageBox.critical(self, "Erreur d'export", f"Erreur lors de l'export:\n{str(e)}")

# Mise à jour de la méthode create_job_details_section pour inclure l'audio
def create_job_details_section(self):
    """Crée la section des détails du job avec support audio"""
    widget = QWidget()
    layout = QVBoxLayout(widget)
    
    details_label = QLabel("Détails du job sélectionné")
    details_label.setFont(QFont("Arial", 12, QFont.Bold))
    
    # Zone de texte pour les détails généraux
    self.details_text = QTextEdit()
    self.details_text.setReadOnly(True)
    self.details_text.setMaximumHeight(200)
    self.details_text.setFont(QFont("Consolas", 9))
    self.details_text.setPlainText("Sélectionnez un job pour voir les détails")
    
    # Section pistes audio
    audio_group = self.create_audio_details_section()
    
    # Section sous-titres (existante)
    subtitles_group = QGroupBox("Sous-titres détectés")
    subtitles_layout = QVBoxLayout(subtitles_group)
    
    # ... code existant pour les sous-titres ...
    
    layout.addWidget(details_label)
    layout.addWidget(self.details_text)
    layout.addWidget(audio_group)
    layout.addWidget(subtitles_group)
    layout.addStretch()
    
    return widget