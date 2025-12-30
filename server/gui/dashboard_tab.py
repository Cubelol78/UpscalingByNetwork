"""
Onglet Dashboard - Vue d'ensemble du serveur
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QGridLayout
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class DashboardTab(QWidget):
    """Onglet affichant le tableau de bord du serveur"""

    def __init__(self, ParentWindow):
        super().__init__()
        self.ParentWindow = ParentWindow
        self.SetupUI()

    def SetupUI(self):
        """Configure l'interface utilisateur"""
        Layout = QVBoxLayout(self)

        # Titre
        Title = QLabel("Tableau de bord")
        TitleFont = QFont()
        TitleFont.setPointSize(16)
        TitleFont.setBold(True)
        Title.setFont(TitleFont)
        Layout.addWidget(Title)

        # Statistiques générales
        StatsGroup = self.CreateStatsGroup()
        Layout.addWidget(StatsGroup)

        # Activité récente
        ActivityGroup = self.CreateActivityGroup()
        Layout.addWidget(ActivityGroup)

        Layout.addStretch()

    def CreateStatsGroup(self) -> QGroupBox:
        """Crée le groupe de statistiques générales"""
        Group = QGroupBox("Statistiques en temps réel")

        GridLayout = QGridLayout()

        # Labels des statistiques
        self.ClientsConnectedLabel = self.CreateStatLabel("0", "Clients connectés")
        self.ClientsActiveLabel = self.CreateStatLabel("0", "Clients actifs")
        self.VideosQueuedLabel = self.CreateStatLabel("0", "Vidéos en attente")
        self.VideosProcessingLabel = self.CreateStatLabel("0", "Vidéos en traitement")
        self.BatchesPendingLabel = self.CreateStatLabel("0", "Batchs en attente")
        self.BatchesCompletedLabel = self.CreateStatLabel("0", "Batchs complétés")

        # Disposition en grille 2x3
        GridLayout.addWidget(self.ClientsConnectedLabel[0], 0, 0)
        GridLayout.addWidget(self.ClientsActiveLabel[0], 0, 1)
        GridLayout.addWidget(self.VideosQueuedLabel[0], 1, 0)
        GridLayout.addWidget(self.VideosProcessingLabel[0], 1, 1)
        GridLayout.addWidget(self.BatchesPendingLabel[0], 2, 0)
        GridLayout.addWidget(self.BatchesCompletedLabel[0], 2, 1)

        Group.setLayout(GridLayout)
        return Group

    def CreateActivityGroup(self) -> QGroupBox:
        """Crée le groupe d'activité récente"""
        Group = QGroupBox("Activité récente")

        Layout = QVBoxLayout()

        self.ActivityLabel = QLabel("Aucune activité récente")
        self.ActivityLabel.setAlignment(Qt.AlignTop)
        self.ActivityLabel.setWordWrap(True)
        self.ActivityLabel.setContentsMargins(10, 10, 10, 10)

        Layout.addWidget(self.ActivityLabel)
        Group.setLayout(Layout)

        return Group

    def CreateStatLabel(self, Value: str, Description: str):
        """Crée un label de statistique avec valeur et description"""
        Container = QWidget()
        Layout = QVBoxLayout(Container)
        Layout.setSpacing(5)

        # Valeur
        ValueLabel = QLabel(Value)
        ValueFont = QFont()
        ValueFont.setPointSize(24)
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
        """Rafraîchit les données du dashboard"""
        try:
            Database = self.ParentWindow.GetDatabase()
            Server = self.ParentWindow.GetServer()

            if not Database or not Server:
                return

            # Récupérer les statistiques
            Stats = Database.GetStatistics()

            # Mettre à jour les labels
            self.ClientsConnectedLabel[1].setText(str(Stats.get('total_clients', 0)))
            self.ClientsActiveLabel[1].setText(str(Stats.get('active_clients', 0)))
            self.VideosQueuedLabel[1].setText(str(Stats.get('queued_videos', 0)))
            self.VideosProcessingLabel[1].setText(str(Stats.get('processing_videos', 0)))
            self.BatchesPendingLabel[1].setText(str(Stats.get('pending_batches', 0)))
            self.BatchesCompletedLabel[1].setText(str(Stats.get('completed_batches', 0)))

            # Mettre à jour l'activité récente
            RecentActivity = self.GetRecentActivity(Database)
            self.ActivityLabel.setText(RecentActivity if RecentActivity else "Aucune activité récente")

        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur lors du rafraîchissement du dashboard: {e}")

    def GetRecentActivity(self, Database) -> str:
        """Récupère l'activité récente sous forme de texte"""
        try:
            # Récupérer les dernières vidéos
            Videos = Database.GetAllVideos(Limit=5)

            if not Videos:
                return "Aucune activité récente"

            ActivityLines = []
            for Video in Videos:
                Status = Video.Status
                Progress = Video.Progress
                StatusEmoji = {
                    "queued": "⏳",
                    "extracting": "📤",
                    "processing": "⚙️",
                    "reassembling": "🔧",
                    "completed": "✅",
                    "failed": "❌"
                }.get(Status, "❓")

                ActivityLines.append(
                    f"{StatusEmoji} {Video.VideoPath.split('/')[-1]} - {Status.upper()} ({Progress:.1f}%)"
                )

            return "\n".join(ActivityLines)

        except Exception as e:
            return f"Erreur: {str(e)}"
