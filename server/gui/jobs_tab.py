"""
Onglet Jobs - Gestion de la file d'attente des vidéos
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QPushButton,
    QHeaderView, QFileDialog, QComboBox, QDialog,
    QDialogButtonBox, QFormLayout, QMessageBox, QProgressBar,
    QCheckBox, QSpinBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor

from shared.utils.constants import ProcessingConfig


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
        self.JobsTable.setColumnCount(8)
        self.JobsTable.setHorizontalHeaderLabels([
            "ID", "Vidéo", "Statut", "Progrès", "Batchs", "Upscale", "Modèle", "TTA"
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
        Header.setSectionResizeMode(7, QHeaderView.ResizeToContents)

        self.JobsTable.setAlternatingRowColors(True)

        # Active la sélection multiple (Ctrl+clic ou Shift+clic)
        self.JobsTable.setSelectionMode(QTableWidget.ExtendedSelection)
        self.JobsTable.setSelectionBehavior(QTableWidget.SelectRows)

        # Connecter le signal de sélection
        self.JobsTable.itemSelectionChanged.connect(self.OnSelectionChanged)

        Layout.addWidget(self.JobsTable)

        # Barre d'actions
        ActionBar = self.CreateActionBar()
        Layout.addWidget(ActionBar)

    def CreateActionBar(self) -> QWidget:
        """Crée la barre d'actions"""
        ActionWidget = QWidget()
        ActionLayout = QHBoxLayout(ActionWidget)

        self.AddVideoButton = QPushButton("➕ Ajouter une vidéo")
        self.AddVideoButton.setObjectName("AddVideoButton")
        self.AddVideoButton.setProperty("class", "primary")
        self.AddVideoButton.clicked.connect(self.AddVideo)
        ActionLayout.addWidget(self.AddVideoButton)

        self.CancelVideoButton = QPushButton("❌ Annuler la vidéo")
        self.CancelVideoButton.setObjectName("CancelVideoButton")
        self.CancelVideoButton.setProperty("class", "danger")
        self.CancelVideoButton.clicked.connect(self.CancelSelectedVideo)
        self.CancelVideoButton.setEnabled(False)
        ActionLayout.addWidget(self.CancelVideoButton)

        self.DeleteVideoButton = QPushButton("🗑️ Supprimer de la BDD")
        self.DeleteVideoButton.setObjectName("DeleteVideoButton")
        self.DeleteVideoButton.setProperty("class", "danger")
        self.DeleteVideoButton.clicked.connect(self.DeleteSelectedVideo)
        self.DeleteVideoButton.setEnabled(False)
        ActionLayout.addWidget(self.DeleteVideoButton)

        ActionLayout.addStretch()

        # Label de pagination
        self.PaginationLabel = QLabel("Affichage: 0-0 sur 0")
        ActionLayout.addWidget(self.PaginationLabel)

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
                self.PaginationLabel.setText("Affichage: 0-0 sur 0")
                return

            # Sauvegarder toutes les sélections actuelles (support multi-sélection)
            SelectedVideoIds = []
            SelectedRows = self.JobsTable.selectionModel().selectedRows()
            for RowIndex in SelectedRows:
                Row = RowIndex.row()
                IdItem = self.JobsTable.item(Row, 0)
                if IdItem:
                    SelectedVideoIds.append(IdItem.data(Qt.UserRole))

            # Récupérer tous les jobs (limite à 100 pour éviter surcharge RAM)
            MaxJobs = 100
            Videos = Database.GetAllVideos(Limit=MaxJobs)

            # Récupérer le nombre total (pour info pagination)
            Stats = Database.GetStatistics()
            TotalVideos = Stats.get('total_videos', 0)

            # Vider le tableau
            self.JobsTable.setRowCount(0)

            # Mettre à jour le label de pagination
            DisplayedCount = len(Videos)
            if DisplayedCount > 0:
                self.PaginationLabel.setText(f"Affichage: 1-{DisplayedCount} sur {TotalVideos}")
                if TotalVideos > MaxJobs:
                    self.PaginationLabel.setStyleSheet("color: orange; font-weight: bold;")
                    self.PaginationLabel.setToolTip(
                        f"⚠️ Seuls les {MaxJobs} jobs les plus récents sont affichés.\n"
                        f"Total dans la BDD: {TotalVideos}\n"
                        "Supprimez les anciens jobs pour libérer de la mémoire."
                    )
                else:
                    self.PaginationLabel.setStyleSheet("")
                    self.PaginationLabel.setToolTip("")
            else:
                self.PaginationLabel.setText("Affichage: 0-0 sur 0")
                self.PaginationLabel.setStyleSheet("")

            # Remplir le tableau
            RowsToSelect = []  # Liste des lignes à re-sélectionner
            for Video in Videos:
                RowPosition = self.JobsTable.rowCount()
                self.JobsTable.insertRow(RowPosition)

                # ID (court)
                ShortId = Video.VideoId[:8] + "..."
                IdItem = QTableWidgetItem(ShortId)
                IdItem.setData(Qt.UserRole, Video.VideoId)
                self.JobsTable.setItem(RowPosition, 0, IdItem)

                # Vérifier si cette ligne était sélectionnée avant le refresh
                if Video.VideoId in SelectedVideoIds:
                    RowsToSelect.append(RowPosition)

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

                # TTA Mode
                TtaText = "Oui" if Video.TtaMode else "Non"
                TtaItem = QTableWidgetItem(TtaText)
                if Video.TtaMode:
                    TtaItem.setBackground(QColor("#2196F3"))  # Bleu
                    TtaItem.setForeground(QColor("white"))
                self.JobsTable.setItem(RowPosition, 7, TtaItem)

            # Restaurer toutes les sélections
            for RowIndex in RowsToSelect:
                self.JobsTable.selectRow(RowIndex)

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
                        Engine=Config.get('engine', 'realesrgan'),
                        Model=Config['model'],
                        DenoiseLevel=Config.get('denoise_level', -1),
                        TtaMode=Config['tta_mode']
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

    def OnSelectionChanged(self):
        """Gère le changement de sélection dans le tableau"""
        SelectedRows = self.JobsTable.selectionModel().selectedRows()
        HasSelection = len(SelectedRows) > 0
        self.CancelVideoButton.setEnabled(HasSelection)
        self.DeleteVideoButton.setEnabled(HasSelection)

        # Met à jour le texte des boutons selon le nombre de sélections
        if len(SelectedRows) > 1:
            self.CancelVideoButton.setText(f"❌ Annuler ({len(SelectedRows)} vidéos)")
            self.DeleteVideoButton.setText(f"🗑️ Supprimer ({len(SelectedRows)} vidéos)")
        else:
            self.CancelVideoButton.setText("❌ Annuler la vidéo")
            self.DeleteVideoButton.setText("🗑️ Supprimer de la BDD")

    def CancelSelectedVideo(self):
        """Annule la ou les vidéos sélectionnées"""
        try:
            # Récupérer toutes les vidéos sélectionnées
            SelectedRows = self.JobsTable.selectionModel().selectedRows()
            if not SelectedRows:
                return

            VideosToCancel = []
            for RowIndex in SelectedRows:
                Row = RowIndex.row()
                IdItem = self.JobsTable.item(Row, 0)
                VideoNameItem = self.JobsTable.item(Row, 1)
                if IdItem and VideoNameItem:
                    VideosToCancel.append({
                        'id': IdItem.data(Qt.UserRole),
                        'name': VideoNameItem.text()
                    })

            if not VideosToCancel:
                return

            # Confirmation
            if len(VideosToCancel) == 1:
                Message = f"Voulez-vous vraiment annuler le traitement de:\n{VideosToCancel[0]['name']}?\n\n"
            else:
                VideoList = "\n".join([f"• {v['name']}" for v in VideosToCancel[:5]])
                if len(VideosToCancel) > 5:
                    VideoList += f"\n... et {len(VideosToCancel) - 5} autres"
                Message = f"Voulez-vous vraiment annuler le traitement de {len(VideosToCancel)} vidéos?\n\n{VideoList}\n\n"

            Message += "Les fichiers temporaires seront supprimés."

            Reply = QMessageBox.question(
                self,
                "Confirmation",
                Message,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if Reply != QMessageBox.Yes:
                return

            # Annuler toutes les vidéos via le JobManager
            JobManager = self.ParentWindow.GetJobManager()
            if not JobManager:
                raise Exception("JobManager non disponible")

            SuccessCount = 0
            FailCount = 0
            for Video in VideosToCancel:
                Success = JobManager.CancelVideo(Video['id'])
                if Success:
                    SuccessCount += 1
                    self.ParentWindow.Logger.info(f"Vidéo annulée: {Video['name']}")
                else:
                    FailCount += 1

            # Message de résultat
            if SuccessCount > 0:
                if FailCount == 0:
                    QMessageBox.information(
                        self,
                        "Succès",
                        f"{SuccessCount} vidéo(s) annulée(s) avec succès."
                    )
                else:
                    QMessageBox.warning(
                        self,
                        "Partiellement réussi",
                        f"{SuccessCount} vidéo(s) annulée(s).\n{FailCount} échec(s) (peut-être déjà terminées)."
                    )
            else:
                QMessageBox.warning(
                    self,
                    "Échec",
                    "Aucune vidéo n'a pu être annulée."
                )

            self.Refresh()

        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur lors de l'annulation: {e}")
            QMessageBox.critical(self, "Erreur", f"Impossible d'annuler les vidéos:\n{str(e)}")

    def DeleteSelectedVideo(self):
        """Supprime définitivement la ou les vidéos sélectionnées de la base de données"""
        try:
            # Récupérer toutes les vidéos sélectionnées
            SelectedRows = self.JobsTable.selectionModel().selectedRows()
            if not SelectedRows:
                return

            VideosToDelete = []
            HasActiveJobs = False
            for RowIndex in SelectedRows:
                Row = RowIndex.row()
                IdItem = self.JobsTable.item(Row, 0)
                VideoNameItem = self.JobsTable.item(Row, 1)
                VideoStatusItem = self.JobsTable.item(Row, 2)
                if IdItem and VideoNameItem and VideoStatusItem:
                    VideoStatus = VideoStatusItem.text().lower()
                    VideosToDelete.append({
                        'id': IdItem.data(Qt.UserRole),
                        'name': VideoNameItem.text(),
                        'status': VideoStatus
                    })
                    # Vérifier si au moins un job est actif
                    if VideoStatus in ['processing', 'extracting', 'distributing', 'reassembling', 'encoding']:
                        HasActiveJobs = True

            if not VideosToDelete:
                return

            # Vérifier si des jobs sont en cours
            if HasActiveJobs:
                QMessageBox.warning(
                    self,
                    "Impossible",
                    "Impossible de supprimer certaines vidéos car elles sont actuellement en cours de traitement.\n\n"
                    "Annulez d'abord le traitement avant de supprimer."
                )
                return

            # Confirmation avec avertissement fort
            if len(VideosToDelete) == 1:
                Message = f"Voulez-vous vraiment SUPPRIMER DÉFINITIVEMENT:\n{VideosToDelete[0]['name']}?\n\n"
            else:
                VideoList = "\n".join([f"• {v['name']}" for v in VideosToDelete[:5]])
                if len(VideosToDelete) > 5:
                    VideoList += f"\n... et {len(VideosToDelete) - 5} autres"
                Message = f"Voulez-vous vraiment SUPPRIMER DÉFINITIVEMENT {len(VideosToDelete)} vidéos?\n\n{VideoList}\n\n"

            Message += (
                "⚠️ Cette action est IRRÉVERSIBLE!\n"
                "• Les vidéos seront supprimées de la base de données\n"
                "• Tous les batches associés seront supprimés\n"
                "• Les fichiers temporaires resteront (suppression manuelle recommandée)\n\n"
                "Êtes-vous absolument sûr?"
            )

            Reply = QMessageBox.question(
                self,
                "⚠️ Confirmation de suppression",
                Message,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if Reply != QMessageBox.Yes:
                return

            # Supprimer toutes les vidéos via la base de données
            Database = self.ParentWindow.GetDatabase()
            if not Database:
                raise Exception("Base de données non disponible")

            SuccessCount = 0
            FailCount = 0
            for Video in VideosToDelete:
                Success = Database.DeleteVideo(Video['id'])
                if Success:
                    SuccessCount += 1
                    self.ParentWindow.Logger.info(f"Vidéo supprimée de la BDD: {Video['name']}")
                else:
                    FailCount += 1

            # Message de résultat
            if SuccessCount > 0:
                if FailCount == 0:
                    QMessageBox.information(
                        self,
                        "Succès",
                        f"{SuccessCount} vidéo(s) supprimée(s) de la base de données.\n\n"
                        "Note: Les fichiers temporaires n'ont pas été supprimés.\n"
                        "Vous pouvez les supprimer manuellement si nécessaire."
                    )
                else:
                    QMessageBox.warning(
                        self,
                        "Partiellement réussi",
                        f"{SuccessCount} vidéo(s) supprimée(s).\n{FailCount} échec(s)."
                    )
            else:
                QMessageBox.warning(
                    self,
                    "Échec",
                    "Aucune vidéo n'a pu être supprimée."
                )

            self.Refresh()

        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur lors de la suppression: {e}")
            QMessageBox.critical(self, "Erreur", f"Impossible de supprimer les vidéos:\n{str(e)}")


class AddVideoDialog(QDialog):
    """Dialogue de configuration pour ajouter une vidéo"""

    def __init__(self, Parent):
        super().__init__(Parent)
        self.setWindowTitle("Configuration de l'upscaling")
        self.SetupUI()

    def SetupUI(self):
        """Configure l'interface du dialogue"""
        Layout = QFormLayout(self)

        # Engine d'upscaling
        self.EngineCombo = QComboBox()
        self.EngineCombo.addItem("Real-ESRGAN", ProcessingConfig.ENGINE_REALESRGAN)
        self.EngineCombo.addItem("Real-CUGAN", ProcessingConfig.ENGINE_REALCUGAN)
        self.EngineCombo.currentIndexChanged.connect(self._OnEngineChanged)
        Layout.addRow("Engine:", self.EngineCombo)

        # Facteur d'upscaling
        self.UpscaleCombo = QComboBox()
        self.UpscaleCombo.addItems(["x2", "x3", "x4"])
        self.UpscaleCombo.setCurrentText("x4")
        Layout.addRow("Facteur d'upscaling:", self.UpscaleCombo)

        # Modèle (change selon l'engine)
        self.ModelCombo = QComboBox()
        self.ModelCombo.currentIndexChanged.connect(self._OnModelChanged)
        self._UpdateModelList()
        Layout.addRow("Modèle:", self.ModelCombo)

        # Niveau de débruitage (Real-CUGAN uniquement)
        self.DenoiseLabel = QLabel("Denoise:")
        self.DenoiseCombo = QComboBox()
        self.DenoiseCombo.setToolTip(
            "Niveau de débruitage pour Real-CUGAN:\n"
            "-1 = Auto\n"
            " 0 = Désactivé\n"
            " 1 = Léger\n"
            " 2 = Moyen\n"
            " 3 = Fort"
        )
        Layout.addRow(self.DenoiseLabel, self.DenoiseCombo)
        # Masque par défaut (Real-ESRGAN)
        self.DenoiseLabel.setVisible(False)
        self.DenoiseCombo.setVisible(False)

        # Mode TTA
        self.TtaCheckbox = QCheckBox()
        self.TtaCheckbox.setChecked(False)
        self.TtaCheckbox.setToolTip(
            "Test-Time Augmentation: meilleure qualité mais traitement plus lent.\n"
            "Recommandé pour les vidéos importantes."
        )
        Layout.addRow("Mode TTA (qualité+):", self.TtaCheckbox)

        # Boutons
        Buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        Buttons.accepted.connect(self.accept)
        Buttons.rejected.connect(self.reject)
        Layout.addRow(Buttons)

    def _OnEngineChanged(self):
        """Appelé quand l'engine change - met à jour les options disponibles"""
        Engine = self.EngineCombo.currentData()
        IsRealCugan = (Engine == ProcessingConfig.ENGINE_REALCUGAN)

        # Affiche/masque les options Real-CUGAN
        self.DenoiseLabel.setVisible(IsRealCugan)
        self.DenoiseCombo.setVisible(IsRealCugan)

        # Met à jour la liste des modèles
        self._UpdateModelList()

    def _UpdateModelList(self):
        """Met à jour la liste des modèles selon l'engine sélectionné"""
        Engine = self.EngineCombo.currentData()
        self.ModelCombo.clear()

        if Engine == ProcessingConfig.ENGINE_REALCUGAN:
            # Modèles Real-CUGAN
            self.ModelCombo.addItem("Standard Edition (SE)", "models-se")
            self.ModelCombo.addItem("Pro", "models-pro")
            self.ModelCombo.addItem("Nose (léger)", "models-nose")
        else:
            # Modèles Real-ESRGAN
            self.ModelCombo.addItem("AniméVidéo v3 (recommandé)", "realesr-animevideov3")
            self.ModelCombo.addItem("x4plus Anime", "realesrgan-x4plus-anime")
            self.ModelCombo.addItem("x4plus (photo)", "realesrgan-x4plus")

        # Met à jour les facteurs d'upscaling disponibles pour le nouveau modèle
        self._UpdateScaleFactorList()
        # Met à jour les niveaux de denoise disponibles pour le nouveau modèle
        self._UpdateDenoiseLevelList()

    def _OnModelChanged(self):
        """Appelé quand le modèle change - met à jour les options disponibles"""
        self._UpdateScaleFactorList()
        self._UpdateDenoiseLevelList()

    def _UpdateScaleFactorList(self):
        """Met à jour la liste des facteurs d'upscaling selon le modèle sélectionné"""
        Engine = self.EngineCombo.currentData()
        Model = self.ModelCombo.currentData()

        if not Model:
            return

        SupportedScales = ProcessingConfig.GetSupportedScales(Engine, Model)

        # Mémorise la sélection actuelle
        CurrentText = self.UpscaleCombo.currentText()
        CurrentScale = int(CurrentText[1:]) if CurrentText else 4

        # Met à jour le combo
        self.UpscaleCombo.clear()
        for Scale in SupportedScales:
            self.UpscaleCombo.addItem(f"x{Scale}")

        # Restaure la sélection si valide, sinon sélectionne le plus haut disponible
        if CurrentScale in SupportedScales:
            self.UpscaleCombo.setCurrentText(f"x{CurrentScale}")
        else:
            self.UpscaleCombo.setCurrentIndex(self.UpscaleCombo.count() - 1)

    def _UpdateDenoiseLevelList(self):
        """Met à jour la liste des niveaux de denoise selon le modèle Real-CUGAN sélectionné"""
        Engine = self.EngineCombo.currentData()
        Model = self.ModelCombo.currentData()

        # Seulement pour Real-CUGAN
        if Engine != ProcessingConfig.ENGINE_REALCUGAN or not Model:
            return

        SupportedLevels = ProcessingConfig.GetSupportedDenoiseLevels(Model)

        # Mémorise la sélection actuelle
        CurrentLevel = self.DenoiseCombo.currentData()
        if CurrentLevel is None:
            CurrentLevel = -1

        # Labels pour chaque niveau
        DenoiseLabels = {
            -1: "Auto (-1)",
            0: "Désactivé (0)",
            1: "Léger (1)",
            2: "Moyen (2)",
            3: "Fort (3)"
        }

        # Met à jour le combo
        self.DenoiseCombo.clear()
        for Level in SupportedLevels:
            self.DenoiseCombo.addItem(DenoiseLabels.get(Level, str(Level)), Level)

        # Restaure la sélection si valide, sinon sélectionne le premier disponible
        if CurrentLevel in SupportedLevels:
            Index = SupportedLevels.index(CurrentLevel)
            self.DenoiseCombo.setCurrentIndex(Index)
        else:
            self.DenoiseCombo.setCurrentIndex(0)

    def GetConfiguration(self) -> dict:
        """Retourne la configuration sélectionnée"""
        UpscaleText = self.UpscaleCombo.currentText()
        UpscaleFactor = int(UpscaleText[1:])  # Extraire le chiffre de "x4"
        Engine = self.EngineCombo.currentData()

        Config = {
            'engine': Engine,
            'upscale_factor': UpscaleFactor,
            'model': self.ModelCombo.currentData(),
            'tta_mode': self.TtaCheckbox.isChecked()
        }

        # Ajoute le niveau de débruitage pour Real-CUGAN
        if Engine == ProcessingConfig.ENGINE_REALCUGAN:
            DenoiseLevel = self.DenoiseCombo.currentData()
            Config['denoise_level'] = DenoiseLevel if DenoiseLevel is not None else -1

        return Config
