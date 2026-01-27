"""
Onglet Monitoring - Surveillance de l'activité du client
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QGridLayout, QTextEdit, QProgressBar
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
        self.StorageModeLabel = self.CreateStatLabel("-", "Mode de stockage")

        # Disposition en grille 4x2
        GridLayout.addWidget(self.BatchesProcessedLabel[0], 0, 0)
        GridLayout.addWidget(self.BatchesFailedLabel[0], 0, 1)
        GridLayout.addWidget(self.ImagesProcessedLabel[0], 1, 0)
        GridLayout.addWidget(self.QueueSizeLabel[0], 1, 1)
        GridLayout.addWidget(self.CurrentBatchLabel[0], 2, 0)
        GridLayout.addWidget(self.StatusLabel[0], 2, 1)
        GridLayout.addWidget(self.StorageModeLabel[0], 3, 0, 1, 2)  # Prend 2 colonnes

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

        # Barre de progression du batch en cours
        self.BatchProgressBar = QProgressBar()
        self.BatchProgressBar.setMinimum(0)
        self.BatchProgressBar.setMaximum(100)
        self.BatchProgressBar.setValue(0)
        self.BatchProgressBar.setTextVisible(True)
        self.BatchProgressBar.setFormat("Aucun batch en cours")
        self.BatchProgressBar.setVisible(False)  # Caché par défaut
        Layout.addWidget(self.BatchProgressBar)

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

                # Mode de stockage
                TempMode = Status.get('temp_mode', 'disk')
                TempDir = Status.get('temp_dir', '-')
                if TempMode == 'ramdisk':
                    StorageModeText = f"💾 RAM Disk"
                    self.StorageModeLabel[1].setProperty("class", "stat-value-success")
                else:
                    StorageModeText = f"💿 Disque"
                    self.StorageModeLabel[1].setProperty("class", "stat-value")
                self.StorageModeLabel[1].setText(StorageModeText)
                # Refresh le style pour appliquer la classe
                self.StorageModeLabel[1].style().unpolish(self.StorageModeLabel[1])
                self.StorageModeLabel[1].style().polish(self.StorageModeLabel[1])

                # Récupère la progression du batch en cours
                BatchProgress = Status.get('batch_progress', 0)
                BatchTotal = Status.get('batch_total', 0)

                # Mettre à jour l'activité avec plus de détails
                if CurrentBatch:
                    ActivityText = f"⚙️ Traitement du batch {CurrentBatch[:16]}...\n"
                    ActivityText += f"Statut: {StatusText}\n"
                    if QueueSize > 0:
                        ActivityText += f"📤 {QueueSize} batch(s) en attente d'envoi"
                    self.ActivityLabel.setText(ActivityText)

                    # Affiche la barre de progression si un batch est en cours
                    if BatchTotal > 0:
                        self.BatchProgressBar.setVisible(True)
                        self.BatchProgressBar.setMaximum(BatchTotal)
                        self.BatchProgressBar.setValue(BatchProgress)
                        ProgressPercent = (BatchProgress / BatchTotal) * 100
                        self.BatchProgressBar.setFormat(f"{BatchProgress}/{BatchTotal} images ({ProgressPercent:.1f}%)")
                    else:
                        self.BatchProgressBar.setVisible(False)
                elif QueueSize > 0:
                    self.ActivityLabel.setText(
                        f"📤 Envoi de {QueueSize} batch(s) traité(s)...\n"
                        f"Statut: {StatusText}"
                    )
                    self.BatchProgressBar.setVisible(False)
                else:
                    SuccessRate = ""
                    if BatchesProcessed + BatchesFailed > 0:
                        TotalBatches = BatchesProcessed + BatchesFailed
                        SuccessPercent = (BatchesProcessed / TotalBatches) * 100
                        SuccessRate = f"\n✅ Taux de réussite: {SuccessPercent:.1f}%"

                    self.ActivityLabel.setText(
                        f"💤 En attente d'un nouveau batch...{SuccessRate}"
                    )
                    self.BatchProgressBar.setVisible(False)

                # Mettre à jour les logs récents
                self.UpdateLogs(Client)

        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur lors du rafraîchissement du monitoring: {e}")

    def UpdateLogs(self, Client):
        """
        Met à jour l'affichage des logs récents

        Args:
            Client: Instance du client
        """
        try:
            # Récupère les 20 derniers logs
            RecentLogs = Client.GetRecentLogs(Count=20)

            if not RecentLogs:
                self.LogsTextEdit.setPlainText("Aucun log disponible")
                return

            # Formate les logs pour l'affichage
            LogLines = []
            for Log in RecentLogs:
                # Format: HH:MM:SS | LEVEL | Message
                Time = Log['time'].strftime('%H:%M:%S')
                Level = Log['level']
                Message = Log['message']

                # Limite la longueur du message pour l'affichage
                if len(Message) > 80:
                    Message = Message[:77] + "..."

                LogLine = f"{Time} | {Level:8s} | {Message}"
                LogLines.append(LogLine)

            # Affiche les logs (plus récent en bas)
            self.LogsTextEdit.setPlainText("\n".join(LogLines))

            # Scroll vers le bas pour voir les logs les plus récents
            self.LogsTextEdit.verticalScrollBar().setValue(
                self.LogsTextEdit.verticalScrollBar().maximum()
            )

        except Exception as e:
            self.LogsTextEdit.setPlainText(f"Erreur lors de la récupération des logs: {e}")

    def ResetStats(self):
        """Réinitialise les statistiques"""
        self.BatchesProcessedLabel[1].setText("0")
        self.BatchesFailedLabel[1].setText("0")
        self.ImagesProcessedLabel[1].setText("0")
        self.QueueSizeLabel[1].setText("0")
        self.CurrentBatchLabel[1].setText("-")
        self.StatusLabel[1].setText("Inactif")
        self.StorageModeLabel[1].setText("-")
        self.ActivityLabel.setText("Aucune activité")
        self.LogsTextEdit.setPlainText("Déconnecté - aucun log disponible")
        # Réinitialise et cache la barre de progression
        self.BatchProgressBar.setVisible(False)
        self.BatchProgressBar.setValue(0)
        self.BatchProgressBar.setFormat("Aucun batch en cours")
