"""
Onglet Jobs - Gestion de la file d'attente des vidéos
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QPushButton,
    QHeaderView, QFileDialog, QComboBox, QDialog,
    QDialogButtonBox, QFormLayout, QMessageBox, QProgressBar
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor


class JobsTab(QWidget):
    """Onglet affichant la file d'attente des jobs vidéo"""

    def __init__(self, ParentWindow):
        super().__init__()
        self.ParentWindow = ParentWindow
        self.SetupUI()

    def SetupUI(self):
        """Configure l'interface utilisateur"""
        Layout = QVBoxLayout(self)

        # Titre
        Title = QLabel("File d'attente des vidéos")
        TitleFont = QFont()
        TitleFont.setPointSize(16)
        TitleFont.setBold(True)
        Title.setFont(TitleFont)
        Layout.addWidget(Title)

        # Tableau des jobs
        self.JobsTable = QTableWidget()
        self.JobsTable.setColumnCount(7)
        self.JobsTable.setHorizontalHeaderLabels([
            "ID", "Vidéo", "Statut", "Progrès", "Batchs", "Upscale", "Modèle"
        ])

        # Configuration du tableau
        Header = self.JobsTable.horizontalHeader()
        Header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        Header.setSectionResizeMode(1, QHeaderView.Stretch)
        Header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        Header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        Header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        Header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        Header.setSectionResizeMode(6, QHeaderView.ResizeToContents)

        self.JobsTable.setAlternatingRowColors(True)
        self.JobsTable.setStyleSheet("""
            QTableWidget {
                gridline-color: #d0d0d0;
                background-color: white;
            }
            QTableWidget::item:selected {
                background-color: #2196F3;
                color: white;
            }
            QTableWidget::item:alternate {
                background-color: #f5f5f5;
            }
        """)

        Layout.addWidget(self.JobsTable)

        # Barre d'actions
        ActionBar = self.CreateActionBar()
        Layout.addWidget(ActionBar)

    def CreateActionBar(self) -> QWidget:
        """Crée la barre d'actions"""
        ActionWidget = QWidget()
        ActionLayout = QHBoxLayout(ActionWidget)

        self.AddVideoButton = QPushButton("➕ Ajouter une vidéo")
        self.AddVideoButton.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.AddVideoButton.clicked.connect(self.AddVideo)
        ActionLayout.addWidget(self.AddVideoButton)

        ActionLayout.addStretch()

        self.RefreshButton = QPushButton("🔄 Rafraîchir")
        self.RefreshButton.clicked.connect(self.Refresh)
        ActionLayout.addWidget(self.RefreshButton)

        return ActionWidget

    def Refresh(self):
        """Rafraîchit la liste des jobs"""
        try:
            Database = self.ParentWindow.GetDatabase()

            if not Database:
                self.JobsTable.setRowCount(0)
                return

            # Récupérer tous les jobs
            Videos = Database.GetAllVideos()

            # Vider le tableau
            self.JobsTable.setRowCount(0)

            # Remplir le tableau
            for Video in Videos:
                RowPosition = self.JobsTable.rowCount()
                self.JobsTable.insertRow(RowPosition)

                # ID (court)
                ShortId = Video.VideoId[:8] + "..."
                IdItem = QTableWidgetItem(ShortId)
                IdItem.setData(Qt.UserRole, Video.VideoId)
                self.JobsTable.setItem(RowPosition, 0, IdItem)

                # Nom du fichier vidéo
                VideoName = Video.VideoPath.split('/')[-1]
                self.JobsTable.setItem(RowPosition, 1, QTableWidgetItem(VideoName))

                # Statut
                Status = Video.Status
                StatusItem = QTableWidgetItem(Status.upper())
                StatusColor = self.GetStatusColor(Status)
                StatusItem.setBackground(StatusColor)
                StatusItem.setForeground(QColor("white"))
                self.JobsTable.setItem(RowPosition, 2, StatusItem)

                # Progrès (barre de progression)
                ProgressBar = QProgressBar()
                ProgressBar.setValue(int(Video.Progress))
                ProgressBar.setFormat(f"{Video.Progress:.1f}%")
                self.JobsTable.setCellWidget(RowPosition, 3, ProgressBar)

                # Batchs
                BatchText = f"{Video.CompletedBatches}/{Video.TotalBatches}"
                self.JobsTable.setItem(RowPosition, 4, QTableWidgetItem(BatchText))

                # Upscale factor
                UpscaleText = f"x{Video.UpscaleFactor}"
                self.JobsTable.setItem(RowPosition, 5, QTableWidgetItem(UpscaleText))

                # Modèle
                self.JobsTable.setItem(RowPosition, 6, QTableWidgetItem(Video.Model))

        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur lors du rafraîchissement des jobs: {e}")

    def GetStatusColor(self, Status: str) -> QColor:
        """Retourne une couleur selon le statut"""
        ColorMap = {
            "queued": QColor("#9E9E9E"),      # Gris
            "extracting": QColor("#FF9800"),   # Orange
            "processing": QColor("#2196F3"),   # Bleu
            "reassembling": QColor("#9C27B0"), # Violet
            "encoding": QColor("#673AB7"),     # Violet foncé
            "completed": QColor("#4CAF50"),    # Vert
            "failed": QColor("#F44336")        # Rouge
        }
        return ColorMap.get(Status, QColor("#9E9E9E"))

    def AddVideo(self):
        """Ouvre le dialogue pour ajouter une vidéo"""
        try:
            # Ouvrir le dialogue de sélection de fichier
            FilePath, _ = QFileDialog.getOpenFileName(
                self,
                "Sélectionner une vidéo",
                "",
                "Fichiers vidéo (*.mp4 *.avi *.mkv *.mov *.flv *.wmv);;Tous les fichiers (*.*)"
            )

            if not FilePath:
                return

            # Ouvrir le dialogue de configuration
            Dialog = AddVideoDialog(self)
            if Dialog.exec_() == QDialog.Accepted:
                Config = Dialog.GetConfiguration()

                # Ajouter la vidéo via le JobManager
                JobManager = self.ParentWindow.GetJobManager()
                if JobManager:
                    VideoId = JobManager.AddVideo(
                        VideoPath=FilePath,
                        UpscaleFactor=Config['upscale_factor'],
                        Model=Config['model']
                    )

                    self.ParentWindow.Logger.info(f"Vidéo ajoutée: {FilePath} (ID: {VideoId})")
                    QMessageBox.information(
                        self,
                        "Succès",
                        f"Vidéo ajoutée à la file d'attente:\n{FilePath}"
                    )
                    self.Refresh()
                else:
                    raise Exception("JobManager non disponible. Le serveur doit être démarré.")

        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur lors de l'ajout de la vidéo: {e}")
            QMessageBox.critical(self, "Erreur", f"Impossible d'ajouter la vidéo:\n{str(e)}")


