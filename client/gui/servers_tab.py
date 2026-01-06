"""
Onglet Serveurs - Gestion des serveurs sauvegardés
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QPushButton,
    QHeaderView, QMessageBox, QDialog, QDialogButtonBox,
    QFormLayout, QLineEdit, QSpinBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class ServersTab(QWidget):
    """Onglet de gestion des serveurs sauvegardés"""

    def __init__(self, ParentWindow):
        super().__init__()
        self.ParentWindow = ParentWindow
        self.SetupUI()

    def SetupUI(self):
        """Configure l'interface utilisateur"""
        Layout = QVBoxLayout(self)

        # Titre
        Title = QLabel("Serveurs sauvegardés")
        TitleFont = QFont()
        TitleFont.setPointSize(16)
        TitleFont.setBold(True)
        Title.setFont(TitleFont)
        Layout.addWidget(Title)

        # Tableau des serveurs
        self.ServersTable = QTableWidget()
        self.ServersTable.setColumnCount(4)
        self.ServersTable.setHorizontalHeaderLabels([
            "Nom", "Adresse", "Port", "Actions"
        ])

        # Configuration du tableau
        Header = self.ServersTable.horizontalHeader()
        Header.setSectionResizeMode(0, QHeaderView.Stretch)
        Header.setSectionResizeMode(1, QHeaderView.Stretch)
        Header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        Header.setSectionResizeMode(3, QHeaderView.ResizeToContents)

        self.ServersTable.setAlternatingRowColors(True)

        Layout.addWidget(self.ServersTable)

        # Barre d'actions
        ActionBar = self.CreateActionBar()
        Layout.addWidget(ActionBar)

    def CreateActionBar(self) -> QWidget:
        """Crée la barre d'actions"""
        ActionWidget = QWidget()
        ActionLayout = QHBoxLayout(ActionWidget)

        self.AddServerButton = QPushButton("➕ Ajouter un serveur")
        self.AddServerButton.setObjectName("AddServerButton")
        self.AddServerButton.setProperty("class", "primary")
        self.AddServerButton.clicked.connect(self.AddServer)
        ActionLayout.addWidget(self.AddServerButton)

        ActionLayout.addStretch()

        self.RefreshButton = QPushButton("🔄 Rafraîchir")
        self.RefreshButton.clicked.connect(self.Refresh)
        ActionLayout.addWidget(self.RefreshButton)

        return ActionWidget

    def Refresh(self):
        """Rafraîchit la liste des serveurs"""
        try:
            ConnectionManager = self.ParentWindow.GetConnectionManager()
            SavedServers = ConnectionManager.SavedServers.LoadServers()

            # Vider le tableau
            self.ServersTable.setRowCount(0)

            # Remplir le tableau
            for Server in SavedServers:
                RowPosition = self.ServersTable.rowCount()
                self.ServersTable.insertRow(RowPosition)

                # Nom
                self.ServersTable.setItem(RowPosition, 0, QTableWidgetItem(Server['name']))

                # Adresse
                self.ServersTable.setItem(RowPosition, 1, QTableWidgetItem(Server['host']))

                # Port
                self.ServersTable.setItem(RowPosition, 2, QTableWidgetItem(str(Server['port'])))

                # Actions
                ActionsWidget = QWidget()
                ActionsLayout = QHBoxLayout(ActionsWidget)
                ActionsLayout.setContentsMargins(4, 2, 4, 2)
                ActionsLayout.setSpacing(4)

                # Bouton Connecter
                ConnectBtn = QPushButton("📡")
                ConnectBtn.setToolTip("Connecter à ce serveur")
                ConnectBtn.setMaximumWidth(40)
                ConnectBtn.setMaximumHeight(28)
                ConnectBtn.clicked.connect(
                    lambda checked, s=Server: self.ConnectToServer(s)
                )
                ActionsLayout.addWidget(ConnectBtn)

                # Bouton Supprimer
                DeleteBtn = QPushButton("🗑️")
                DeleteBtn.setToolTip("Supprimer ce serveur")
                DeleteBtn.setProperty("class", "danger")
                DeleteBtn.setMaximumWidth(40)
                DeleteBtn.setMaximumHeight(28)
                DeleteBtn.clicked.connect(
                    lambda checked, name=Server['name']: self.DeleteServer(name)
                )
                ActionsLayout.addWidget(DeleteBtn)

                self.ServersTable.setCellWidget(RowPosition, 3, ActionsWidget)

        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur lors du rafraîchissement des serveurs: {e}")

    def AddServer(self):
        """Ouvre le dialogue pour ajouter un serveur"""
        Dialog = AddServerDialog(self)
        if Dialog.exec_() == QDialog.Accepted:
            ServerInfo = Dialog.GetServerInfo()

            try:
                ConnectionManager = self.ParentWindow.GetConnectionManager()
                ConnectionManager.SavedServers.SaveServer(
                    Name=ServerInfo['name'],
                    Host=ServerInfo['host'],
                    Port=ServerInfo['port'],
                    Password=ServerInfo['password']
                )

                self.Refresh()
                QMessageBox.information(
                    self,
                    "Succès",
                    f"Serveur '{ServerInfo['name']}' ajouté avec succès!"
                )

            except Exception as e:
                self.ParentWindow.Logger.error(f"Erreur lors de l'ajout du serveur: {e}")
                QMessageBox.critical(
                    self,
                    "Erreur",
                    f"Impossible d'ajouter le serveur:\n{str(e)}"
                )

    def DeleteServer(self, ServerName: str):
        """Supprime un serveur sauvegardé"""
        Reply = QMessageBox.question(
            self,
            'Confirmation',
            f'Voulez-vous vraiment supprimer le serveur "{ServerName}"?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if Reply == QMessageBox.Yes:
            try:
                ConnectionManager = self.ParentWindow.GetConnectionManager()
                ConnectionManager.SavedServers.RemoveServer(ServerName)
                self.Refresh()
                self.ParentWindow.Logger.info(f"Serveur '{ServerName}' supprimé")

            except Exception as e:
                self.ParentWindow.Logger.error(f"Erreur lors de la suppression: {e}")
                QMessageBox.critical(
                    self,
                    "Erreur",
                    f"Impossible de supprimer le serveur:\n{str(e)}"
                )

    def ConnectToServer(self, ServerInfo: dict):
        """Se connecte à un serveur sauvegardé"""
        try:
            # Passer à l'onglet de connexion
            self.ParentWindow.Tabs.setCurrentIndex(0)

            # Remplir les champs avec les infos du serveur
            ConnectionTab = self.ParentWindow.ConnectionTab
            ConnectionTab.HostInput.setText(ServerInfo['host'])
            ConnectionTab.PortInput.setValue(ServerInfo['port'])
            ConnectionTab.PasswordInput.setText(ServerInfo.get('password', ''))

            # Se connecter automatiquement
            ConnectionTab.Connect()

        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur lors de la connexion: {e}")
            QMessageBox.critical(
                self,
                "Erreur",
                f"Impossible de se connecter:\n{str(e)}"
            )


class AddServerDialog(QDialog):
    """Dialogue pour ajouter un nouveau serveur"""

    def __init__(self, Parent):
        super().__init__(Parent)
        self.setWindowTitle("Ajouter un serveur")
        self.SetupUI()

    def SetupUI(self):
        """Configure l'interface du dialogue"""
        Layout = QFormLayout(self)

        # Nom du serveur
        self.NameInput = QLineEdit()
        self.NameInput.setPlaceholderText("Mon serveur")
        Layout.addRow("Nom:", self.NameInput)

        # Adresse
        self.HostInput = QLineEdit()
        self.HostInput.setPlaceholderText("localhost ou 192.168.1.100")
        Layout.addRow("Adresse:", self.HostInput)

        # Port
        self.PortInput = QSpinBox()
        self.PortInput.setMinimum(1024)
        self.PortInput.setMaximum(65535)
        self.PortInput.setValue(8765)
        Layout.addRow("Port:", self.PortInput)

        # Mot de passe (optionnel)
        self.PasswordInput = QLineEdit()
        self.PasswordInput.setEchoMode(QLineEdit.Password)
        self.PasswordInput.setPlaceholderText("Optionnel")
        Layout.addRow("Mot de passe:", self.PasswordInput)

        # Boutons
        Buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        Buttons.accepted.connect(self.Validate)
        Buttons.rejected.connect(self.reject)
        Layout.addRow(Buttons)

    def Validate(self):
        """Valide les entrées avant d'accepter"""
        if not self.NameInput.text().strip():
            QMessageBox.warning(self, "Erreur", "Veuillez entrer un nom pour le serveur")
            return

        if not self.HostInput.text().strip():
            QMessageBox.warning(self, "Erreur", "Veuillez entrer une adresse")
            return

        self.accept()

    def GetServerInfo(self) -> dict:
        """Retourne les informations du serveur"""
        return {
            'name': self.NameInput.text().strip(),
            'host': self.HostInput.text().strip(),
            'port': self.PortInput.value(),
            'password': self.PasswordInput.text()
        }
