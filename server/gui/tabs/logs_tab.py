"""
Onglet logs
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                            QPlainTextEdit, QLabel, QComboBox, QFileDialog, QMessageBox)
from PyQt5.QtGui import QFont
import logging

from config.settings import config

class LogsTab(QWidget):
    """Onglet logs"""
    
    def __init__(self, server, main_window):
        super().__init__()
        self.server = server
        self.main_window = main_window
        self.setup_ui()
    
    def setup_ui(self):
        """Configuration de l'interface"""
        layout = QVBoxLayout(self)
        
        # Barre d'outils
        toolbar_layout = QHBoxLayout()
        
        clear_btn = QPushButton("Effacer")
        clear_btn.clicked.connect(self.clear_logs)
        
        save_btn = QPushButton("Sauvegarder")
        save_btn.clicked.connect(self.save_logs)
        
        level_combo = QComboBox()
        level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        level_combo.setCurrentText("INFO")
        level_combo.currentTextChanged.connect(self.change_log_level)
        
        toolbar_layout.addWidget(QLabel("Niveau:"))
        toolbar_layout.addWidget(level_combo)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(clear_btn)
        toolbar_layout.addWidget(save_btn)
        
        # Zone de texte pour les logs
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(config.LOG_MAX_LINES)
        
        # Police monospace pour les logs
        font = QFont("Consolas", 9)
        font.setStyleHint(QFont.Monospace)
        self.log_text.setFont(font)
        
        layout.addLayout(toolbar_layout)
        layout.addWidget(self.log_text)
    
    def clear_logs(self):
        """Efface les logs"""
        self.log_text.clear()
    
    def save_logs(self):
        """Sauvegarde les logs"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Sauvegarder les logs", "server_logs.txt",
            "Fichiers texte (*.txt);;Tous les fichiers (*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.toPlainText())
                QMessageBox.information(self, "Succès", "Logs sauvegardés")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Erreur lors de la sauvegarde:\n{str(e)}")
    
    def change_log_level(self, level):
        """Change le niveau de logging"""
        try:
            numeric_level = getattr(logging, level.upper())
            logging.getLogger().setLevel(numeric_level)
        except AttributeError:
            pass  # Niveau invalide
    
    def append_log(self, message):
        """Ajoute un message de log"""
        self.log_text.appendPlainText(message)
        
        # Auto-scroll vers le bas
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())