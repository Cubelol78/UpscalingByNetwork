"""
Onglet Connexion - Connexion à un serveur
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QGroupBox, QFormLayout,
    QSpinBox, QComboBox, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class ConnectionTab(QWidget):
    """Onglet de connexion au serveur"""

    def __init__(self, ParentWindow):
        super().__init__()
        self.ParentWindow = ParentWindow
        self.SetupUI()

    def SetupUI(self):
        """Configure l'interface utilisateur"""
        Layout = QVBoxLayout(self)

        # Titre
        Title = QLabel("Connexion au serveur")
        TitleFont = QFont()
        TitleFont.setPointSize(16)
        TitleFont.setBold(True)
        Title.setFont(TitleFont)
        Layout.addWidget(Title)

        # Statut de connexion
        self.StatusLabel = QLabel("● Déconnecté")
        self.StatusLabel.setObjectName("StatusLabel")
        self.StatusLabel.setProperty("status", "stopped")
        Layout.addWidget(self.StatusLabel)

        # Groupe de connexion
        ConnectionGroup = self.CreateConnectionGroup()
        Layout.addWidget(ConnectionGroup)

        Layout.addStretch()

        # Boutons d'action
        ActionBar = self.CreateActionBar()
        Layout.addWidget(ActionBar)

    def CreateConnectionGroup(self) -> QGroupBox:
        """Crée le groupe de configuration de connexion"""
        Group = QGroupBox("Informations du serveur")

        FormLayout = QFormLayout()

        # Serveur sauvegardé (optionnel)
        self.SavedServerCombo = QComboBox()
        self.SavedServerCombo.addItem("-- Saisie manuelle --")
        self.SavedServerCombo.currentTextChanged.connect(self.OnSavedServerSelected)
        FormLayout.addRow("Serveur sauvegardé:", self.SavedServerCombo)

        # Adresse IP
        self.HostInput = QLineEdit()
        self.HostInput.setPlaceholderText("localhost ou 192.168.1.100")
        FormLayout.addRow("Adresse:", self.HostInput)

        # Port
        self.PortInput = QSpinBox()
        self.PortInput.setMinimum(1024)
        self.PortInput.setMaximum(65535)
        self.PortInput.setValue(8765)
        FormLayout.addRow("Port:", self.PortInput)

        # Mot de passe
        self.PasswordInput = QLineEdit()
        self.PasswordInput.setEchoMode(QLineEdit.Password)
        self.PasswordInput.setPlaceholderText("Laisser vide si pas de mot de passe")
        FormLayout.addRow("Mot de passe:", self.PasswordInput)

        Group.setLayout(FormLayout)
        return Group

    def CreateActionBar(self) -> QWidget:
        """Crée la barre d'actions"""
        ActionWidget = QWidget()
        ActionLayout = QHBoxLayout(ActionWidget)

        ActionLayout.addStretch()

        # Bouton Connecter
        self.ConnectButton = QPushButton("🔌 Se connecter")
        self.ConnectButton.setObjectName("ConnectButton")
        self.ConnectButton.setProperty("class", "primary")
        self.ConnectButton.clicked.connect(self.Connect)
        ActionLayout.addWidget(self.ConnectButton)

        # Bouton Déconnecter
        self.DisconnectButton = QPushButton("✖ Se déconnecter")
        self.DisconnectButton.setObjectName("DisconnectButton")
        self.DisconnectButton.setProperty("class", "danger")
        self.DisconnectButton.clicked.connect(self.Disconnect)
        self.DisconnectButton.setEnabled(False)
        ActionLayout.addWidget(self.DisconnectButton)

        return ActionWidget

    def OnSavedServerSelected(self, ServerName: str):
        """Appelé quand un serveur sauvegardé est sélectionné"""
        if ServerName == "-- Saisie manuelle --":
            return

        try:
            # Récupérer les informations du serveur sauvegardé
            ConnectionManager = self.ParentWindow.GetConnectionManager()
            SavedServers = ConnectionManager.SavedServers.LoadServers()

            for Server in SavedServers:
                if Server['name'] == ServerName:
                    self.HostInput.setText(Server['host'])
                    self.PortInput.setValue(Server['port'])
                    self.PasswordInput.setText(Server.get('password', ''))
                    break

        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur lors du chargement du serveur: {e}")

    def Connect(self):
        """Se connecte au serveur"""
        try:
            Host = self.HostInput.text().strip()
            Port = self.PortInput.value()
            Password = self.PasswordInput.text()

            if not Host:
                QMessageBox.warning(self, "Erreur", "Veuillez entrer une adresse de serveur")
                return

            # Se connecter
            Success = self.ParentWindow.ConnectToServer(Host, Port, Password)

            if Success:
                self.StatusLabel.setText("● Connecté")
                self.StatusLabel.setProperty("status", "running")
                self.StatusLabel.style().unpolish(self.StatusLabel)
                self.StatusLabel.style().polish(self.StatusLabel)
                self.ConnectButton.setEnabled(False)
                self.DisconnectButton.setEnabled(True)

                # Demander si on veut sauvegarder le serveur
                Reply = QMessageBox.question(
                    self,
                    'Sauvegarder le serveur?',
                    'Voulez-vous sauvegarder ce serveur pour une connexion ultérieure?',
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )

                if Reply == QMessageBox.Yes:
                    from PyQt5.QtWidgets import QInputDialog
                    ServerName, Ok = QInputDialog.getText(
                        self,
                        'Nom du serveur',
                        'Entrez un nom pour ce serveur:'
                    )

                    if Ok and ServerName:
                        self.SaveServer(ServerName, Host, Port, Password)

        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur lors de la connexion: {e}")
            QMessageBox.critical(self, "Erreur", f"Impossible de se connecter:\n{str(e)}")

    def Disconnect(self):
        """Se déconnecte du serveur"""
        self.ParentWindow.DisconnectFromServer()
        self.StatusLabel.setText("● Déconnecté")
        self.StatusLabel.setProperty("status", "stopped")
        self.StatusLabel.style().unpolish(self.StatusLabel)
        self.StatusLabel.style().polish(self.StatusLabel)
        self.ConnectButton.setEnabled(True)
        self.DisconnectButton.setEnabled(False)

    def SaveServer(self, Name: str, Host: str, Port: int, Password: str = ""):
        """Sauvegarde un serveur"""
        try:
            ConnectionManager = self.ParentWindow.GetConnectionManager()
            ConnectionManager.SavedServers.SaveServer(Name, Host, Port, Password)
            self.RefreshSavedServers()
            QMessageBox.information(self, "Succès", f"Serveur '{Name}' sauvegardé!")

        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur lors de la sauvegarde du serveur: {e}")
            QMessageBox.critical(self, "Erreur", f"Impossible de sauvegarder le serveur:\n{str(e)}")

    def RefreshSavedServers(self):
        """Rafraîchit la liste des serveurs sauvegardés"""
        try:
            self.SavedServerCombo.clear()
            self.SavedServerCombo.addItem("-- Saisie manuelle --")

            ConnectionManager = self.ParentWindow.GetConnectionManager()
            SavedServers = ConnectionManager.SavedServers.LoadServers()

            for Server in SavedServers:
                self.SavedServerCombo.addItem(Server['name'])

        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur lors du rafraîchissement: {e}")

    def Refresh(self):
        """Rafraîchit l'onglet"""
        # Rafraîchir la liste des serveurs sauvegardés
        self.RefreshSavedServers()

        # Mettre à jour le statut
        # Vérifie d'abord si le client est en train de se reconnecter
        if self.ParentWindow.Client.IsReconnecting:
            self.StatusLabel.setText("🔄 Reconnexion...")
            self.StatusLabel.setProperty("status", "reconnecting")
            self.StatusLabel.style().unpolish(self.StatusLabel)
            self.StatusLabel.style().polish(self.StatusLabel)
            self.ConnectButton.setEnabled(False)
            self.DisconnectButton.setEnabled(True)  # Permettre d'arrêter la reconnexion
        elif self.ParentWindow.IsClientRunning():
            self.StatusLabel.setText("● Connecté")
            self.StatusLabel.setProperty("status", "running")
            self.StatusLabel.style().unpolish(self.StatusLabel)
            self.StatusLabel.style().polish(self.StatusLabel)
            self.ConnectButton.setEnabled(False)
            self.DisconnectButton.setEnabled(True)
        else:
            self.StatusLabel.setText("● Déconnecté")
            self.StatusLabel.setProperty("status", "stopped")
            self.StatusLabel.style().unpolish(self.StatusLabel)
            self.StatusLabel.style().polish(self.StatusLabel)
            self.ConnectButton.setEnabled(True)
            self.DisconnectButton.setEnabled(False)
