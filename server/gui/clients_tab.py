"""
Onglet Clients - Liste et statut des clients connectés
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QPushButton,
    QHeaderView, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor


class ClientsTab(QWidget):
    """Onglet affichant la liste des clients connectés"""

    def __init__(self, ParentWindow):
        super().__init__()
        self.ParentWindow = ParentWindow
        self.SetupUI()

    def SetupUI(self):
        """Configure l'interface utilisateur"""
        Layout = QVBoxLayout(self)

        # Titre
        Title = QLabel("Clients connectés")
        TitleFont = QFont()
        TitleFont.setPointSize(16)
        TitleFont.setBold(True)
        Title.setFont(TitleFont)
        Layout.addWidget(Title)

        # Tableau des clients
        self.ClientsTable = QTableWidget()
        self.ClientsTable.setColumnCount(7)
        self.ClientsTable.setHorizontalHeaderLabels([
            "ID", "Adresse IP", "Statut", "Batches", "Batches en cours", "Dernier heartbeat", "Actions"
        ])

        # Configuration du tableau
        Header = self.ClientsTable.horizontalHeader()
        Header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        Header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        Header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        Header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        Header.setSectionResizeMode(4, QHeaderView.Stretch)
        Header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        Header.setSectionResizeMode(6, QHeaderView.ResizeToContents)

        self.ClientsTable.setAlternatingRowColors(True)

        Layout.addWidget(self.ClientsTable)

        # Barre d'actions
        ActionBar = self.CreateActionBar()
        Layout.addWidget(ActionBar)

    def CreateActionBar(self) -> QWidget:
        """Crée la barre d'actions"""
        ActionWidget = QWidget()
        ActionLayout = QHBoxLayout(ActionWidget)

        self.RefreshButton = QPushButton("🔄 Rafraîchir")
        self.RefreshButton.clicked.connect(self.Refresh)
        ActionLayout.addWidget(self.RefreshButton)

        ActionLayout.addStretch()

        self.DisconnectButton = QPushButton("✖ Déconnecter le client sélectionné")
        self.DisconnectButton.clicked.connect(self.DisconnectSelectedClient)
        self.DisconnectButton.setEnabled(False)
        ActionLayout.addWidget(self.DisconnectButton)

        return ActionWidget

    def Refresh(self):
        """Rafraichit la liste des clients"""
        try:
            Server = self.ParentWindow.GetServer()

            if not Server or not Server.ClientManager:
                self.ClientsTable.setRowCount(0)
                return

            # Sauvegarder la selection actuelle
            SelectedClientId = None
            CurrentRow = self.ClientsTable.currentRow()
            if CurrentRow >= 0:
                IdItem = self.ClientsTable.item(CurrentRow, 0)
                if IdItem:
                    SelectedClientId = IdItem.data(Qt.UserRole)

            # Recuperer les clients connectes
            Clients = Server.ClientManager.GetAllClients()

            # Recuperer les infos de batches par client depuis le BatchDistributor
            BatchInfoByClient = {}
            if Server.BatchDistributor:
                BatchInfoByClient = Server.BatchDistributor.GetAllClientsBatchInfo()

            # Vider le tableau
            self.ClientsTable.setRowCount(0)

            # Remplir le tableau
            RowToSelect = -1
            for ClientId, ClientInfo in Clients.items():
                RowPosition = self.ClientsTable.rowCount()
                self.ClientsTable.insertRow(RowPosition)

                # ID (court)
                ShortId = ClientId[:8] + "..."
                IdItem = QTableWidgetItem(ShortId)
                IdItem.setData(Qt.UserRole, ClientId)  # Stocker l'ID complet
                self.ClientsTable.setItem(RowPosition, 0, IdItem)

                # Verifier si c'est la ligne precedemment selectionnee
                if SelectedClientId and ClientId == SelectedClientId:
                    RowToSelect = RowPosition

                # Adresse IP
                Address = f"{ClientInfo.Address[0]}:{ClientInfo.Address[1]}"
                self.ClientsTable.setItem(RowPosition, 1, QTableWidgetItem(Address))

                # Statut
                Status = ClientInfo.Status
                StatusItem = QTableWidgetItem(Status.upper())
                StatusColor = self.GetStatusColor(Status)
                StatusItem.setBackground(StatusColor)
                StatusItem.setForeground(QColor("white"))
                self.ClientsTable.setItem(RowPosition, 2, StatusItem)

                # Infos batches depuis le distributeur
                BatchInfo = BatchInfoByClient.get(ClientId, {
                    "active_count": 0,
                    "max_batches": ClientInfo.MaxConcurrentBatches or 2,
                    "batch_ids": []
                })

                # Colonne Batches: X/Y (actifs/max)
                ActiveCount = BatchInfo.get("active_count", 0)
                MaxBatches = BatchInfo.get("max_batches", 2)
                BatchCountText = f"{ActiveCount}/{MaxBatches}"
                BatchCountItem = QTableWidgetItem(BatchCountText)
                # Coloration selon l'utilisation
                if ActiveCount == 0:
                    BatchCountItem.setForeground(QColor("#9E9E9E"))  # Gris
                elif ActiveCount >= MaxBatches:
                    BatchCountItem.setForeground(QColor("#FF9800"))  # Orange (plein)
                else:
                    BatchCountItem.setForeground(QColor("#4CAF50"))  # Vert (actif)
                self.ClientsTable.setItem(RowPosition, 3, BatchCountItem)

                # Colonne Batches en cours: liste des IDs
                BatchIds = BatchInfo.get("batch_ids", [])
                if BatchIds:
                    # Affiche les IDs courts separes par virgule
                    ShortBatchIds = [bid[:8] + "..." for bid in BatchIds]
                    BatchIdsText = ", ".join(ShortBatchIds)
                else:
                    BatchIdsText = "-"
                BatchIdsItem = QTableWidgetItem(BatchIdsText)
                # Tooltip avec les IDs complets
                if BatchIds:
                    BatchIdsItem.setToolTip("\n".join(BatchIds))
                self.ClientsTable.setItem(RowPosition, 4, BatchIdsItem)

                # Dernier heartbeat
                import time
                if ClientInfo.LastHeartbeat:
                    TimeDiff = time.time() - ClientInfo.LastHeartbeat
                    HeartbeatText = f"Il y a {int(TimeDiff)}s"
                else:
                    HeartbeatText = "Jamais"
                self.ClientsTable.setItem(RowPosition, 5, QTableWidgetItem(HeartbeatText))

                # Actions (bouton deconnecter)
                ActionsWidget = QWidget()
                ActionsLayout = QHBoxLayout(ActionsWidget)
                ActionsLayout.setContentsMargins(4, 2, 4, 2)
                ActionsLayout.setSpacing(4)

                DisconnectBtn = QPushButton("X")
                DisconnectBtn.setToolTip("Deconnecter ce client")
                DisconnectBtn.setProperty("class", "danger")
                DisconnectBtn.setMaximumWidth(40)
                DisconnectBtn.setMaximumHeight(28)
                DisconnectBtn.clicked.connect(lambda checked, cid=ClientId: self.DisconnectClient(cid))
                ActionsLayout.addWidget(DisconnectBtn)

                self.ClientsTable.setCellWidget(RowPosition, 6, ActionsWidget)

            # Restaurer la sélection
            if RowToSelect >= 0:
                self.ClientsTable.selectRow(RowToSelect)

            # Mettre à jour le bouton de déconnexion
            self.DisconnectButton.setEnabled(self.ClientsTable.rowCount() > 0)

        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur lors du rafraîchissement des clients: {e}")

    def GetStatusColor(self, Status: str) -> QColor:
        """Retourne une couleur selon le statut"""
        ColorMap = {
            "idle": QColor("#4CAF50"),       # Vert
            "processing": QColor("#2196F3"),  # Bleu
            "sending": QColor("#FF9800"),     # Orange
            "receiving": QColor("#9C27B0"),   # Violet
            "disconnected": QColor("#F44336") # Rouge
        }
        return ColorMap.get(Status, QColor("#9E9E9E"))  # Gris par défaut

    def DisconnectSelectedClient(self):
        """Déconnecte le client sélectionné"""
        SelectedRow = self.ClientsTable.currentRow()
        if SelectedRow >= 0:
            IdItem = self.ClientsTable.item(SelectedRow, 0)
            ClientId = IdItem.data(Qt.UserRole)
            self.DisconnectClient(ClientId)

    def DisconnectClient(self, ClientId: str):
        """Déconnecte un client spécifique"""
        try:
            Reply = QMessageBox.question(
                self,
                'Confirmation',
                f'Voulez-vous vraiment déconnecter le client {ClientId[:8]}...?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if Reply == QMessageBox.Yes:
                Server = self.ParentWindow.GetServer()
                ServerLoop = self.ParentWindow.ServerLoop
                if Server and Server.ClientManager and ServerLoop:
                    import asyncio
                    # Scheduler la coroutine sur la boucle du serveur
                    ServerLoop.call_soon_threadsafe(
                        lambda: asyncio.ensure_future(
                            Server.ClientManager.DisconnectClient(ClientId),
                            loop=ServerLoop
                        )
                    )
                    self.Refresh()
                    self.ParentWindow.Logger.info(f"Client {ClientId} déconnecté manuellement")

        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur lors de la déconnexion du client: {e}")
            QMessageBox.critical(self, "Erreur", f"Impossible de déconnecter le client:\n{str(e)}")
