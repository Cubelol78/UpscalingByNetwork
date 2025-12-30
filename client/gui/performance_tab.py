"""
Onglet Performances - Configuration des performances Real-ESRGAN
Détection matériel et optimisation automatique
Auto-save avec debounce et indicateur visuel
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QFormLayout, QSpinBox, QCheckBox,
    QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QProgressDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont

from client.utils.hardware_detector import HardwareDetector
from client.utils.performance_config import PerformanceConfigManager, PerformancePresets
from shared.utils.constants import CompressionConfig
from shared.gui.theme_manager import ThemeManager


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
    """Onglet de configuration des performances avec auto-save"""

    # Délai de debounce pour l'auto-save (en ms)
    AUTOSAVE_DELAY_MS = 500

    def __init__(self, ParentWindow):
        super().__init__()
        self.ParentWindow = ParentWindow
        self.HardwareDetector = HardwareDetector()
        self.ConfigManager = PerformanceConfigManager()
        self.DetectedHardware = None
        self.DetectionThread = None

        # Flag pour bloquer l'auto-save pendant le chargement
        self.IsLoading = False

        # Timer pour debounce de l'auto-save
        self.AutoSaveTimer = QTimer()
        self.AutoSaveTimer.setSingleShot(True)
        self.AutoSaveTimer.timeout.connect(self.DoAutoSave)

        # Timer pour masquer l'indicateur "Sauvegardé"
        self.SavedIndicatorTimer = QTimer()
        self.SavedIndicatorTimer.setSingleShot(True)
        self.SavedIndicatorTimer.timeout.connect(self.HideSavedIndicator)

        # Timer pour debounce de l'auto-save du thème
        self.ThemeAutoSaveTimer = QTimer()
        self.ThemeAutoSaveTimer.setSingleShot(True)
        self.ThemeAutoSaveTimer.timeout.connect(self.AutoSaveTheme)

        self.SetupUI()
        self.LoadConfig()

        # Essaie d'utiliser le cache hardware du parent s'il existe
        self.TryUseCachedHardware()

    def SetupUI(self):
        """Configure l'interface utilisateur"""
        Layout = QVBoxLayout(self)

        # En-tête avec titre et indicateur de sauvegarde
        HeaderLayout = QHBoxLayout()

        Title = QLabel("Configuration des performances")
        TitleFont = QFont()
        TitleFont.setPointSize(16)
        TitleFont.setBold(True)
        Title.setFont(TitleFont)
        HeaderLayout.addWidget(Title)

        HeaderLayout.addStretch()

        # Indicateur de sauvegarde (discret)
        self.SavedIndicator = QLabel("")
        self.SavedIndicator.setProperty("class", "hint-success")
        HeaderLayout.addWidget(self.SavedIndicator)

        Layout.addLayout(HeaderLayout)

        # Section Apparence (thème)
        AppearanceGroup = self.CreateAppearanceGroup()
        Layout.addWidget(AppearanceGroup)

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
        Group = QGroupBox("Materiel detecte")
        Layout = QVBoxLayout(Group)

        # Indicateur de chargement
        self.HardwareLoadingLabel = QLabel("Detection en cours...")
        self.HardwareLoadingLabel.setProperty("class", "hint-warning")
        Layout.addWidget(self.HardwareLoadingLabel)

        # Informations CPU/RAM
        InfoLayout = QFormLayout()

        self.CpuLabel = QLabel("--")
        InfoLayout.addRow("CPU:", self.CpuLabel)

        self.RamLabel = QLabel("--")
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

        # Bouton re-détection (au cas où le matériel change)
        DetectButton = QPushButton("Re-detecter le materiel")
        DetectButton.clicked.connect(self.DetectHardware)
        Layout.addWidget(DetectButton)

        return Group

    def CreateAppearanceGroup(self) -> QGroupBox:
        """Crée le groupe Apparence (thème)"""
        Group = QGroupBox("Apparence")

        FormLayout = QFormLayout(Group)

        # Sélecteur de thème
        ThemeLayout = QHBoxLayout()
        self.ThemeComboBox = QComboBox()
        self.ThemeComboBox.addItem("Auto (Systeme)", ThemeManager.THEME_AUTO)
        self.ThemeComboBox.addItem("Clair", ThemeManager.THEME_LIGHT)
        self.ThemeComboBox.addItem("Sombre", ThemeManager.THEME_DARK)
        self.ThemeComboBox.currentIndexChanged.connect(self.OnThemeChanged)
        ThemeLayout.addWidget(self.ThemeComboBox)

        ThemeNote = QLabel("(applique immediatement)")
        ThemeNote.setProperty("class", "hint")
        ThemeLayout.addWidget(ThemeNote)
        ThemeLayout.addStretch()

        FormLayout.addRow("Theme:", ThemeLayout)

        return Group

    def OnThemeChanged(self, Index: int):
        """Appelé quand le thème change - applique immédiatement et déclenche l'auto-save"""
        if self.IsLoading:
            return

        # Récupère la valeur du thème sélectionné
        ThemeValue = self.ThemeComboBox.currentData()

        # Applique immédiatement le thème
        if hasattr(self.ParentWindow, 'ThemeManager') and self.ParentWindow.ThemeManager:
            self.ParentWindow.ThemeManager.SetUserPreference(ThemeValue)

        # Redémarre le timer de debounce pour la sauvegarde
        self.ThemeAutoSaveTimer.stop()
        self.ThemeAutoSaveTimer.start(self.AUTOSAVE_DELAY_MS)

    def AutoSaveTheme(self):
        """Sauvegarde automatique du thème dans le fichier de configuration"""
        try:
            ThemeValue = self.ThemeComboBox.currentData()

            # Charge la config actuelle, met à jour le thème, et sauvegarde
            Config = self.ConfigManager.Load()
            Config['theme'] = ThemeValue
            self.ConfigManager.Save(Config)

            # Affiche l'indicateur "Sauvegardé"
            self.ShowSavedIndicator()

            if hasattr(self.ParentWindow, 'Logger'):
                self.ParentWindow.Logger.info(f"Theme mis a jour: {ThemeValue}")

        except Exception as e:
            if hasattr(self.ParentWindow, 'Logger'):
                self.ParentWindow.Logger.error(f"Erreur lors de l'auto-save du theme: {e}")

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
        self.GpuModeCombo.currentIndexChanged.connect(self.OnConfigChanged)
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
        self.TileSizeRecommendLabel.setProperty("class", "hint")
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

        # Niveau de compression réseau
        CompressionLayout = QHBoxLayout()
        self.CompressionLevelSpinBox = QSpinBox()
        self.CompressionLevelSpinBox.setRange(CompressionConfig.LEVEL_MIN, CompressionConfig.LEVEL_MAX)
        self.CompressionLevelSpinBox.setValue(CompressionConfig.LEVEL_DEFAULT)
        self.CompressionLevelSpinBox.setToolTip("1 = compression rapide, 10 = compression maximale")
        self.CompressionLevelSpinBox.valueChanged.connect(self.OnConfigChanged)
        CompressionLayout.addWidget(self.CompressionLevelSpinBox)

        CompressionNote = QLabel("(1=rapide, 10=max)")
        CompressionNote.setProperty("class", "hint")
        CompressionLayout.addWidget(CompressionNote)
        CompressionLayout.addStretch()

        CompressionWidget = QWidget()
        CompressionWidget.setLayout(CompressionLayout)
        Layout.addRow("Compression reseau:", CompressionWidget)

        # Note TTA
        TtaNote = QLabel("Note: Le mode TTA est configure cote serveur")
        TtaNote.setProperty("class", "hint")
        Layout.addRow("", TtaNote)

        return Group

    def CreateActionBar(self) -> QWidget:
        """Crée la barre d'actions"""
        ActionWidget = QWidget()
        ActionLayout = QHBoxLayout(ActionWidget)

        # Auto-configurer
        self.AutoConfigButton = QPushButton("Configuration automatique")
        self.AutoConfigButton.setObjectName("AutoConfigButton")
        self.AutoConfigButton.setProperty("class", "info")
        self.AutoConfigButton.clicked.connect(self.AutoConfigure)
        ActionLayout.addWidget(self.AutoConfigButton)

        ActionLayout.addStretch()

        # Restaurer défauts
        self.ResetButton = QPushButton("Reinitialiser")
        self.ResetButton.clicked.connect(self.ResetConfig)
        ActionLayout.addWidget(self.ResetButton)

        # Note: Plus de bouton "Sauvegarder" - auto-save actif

        return ActionWidget

    def TryUseCachedHardware(self):
        """Essaie d'utiliser le cache hardware du parent"""
        if hasattr(self.ParentWindow, 'GetCachedHardware'):
            CachedHardware = self.ParentWindow.GetCachedHardware()
            if CachedHardware:
                self.OnHardwareCacheReady(CachedHardware)
            # Sinon, attend que OnHardwareCacheReady soit appelé par le parent

    def OnHardwareCacheReady(self, Hardware: dict):
        """Appelé quand le cache hardware du parent est prêt"""
        if Hardware and not self.DetectedHardware:
            self.DetectedHardware = Hardware
            self.UpdateHardwareDisplay()

            # Auto-configure au premier lancement si nécessaire
            if self.ConfigManager.IsFirstRun():
                self.AutoConfigureQuiet()

    def DetectHardware(self):
        """Lance la re-détection du matériel"""
        self.HardwareLoadingLabel.setText("Detection en cours...")
        self.HardwareLoadingLabel.setVisible(True)

        # Lance la détection dans un thread
        self.DetectionThread = HardwareDetectionThread()
        self.DetectionThread.Finished.connect(self.OnHardwareDetected)
        self.DetectionThread.Error.connect(self.OnHardwareError)
        self.DetectionThread.start()

    def OnHardwareDetected(self, Hardware: dict):
        """Appelé quand la détection est terminée"""
        self.HardwareLoadingLabel.setVisible(False)
        self.DetectedHardware = Hardware
        self.UpdateHardwareDisplay()

    def OnHardwareError(self, ErrorMsg: str):
        """Appelé si une erreur survient pendant la détection"""
        self.HardwareLoadingLabel.setText(f"Erreur: {ErrorMsg}")
        self.HardwareLoadingLabel.setProperty("class", "hint-danger")
        self.HardwareLoadingLabel.style().unpolish(self.HardwareLoadingLabel)
        self.HardwareLoadingLabel.style().polish(self.HardwareLoadingLabel)

    def UpdateHardwareDisplay(self):
        """Met à jour l'affichage du matériel détecté"""
        if not self.DetectedHardware:
            return

        self.HardwareLoadingLabel.setVisible(False)

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

        # Bloque les signaux pendant la mise à jour
        WasLoading = self.IsLoading
        self.IsLoading = True

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

            # Nom (avec indication dédié/intégré)
            GpuName = Gpu.get("name", "Inconnu")
            IsIntegrated = self.ConfigManager._IsIntegratedGpu(GpuName)
            TypeSuffix = " (integre)" if IsIntegrated else ""
            NameItem = QTableWidgetItem(f"{GpuName}{TypeSuffix}")
            NameItem.setFlags(NameItem.flags() & ~Qt.ItemIsEditable)
            self.GpuTable.setItem(Row, 2, NameItem)

            # VRAM
            VramMb = Gpu.get("vram_mb", 0)
            VramText = f"{VramMb} MB" if VramMb else "?"
            VramItem = QTableWidgetItem(VramText)
            VramItem.setFlags(VramItem.flags() & ~Qt.ItemIsEditable)
            self.GpuTable.setItem(Row, 3, VramItem)

        self.IsLoading = WasLoading

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
        # Bloque l'auto-save pendant le chargement
        self.IsLoading = True

        try:
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

            # Compression level
            CompressionLevel = Config.get("compression_level", CompressionConfig.LEVEL_DEFAULT)
            self.CompressionLevelSpinBox.setValue(CompressionLevel)

            # Thème
            ThemeValue = Config.get("theme", ThemeManager.THEME_AUTO)
            ThemeIndex = self.ThemeComboBox.findData(ThemeValue)
            if ThemeIndex >= 0:
                self.ThemeComboBox.setCurrentIndex(ThemeIndex)

        finally:
            # Réactive l'auto-save
            self.IsLoading = False

    def OnConfigChanged(self):
        """Appelé quand une valeur de configuration change - déclenche l'auto-save"""
        if self.IsLoading:
            return

        # Redémarre le timer de debounce
        self.AutoSaveTimer.stop()
        self.AutoSaveTimer.start(self.AUTOSAVE_DELAY_MS)

    def OnGpuSelectionChanged(self, State):
        """Appelé quand la sélection GPU change"""
        self.OnConfigChanged()

    def DoAutoSave(self):
        """Effectue la sauvegarde automatique"""
        Config = self.BuildConfigFromUI()

        if self.ConfigManager.Save(Config):
            # Affiche l'indicateur "Sauvegardé"
            self.ShowSavedIndicator()

            # Propage la config au processeur actif
            if hasattr(self.ParentWindow, 'ReloadPerformanceConfig'):
                self.ParentWindow.ReloadPerformanceConfig()

    def ShowSavedIndicator(self):
        """Affiche brièvement l'indicateur de sauvegarde"""
        self.SavedIndicator.setText("Sauvegarde")
        self.SavedIndicatorTimer.start(2000)  # Masque après 2 secondes

    def HideSavedIndicator(self):
        """Masque l'indicateur de sauvegarde"""
        self.SavedIndicator.setText("")

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
            "first_run": False,
            "compression_level": self.CompressionLevelSpinBox.value()
        }

    def AutoConfigureQuiet(self):
        """Auto-configure sans afficher de message (pour le premier lancement)"""
        if not self.DetectedHardware:
            return

        UseMultiGpu = False
        Config = self.ConfigManager.AutoConfigure(self.DetectedHardware, UseMultiGpu=UseMultiGpu)
        self.ApplyConfigToUI(Config)

    def AutoConfigure(self):
        """Applique la configuration automatique avec sélection intelligente des GPU"""
        if not self.DetectedHardware:
            # Détecte d'abord le matériel
            self.DetectHardware()
            return

        # Détermine si on utilise le multi-GPU basé sur la sélection actuelle
        UseMultiGpu = self.GpuModeCombo.currentIndex() == 2  # "Multi-GPU (tous)"

        # Auto-configure avec sélection intelligente (préfère les GPU dédiés)
        Config = self.ConfigManager.AutoConfigure(self.DetectedHardware, UseMultiGpu=UseMultiGpu)

        # Applique à l'UI (déclenchera auto-save)
        self.ApplyConfigToUI(Config)

        # Affiche les GPU sélectionnés dans le message
        SelectedGpuIds = Config.get("gpu_ids", [])
        Gpus = self.DetectedHardware.get("gpu", [])
        SelectedNames = []
        for Gpu in Gpus:
            if Gpu.get("id") in SelectedGpuIds:
                SelectedNames.append(Gpu.get("name", f"GPU {Gpu.get('id')}"))

        GpuInfo = "\n".join(f"  - {name}" for name in SelectedNames) if SelectedNames else "  - Aucun (mode CPU)"

        QMessageBox.information(
            self,
            "Configuration automatique",
            f"Configuration optimale appliquee et sauvegardee.\n\n"
            f"GPU selectionnes (prefere les GPU dedies):\n{GpuInfo}"
        )

    def ApplyConfigToUI(self, Config: dict):
        """Applique une configuration à l'UI"""
        # Bloque temporairement pour éviter multiple saves
        WasLoading = self.IsLoading
        self.IsLoading = True

        try:
            # Met à jour l'UI
            self.TileSizeSpinBox.setValue(Config.get("tile_size", 0))

            Threads = Config.get("threads", {})
            self.LoadThreadsSpinBox.setValue(Threads.get("load", 1))
            self.ProcessThreadsSpinBox.setValue(Threads.get("process", 2))
            self.SaveThreadsSpinBox.setValue(Threads.get("save", 2))

            # Sélectionne uniquement les GPU choisis par l'auto-configuration
            SelectedGpuIds = Config.get("gpu_ids", [])

            for Row in range(self.GpuTable.rowCount()):
                CheckBox = self.GpuTable.cellWidget(Row, 0)
                if CheckBox:
                    IdItem = self.GpuTable.item(Row, 1)
                    if IdItem:
                        try:
                            GpuId = int(IdItem.text())
                            CheckBox.setChecked(GpuId in SelectedGpuIds)
                        except ValueError:
                            CheckBox.setChecked(False)

            # Met à jour le mode GPU
            if len(SelectedGpuIds) > 1:
                self.GpuModeCombo.setCurrentIndex(2)  # Multi-GPU
            elif len(SelectedGpuIds) == 1:
                self.GpuModeCombo.setCurrentIndex(1)  # GPU unique
            else:
                self.GpuModeCombo.setCurrentIndex(0)  # Auto

        finally:
            self.IsLoading = WasLoading

        # Déclenche une sauvegarde manuelle (car IsLoading était True)
        self.DoAutoSave()

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
            self.ShowSavedIndicator()

            # Propage la config
            if hasattr(self.ParentWindow, 'ReloadPerformanceConfig'):
                self.ParentWindow.ReloadPerformanceConfig()

    def Refresh(self):
        """Rafraîchit l'onglet"""
        # Ne recharge pas la config pour éviter de perdre les changements non sauvés
        if self.DetectedHardware:
            self.UpdateHardwareDisplay()
