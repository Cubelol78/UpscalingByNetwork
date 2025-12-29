"""
Onglet Configuration - Paramètres du serveur
Configuration stockée dans la base de données SQLite (table parameters)

Comportements:
- Mot de passe: auto-save, appliqué immédiatement aux nouvelles connexions
- Batch size: auto-save, appliqué immédiatement
- Work directory: auto-save, nécessite redémarrage du serveur
- IP/Port: bouton "Appliquer" pour rebind dynamique sans perdre les clients
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

        # Timer pour debounce de l'auto-save du mot de passe
        self.PasswordAutoSaveTimer = QTimer()
        self.PasswordAutoSaveTimer.setSingleShot(True)
        self.PasswordAutoSaveTimer.timeout.connect(self.AutoSavePassword)

        # Timer pour debounce de l'auto-save du work_directory
        self.WorkDirAutoSaveTimer = QTimer()
        self.WorkDirAutoSaveTimer.setSingleShot(True)
        self.WorkDirAutoSaveTimer.timeout.connect(self.AutoSaveWorkDirectory)

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

        # Groupe adresse réseau (IP/Port) - orange, appliqué via bouton
        NetworkAddressGroup = self.CreateNetworkAddressGroup()
        Layout.addWidget(NetworkAddressGroup)

        # Groupe paramètres dynamiques (mot de passe, batch_size, work_dir) - vert
        DynamicGroup = self.CreateDynamicGroup()
        Layout.addWidget(DynamicGroup)

        Layout.addStretch()

    def CreateNetworkAddressGroup(self) -> QGroupBox:
        """Crée le groupe d'adresse réseau (IP/Port) - appliqué via bouton"""
        Group = QGroupBox("Adresse reseau (cliquer Appliquer pour changer)")
        Group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #FF9800;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #FF9800;
            }
        """)

        MainLayout = QVBoxLayout()
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

        MainLayout.addLayout(FormLayout)

        # Bouton et note pour appliquer les changements réseau
        ButtonLayout = QHBoxLayout()

        NoteLabel = QLabel("Les clients connectes ne seront pas affectes")
        NoteLabel.setStyleSheet("color: #FF9800; font-style: italic; font-size: 10px;")
        ButtonLayout.addWidget(NoteLabel)

        ButtonLayout.addStretch()

        self.ApplyNetworkButton = QPushButton("Appliquer les changements reseau")
        self.ApplyNetworkButton.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                padding: 6px 12px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
        """)
        self.ApplyNetworkButton.clicked.connect(self.ApplyNetworkChanges)
        ButtonLayout.addWidget(self.ApplyNetworkButton)

        MainLayout.addLayout(ButtonLayout)
        Group.setLayout(MainLayout)
        return Group

    def CreateDynamicGroup(self) -> QGroupBox:
        """Crée le groupe des paramètres dynamiques (appliqués immédiatement)"""
        Group = QGroupBox("Parametres dynamiques (appliques immediatement)")
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

        # Mot de passe (dynamique - appliqué immédiatement)
        PasswordLayout = QHBoxLayout()
        self.PasswordInput = QLineEdit()
        self.PasswordInput.setEchoMode(QLineEdit.Password)
        self.PasswordInput.setPlaceholderText("Laisser vide pour desactiver")
        self.PasswordInput.textChanged.connect(self.OnPasswordChanged)
        PasswordLayout.addWidget(self.PasswordInput)

        PasswordNote = QLabel("(sauvegarde automatique)")
        PasswordNote.setStyleSheet("color: gray; font-style: italic; font-size: 10px;")
        PasswordLayout.addWidget(PasswordNote)
        PasswordLayout.addStretch()

        FormLayout.addRow("Mot de passe:", PasswordLayout)

        # Taille des batchs (dynamique, auto-save)
        BatchSizeLayout = QHBoxLayout()
        self.BatchSizeInput = QSpinBox()
        self.BatchSizeInput.setMinimum(10)
        self.BatchSizeInput.setMaximum(1000)
        self.BatchSizeInput.setValue(100)
        self.BatchSizeInput.setSuffix(" images")
        self.BatchSizeInput.valueChanged.connect(self.OnBatchSizeChanged)
        BatchSizeLayout.addWidget(self.BatchSizeInput)

        BatchSizeNote = QLabel("(sauvegarde automatique)")
        BatchSizeNote.setStyleSheet("color: gray; font-style: italic; font-size: 10px;")
        BatchSizeLayout.addWidget(BatchSizeNote)
        BatchSizeLayout.addStretch()

        FormLayout.addRow("Taille des batchs:", BatchSizeLayout)

        # Répertoire de travail (auto-save, mais nécessite redémarrage)
        WorkDirLayout = QHBoxLayout()
        self.WorkDirInput = QLineEdit()
        self.WorkDirInput.setPlaceholderText("./work")
        self.WorkDirInput.textChanged.connect(self.OnWorkDirChanged)
        WorkDirLayout.addWidget(self.WorkDirInput)

        BrowseButton = QPushButton("Parcourir...")
        BrowseButton.clicked.connect(self.BrowseWorkDirectory)
        WorkDirLayout.addWidget(BrowseButton)

        WorkDirNote = QLabel("(necessite redemarrage)")
        WorkDirNote.setStyleSheet("color: #FF9800; font-style: italic; font-size: 10px;")
        WorkDirLayout.addWidget(WorkDirNote)

        FormLayout.addRow("Repertoire de travail:", WorkDirLayout)

        Group.setLayout(FormLayout)
        return Group

    def BrowseWorkDirectory(self):
        """Ouvre le dialogue de sélection du répertoire de travail"""
        Directory = QFileDialog.getExistingDirectory(
            self,
            "Selectionner le repertoire de travail",
            self.WorkDirInput.text() or "./work"
        )

        if Directory:
            self.WorkDirInput.setText(Directory)
            # Le textChanged déclenchera automatiquement l'auto-save

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

    def OnPasswordChanged(self, NewPassword: str):
        """Appelé quand le mot de passe change - déclenche l'auto-save"""
        if self.IsLoading:
            return

        # Redémarre le timer de debounce
        self.PasswordAutoSaveTimer.stop()
        self.PasswordAutoSaveTimer.start(self.AUTOSAVE_DELAY_MS)

    def AutoSavePassword(self):
        """Sauvegarde automatique du mot de passe et propagation au serveur actif"""
        try:
            Database = self.ParentWindow.GetDatabase()
            NewPassword = self.PasswordInput.text()

            if Database:
                # Sauvegarder dans la base de données
                Database.SetParameter('server_password', NewPassword, "Mot de passe du serveur")

            # Propager au serveur actif s'il existe
            self.PropagatePasswordToServer(NewPassword)

            # Affiche l'indicateur "Sauvegardé"
            self.ShowSavedIndicator()

            self.ParentWindow.Logger.info(f"Mot de passe mis a jour (vide: {NewPassword == ''})")

        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur lors de l'auto-save du mot de passe: {e}")

    def PropagatePasswordToServer(self, NewPassword: str):
        """
        Propage le mot de passe au serveur actif.
        Les clients déjà connectés ne sont pas affectés.
        """
        try:
            # Vérifie si le serveur est actif
            if hasattr(self.ParentWindow, 'Server') and self.ParentWindow.Server:
                Server = self.ParentWindow.Server

                # Met à jour dans le serveur
                Server.Password = NewPassword

                # Met à jour dans le ClientManager
                if hasattr(Server, 'ClientManager') and Server.ClientManager:
                    Server.ClientManager.UpdatePassword(NewPassword)

                self.ParentWindow.Logger.info("Mot de passe propag au serveur actif")

        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur lors de la propagation du mot de passe: {e}")

    def OnWorkDirChanged(self, NewPath: str):
        """Appelé quand le work_directory change - déclenche l'auto-save"""
        if self.IsLoading:
            return

        # Redémarre le timer de debounce
        self.WorkDirAutoSaveTimer.stop()
        self.WorkDirAutoSaveTimer.start(self.AUTOSAVE_DELAY_MS)

    def AutoSaveWorkDirectory(self):
        """Sauvegarde automatique du work_directory (prend effet au redémarrage)"""
        try:
            Database = self.ParentWindow.GetDatabase()
            NewWorkDir = self.WorkDirInput.text() or './work'

            if Database:
                Database.SetParameter('work_directory', NewWorkDir, "Répertoire de travail")

            # Affiche l'indicateur "Sauvegardé"
            self.ShowSavedIndicator()

            self.ParentWindow.Logger.info(f"Work directory mis a jour: {NewWorkDir} (prendra effet au redemarrage)")

        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur lors de l'auto-save du work_directory: {e}")

    def ApplyNetworkChanges(self):
        """
        Applique les changements d'adresse réseau (IP/Port) au serveur actif.
        Utilise le rebind dynamique sans perdre les clients connectés.
        """
        NewIp = self.IpInput.text() or '0.0.0.0'
        NewPort = self.PortInput.value()

        # Sauvegarde d'abord dans la base de données
        Database = self.ParentWindow.GetDatabase()
        if Database:
            Database.SetParameter('server_ip', NewIp, "Adresse IP d'écoute du serveur")
            Database.SetParameter('server_port', str(NewPort), "Port d'écoute du serveur")

        # Vérifie si le serveur est actif
        if not hasattr(self.ParentWindow, 'Server') or not self.ParentWindow.Server:
            QMessageBox.information(
                self,
                "Information",
                "Configuration sauvegardee.\n\n"
                "Le serveur n'est pas en cours d'execution.\n"
                "Les changements seront appliques au prochain demarrage."
            )
            self.ShowSavedIndicator()
            return

        Server = self.ParentWindow.Server

        # Vérifie si l'adresse a changé
        CurrentHost, CurrentPort = Server.NetworkManager.GetAddress()
        if NewIp == CurrentHost and NewPort == CurrentPort:
            QMessageBox.information(
                self,
                "Information",
                "L'adresse reseau n'a pas change."
            )
            return

        # Effectue le rebind via asyncio
        import asyncio

        def DoRebind():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(Server.RebindNetwork(NewIp, NewPort))
            finally:
                loop.close()

        import threading
        RebindThread = threading.Thread(target=DoRebind)
        RebindThread.start()
        RebindThread.join(timeout=5)

        # Vérifie le résultat
        NewCurrentHost, NewCurrentPort = Server.NetworkManager.GetAddress()
        if NewCurrentHost == NewIp and NewCurrentPort == NewPort:
            self.ShowSavedIndicator()
            QMessageBox.information(
                self,
                "Succes",
                f"Adresse reseau changee!\n\n"
                f"Nouvelle adresse: {NewIp}:{NewPort}\n\n"
                f"Les clients connectes ne sont pas affectes."
            )
            self.ParentWindow.Logger.info(f"Rebind reseau reussi: {NewIp}:{NewPort}")
        else:
            QMessageBox.warning(
                self,
                "Echec",
                f"Impossible de changer l'adresse reseau vers {NewIp}:{NewPort}.\n\n"
                f"Le port est peut-etre deja utilise.\n"
                f"Le serveur continue sur {NewCurrentHost}:{NewCurrentPort}."
            )
            self.ParentWindow.Logger.error(f"Echec du rebind vers {NewIp}:{NewPort}")

    def ShowSavedIndicator(self):
        """Affiche brièvement l'indicateur de sauvegarde"""
        self.SavedIndicator.setText("Sauvegarde")
        self.SavedIndicatorTimer.start(2000)  # Masque après 2 secondes

    def HideSavedIndicator(self):
        """Masque l'indicateur de sauvegarde"""
        self.SavedIndicator.setText("")

    def SaveConfiguration(self):
        """
        Force la sauvegarde immédiate de tous les paramètres.
        Note: Avec le nouveau système d'auto-save, cette méthode n'est plus
        nécessaire mais est conservée pour compatibilité.
        """
        # Arrête les timers et force l'auto-save immédiat
        self.BatchSizeAutoSaveTimer.stop()
        self.PasswordAutoSaveTimer.stop()
        self.WorkDirAutoSaveTimer.stop()

        # Force l'exécution des auto-saves
        self.AutoSaveBatchSize()
        self.AutoSavePassword()
        self.AutoSaveWorkDirectory()

        self.ParentWindow.Logger.info("Configuration sauvegardee (force)")

    def GetConfiguration(self) -> dict:
        """Retourne la configuration actuelle"""
        return {
            'ip': self.IpInput.text() or '0.0.0.0',
            'port': self.PortInput.value(),
            'password': self.PasswordInput.text(),
            'work_directory': self.WorkDirInput.text() or './work',
            'batch_size': self.BatchSizeInput.value()
        }
