"""
Onglet Configuration - Paramètres du serveur
"""

import json
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QGroupBox, QFormLayout,
    QSpinBox, QFileDialog, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class ConfigTab(QWidget):
    """Onglet de configuration du serveur"""

    def __init__(self, ParentWindow):
        super().__init__()
        self.ParentWindow = ParentWindow
        self.ConfigFile = "/DATA-2T/UpscalingByNetwork/config/default_config.json"
        self.SetupUI()
        self.LoadConfiguration()

    def SetupUI(self):
        """Configure l'interface utilisateur"""
        Layout = QVBoxLayout(self)

        # Titre
        Title = QLabel("Configuration du serveur")
        TitleFont = QFont()
        TitleFont.setPointSize(16)
        TitleFont.setBold(True)
        Title.setFont(TitleFont)
        Layout.addWidget(Title)

        # Groupe réseau
        NetworkGroup = self.CreateNetworkGroup()
        Layout.addWidget(NetworkGroup)

        # Groupe traitement
        ProcessingGroup = self.CreateProcessingGroup()
        Layout.addWidget(ProcessingGroup)

        Layout.addStretch()

        # Boutons d'action
        ActionBar = self.CreateActionBar()
        Layout.addWidget(ActionBar)

    def CreateNetworkGroup(self) -> QGroupBox:
        """Crée le groupe de configuration réseau"""
        Group = QGroupBox("Configuration réseau")
        Group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #cccccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)

        FormLayout = QFormLayout()

        # IP
        self.IpInput = QLineEdit()
        self.IpInput.setPlaceholderText("0.0.0.0 (toutes les interfaces)")
        FormLayout.addRow("Adresse IP:", self.IpInput)

        # Port
        self.PortInput = QSpinBox()
        self.PortInput.setMinimum(1024)
        self.PortInput.setMaximum(65535)
        self.PortInput.setValue(8765)
        FormLayout.addRow("Port:", self.PortInput)

        # Mot de passe
        self.PasswordInput = QLineEdit()
        self.PasswordInput.setEchoMode(QLineEdit.Password)
        self.PasswordInput.setPlaceholderText("Laisser vide pour désactiver")
        FormLayout.addRow("Mot de passe:", self.PasswordInput)

        Group.setLayout(FormLayout)
        return Group

    def CreateProcessingGroup(self) -> QGroupBox:
        """Crée le groupe de configuration du traitement"""
        Group = QGroupBox("Configuration du traitement")
        Group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #cccccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)

        FormLayout = QFormLayout()

        # Répertoire de travail
        WorkDirLayout = QHBoxLayout()
        self.WorkDirInput = QLineEdit()
        self.WorkDirInput.setPlaceholderText("./work")
        WorkDirLayout.addWidget(self.WorkDirInput)

        BrowseButton = QPushButton("Parcourir...")
        BrowseButton.clicked.connect(self.BrowseWorkDirectory)
        WorkDirLayout.addWidget(BrowseButton)

        FormLayout.addRow("Répertoire de travail:", WorkDirLayout)

        # Taille des batchs
        self.BatchSizeInput = QSpinBox()
        self.BatchSizeInput.setMinimum(10)
        self.BatchSizeInput.setMaximum(1000)
        self.BatchSizeInput.setValue(100)
        self.BatchSizeInput.setSuffix(" images")
        FormLayout.addRow("Taille des batchs:", self.BatchSizeInput)

        Group.setLayout(FormLayout)
        return Group

    def CreateActionBar(self) -> QWidget:
        """Crée la barre d'actions"""
        ActionWidget = QWidget()
        ActionLayout = QHBoxLayout(ActionWidget)

        ActionLayout.addStretch()

        # Bouton Annuler
        self.CancelButton = QPushButton("Annuler")
        self.CancelButton.clicked.connect(self.LoadConfiguration)
        ActionLayout.addWidget(self.CancelButton)

        # Bouton Enregistrer
        self.SaveButton = QPushButton("💾 Enregistrer")
        self.SaveButton.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
        """)
        self.SaveButton.clicked.connect(self.SaveConfiguration)
        ActionLayout.addWidget(self.SaveButton)

        return ActionWidget

    def BrowseWorkDirectory(self):
        """Ouvre le dialogue de sélection du répertoire de travail"""
        Directory = QFileDialog.getExistingDirectory(
            self,
            "Sélectionner le répertoire de travail",
            self.WorkDirInput.text() or "./work"
        )

        if Directory:
            self.WorkDirInput.setText(Directory)

    def LoadConfiguration(self):
        """Charge la configuration depuis le fichier"""
        try:
            if os.path.exists(self.ConfigFile):
                with open(self.ConfigFile, 'r') as f:
                    Config = json.load(f)

                # Charger les valeurs réseau
                ServerConfig = Config.get('server', {})
                self.IpInput.setText(ServerConfig.get('ip', '0.0.0.0'))
                self.PortInput.setValue(ServerConfig.get('port', 8765))
                self.PasswordInput.setText(ServerConfig.get('password', ''))

                # Charger les valeurs de traitement
                self.WorkDirInput.setText(ServerConfig.get('work_directory', './work'))
                self.BatchSizeInput.setValue(ServerConfig.get('batch_size', 100))

                self.ParentWindow.Logger.info("Configuration chargée depuis le fichier")

        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur lors du chargement de la configuration: {e}")
            QMessageBox.warning(
                self,
                "Avertissement",
                f"Impossible de charger la configuration:\n{str(e)}\n\nValeurs par défaut utilisées."
            )

    def SaveConfiguration(self):
        """Enregistre la configuration dans le fichier"""
        try:
            # Lire la configuration existante
            if os.path.exists(self.ConfigFile):
                with open(self.ConfigFile, 'r') as f:
                    Config = json.load(f)
            else:
                Config = {}

            # Mettre à jour les valeurs serveur
            if 'server' not in Config:
                Config['server'] = {}

            Config['server']['ip'] = self.IpInput.text() or '0.0.0.0'
            Config['server']['port'] = self.PortInput.value()
            Config['server']['password'] = self.PasswordInput.text()
            Config['server']['work_directory'] = self.WorkDirInput.text() or './work'
            Config['server']['batch_size'] = self.BatchSizeInput.value()

            # Sauvegarder dans le fichier
            with open(self.ConfigFile, 'w') as f:
                json.dump(Config, f, indent=2)

            self.ParentWindow.Logger.info("Configuration sauvegardée")
            QMessageBox.information(
                self,
                "Succès",
                "Configuration sauvegardée avec succès!\n\nRedémarrez le serveur pour appliquer les changements."
            )

        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur lors de la sauvegarde de la configuration: {e}")
            QMessageBox.critical(
                self,
                "Erreur",
                f"Impossible de sauvegarder la configuration:\n{str(e)}"
            )

    def GetConfiguration(self) -> dict:
        """Retourne la configuration actuelle"""
        return {
            'ip': self.IpInput.text() or '0.0.0.0',
            'port': self.PortInput.value(),
            'password': self.PasswordInput.text(),
            'work_directory': self.WorkDirInput.text() or './work',
            'batch_size': self.BatchSizeInput.value()
        }
