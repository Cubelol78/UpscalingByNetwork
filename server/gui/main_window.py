import sys
import os
import threading
import asyncio
from PyQt5.QtWidgets import QMainWindow, QMessageBox, QProgressDialog
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QThread, pyqtSlot, QObject
from PyQt5.QtGui import QFont
from pathlib import Path

# Worker thread pour la création de jobs
class JobCreationWorker(QThread):
    """Worker thread pour créer des jobs sans bloquer l'interface"""
    
    # Signaux pour communiquer avec l'interface principale
    job_created = pyqtSignal(object)  # Émis quand le job est créé
    extraction_progress = pyqtSignal(str, int)  # Émis pendant l'extraction (message, pourcentage)
    error_occurred = pyqtSignal(str)  # Émis en cas d'erreur
    finished = pyqtSignal()  # Émis à la fin
    
    def __init__(self, server, file_path):
        super().__init__()
        self.server = server
        self.file_path = file_path
        self.job = None
        
    def run(self):
        """Exécution du worker dans un thread séparé"""
        try:
            # Créer une nouvelle boucle d'événements pour ce thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # Phase 1: Création du job
                self.extraction_progress.emit("Analyse du fichier vidéo...", 10)
                self.job = loop.run_until_complete(
                    self.server.video_processor.create_job_from_video(self.file_path)
                )
                
                if not self.job:
                    self.error_occurred.emit("Impossible de créer le job à partir du fichier vidéo")
                    return
                
                self.extraction_progress.emit("Job créé, extraction des médias...", 30)
                
                # Phase 2: Extraction des frames et médias
                success = loop.run_until_complete(
                    self._extract_with_progress()
                )
                
                if success:
                    # Ajouter le job au serveur
                    self.server.jobs[self.job.id] = self.job
                    self.server.current_job = self.job.id
                    
                    self.extraction_progress.emit("Extraction terminée !", 100)
                    self.job_created.emit(self.job)
                else:
                    self.error_occurred.emit("Erreur lors de l'extraction des frames et médias")
                    
            finally:
                loop.close()
                
        except Exception as e:
            self.error_occurred.emit(f"Erreur lors de la création du job: {str(e)}")
        finally:
            self.finished.emit()
    
    async def _extract_with_progress(self):
        """Extraction avec émission de signaux de progression"""
        try:
            # Démarrer l'extraction
            success = await self.server.video_processor.extract_frames(self.job)
            
            if success:
                # Mise à jour périodique de la progression
                total_frames = self.job.total_frames
                
                if total_frames > 0:
                    # Simuler une progression (en réalité, l'extraction FFmpeg est difficile à monitorer)
                    for progress in range(40, 90, 10):
                        self.extraction_progress.emit(
                            f"Extraction en cours... {self.job.total_frames} frames détectées", 
                            progress
                        )
                        await asyncio.sleep(0.1)  # Petite pause pour permettre les signaux
                
                self.extraction_progress.emit(
                    f"Extraction terminée: {self.job.total_frames} frames, {len(self.job.batches)} lots créés", 
                    95
                )
                
            return success
            
        except Exception as e:
            self.error_occurred.emit(f"Erreur extraction: {str(e)}")
            return False