class AddVideoDialog(QDialog):
    """Dialogue de configuration pour ajouter une vidéo"""

    def __init__(self, Parent):
        super().__init__(Parent)
        self.setWindowTitle("Configuration de l'upscaling")
        self.SetupUI()

    def SetupUI(self):
        """Configure l'interface du dialogue"""
        Layout = QFormLayout(self)

        # Facteur d'upscaling
        self.UpscaleCombo = QComboBox()
        self.UpscaleCombo.addItems(["x2", "x3", "x4"])
        self.UpscaleCombo.setCurrentText("x4")
        Layout.addRow("Facteur d'upscaling:", self.UpscaleCombo)

        # Modèle
        self.ModelCombo = QComboBox()
        self.ModelCombo.addItems([
            "realesr-animevideov3",
            "realesrgan-x4plus-anime",
            "realesrgan-x4plus"
        ])
        Layout.addRow("Modèle:", self.ModelCombo)

        # Boutons
        Buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        Buttons.accepted.connect(self.accept)
        Buttons.rejected.connect(self.reject)
        Layout.addRow(Buttons)

    def GetConfiguration(self) -> dict:
        """Retourne la configuration sélectionnée"""
        UpscaleText = self.UpscaleCombo.currentText()
        UpscaleFactor = int(UpscaleText[1:])  # Extraire le chiffre de "x4"

        return {
            'upscale_factor': UpscaleFactor,
            'model': self.ModelCombo.currentText()
        }
