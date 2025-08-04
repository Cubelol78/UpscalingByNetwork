# UpscalingByNetwork/client/windows/gui/processing_panel.py

import sys
import asyncio
import time
from pathlib import Path
from typing import Optional, Dict, Any
import qasync
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QTabWidget, QGroupBox, QGridLayout, QLabel, QPushButton, QLineEdit,
    QSpinBox, QTextEdit, QProgressBar, QSystemTrayIcon, QMenu, QAction,
    QMessageBox, QFrame, QSplitter, QCheckBox, QComboBox, QStyle,
    QHeaderView, QTableWidget, QTableWidgetItem, QSlider
)
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QThread
from PyQt5.QtGui import QFont, QIcon, QPixmap, QPalette, QColor

from ..core.distributed_client import DistributedClient
from .connection_panel import ConnectionPanel
from .processing_panel import ProcessingPanel
from .settings_panel import SettingsPanel

class ProcessingPanel(QWidget):
    """Onglet de suivi du traitement"""
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setup_ui()
        
        # Historique des lots traités
        self.batch_history = []
        self.max_history = 100
    
    def setup_ui(self):
        """Configure l'interface du panneau"""
        layout = QVBoxLayout(self)
        
        # Splitter principal
        main_splitter = QSplitter(Qt.Vertical)
        layout.addWidget(main_splitter)
        
        # Partie haute: Traitement en cours
        current_widget = self.create_current_processing()
        main_splitter.addWidget(current_widget)
        
        # Partie basse: Historique et statistiques
        history_widget = self.create_processing_history()
        main_splitter.addWidget(history_widget)
        
        main_splitter.setSizes([300, 400])
    
    def create_current_processing(self):
        """Crée la section de traitement en cours"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Lot en cours
        current_group = QGroupBox("Lot en cours de traitement")
        current_layout = QGridLayout(current_group)
        
        self.current_labels = {}
        current_items = [
            ("ID du lot:", "batch_id"),
            ("Job parent:", "job_id"),
            ("Images à traiter:", "total_images"),
            ("Images traitées:", "processed_images"),
            ("Temps écoulé:", "elapsed_time"),
            ("Temps estimé restant:", "eta"),
            ("Vitesse actuelle:", "current_speed"),
            ("Client assigné:", "assigned_client")
        ]
        
        for i, (label, key) in enumerate(current_items):
            row, col = i // 2, (i % 2) * 2
            
            current_layout.addWidget(QLabel(label), row, col)
            
            value_label = QLabel("-")
            value_label.setStyleSheet("font-weight: bold;")
            current_layout.addWidget(value_label, row, col + 1)
            
            self.current_labels[key] = value_label
        
        layout.addWidget(current_group)
        
        # Barre de progression détaillée
        progress_group = QGroupBox("Progression")
        progress_layout = QVBoxLayout(progress_group)
        
        # Barre de progression principale
        self.main_progress = QProgressBar()
        self.main_progress.setMinimumHeight(30)
        self.main_progress.setStyleSheet("""
            QProgressBar {
                border: 2px solid #d0d0d0;
                border-radius: 8px;
                text-align: center;
                font-weight: bold;
                font-size: 12px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4CAF50, stop:1 #45a049);
                border-radius: 6px;
                margin: 2px;
            }
        """)
        progress_layout.addWidget(self.main_progress)
        
        # Informations de progression
        progress_info_layout = QHBoxLayout()
        
        self.progress_percent_label = QLabel("0%")
        self.progress_percent_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #0078d4;")
        progress_info_layout.addWidget(self.progress_percent_label)
        
        progress_info_layout.addStretch()
        
        self.progress_detail_label = QLabel("En attente...")
        progress_info_layout.addWidget(self.progress_detail_label)
        
        progress_layout.addLayout(progress_info_layout)
        layout.addWidget(progress_group)
        
        # Contrôles de traitement
        controls_group = QGroupBox("Contrôles")
        controls_layout = QHBoxLayout(controls_group)
        
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setEnabled(False)
        controls_layout.addWidget(self.pause_btn)
        
        self.stop_btn = QPushButton("Arrêter")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("QPushButton { background-color: #dc3545; }")
        controls_layout.addWidget(self.stop_btn)
        
        controls_layout.addStretch()
        
        self.priority_label = QLabel("Priorité:")
        controls_layout.addWidget(self.priority_label)
        
        self.priority_slider = QSlider(Qt.Horizontal)
        self.priority_slider.setRange(1, 5)
        self.priority_slider.setValue(3)
        self.priority_slider.setEnabled(False)
        controls_layout.addWidget(self.priority_slider)
        
        layout.addWidget(controls_group)
        
        return widget
    
    def create_processing_history(self):
        """Crée la section d'historique"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # En-tête avec contrôles
        header_layout = QHBoxLayout()
        
        header_layout.addWidget(QLabel("Historique des lots traités"))
        header_layout.addStretch()
        
        clear_history_btn = QPushButton("Effacer")
        clear_history_btn.clicked.connect(self.clear_history)
        header_layout.addWidget(clear_history_btn)
        
        export_history_btn = QPushButton("Exporter")
        export_history_btn.clicked.connect(self.export_history)
        header_layout.addWidget(export_history_btn)
        
        layout.addLayout(header_layout)
        
        # Tableau d'historique
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(7)
        self.history_table.setHorizontalHeaderLabels([
            "Heure", "ID Lot", "Images", "Temps", "Statut", "Vitesse", "Erreur"
        ])
        
        # Configuration du tableau
        header = self.history_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Heure
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # ID
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Images
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Temps
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Statut
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Vitesse
        
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setSelectionBehavior(QTableWidget.SelectRows)
        
        layout.addWidget(self.history_table)
        
        # Statistiques globales
        stats_group = QGroupBox("Statistiques globales")
        stats_layout = QGridLayout(stats_group)
        
        self.stats_labels = {}
        stats_items = [
            ("Total lots traités:", "total_batches"),
            ("Total images:", "total_images"),
            ("Temps total:", "total_time"),
            ("Vitesse moyenne:", "avg_speed"),
            ("Taux de succès:", "success_rate"),
            ("Efficacité:", "efficiency")
        ]
        
        for i, (label, key) in enumerate(stats_items):
            row, col = i // 3, (i % 3) * 2
            
            stats_layout.addWidget(QLabel(label), row, col)
            
            value_label = QLabel("0")
            value_label.setStyleSheet("font-weight: bold; color: #0078d4;")
            stats_layout.addWidget(value_label, row, col + 1)
            
            self.stats_labels[key] = value_label
        
        layout.addWidget(stats_group)
        
        return widget
    
    def update_data(self, stats: Dict[str, Any]):
        """Met à jour les données du panneau"""
        if not self.main_window.client:
            return
        
        client = self.main_window.client
        
        # Mise à jour du lot en cours
        if client.current_batch_id:
            batch_id = client.current_batch_id
            short_id = batch_id.split('_')[-1] if '_' in batch_id else batch_id[:8]
            
            self.current_labels["batch_id"].setText(short_id)
            self.current_labels["processed_images"].setText(str(int(client.current_progress * 50 / 100)))
            self.current_labels["total_images"].setText("50")  # Taille lot par défaut
            
            # Progression
            progress = client.current_progress
            self.main_progress.setValue(int(progress))
            self.progress_percent_label.setText(f"{progress:.1f}%")
            
            if client.processing:
                self.progress_detail_label.setText("Traitement en cours...")
                self.pause_btn.setEnabled(True)
                self.stop_btn.setEnabled(True)
            else:
                self.progress_detail_label.setText("En attente...")
                self.pause_btn.setEnabled(False)
                self.stop_btn.setEnabled(False)
        else:
            self.current_labels["batch_id"].setText("-")
            self.current_labels["processed_images"].setText("-")
            self.current_labels["total_images"].setText("-")
            self.main_progress.setValue(0)
            self.progress_percent_label.setText("0%")
            self.progress_detail_label.setText("Aucun lot en traitement")
            self.pause_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
        
        # Mise à jour des statistiques globales
        self.stats_labels["total_batches"].setText(str(stats.get('batches_completed', 0)))
        self.stats_labels["total_images"].setText(str(stats.get('images_processed', 0)))
        
        total_time = stats.get('total_processing_time', 0)
        if total_time > 0:
            hours = int(total_time // 3600)
            minutes = int((total_time % 3600) // 60)
            self.stats_labels["total_time"].setText(f"{hours}h {minutes}m")
        else:
            self.stats_labels["total_time"].setText("0")
        
        avg_time = stats.get('avg_processing_time', 0)
        if avg_time > 0:
            avg_speed = 50 / avg_time * 60  # images par minute
            self.stats_labels["avg_speed"].setText(f"{avg_speed:.1f} img/min")
        else:
            self.stats_labels["avg_speed"].setText("N/A")
        
        # Taux de succès (simplifié)
        completed = stats.get('batches_completed', 0)
        if completed > 0:
            success_rate = 100.0  # Simplifié, tous les lots complétés sont des succès
            self.stats_labels["success_rate"].setText(f"{success_rate:.1f}%")
        else:
            self.stats_labels["success_rate"].setText("N/A")
        
        # Efficacité (basée sur la vitesse par rapport à une référence)
        if avg_time > 0:
            reference_time = 2.0  # 2 secondes par image comme référence
            efficiency = (reference_time / (avg_time / 50)) * 100
            efficiency = min(200, max(0, efficiency))  # Limite entre 0 et 200%
            self.stats_labels["efficiency"].setText(f"{efficiency:.0f}%")
        else:
            self.stats_labels["efficiency"].setText("N/A")
    
    def add_batch_to_history(self, batch_id: str, images_count: int, 
                           processing_time: float, status: str, error: str = ""):
        """Ajoute un lot à l'historique"""
        timestamp = time.strftime("%H:%M:%S")
        short_id = batch_id.split('_')[-1] if '_' in batch_id else batch_id[:8]
        
        # Calcul de la vitesse
        if processing_time > 0:
            speed = (images_count / processing_time) * 60  # images par minute
            speed_text = f"{speed:.1f} img/min"
        else:
            speed_text = "N/A"
        
        # Ajout à l'historique interne
        history_entry = {
            'timestamp': timestamp,
            'batch_id': short_id,
            'images_count': images_count,
            'processing_time': processing_time,
            'status': status,
            'speed': speed_text,
            'error': error
        }
        
        self.batch_history.append(history_entry)
        
        # Limitation de l'historique
        if len(self.batch_history) > self.max_history:
            self.batch_history.pop(0)
        
        # Mise à jour du tableau
        self.update_history_table()
    
    def update_history_table(self):
        """Met à jour le tableau d'historique"""
        self.history_table.setRowCount(len(self.batch_history))
        
        for row, entry in enumerate(reversed(self.batch_history)):  # Plus récent en premier
            self.history_table.setItem(row, 0, QTableWidgetItem(entry['timestamp']))
            self.history_table.setItem(row, 1, QTableWidgetItem(entry['batch_id']))
            self.history_table.setItem(row, 2, QTableWidgetItem(str(entry['images_count'])))
            self.history_table.setItem(row, 3, QTableWidgetItem(f"{entry['processing_time']:.1f}s"))
            
            # Statut avec couleur
            status_item = QTableWidgetItem(entry['status'])
            if entry['status'] == 'Succès':
                status_item.setBackground(QColor(144, 238, 144))
            elif entry['status'] == 'Échec':
                status_item.setBackground(QColor(255, 182, 193))
            
            self.history_table.setItem(row, 4, status_item)
            self.history_table.setItem(row, 5, QTableWidgetItem(entry['speed']))
            self.history_table.setItem(row, 6, QTableWidgetItem(entry['error']))
    
    def clear_history(self):
        """Efface l'historique"""
        reply = QMessageBox.question(
            self, "Effacer l'historique",
            "Voulez-vous vraiment effacer tout l'historique ?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.batch_history.clear()
            self.history_table.setRowCount(0)
    
    def export_history(self):
        """Exporte l'historique"""
        if not self.batch_history:
            QMessageBox.information(self, "Export", "Aucun historique à exporter")
            return
        
        from PyQt5.QtWidgets import QFileDialog
        
        filename, _ = QFileDialog.getSaveFileName(
            self, "Exporter l'historique",
            f"historique_traitement_{time.strftime('%Y%m%d_%H%M%S')}.csv",
            "Fichiers CSV (*.csv)"
        )
        
        if filename:
            try:
                import csv
                with open(filename, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['Heure', 'ID Lot', 'Images', 'Temps', 'Statut', 'Vitesse', 'Erreur'])
                    
                    for entry in self.batch_history:
                        writer.writerow([
                            entry['timestamp'],
                            entry['batch_id'],
                            entry['images_count'],
                            f"{entry['processing_time']:.1f}s",
                            entry['status'],
                            entry['speed'],
                            entry['error']
                        ])
                
                QMessageBox.information(self, "Export", "Historique exporté avec succès")
                
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Erreur d'export:\n{e}")