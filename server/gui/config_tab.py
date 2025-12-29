"""
Onglet Configuration - Paramètres du serveur
Configuration stockée dans la base de données SQLite (table parameters)
Auto-save pour batch_size, bouton Sauvegarder pour les paramètres réseau
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QGroupBox, QFormLayout,
    QSpinBox, QFileDialog, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont


class ConfigTab(QWidget):
    """Onglet de configuration du serveur"""

    # Délai de debounce pour l'auto-save du batch_size (en ms)
    AUTOSAVE_DELAY_MS = 500

    def __init__(self, ParentWindow):
        super().__init__()
        self.ParentWindow = ParentWindow

        # Flag pour bloquer l'auto-save pendant le chargement
        self.IsLoading = False

        # Timer pour debounce de l'auto-save du batch_size
        self.BatchSizeAutoSaveTimer = QTimer()
        self.BatchSizeAutoSaveTimer.setSingleShot(True)
        self.BatchSizeAutoSaveTimer.timeout.connect(self.AutoSaveBatchSize)

        # Timer pour masquer l'indicateur "Sauvegardé"
        self.SavedIndicatorTimer = QTimer()
        self.SavedIndicatorTimer.setSingleShot(True)
        self.SavedIndicatorTimer.timeout.connect(self.HideSavedIndicator)

        self.SetupUI()
        self.LoadConfiguration()

    def SetupUI(self):
        """Configure l'interface utilisateur"""
        Layout = QVBoxLayout(self)

        # En-tête avec titre et indicateur de sauvegarde
        HeaderLayout = QHBoxLayout()

        Title = QLabel("Configuration du serveur")
        TitleFont = QFont()
        TitleFont.setPointSize(16)
        TitleFont.setBold(True)
        Title.setFont(TitleFont)
        HeaderLayout.addWidget(Title)

        HeaderLayout.addStretch()

        # Indicateur de sauvegarde (discret)
        self.SavedIndicator = QLabel("")
        self.SavedIndicator.setStyleSheet("color: #4CAF50; font-style: italic;")
        HeaderLayout.addWidget(self.SavedIndicator)

        Layout.addLayout(HeaderLayout)

        # Groupe réseau (nécessite redémarrage)
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
        """Crée le groupe de configuration réseau (nécessite redémarrage)"""
        Group = QGroupBox("Configuration reseau (necessite redemarrage)")
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
        self.PasswordInput.setPlaceholderText("Laisser vide pour desactiver")
        FormLayout.addRow("Mot de passe:", self.PasswordInput)

        # Répertoire de travail
        WorkDirLayout = QHBoxLayout()
        self.WorkDirInput = QLineEdit()
        self.WorkDirInput.setPlaceholderText("./work")
        WorkDirLayout.addWidget(self.WorkDirInput)

        BrowseButton = QPushButton("Parcourir...")
        BrowseButton.clicked.connect(self.BrowseWorkDirectory)
        WorkDirLayout.addWidget(BrowseButton)

        FormLayout.addRow("Repertoire de travail:", WorkDirLayout)

        Group.setLayout(FormLayout)
        return Group

    def CreateProcessingGroup(self) -> QGroupBox:
        """Crée le groupe de configuration du traitement (dynamique)"""
        Group = QGroupBox("Configuration du traitement (appliquee immediatement)")
        Group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #4CAF50;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #4CAF50;
            }
        """)

        FormLayout = QFormLayout()

        # Taille des batchs (dynamique, auto-save)
        BatchSizeLayout = QHBoxLayout()
        self.BatchSizeInput = QSpinBox()
        self.BatchSizeInput.setMinimum(10)
        self.BatchSizeInput.setMaximum(1000)
        self.BatchSizeInput.setValue(100)
        self.BatchSizeInput.setSuffix(" images")
        self.BatchSizeInput.valueChanged.connect(self.OnBatchSizeChanged)
        BatchSizeLayout.addWidget(self.BatchSizeInput)

        # Note
        BatchSizeNote = QLabel("(sauvegarde automatique)")
        BatchSizeNote.setStyleSheet("color: gray; font-style: italic; font-size: 10px;")
        BatchSizeLayout.addWidget(BatchSizeNote)
        BatchSizeLayout.addStretch()

        FormLayout.addRow("Taille des batchs:", BatchSizeLayout)

        Group.setLayout(FormLayout)
        return Group

    def CreateActionBar(self) -> QWidget:
        """Crée la barre d'actions"""
        ActionWidget = QWidget()
        ActionLayout = QHBoxLayout(ActionWidget)

        # Note explicative
        NoteLabel = QLabel("Les parametres reseau necessitent un redemarrage du serveur")
        NoteLabel.setStyleSheet("color: #FF9800; font-size: 11px;")
        ActionLayout.addWidget(NoteLabel)

        ActionLayout.addStretch()

        # Bouton Annuler
        self.CancelButton = QPushButton("Annuler")
        self.CancelButton.clicked.connect(self.LoadConfiguration)
        ActionLayout.addWidget(self.CancelButton)

        # Bouton Enregistrer (pour les paramètres réseau)
        self.SaveButton = QPushButton("Enregistrer parametres reseau")
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
        self.SaveButton.clicked.connect(self.SaveNetworkConfiguration)
        ActionLayout.addWidget(self.SaveButton)

        return ActionWidget

    def BrowseWorkDirectory(self):
        """Ouvre le dialogue de sélection du répertoire de travail"""
        Directory = QFileDialog.getExistingDirectory(
            self,
            "Selectionner le repertoire de travail",
            self.WorkDirInput.text() or "./work"
        )

        if Directory:
            self.WorkDirInput.setText(Directory)

    def LoadConfiguration(self):
        """Charge la configuration depuis la base de données"""
        self.IsLoading = True

        try:
            # Récupère la base de données depuis le parent
            Database = self.ParentWindow.GetDatabase()

            if Database:
                # Charger les valeurs depuis la DB
                Config = Database.GetServerConfig()

                self.IpInput.setText(Config.get('ip', '0.0.0.0'))
                self.PortInput.setValue(Config.get('port', 8765))
                self.PasswordInput.setText(Config.get('password', ''))
                self.WorkDirInput.setText(Config.get('work_directory', './work'))
                self.BatchSizeInput.setValue(Config.get('batch_size', 100))

                self.ParentWindow.Logger.info("Configuration chargee depuis la base de donnees")
            else:
                # Valeurs par défaut si pas de DB
                self.IpInput.setText('0.0.0.0')
                self.PortInput.setValue(8765)
                self.PasswordInput.setText('')
                self.WorkDirInput.setText('./work')
                self.BatchSizeInput.setValue(100)

        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur lors du chargement de la configuration: {e}")
            QMessageBox.warning(
                self,
                "Avertissement",
                f"Impossible de charger la configuration:\n{str(e)}\n\nValeurs par defaut utilisees."
            )

        finally:
            self.IsLoading = False

    def OnBatchSizeChanged(self, Value: int):
        """Appelé quand le batch_size change - déclenche l'auto-save"""
        if self.IsLoading:
            return

        # Redémarre le timer de debounce
        self.BatchSizeAutoSaveTimer.stop()
        self.BatchSizeAutoSaveTimer.start(self.AUTOSAVE_DELAY_MS)

    def AutoSaveBatchSize(self):
        """Sauvegarde automatique du batch_size et propagation au serveur actif"""
        try:
            Database = self.ParentWindow.GetDatabase()
            NewBatchSize = self.BatchSizeInput.value()

            if Database:
                # Sauvegarder dans la base de données
                Database.SetParameter('batch_size', str(NewBatchSize), "Nombre d'images par batch")

            # Propager au serveur actif s'il existe
            self.PropageBatchSizeToServer(NewBatchSize)

            # Affiche l'indicateur "Sauvegardé"
            self.ShowSavedIndicator()

            self.ParentWindow.Logger.info(f"Batch size mis a jour: {NewBatchSize}")

        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur lors de l'auto-save du batch_size: {e}")

    def PropageBatchSizeToServer(self, BatchSize: int):
        """Propage le batch_size au serveur actif"""
        try:
            # Vérifie si le serveur est actif
            if hasattr(self.ParentWindow, 'Server') and self.ParentWindow.Server:
                Server = self.ParentWindow.Server

                # Met à jour dans le serveur
                Server.BatchSize = BatchSize

                # Met à jour dans la base de données
                if hasattr(Server, 'DbManager') and Server.DbManager:
                    Server.DbManager.SetParameter("batch_size", str(BatchSize))

                # Met à jour dans le BatchDistributor si actif
                if hasattr(Server, 'BatchDistributor') and Server.BatchDistributor:
                    Server.BatchDistributor.BatchSize = BatchSize

                self.ParentWindow.Logger.info(f"Batch size propag au serveur actif: {BatchSize}")

        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur lors de la propagation du batch_size: {e}")

    def ShowSavedIndicator(self):
        """Affiche brièvement l'indicateur de sauvegarde"""
        self.SavedIndicator.setText("Sauvegarde")
        self.SavedIndicatorTimer.start(2000)  # Masque après 2 secondes

    def HideSavedIndicator(self):
        """Masque l'indicateur de sauvegarde"""
        self.SavedIndicator.setText("")

    def SaveNetworkConfiguration(self):
        """Enregistre les paramètres réseau (nécessite redémarrage)"""
        try:
            Database = self.ParentWindow.GetDatabase()

            if Database:
                # Sauvegarder dans la base de données
                Database.SetParameter('server_ip', self.IpInput.text() or '0.0.0.0', "Adresse IP d'écoute du serveur")
                Database.SetParameter('server_port', str(self.PortInput.value()), "Port d'écoute du serveur")
                Database.SetParameter('server_password', self.PasswordInput.text(), "Mot de passe du serveur")
                Database.SetParameter('work_directory', self.WorkDirInput.text() or './work', "Répertoire de travail")
                # Note: batch_size est déjà sauvegardé via auto-save

            self.ParentWindow.Logger.info("Configuration reseau sauvegardee")
            QMessageBox.information(
                self,
                "Succes",
                "Configuration reseau sauvegardee!\n\n"
                "Redemarrez le serveur pour appliquer les changements."
            )

        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur lors de la sauvegarde de la configuration: {e}")
            QMessageBox.critical(
                self,
                "Erreur",
                f"Impossible de sauvegarder la configuration:\n{str(e)}"
            )

    def SaveConfiguration(self):
        """Enregistre toute la configuration (compatibilité)"""
        self.SaveNetworkConfiguration()

    def GetConfiguration(self) -> dict:
        """Retourne la configuration actuelle"""
        return {
            'ip': self.IpInput.text() or '0.0.0.0',
            'port': self.PortInput.value(),
            'password': self.PasswordInput.text(),
            'work_directory': self.WorkDirInput.text() or './work',
            'batch_size': self.BatchSizeInput.value()
        }