# Mise à jour de la MainWindow
class MainWindow(QMainWindow):
    """Version corrigée avec threads pour éviter le blocage de l'interface"""
    
    def __init__(self, server):
        super().__init__()
        self.server = server
        self.logger = get_logger(__name__)
        self.server_thread = None
        self.job_worker = None
        self.progress_dialog = None
        
        # Configuration de la fenêtre
        self.setWindowTitle("Distributed Upscaling Server v1.0")
        self.setGeometry(100, 100, 1400, 900)
        self.setMinimumSize(1200, 800)
        
        # Initialisation de l'interface
        self.setup_ui()
        self.setup_timers()
        self.setup_connections()
        
        # Chargement de la configuration sauvegardée dans l'interface
        self.load_saved_configuration()
        
        # Démarrage du monitoring
        performance_monitor.start_monitoring()
        
        self.logger.info("Interface graphique initialisée avec configuration chargée")
    
    def start_new_job(self):
        """Démarre un nouveau job avec interface non-bloquante"""
        if not self.server.running:
            QMessageBox.warning(self, "Erreur", "Le serveur doit être démarré pour créer un job")
            return
            
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Sélectionner une vidéo", "",
            "Vidéos (*.mp4 *.avi *.mov *.mkv *.webm *.flv);;Tous les fichiers (*)"
        )
        
        if file_path:
            self.start_job_async_threaded(file_path)
    
    def start_job_async_threaded(self, file_path):
        """Démarre un job de manière asynchrone avec thread worker"""
        try:
            # Vérifier que le fichier vidéo existe
            if not os.path.exists(file_path):
                QMessageBox.critical(self, "Erreur", f"Le fichier vidéo n'existe pas:\n{file_path}")
                return
            
            # Créer et configurer la boîte de dialogue de progression
            self.progress_dialog = QProgressDialog("Préparation du job...", "Annuler", 0, 100, self)
            self.progress_dialog.setWindowTitle("Création du job en cours")
            self.progress_dialog.setModal(True)
            self.progress_dialog.setMinimumDuration(0)  # Afficher immédiatement
            self.progress_dialog.canceled.connect(self.cancel_job_creation)
            
            # Créer et démarrer le worker thread
            self.job_worker = JobCreationWorker(self.server, file_path)
            
            # Connecter les signaux
            self.job_worker.job_created.connect(self.on_job_created)
            self.job_worker.extraction_progress.connect(self.on_extraction_progress)
            self.job_worker.error_occurred.connect(self.on_job_error)
            self.job_worker.finished.connect(self.on_job_creation_finished)
            
            # Démarrer le worker
            self.job_worker.start()
            
            self.logger.info(f"Création du job démarrée pour: {Path(file_path).name}")
            
        except Exception as e:
            self.logger.error(f"Erreur start_job_async_threaded: {e}")
            QMessageBox.critical(self, "Erreur", f"Erreur lors de la création du job:\n{str(e)}")
    
    @pyqtSlot(str, int)
    def on_extraction_progress(self, message, progress):
        """Gestionnaire de progression de l'extraction"""
        if self.progress_dialog:
            self.progress_dialog.setLabelText(message)
            self.progress_dialog.setValue(progress)
            
            # Traiter les événements Qt pour garder l'interface réactive
            QApplication.processEvents()
    
    @pyqtSlot(object)
    def on_job_created(self, job):
        """Gestionnaire de création réussie du job"""
        try:
            filename = Path(job.input_video_path).name if job.input_video_path else "Fichier inconnu"
            output_name = Path(job.output_video_path).name if job.output_video_path else "Sortie inconnue"
            
            # Fermer la boîte de progression
            if self.progress_dialog:
                self.progress_dialog.close()
            
            # Afficher le message de succès
            QMessageBox.information(self, "Succès", 
                f"Job créé avec succès!\n\n"
                f"📁 Fichier d'entrée: {filename}\n"
                f"📁 Fichier de sortie: {output_name}\n"
                f"🎬 {job.total_frames} frames extraites\n"
                f"📦 {len(job.batches)} lots créés\n"
                f"🎵 Audio: {'Oui' if job.has_audio else 'Non'}\n"
                f"📝 Sous-titres: {len(job.subtitle_tracks) if hasattr(job, 'subtitle_tracks') else 0}\n\n"
                f"Le traitement va maintenant commencer automatiquement."
            )
            
            self.logger.info(f"Job créé avec succès: {job.id[:8]} - {filename}")
            
        except Exception as e:
            self.logger.error(f"Erreur affichage succès job: {e}")
    
    @pyqtSlot(str)
    def on_job_error(self, error_message):
        """Gestionnaire d'erreur de création du job"""
        # Fermer la boîte de progression
        if self.progress_dialog:
            self.progress_dialog.close()
        
        # Afficher l'erreur
        QMessageBox.critical(self, "Erreur de création du job", error_message)
        self.logger.error(f"Erreur création job: {error_message}")
    
    @pyqtSlot()
    def on_job_creation_finished(self):
        """Nettoyage à la fin de la création du job"""
        # Fermer la boîte de progression si elle est encore ouverte
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
        
        # Nettoyer le worker
        if self.job_worker:
            self.job_worker.deleteLater()
            self.job_worker = None
        
        self.logger.debug("Création du job terminée, nettoyage effectué")
    
    def cancel_job_creation(self):
        """Annule la création du job en cours"""
        if self.job_worker and self.job_worker.isRunning():
            self.job_worker.terminate()  # Forcer l'arrêt du thread
            self.job_worker.wait(3000)   # Attendre max 3 secondes
            
            if self.job_worker.isRunning():
                self.job_worker.kill()   # Forcer l'arrêt brutal si nécessaire
            
            self.logger.info("Création du job annulée par l'utilisateur")
        
        self.on_job_creation_finished()
    
    def setup_timers(self):
        """Configure les timers pour les mises à jour - VERSION OPTIMISÉE"""
        # Timer principal - plus fréquent pour les mises à jour critiques
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_interface)
        self.update_timer.start(1000)  # 1 seconde pour plus de réactivité
        
        # Timer pour les graphiques de performance - moins fréquent
        self.performance_timer = QTimer()
        self.performance_timer.timeout.connect(self.update_performance_charts)
        self.performance_timer.start(5000)  # 5 secondes
        
        # Timer spécial pour les jobs/lots - mise à jour plus fréquente
        self.jobs_timer = QTimer()
        self.jobs_timer.timeout.connect(self.update_jobs_display)
        self.jobs_timer.start(2000)  # 2 secondes pour les jobs
    
    def update_interface(self):
        """Met à jour l'interface avec les données du serveur - VERSION OPTIMISÉE"""
        try:
            # Ne pas traiter les mises à jour si un job est en cours de création
            if self.job_worker and self.job_worker.isRunning():
                return
            
            if self.server.running:
                stats = self.server.get_statistics()
                self.status_bar.update_status(stats)
                
                # Mise à jour de l'onglet actuel seulement pour éviter les blocages
                current_tab_index = self.tabs_manager.currentIndex()
                if current_tab_index == 0:  # Vue d'ensemble
                    self.tabs_manager.overview_tab.update_tab(stats)
                elif current_tab_index == 1:  # Clients
                    self.tabs_manager.clients_tab.update_tab()
            else:
                # Serveur arrêté - mise à jour basique
                self.status_bar.update_status_stopped()
            
        except Exception as e:
            self.logger.debug(f"Erreur mise à jour interface: {e}")  # Debug seulement
    
    def update_jobs_display(self):
        """Met à jour spécifiquement l'affichage des jobs et lots - VERSION OPTIMISÉE"""
        try:
            # Ne pas traiter si création de job en cours
            if self.job_worker and self.job_worker.isRunning():
                return
                
            if not self.server.running:
                return
            
            # Mise à jour forcée de l'onglet Jobs & Lots s'il est visible
            current_tab_index = self.tabs_manager.currentIndex()
            if current_tab_index == 2:  # Jobs & Lots
                self.tabs_manager.jobs_tab.update_tab()
            
            # Force la mise à jour de la barre de statut pour les jobs
            if hasattr(self, 'status_bar'):
                try:
                    stats = self.server.get_statistics()
                    self.status_bar.update_status(stats)
                except:
                    pass  # Ignorer les erreurs de stats pendant le traitement
                
        except Exception as e:
            self.logger.debug(f"Erreur mise à jour jobs: {e}")
    
    def closeEvent(self, event):
        """Gestionnaire de fermeture de l'application - VERSION AMÉLIORÉE"""
        try:
            # Vérifier s'il y a une création de job en cours
            if self.job_worker and self.job_worker.isRunning():
                reply = QMessageBox.question(
                    self, "Job en cours", 
                    "Une création de job est en cours. Voulez-vous vraiment quitter?\n"
                    "Cela annulera la création du job.",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                
                if reply == QMessageBox.No:
                    event.ignore()
                    return
                else:
                    # Annuler la création du job
                    self.cancel_job_creation()
            
            # Vérifier les jobs en cours de traitement
            active_jobs = 0
            if hasattr(self.server, 'jobs'):
                active_jobs = len([job for job in self.server.jobs.values() 
                                  if job.status.value in ['processing', 'extracting', 'assembling']])
            
            if active_jobs > 0:
                reply = QMessageBox.question(
                    self, "Confirmation", 
                    f"Le serveur traite actuellement {active_jobs} job(s).\n"
                    "Êtes-vous sûr de vouloir quitter?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                
                if reply == QMessageBox.No:
                    event.ignore()
                    return
            else:
                reply = QMessageBox.question(
                    self, "Confirmation", "Êtes-vous sûr de vouloir quitter?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                
                if reply == QMessageBox.No:
                    event.ignore()
                    return
            
            # Arrêter les timers
            if hasattr(self, 'update_timer'):
                self.update_timer.stop()
            if hasattr(self, 'performance_timer'):
                self.performance_timer.stop()
            if hasattr(self, 'jobs_timer'):
                self.jobs_timer.stop()
            
            # Arrêter le monitoring
            performance_monitor.stop_monitoring()
            
            # Arrêter le serveur
            if self.server.running:
                try:
                    self.server.stop_sync()
                except Exception as e:
                    self.logger.error(f"Erreur arrêt serveur lors fermeture: {e}")
            
            event.accept()
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la fermeture: {e}")
            event.accept()  # Forcer la fermeture en cas d'erreur