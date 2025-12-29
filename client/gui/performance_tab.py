"""
Onglet Performances - Configuration des performances Real-ESRGAN
Détection matériel et optimisation automatique
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QFormLayout, QSpinBox, QCheckBox,
    QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QProgressDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont

from client.utils.hardware_detector import HardwareDetector
from client.utils.performance_config import PerformanceConfigManager, PerformancePresets


class HardwareDetectionThread(QThread):
    """Thread pour la détection matériel (évite de bloquer l'UI)"""
    Finished = pyqtSignal(dict)
    Error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.Detector = HardwareDetector()

    def run(self):
        try:
            Hardware = self.Detector.DetectAll(ForceRefresh=True)
            self.Finished.emit(Hardware)
        except Exception as e:
            self.Error.emit(str(e))


class PerformanceTab(QWidget):
    """Onglet de configuration des performances"""

    def __init__(self, ParentWindow):
        super().__init__()
        self.ParentWindow = ParentWindow
        self.HardwareDetector = HardwareDetector()
        self.ConfigManager = PerformanceConfigManager()
        self.DetectedHardware = None
        self.DetectionThread = None

        self.SetupUI()
        self.LoadConfig()

        # Détection automatique au premier lancement
        if self.ConfigManager.IsFirstRun():
            self.DetectHardware()

    def SetupUI(self):
        """Configure l'interface utilisateur"""
        Layout = QVBoxLayout(self)

        # Titre
        Title = QLabel("Configuration des performances")
        TitleFont = QFont()
        TitleFont.setPointSize(16)
        TitleFont.setBold(True)
        Title.setFont(TitleFont)
        Layout.addWidget(Title)

        # Section Matériel détecté
        HardwareGroup = self.CreateHardwareGroup()
        Layout.addWidget(HardwareGroup)

        # Section Configuration GPU
        GpuConfigGroup = self.CreateGpuConfigGroup()
        Layout.addWidget(GpuConfigGroup)

        # Section Configuration avancée
        AdvancedGroup = self.CreateAdvancedGroup()
        Layout.addWidget(AdvancedGroup)

        # Barre d'actions
        ActionBar = self.CreateActionBar()
        Layout.addWidget(ActionBar)

        Layout.addStretch()

    def CreateHardwareGroup(self) -> QGroupBox:
        """Crée le groupe d'affichage du matériel détecté"""
        Group = QGroupBox("Matériel détecté")
        Layout = QVBoxLayout(Group)

        # Informations CPU/RAM
        InfoLayout = QFormLayout()

        self.CpuLabel = QLabel("Non détecté")
        InfoLayout.addRow("CPU:", self.CpuLabel)

        self.RamLabel = QLabel("Non détecté")
        InfoLayout.addRow("RAM:", self.RamLabel)

        Layout.addLayout(InfoLayout)

        # Tableau des GPU
        self.GpuTable = QTableWidget()
        self.GpuTable.setColumnCount(4)
        self.GpuTable.setHorizontalHeaderLabels(["", "ID", "Nom", "VRAM"])
        self.GpuTable.setMaximumHeight(120)

        Header = self.GpuTable.horizontalHeader()
        Header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        Header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        Header.setSectionResizeMode(2, QHeaderView.Stretch)
        Header.setSectionResizeMode(3, QHeaderView.ResizeToContents)

        Layout.addWidget(self.GpuTable)

        # Bouton détection
        DetectButton = QPushButton("Detecter le materiel")
        DetectButton.clicked.connect(self.DetectHardware)
        Layout.addWidget(DetectButton)

        return Group

    def CreateGpuConfigGroup(self) -> QGroupBox:
        """Crée le groupe de configuration GPU"""
        Group = QGroupBox("Configuration GPU")
        Layout = QFormLayout(Group)

        # Mode GPU
        self.GpuModeCombo = QComboBox()
        self.GpuModeCombo.addItems([
            "Automatique",
            "GPU unique",
            "Multi-GPU (tous)"
        ])
        self.GpuModeCombo.currentIndexChanged.connect(self.OnGpuModeChanged)
        Layout.addRow("Mode:", self.GpuModeCombo)

        # Tile size
        TileSizeLayout = QHBoxLayout()
        self.TileSizeSpinBox = QSpinBox()
        self.TileSizeSpinBox.setRange(0, PerformancePresets.MAX_TILE_SIZE)
        self.TileSizeSpinBox.setSingleStep(32)
        self.TileSizeSpinBox.setSpecialValueText("Auto")
        self.TileSizeSpinBox.valueChanged.connect(self.OnConfigChanged)
        TileSizeLayout.addWidget(self.TileSizeSpinBox)

        self.TileSizeRecommendLabel = QLabel("")
        self.TileSizeRecommendLabel.setStyleSheet("color: gray; font-style: italic;")
        TileSizeLayout.addWidget(self.TileSizeRecommendLabel)
        TileSizeLayout.addStretch()

        TileSizeWidget = QWidget()
        TileSizeWidget.setLayout(TileSizeLayout)
        Layout.addRow("Tile size:", TileSizeWidget)

        return Group

    def CreateAdvancedGroup(self) -> QGroupBox:
        """Crée le groupe de configuration avancée"""
        Group = QGroupBox("Configuration avancee")
        Layout = QFormLayout(Group)

        # Threads
        ThreadsLayout = QHBoxLayout()

        self.LoadThreadsSpinBox = QSpinBox()
        self.LoadThreadsSpinBox.setRange(1, PerformancePresets.MAX_THREADS)
        self.LoadThreadsSpinBox.valueChanged.connect(self.OnConfigChanged)
        ThreadsLayout.addWidget(QLabel("Load:"))
        ThreadsLayout.addWidget(self.LoadThreadsSpinBox)

        self.ProcessThreadsSpinBox = QSpinBox()
        self.ProcessThreadsSpinBox.setRange(1, PerformancePresets.MAX_THREADS)
        self.ProcessThreadsSpinBox.valueChanged.connect(self.OnConfigChanged)
        ThreadsLayout.addWidget(QLabel("Process:"))
        ThreadsLayout.addWidget(self.ProcessThreadsSpinBox)

        self.SaveThreadsSpinBox = QSpinBox()
        self.SaveThreadsSpinBox.setRange(1, PerformancePresets.MAX_THREADS)
        self.SaveThreadsSpinBox.valueChanged.connect(self.OnConfigChanged)
        ThreadsLayout.addWidget(QLabel("Save:"))
        ThreadsLayout.addWidget(self.SaveThreadsSpinBox)

        ThreadsLayout.addStretch()

        ThreadsWidget = QWidget()
        ThreadsWidget.setLayout(ThreadsLayout)
        Layout.addRow("Threads:", ThreadsWidget)

        # Note: Le mode TTA est configuré côté serveur pour garantir
        # une qualité uniforme sur tous les paquets d'une vidéo

        return Group

    def CreateActionBar(self) -> QWidget:
        """Crée la barre d'actions"""
        ActionWidget = QWidget()
        ActionLayout = QHBoxLayout(ActionWidget)

        # Auto-configurer
        self.AutoConfigButton = QPushButton("Configuration automatique")
        self.AutoConfigButton.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        self.AutoConfigButton.clicked.connect(self.AutoConfigure)
        ActionLayout.addWidget(self.AutoConfigButton)

        ActionLayout.addStretch()

        # Restaurer défauts
        self.ResetButton = QPushButton("Reinitialiser")
        self.ResetButton.clicked.connect(self.ResetConfig)
        ActionLayout.addWidget(self.ResetButton)

        # Sauvegarder
        self.SaveButton = QPushButton("Sauvegarder")
        self.SaveButton.setStyleSheet("""
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
        self.SaveButton.clicked.connect(self.SaveConfig)
        ActionLayout.addWidget(self.SaveButton)

        return ActionWidget

    def DetectHardware(self):
        """Lance la détection du matériel"""
        # Affiche un dialog de progression
        self.ProgressDialog = QProgressDialog(
            "Detection du materiel en cours...",
            None, 0, 0, self
        )
        self.ProgressDialog.setWindowModality(Qt.WindowModal)
        self.ProgressDialog.show()

        # Lance la détection dans un thread
        self.DetectionThread = HardwareDetectionThread()
        self.DetectionThread.Finished.connect(self.OnHardwareDetected)
        self.DetectionThread.Error.connect(self.OnHardwareError)
        self.DetectionThread.start()

    def OnHardwareDetected(self, Hardware: dict):
        """Appelé quand la détection est terminée"""
        self.ProgressDialog.close()
        self.DetectedHardware = Hardware
        self.UpdateHardwareDisplay()

        # Propose l'auto-configuration si première exécution
        if self.ConfigManager.IsFirstRun():
            Reply = QMessageBox.question(
                self,
                "Configuration automatique",
                "Voulez-vous appliquer la configuration optimale basee sur votre materiel?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if Reply == QMessageBox.Yes:
                self.AutoConfigure()

    def OnHardwareError(self, ErrorMsg: str):
        """Appelé si une erreur survient pendant la détection"""
        self.ProgressDialog.close()
        QMessageBox.warning(
            self,
            "Erreur de detection",
            f"Impossible de detecter le materiel: {ErrorMsg}"
        )

    def UpdateHardwareDisplay(self):
        """Met à jour l'affichage du matériel détecté"""
        if not self.DetectedHardware:
            return

        # CPU
        Cpu = self.DetectedHardware.get("cpu", {})
        CpuText = f"{Cpu.get('name', 'Inconnu')} ({Cpu.get('physical_cores', '?')} coeurs)"
        self.CpuLabel.setText(CpuText)

        # RAM
        Ram = self.DetectedHardware.get("ram", {})
        RamText = f"{Ram.get('total_gb', '?')} GB ({Ram.get('available_gb', '?')} GB disponible)"
        self.RamLabel.setText(RamText)

        # GPU
        Gpus = self.DetectedHardware.get("gpu", [])
        self.GpuTable.setRowCount(len(Gpus))

        for Row, Gpu in enumerate(Gpus):
            # Checkbox
            CheckBox = QCheckBox()
            CheckBox.setChecked(Gpu.get("id", -1) >= 0)
            CheckBox.stateChanged.connect(self.OnGpuSelectionChanged)
            self.GpuTable.setCellWidget(Row, 0, CheckBox)

            # ID
            IdItem = QTableWidgetItem(str(Gpu.get("id", "?")))
            IdItem.setFlags(IdItem.flags() & ~Qt.ItemIsEditable)
            self.GpuTable.setItem(Row, 1, IdItem)

            # Nom
            NameItem = QTableWidgetItem(Gpu.get("name", "Inconnu"))
            NameItem.setFlags(NameItem.flags() & ~Qt.ItemIsEditable)
            self.GpuTable.setItem(Row, 2, NameItem)

            # VRAM
            VramMb = Gpu.get("vram_mb", 0)
            VramText = f"{VramMb} MB" if VramMb else "?"
            VramItem = QTableWidgetItem(VramText)
            VramItem.setFlags(VramItem.flags() & ~Qt.ItemIsEditable)
            self.GpuTable.setItem(Row, 3, VramItem)

        # Met à jour la recommandation de tile size
        self.UpdateTileSizeRecommendation()

    def UpdateTileSizeRecommendation(self):
        """Met à jour la recommandation de tile size"""
        if not self.DetectedHardware:
            self.TileSizeRecommendLabel.setText("")
            return

        Gpus = self.DetectedHardware.get("gpu", [])
        if not Gpus:
            self.TileSizeRecommendLabel.setText("")
            return

        # Trouve la plus petite VRAM parmi les GPU sélectionnés
        MinVram = None
        for Gpu in Gpus:
            if Gpu.get("id", -1) >= 0:
                VramMb = Gpu.get("vram_mb", 0)
                if VramMb and (MinVram is None or VramMb < MinVram):
                    MinVram = VramMb

        if MinVram:
            RecommendedTileSize = self.ConfigManager.GetTileSizeForVram(MinVram)
            self.TileSizeRecommendLabel.setText(f"(Recommande: {RecommendedTileSize})")
        else:
            self.TileSizeRecommendLabel.setText("")

    def LoadConfig(self):
        """Charge la configuration actuelle"""
        Config = self.ConfigManager.Load()

        # Tile size
        TileSize = Config.get("tile_size", 0)
        self.TileSizeSpinBox.setValue(TileSize)

        # GPU mode
        GpuIds = Config.get("gpu_ids", [])
        if not GpuIds:
            self.GpuModeCombo.setCurrentIndex(0)  # Auto
        elif len(GpuIds) == 1:
            self.GpuModeCombo.setCurrentIndex(1)  # GPU unique
        else:
            self.GpuModeCombo.setCurrentIndex(2)  # Multi-GPU

        # Threads
        Threads = Config.get("threads", {})
        self.LoadThreadsSpinBox.setValue(Threads.get("load", 1))
        self.ProcessThreadsSpinBox.setValue(Threads.get("process", 2))
        self.SaveThreadsSpinBox.setValue(Threads.get("save", 2))

    def SaveConfig(self):
        """Sauvegarde la configuration"""
        Config = self.BuildConfigFromUI()

        if self.ConfigManager.Save(Config):
            QMessageBox.information(
                self,
                "Configuration sauvegardee",
                "La configuration de performance a ete sauvegardee.\n"
                "Elle sera appliquee au prochain traitement."
            )

            # Notifie le parent pour recharger la config
            if hasattr(self.ParentWindow, 'ReloadPerformanceConfig'):
                self.ParentWindow.ReloadPerformanceConfig()
        else:
            QMessageBox.warning(
                self,
                "Erreur",
                "Impossible de sauvegarder la configuration."
            )

    def BuildConfigFromUI(self) -> dict:
        """Construit la configuration depuis l'UI"""
        # GPU IDs
        GpuIds = []
        GpuMode = self.GpuModeCombo.currentIndex()

        if self.DetectedHardware:
            Gpus = self.DetectedHardware.get("gpu", [])
            for Row in range(self.GpuTable.rowCount()):
                CheckBox = self.GpuTable.cellWidget(Row, 0)
                if CheckBox and CheckBox.isChecked():
                    if Row < len(Gpus):
                        GpuId = Gpus[Row].get("id", -1)
                        if GpuId >= 0:
                            GpuIds.append(GpuId)

        return {
            "auto_detect": GpuMode == 0,
            "tile_size": self.TileSizeSpinBox.value(),
            "gpu_ids": GpuIds,
            "threads": {
                "load": self.LoadThreadsSpinBox.value(),
                "process": self.ProcessThreadsSpinBox.value(),
                "save": self.SaveThreadsSpinBox.value()
            },
            "output_format": "png",
            "first_run": False
        }

    def AutoConfigure(self):
        """Applique la configuration automatique"""
        if not self.DetectedHardware:
            # Détecte d'abord le matériel
            self.DetectHardware()
            return

        Config = self.ConfigManager.AutoConfigure(self.DetectedHardware)

        # Met à jour l'UI
        self.TileSizeSpinBox.setValue(Config.get("tile_size", 0))

        Threads = Config.get("threads", {})
        self.LoadThreadsSpinBox.setValue(Threads.get("load", 1))
        self.ProcessThreadsSpinBox.setValue(Threads.get("process", 2))
        self.SaveThreadsSpinBox.setValue(Threads.get("save", 2))

        # Sélectionne tous les GPU valides
        for Row in range(self.GpuTable.rowCount()):
            CheckBox = self.GpuTable.cellWidget(Row, 0)
            if CheckBox:
                IdItem = self.GpuTable.item(Row, 1)
                if IdItem:
                    try:
                        GpuId = int(IdItem.text())
                        CheckBox.setChecked(GpuId >= 0)
                    except ValueError:
                        CheckBox.setChecked(False)

        QMessageBox.information(
            self,
            "Configuration automatique",
            "La configuration optimale a ete appliquee.\n"
            "N'oubliez pas de sauvegarder si vous souhaitez la conserver."
        )

    def ResetConfig(self):
        """Réinitialise la configuration"""
        Reply = QMessageBox.question(
            self,
            "Reinitialiser",
            "Voulez-vous vraiment reinitialiser la configuration aux valeurs par defaut?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if Reply == QMessageBox.Yes:
            self.ConfigManager.Reset()
            self.LoadConfig()
            QMessageBox.information(
                self,
                "Configuration reinitialisee",
                "La configuration a ete reinitialisee aux valeurs par defaut."
            )

    def OnGpuModeChanged(self, Index: int):
        """Appelé quand le mode GPU change"""
        self.OnConfigChanged()

    def OnGpuSelectionChanged(self, State):
        """Appelé quand la sélection GPU change"""
        self.OnConfigChanged()

    def OnConfigChanged(self):
        """Appelé quand une valeur de configuration change"""
        # On pourrait ajouter une indication visuelle ici
        pass

    def Refresh(self):
        """Rafraîchit l'onglet"""
        self.LoadConfig()
        if self.DetectedHardware:
            self.UpdateHardwareDisplay()
