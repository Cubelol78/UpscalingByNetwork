"""
Onglet Monitoring - Surveillance de l'activité du client
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QGridLayout, QTextEdit
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class MonitoringTab(QWidget):
    """Onglet de monitoring de l'activité du client"""

    def __init__(self, ParentWindow):
        super().__init__()
        self.ParentWindow = ParentWindow
        self.SetupUI()

    def SetupUI(self):
        """Configure l'interface utilisateur"""
        Layout = QVBoxLayout(self)

        # Titre
        Title = QLabel("Monitoring du client")
        TitleFont = QFont()
        TitleFont.setPointSize(16)
        TitleFont.setBold(True)
        Title.setFont(TitleFont)
        Layout.addWidget(Title)

        # Statistiques
        StatsGroup = self.CreateStatsGroup()
        Layout.addWidget(StatsGroup)

        # Activité en cours
        ActivityGroup = self.CreateActivityGroup()
        Layout.addWidget(ActivityGroup)

        # Logs récents
        LogsGroup = self.CreateLogsGroup()
        Layout.addWidget(LogsGroup)

    def CreateStatsGroup(self) -> QGroupBox:
        """Crée le groupe de statistiques"""
        Group = QGroupBox("Statistiques de la session")

        GridLayout = QGridLayout()

        # Labels des statistiques
        self.BatchesProcessedLabel = self.CreateStatLabel("0", "Batchs traités")
        self.BatchesFailedLabel = self.CreateStatLabel("0", "Batchs échoués")
        self.ImagesProcessedLabel = self.CreateStatLabel("0", "Images traitées")
        self.QueueSizeLabel = self.CreateStatLabel("0", "En attente d'envoi")
        self.CurrentBatchLabel = self.CreateStatLabel("-", "Batch en cours")
        self.StatusLabel = self.CreateStatLabel("Inactif", "Statut")

        # Disposition en grille 3x2
        GridLayout.addWidget(self.BatchesProcessedLabel[0], 0, 0)
        GridLayout.addWidget(self.BatchesFailedLabel[0], 0, 1)
        GridLayout.addWidget(self.ImagesProcessedLabel[0], 1, 0)
        GridLayout.addWidget(self.QueueSizeLabel[0], 1, 1)
        GridLayout.addWidget(self.CurrentBatchLabel[0], 2, 0)
        GridLayout.addWidget(self.StatusLabel[0], 2, 1)

        Group.setLayout(GridLayout)
        return Group

    def CreateActivityGroup(self) -> QGroupBox:
        """Crée le groupe d'activité en cours"""
        Group = QGroupBox("Activité en cours")

        Layout = QVBoxLayout()

        self.ActivityLabel = QLabel("Aucune activité")
        self.ActivityLabel.setAlignment(Qt.AlignCenter)
        self.ActivityLabel.setWordWrap(True)
        self.ActivityLabel.setContentsMargins(20, 20, 20, 20)

        Layout.addWidget(self.ActivityLabel)
        Group.setLayout(Layout)

        return Group

    def CreateLogsGroup(self) -> QGroupBox:
        """Crée le groupe des logs récents"""
        Group = QGroupBox("Logs récents")

        Layout = QVBoxLayout()

        self.LogsTextEdit = QTextEdit()
        self.LogsTextEdit.setReadOnly(True)
        self.LogsTextEdit.setMaximumHeight(150)
        self.LogsTextEdit.setPlaceholderText("Les logs apparaîtront ici...")

        Layout.addWidget(self.LogsTextEdit)
        Group.setLayout(Layout)

        return Group

    def CreateStatLabel(self, Value: str, Description: str):
        """Crée un label de statistique"""
        Container = QWidget()
        Layout = QVBoxLayout(Container)
        Layout.setSpacing(5)

        # Valeur
        ValueLabel = QLabel(Value)
        ValueFont = QFont()
        ValueFont.setPointSize(20)
        ValueFont.setBold(True)
        ValueLabel.setFont(ValueFont)
        ValueLabel.setAlignment(Qt.AlignCenter)
        ValueLabel.setProperty("class", "stat-value")

        # Description
        DescLabel = QLabel(Description)
        DescLabel.setAlignment(Qt.AlignCenter)
        DescLabel.setProperty("class", "stat-desc")

        Layout.addWidget(ValueLabel)
        Layout.addWidget(DescLabel)

        return (Container, ValueLabel)

    def Refresh(self):
        """Rafraîchit les données de monitoring"""
        try:
            if not self.ParentWindow.IsClientRunning():
                self.ResetStats()
                return

            Client = self.ParentWindow.GetClient()

            if Client:
                # Récupérer le statut du client
                Status = Client.GetStatus()

                # Mettre à jour les statistiques
                BatchesProcessed = Status.get('batches_processed', 0)
                BatchesFailed = Status.get('batches_failed', 0)
                ImagesProcessed = Status.get('images_processed', 0)
                QueueSize = Status.get('queue_size', 0)

                self.BatchesProcessedLabel[1].setText(str(BatchesProcessed))
                self.BatchesFailedLabel[1].setText(str(BatchesFailed))
                self.ImagesProcessedLabel[1].setText(str(ImagesProcessed))

                # Affiche la queue d'envoi avec un indicateur visuel
                if QueueSize > 0:
                    self.QueueSizeLabel[1].setText(f"{QueueSize} 📤")
                else:
                    self.QueueSizeLabel[1].setText("0")

                CurrentBatch = Status.get('current_batch', None)
                if CurrentBatch:
                    ShortBatch = CurrentBatch[:16] + "..."
                    self.CurrentBatchLabel[1].setText(ShortBatch)
                else:
                    self.CurrentBatchLabel[1].setText("-")

                ClientStatus = Status.get('status', 'idle')
                StatusText = {
                    'idle': 'En attente',
                    'processing': 'Traitement en cours',
                    'sending': 'Envoi en cours',
                    'receiving': 'Réception en cours'
                }.get(ClientStatus, 'Inconnu')
                self.StatusLabel[1].setText(StatusText)

                # Mettre à jour l'activité avec plus de détails
                if CurrentBatch:
                    ActivityText = f"⚙️ Traitement du batch {CurrentBatch[:16]}...\n"
                    ActivityText += f"Statut: {StatusText}\n"
                    if QueueSize > 0:
                        ActivityText += f"📤 {QueueSize} batch(s) en attente d'envoi"
                    self.ActivityLabel.setText(ActivityText)
                elif QueueSize > 0:
                    self.ActivityLabel.setText(
                        f"📤 Envoi de {QueueSize} batch(s) traité(s)...\n"
                        f"Statut: {StatusText}"
                    )
                else:
                    SuccessRate = ""
                    if BatchesProcessed + BatchesFailed > 0:
                        TotalBatches = BatchesProcessed + BatchesFailed
                        SuccessPercent = (BatchesProcessed / TotalBatches) * 100
                        SuccessRate = f"\n✅ Taux de réussite: {SuccessPercent:.1f}%"

                    self.ActivityLabel.setText(
                        f"💤 En attente d'un nouveau batch...{SuccessRate}"
                    )

        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur lors du rafraîchissement du monitoring: {e}")

    def ResetStats(self):
        """Réinitialise les statistiques"""
        self.BatchesProcessedLabel[1].setText("0")
        self.BatchesFailedLabel[1].setText("0")
        self.ImagesProcessedLabel[1].setText("0")
        self.QueueSizeLabel[1].setText("0")
        self.CurrentBatchLabel[1].setText("-")
        self.StatusLabel[1].setText("Inactif")
        self.ActivityLabel.setText("Aucune activité")
        self.LogsTextEdit.setPlainText("Déconnecté - aucun log disponible")
