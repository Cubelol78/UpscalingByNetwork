"""
Onglet Performances - Configuration des performances Real-ESRGAN
Detection materiel et optimisation automatique
Auto-save avec debounce et indicateur visuel
Panneaux depliables avec synchronisation GPU
"""

import platform
from typing import Tuple, List, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QFormLayout, QSpinBox, QCheckBox,
    QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QProgressDialog, QLineEdit,
    QFileDialog, QScrollArea
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont

from client.utils.hardware_detector import HardwareDetector
from client.utils.performance_config import PerformanceConfigManager, PerformancePresets
from shared.utils.constants import CompressionConfig
from shared.utils.path_validator import ValidateWorkDirectory, NormalizePath
from shared.gui.theme_manager import ThemeManager
from shared.gui.collapsible_panel import CollapsiblePanel


class HardwareDetectionThread(QThread):
    """Thread pour la detection materiel (evite de bloquer l'UI)"""
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

    # Delai de debounce pour l'auto-save (en ms)
    AUTOSAVE_DELAY_MS = 500

    # Modes GPU
    GPU_MODE_AUTO = 0
    GPU_MODE_SINGLE = 1
    GPU_MODE_MULTI = 2

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

        # Timer pour masquer l'indicateur "Sauvegarde"
        self.SavedIndicatorTimer = QTimer()
        self.SavedIndicatorTimer.setSingleShot(True)
        self.SavedIndicatorTimer.timeout.connect(self.HideSavedIndicator)

        # Timer pour debounce de l'auto-save du theme
        self.ThemeAutoSaveTimer = QTimer()
        self.ThemeAutoSaveTimer.setSingleShot(True)
        self.ThemeAutoSaveTimer.timeout.connect(self.AutoSaveTheme)

        # Stockage des checkboxes GPU
        self.GpuCheckboxes: List[QCheckBox] = []

        # Cache pour l'etat de connexion (evite mises a jour inutiles)
        self._LastConnectionState: Optional[bool] = None

        self.SetupUI()
        self.LoadConfig()

        # Essaie d'utiliser le cache hardware du parent s'il existe
        self.TryUseCachedHardware()

    def SetupUI(self):
        """Configure l'interface utilisateur"""
        # Layout principal avec scroll
        MainLayout = QVBoxLayout(self)
        MainLayout.setContentsMargins(0, 0, 0, 0)

        # Creation d'un widget conteneur pour le contenu scrollable
        ScrollContent = QWidget()
        ContentLayout = QVBoxLayout(ScrollContent)

        # En-tete avec titre et indicateur de sauvegarde
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

        ContentLayout.addLayout(HeaderLayout)

        # Panneau Apparence (theme) - replie par defaut
        self.AppearancePanel = self.CreateAppearancePanel()
        ContentLayout.addWidget(self.AppearancePanel)

        # Panneau GPU & Materiel (fusionne Hardware + GPU Config) - deplie
        self.GpuHardwarePanel = self.CreateGpuHardwarePanel()
        ContentLayout.addWidget(self.GpuHardwarePanel)

        # Panneau Performance - deplie
        self.PerformancePanel = self.CreatePerformancePanel()
        ContentLayout.addWidget(self.PerformancePanel)

        # Panneau Stockage - replie par defaut
        self.StoragePanel = self.CreateStoragePanel()
        ContentLayout.addWidget(self.StoragePanel)

        # Panneau Stockage RAM (Full RAM Mode) - replie par defaut
        self.RamStoragePanel = self.CreateRamStoragePanel()
        ContentLayout.addWidget(self.RamStoragePanel)

        # Barre d'actions (toujours visible)
        ActionBar = self.CreateActionBar()
        ContentLayout.addWidget(ActionBar)

        ContentLayout.addStretch()

        # Creation de la zone de scroll
        ScrollArea = QScrollArea()
        ScrollArea.setWidget(ScrollContent)
        ScrollArea.setWidgetResizable(True)
        ScrollArea.setFrameShape(QScrollArea.NoFrame)

        # Ajout de la zone de scroll au layout principal
        MainLayout.addWidget(ScrollArea)

    def CreateAppearancePanel(self) -> CollapsiblePanel:
        """Cree le panneau Apparence (theme) - replie par defaut"""
        Panel = CollapsiblePanel("Apparence", Expanded=False)

        FormLayout = QFormLayout()

        # Selecteur de theme
        ThemeLayout = QHBoxLayout()
        self.ThemeComboBox = QComboBox()
        self.ThemeComboBox.addItem("Auto (Systeme)", ThemeManager.THEME_AUTO)
        self.ThemeComboBox.addItem("Clair", ThemeManager.THEME_LIGHT)
        self.ThemeComboBox.addItem("Sombre", ThemeManager.THEME_DARK)
        self.ThemeComboBox.setToolTip(
            "Auto: suit les preferences systeme\n"
            "Clair: theme lumineux\n"
            "Sombre: theme fonce"
        )
        self.ThemeComboBox.currentIndexChanged.connect(self.OnThemeChanged)
        ThemeLayout.addWidget(self.ThemeComboBox)

        ThemeNote = QLabel("(applique immediatement)")
        ThemeNote.setProperty("class", "hint")
        ThemeLayout.addWidget(ThemeNote)
        ThemeLayout.addStretch()

        FormLayout.addRow("Theme:", ThemeLayout)

        FormWidget = QWidget()
        FormWidget.setLayout(FormLayout)
        Panel.AddWidget(FormWidget)

        return Panel

    def OnThemeChanged(self, Index: int):
        """Appele quand le theme change - applique immediatement et declenche l'auto-save"""
        if self.IsLoading:
            return

        # Recupere la valeur du theme selectionne
        ThemeValue = self.ThemeComboBox.currentData()

        # Applique immediatement le theme
        if hasattr(self.ParentWindow, 'ThemeManager') and self.ParentWindow.ThemeManager:
            self.ParentWindow.ThemeManager.SetUserPreference(ThemeValue)

        # Redemarre le timer de debounce pour la sauvegarde
        self.ThemeAutoSaveTimer.stop()
        self.ThemeAutoSaveTimer.start(self.AUTOSAVE_DELAY_MS)

    def AutoSaveTheme(self):
        """Sauvegarde automatique du theme dans le fichier de configuration"""
        try:
            ThemeValue = self.ThemeComboBox.currentData()

            # Charge la config actuelle, met a jour le theme, et sauvegarde
            Config = self.ConfigManager.Load()
            Config['theme'] = ThemeValue
            self.ConfigManager.Save(Config)

            # Affiche l'indicateur "Sauvegarde"
            self.ShowSavedIndicator()

            if hasattr(self.ParentWindow, 'Logger'):
                self.ParentWindow.Logger.info(f"Theme mis a jour: {ThemeValue}")

        except Exception as e:
            if hasattr(self.ParentWindow, 'Logger'):
                self.ParentWindow.Logger.error(f"Erreur lors de l'auto-save du theme: {e}")

    def CreateGpuHardwarePanel(self) -> CollapsiblePanel:
        """Cree le panneau GPU & Materiel (fusionne Hardware + GPU Config)"""
        Panel = CollapsiblePanel("GPU & Materiel", Expanded=True)

        ContentWidget = QWidget()
        ContentLayout = QVBoxLayout(ContentWidget)
        ContentLayout.setContentsMargins(0, 0, 0, 0)

        # Indicateur de chargement
        self.HardwareLoadingLabel = QLabel("Detection en cours...")
        self.HardwareLoadingLabel.setProperty("class", "hint-warning")
        ContentLayout.addWidget(self.HardwareLoadingLabel)

        # Informations CPU/RAM
        InfoLayout = QFormLayout()

        self.CpuLabel = QLabel("--")
        InfoLayout.addRow("CPU:", self.CpuLabel)

        self.RamLabel = QLabel("--")
        InfoLayout.addRow("RAM:", self.RamLabel)

        ContentLayout.addLayout(InfoLayout)

        # Separateur
        SepLabel = QLabel("")
        ContentLayout.addWidget(SepLabel)

        # Mode GPU avec tooltip
        GpuModeLayout = QFormLayout()
        self.GpuModeCombo = QComboBox()
        self.GpuModeCombo.addItems([
            "Automatique",
            "GPU unique",
            "Multi-GPU"
        ])
        self.GpuModeCombo.setToolTip(
            "MODE DE SELECTION GPU\n\n"
            "- Automatique: le systeme detecte et utilise\n"
            "  le meilleur GPU disponible (recommande)\n\n"
            "- GPU unique: vous choisissez manuellement\n"
            "  quel GPU utiliser dans la liste ci-dessous\n\n"
            "- Multi-GPU: utilise plusieurs GPUs en parallele\n"
            "  pour traiter plus d'images simultanement\n"
            "  (necessite au moins 2 GPUs dedies)"
        )
        self.GpuModeCombo.currentIndexChanged.connect(self._OnGpuModeChanged)
        GpuModeLayout.addRow("Mode GPU:", self.GpuModeCombo)
        ContentLayout.addLayout(GpuModeLayout)

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

        ContentLayout.addWidget(self.GpuTable)

        # Tile size
        TileSizeLayout = QFormLayout()
        TileSizeWidget = QWidget()
        TileSizeInnerLayout = QHBoxLayout(TileSizeWidget)
        TileSizeInnerLayout.setContentsMargins(0, 0, 0, 0)

        self.TileSizeSpinBox = QSpinBox()
        self.TileSizeSpinBox.setRange(0, PerformancePresets.MAX_TILE_SIZE)
        self.TileSizeSpinBox.setSingleStep(32)
        self.TileSizeSpinBox.setSpecialValueText("Auto")
        self.TileSizeSpinBox.setToolTip(
            "TAILLE DES TUILES (Tile Size)\n\n"
            "L'image est decoupee en tuiles carrees pour le traitement.\n"
            "Chaque tuile est traitee separement par le GPU.\n\n"
            "- Auto (0): calcule automatiquement selon la VRAM\n"
            "- Petit (128-256): utilise moins de VRAM, plus lent\n"
            "- Moyen (384-512): bon equilibre VRAM/vitesse\n"
            "- Grand (768+): plus rapide mais necessite beaucoup de VRAM\n\n"
            "Si vous avez des erreurs 'out of memory', reduisez cette valeur.\n"
            "Valeurs typiques: 256 (4GB), 384 (6GB), 512 (8GB+)"
        )
        self.TileSizeSpinBox.valueChanged.connect(self.OnConfigChanged)
        TileSizeInnerLayout.addWidget(self.TileSizeSpinBox)

        self.TileSizeRecommendLabel = QLabel("")
        self.TileSizeRecommendLabel.setProperty("class", "hint")
        TileSizeInnerLayout.addWidget(self.TileSizeRecommendLabel)
        TileSizeInnerLayout.addStretch()

        TileSizeLayout.addRow("Tile size:", TileSizeWidget)
        ContentLayout.addLayout(TileSizeLayout)

        # Bouton re-detection
        DetectButton = QPushButton("Re-detecter le materiel")
        DetectButton.clicked.connect(self.DetectHardware)
        ContentLayout.addWidget(DetectButton)

        Panel.AddWidget(ContentWidget)
        return Panel

    def CreatePerformancePanel(self) -> CollapsiblePanel:
        """Cree le panneau Performance"""
        Panel = CollapsiblePanel("Performance", Expanded=True)

        FormLayout = QFormLayout()

        # Threads
        ThreadsWidget = QWidget()
        ThreadsLayout = QHBoxLayout(ThreadsWidget)
        ThreadsLayout.setContentsMargins(0, 0, 0, 0)

        self.LoadThreadsSpinBox = QSpinBox()
        self.LoadThreadsSpinBox.setRange(1, PerformancePresets.MAX_THREADS)
        self.LoadThreadsSpinBox.setToolTip(
            "Threads pour le CHARGEMENT des images\n\n"
            "Ces threads lisent les images recues du serveur\n"
            "et les preparent pour le traitement GPU.\n\n"
            "Valeur recommandee: 1-2\n"
            "Augmenter si le GPU attend souvent les images."
        )
        self.LoadThreadsSpinBox.valueChanged.connect(self.OnConfigChanged)
        ThreadsLayout.addWidget(QLabel("Load:"))
        ThreadsLayout.addWidget(self.LoadThreadsSpinBox)

        self.ProcessThreadsSpinBox = QSpinBox()
        self.ProcessThreadsSpinBox.setRange(1, PerformancePresets.MAX_THREADS)
        self.ProcessThreadsSpinBox.setToolTip(
            "Threads pour le TRAITEMENT GPU (upscaling)\n\n"
            "Ces threads envoient les images au GPU\n"
            "pour l'upscaling via Real-ESRGAN.\n\n"
            "Valeur recommandee: 1-2\n"
            "En mode Multi-GPU, augmenter selon le nombre de GPUs."
        )
        self.ProcessThreadsSpinBox.valueChanged.connect(self.OnConfigChanged)
        ThreadsLayout.addWidget(QLabel("Process:"))
        ThreadsLayout.addWidget(self.ProcessThreadsSpinBox)

        self.SaveThreadsSpinBox = QSpinBox()
        self.SaveThreadsSpinBox.setRange(1, PerformancePresets.MAX_THREADS)
        self.SaveThreadsSpinBox.setToolTip(
            "Threads pour la SAUVEGARDE des images\n\n"
            "Ces threads compressent et envoient\n"
            "les images traitees vers le serveur.\n\n"
            "Valeur recommandee: 2-4\n"
            "Augmenter si le reseau est rapide mais le CPU lent."
        )
        self.SaveThreadsSpinBox.valueChanged.connect(self.OnConfigChanged)
        ThreadsLayout.addWidget(QLabel("Save:"))
        ThreadsLayout.addWidget(self.SaveThreadsSpinBox)

        ThreadsLayout.addStretch()
        FormLayout.addRow("Threads:", ThreadsWidget)

        # Niveau de compression reseau
        CompressionWidget = QWidget()
        CompressionLayout = QHBoxLayout(CompressionWidget)
        CompressionLayout.setContentsMargins(0, 0, 0, 0)

        self.CompressionLevelSpinBox = QSpinBox()
        self.CompressionLevelSpinBox.setRange(CompressionConfig.LEVEL_MIN, CompressionConfig.LEVEL_MAX)
        self.CompressionLevelSpinBox.setValue(CompressionConfig.LEVEL_DEFAULT)
        self.CompressionLevelSpinBox.setToolTip(
            "NIVEAU DE COMPRESSION RESEAU\n\n"
            "Compresse les images avant de les envoyer au serveur.\n\n"
            "- 1-3: compression rapide, fichiers plus gros\n"
            "  (bon pour reseau local rapide)\n\n"
            "- 4-6: equilibre vitesse/taille (recommande)\n\n"
            "- 7-10: compression maximale, fichiers plus petits\n"
            "  (bon pour connexion lente, mais utilise plus de CPU)"
        )
        self.CompressionLevelSpinBox.valueChanged.connect(self.OnConfigChanged)
        CompressionLayout.addWidget(self.CompressionLevelSpinBox)

        CompressionNote = QLabel("(1=rapide, 10=max)")
        CompressionNote.setProperty("class", "hint")
        CompressionLayout.addWidget(CompressionNote)
        CompressionLayout.addStretch()

        FormLayout.addRow("Compression reseau:", CompressionWidget)

        # Pipeline multi-batch
        PipelineWidget = QWidget()
        PipelineLayout = QHBoxLayout(PipelineWidget)
        PipelineLayout.setContentsMargins(0, 0, 0, 0)

        self.MaxConcurrentBatchesSpinBox = QSpinBox()
        self.MaxConcurrentBatchesSpinBox.setRange(1, 5)
        self.MaxConcurrentBatchesSpinBox.setValue(2)
        self.MaxConcurrentBatchesSpinBox.setToolTip(
            "PIPELINE MULTI-BATCH\n\n"
            "Permet de recevoir le prochain paquet d'images\n"
            "pendant que le precedent est encore en traitement.\n\n"
            "- 1: desactive - attend que le batch soit envoye\n"
            "  avant de recevoir le suivant\n\n"
            "- 2: recommande - recoit 1 batch en avance\n"
            "  (masque la latence reseau)\n\n"
            "- 3-5: pour connexions tres lentes ou\n"
            "  traitement GPU tres rapide"
        )
        self.MaxConcurrentBatchesSpinBox.valueChanged.connect(self.OnConfigChanged)
        PipelineLayout.addWidget(self.MaxConcurrentBatchesSpinBox)

        PipelineNote = QLabel("(2+ pour reseau lent)")
        PipelineNote.setProperty("class", "hint")
        PipelineLayout.addWidget(PipelineNote)
        PipelineLayout.addStretch()

        FormLayout.addRow("Batches en pipeline:", PipelineWidget)

        # Note TTA
        TtaNote = QLabel("Note: Le mode TTA est configure cote serveur")
        TtaNote.setProperty("class", "hint")
        FormLayout.addRow("", TtaNote)

        FormWidget = QWidget()
        FormWidget.setLayout(FormLayout)
        Panel.AddWidget(FormWidget)

        return Panel

    def CreateStoragePanel(self) -> CollapsiblePanel:
        """Cree le panneau Stockage - replie par defaut"""
        Panel = CollapsiblePanel("Stockage", Expanded=False)

        FormLayout = QFormLayout()

        # Repertoire de travail
        WorkDirWidget = QWidget()
        WorkDirLayout = QHBoxLayout(WorkDirWidget)
        WorkDirLayout.setContentsMargins(0, 0, 0, 0)

        self.WorkDirInput = QLineEdit()
        self.WorkDirInput.setPlaceholderText(self.ConfigManager.GetDefaultWorkDirectory())
        self.WorkDirInput.textChanged.connect(self.OnWorkDirChanged)
        WorkDirLayout.addWidget(self.WorkDirInput)

        BrowseButton = QPushButton("Parcourir...")
        BrowseButton.clicked.connect(self.BrowseWorkDirectory)
        WorkDirLayout.addWidget(BrowseButton)

        self.WorkDirNoteLabel = QLabel("")
        WorkDirLayout.addWidget(self.WorkDirNoteLabel)

        # Met a jour le tooltip et la note selon l'etat de connexion
        self._UpdateWorkDirNote(Force=True)

        FormLayout.addRow("Repertoire de travail:", WorkDirWidget)

        # Affichage de l'espace disque
        self.DiskSpaceLabel = QLabel("")
        self.DiskSpaceLabel.setProperty("class", "hint")
        FormLayout.addRow("Espace disponible:", self.DiskSpaceLabel)

        FormWidget = QWidget()
        FormWidget.setLayout(FormLayout)
        Panel.AddWidget(FormWidget)

        return Panel

    def CreateRamStoragePanel(self) -> CollapsiblePanel:
        """Cree le panneau Stockage RAM (Full RAM Mode) - replie par defaut"""
        Panel = CollapsiblePanel("Stockage RAM (Full RAM Mode)", Expanded=False)

        FormLayout = QFormLayout()

        # Mode RAM disk
        ModeWidget = QWidget()
        ModeLayout = QHBoxLayout(ModeWidget)
        ModeLayout.setContentsMargins(0, 0, 0, 0)

        self.RamModeCombo = QComboBox()
        self.RamModeCombo.addItem("Desactive", "disabled")
        self.RamModeCombo.addItem("Automatique", "auto")
        self.RamModeCombo.addItem("Manuel", "manual")
        self.RamModeCombo.setToolTip(
            "MODE FULL RAM\n\n"
            "- Desactive: utilise le disque classique (par defaut)\n\n"
            "- Automatique: detecte et utilise automatiquement\n"
            "  un RAM disk disponible (tmpfs sur Linux, ImDisk sur Windows)\n\n"
            "- Manuel: vous specifiez un chemin personnalise\n"
            "  vers un RAM disk que vous avez cree\n\n"
            "Avantages: ameliore les performances, evite l'usure du SSD"
        )
        self.RamModeCombo.currentIndexChanged.connect(self.OnRamModeChanged)
        ModeLayout.addWidget(self.RamModeCombo)
        ModeLayout.addStretch()

        FormLayout.addRow("Mode:", ModeWidget)

        # Informations RAM disk detecte
        self.RamDiskInfoLabel = QLabel("Aucun RAM disk detecte")
        self.RamDiskInfoLabel.setProperty("class", "hint")
        self.RamDiskInfoLabel.setWordWrap(True)
        FormLayout.addRow("Detection:", self.RamDiskInfoLabel)

        # Chemin manuel (visible uniquement en mode manuel)
        self.RamDiskPathWidget = QWidget()
        RamDiskPathLayout = QHBoxLayout(self.RamDiskPathWidget)
        RamDiskPathLayout.setContentsMargins(0, 0, 0, 0)

        self.RamDiskPathInput = QLineEdit()
        self.RamDiskPathInput.setPlaceholderText("/dev/shm ou chemin personnalise")
        self.RamDiskPathInput.textChanged.connect(self.OnRamDiskPathChanged)
        RamDiskPathLayout.addWidget(self.RamDiskPathInput)

        BrowseRamButton = QPushButton("Parcourir...")
        BrowseRamButton.clicked.connect(self.BrowseRamDiskPath)
        RamDiskPathLayout.addWidget(BrowseRamButton)

        FormLayout.addRow("Chemin manuel:", self.RamDiskPathWidget)
        self.RamDiskPathWidget.setVisible(False)

        # Espace minimum requis
        MinSpaceWidget = QWidget()
        MinSpaceLayout = QHBoxLayout(MinSpaceWidget)
        MinSpaceLayout.setContentsMargins(0, 0, 0, 0)

        self.RamMinSpaceSpinBox = QSpinBox()
        self.RamMinSpaceSpinBox.setRange(100, 10000)
        self.RamMinSpaceSpinBox.setValue(500)
        self.RamMinSpaceSpinBox.setSuffix(" MB")
        self.RamMinSpaceSpinBox.setToolTip(
            "Espace minimum requis sur le RAM disk\n"
            "Si l'espace disponible est inferieur, le systeme\n"
            "utilisera automatiquement le disque classique"
        )
        self.RamMinSpaceSpinBox.valueChanged.connect(self.OnConfigChanged)
        MinSpaceLayout.addWidget(self.RamMinSpaceSpinBox)

        MinSpaceNote = QLabel("(recommande: 500-2000 MB)")
        MinSpaceNote.setProperty("class", "hint")
        MinSpaceLayout.addWidget(MinSpaceNote)
        MinSpaceLayout.addStretch()

        FormLayout.addRow("Espace minimum:", MinSpaceWidget)

        # Parametres Windows (ImDisk) - visible uniquement sur Windows
        if platform.system() == "Windows":
            self.WindowsRamGroup = QGroupBox("Parametres Windows (ImDisk)")

            WindowsLayout = QFormLayout()

            # Statut ImDisk
            self.ImDiskStatusLabel = QLabel("Verification...")
            self.ImDiskStatusLabel.setProperty("class", "hint")
            WindowsLayout.addRow("Statut ImDisk:", self.ImDiskStatusLabel)

            # Lettre du lecteur
            DriveWidget = QWidget()
            DriveLayout = QHBoxLayout(DriveWidget)
            DriveLayout.setContentsMargins(0, 0, 0, 0)

            self.DriveLetterCombo = QComboBox()
            # Les lettres seront remplies dynamiquement
            for Letter in "RSTUVWXYZ":
                self.DriveLetterCombo.addItem(f"{Letter}:", Letter)
            self.DriveLetterCombo.setToolTip(
                "Lettre du lecteur pour le RAM disk ImDisk\n"
                "Par defaut: R:\n"
                "Choisissez une lettre non utilisee"
            )
            self.DriveLetterCombo.currentIndexChanged.connect(self.OnConfigChanged)
            DriveLayout.addWidget(self.DriveLetterCombo)
            DriveLayout.addStretch()

            WindowsLayout.addRow("Lettre du lecteur:", DriveWidget)

            # Taille du RAM disk
            SizeWidget = QWidget()
            SizeLayout = QHBoxLayout(SizeWidget)
            SizeLayout.setContentsMargins(0, 0, 0, 0)

            self.RamDiskSizeSpinBox = QSpinBox()
            self.RamDiskSizeSpinBox.setRange(512, 16384)
            self.RamDiskSizeSpinBox.setValue(2048)
            self.RamDiskSizeSpinBox.setSuffix(" MB")
            self.RamDiskSizeSpinBox.setToolTip(
                "Taille du RAM disk a creer\n"
                "Recommandation: 2-4 GB pour un traitement fluide\n"
                "Ne depassez pas 50% de votre RAM totale"
            )
            self.RamDiskSizeSpinBox.valueChanged.connect(self.OnConfigChanged)
            SizeLayout.addWidget(self.RamDiskSizeSpinBox)
            SizeLayout.addStretch()

            WindowsLayout.addRow("Taille:", SizeWidget)

            # Options automatiques
            self.AutoCreateCheckBox = QCheckBox("Creer automatiquement au demarrage du client")
            self.AutoCreateCheckBox.setChecked(True)
            self.AutoCreateCheckBox.setToolTip(
                "Si active, le RAM disk sera cree automatiquement\n"
                "au demarrage du client (mode auto uniquement)"
            )
            self.AutoCreateCheckBox.stateChanged.connect(self.OnConfigChanged)
            WindowsLayout.addRow("", self.AutoCreateCheckBox)

            self.AutoRemoveCheckBox = QCheckBox("Supprimer automatiquement a l'arret du client")
            self.AutoRemoveCheckBox.setChecked(True)
            self.AutoRemoveCheckBox.setToolTip(
                "Si active, le RAM disk sera supprime automatiquement\n"
                "a l'arret du client (libere la RAM)"
            )
            self.AutoRemoveCheckBox.stateChanged.connect(self.OnConfigChanged)
            WindowsLayout.addRow("", self.AutoRemoveCheckBox)

            # Note ImDisk
            ImDiskNote = QLabel(
                "ImDisk doit etre installe separement:\n"
                "https://sourceforge.net/projects/imdisk-toolkit/"
            )
            ImDiskNote.setProperty("class", "hint-warning")
            ImDiskNote.setWordWrap(True)
            ImDiskNote.setOpenExternalLinks(True)
            WindowsLayout.addRow("", ImDiskNote)

            self.WindowsRamGroup.setLayout(WindowsLayout)
            FormLayout.addRow(self.WindowsRamGroup)

            # Verification du statut ImDisk
            self.CheckImDiskStatus()

        FormWidget = QWidget()
        FormWidget.setLayout(FormLayout)
        Panel.AddWidget(FormWidget)

        # Mise a jour initiale de l'affichage
        self.UpdateRamDiskInfo()

        return Panel

    def BrowseWorkDirectory(self):
        """Ouvre un dialogue pour selectionner le repertoire de travail"""
        CurrentDir = self.WorkDirInput.text() or self.ConfigManager.GetDefaultWorkDirectory()

        Directory = QFileDialog.getExistingDirectory(
            self,
            "Selectionner le repertoire de travail",
            CurrentDir
        )

        if Directory:
            self.WorkDirInput.setText(Directory)

    def OnWorkDirChanged(self, Text: str):
        """Appele quand le repertoire de travail change"""
        if self.IsLoading:
            return

        # Met a jour l'affichage de l'espace disque
        self.UpdateDiskSpaceDisplay()

        # Met a jour la note selon l'etat de connexion (force car l'utilisateur modifie)
        self._UpdateWorkDirNote(Force=True)

        # Declenche l'auto-save
        self.OnConfigChanged()

    def _IsClientConnected(self) -> bool:
        """Verifie si le client est connecte au serveur"""
        try:
            if hasattr(self.ParentWindow, 'Client') and self.ParentWindow.Client:
                if hasattr(self.ParentWindow.Client, 'ConnectionManager'):
                    return self.ParentWindow.Client.ConnectionManager.IsConnected()
        except Exception:
            pass
        return False

    def _UpdateWorkDirNote(self, Force: bool = False):
        """Met a jour la note et le tooltip du repertoire de travail selon l'etat de connexion"""
        IsConnected = self._IsClientConnected()

        # Evite les mises a jour inutiles si l'etat n'a pas change
        if not Force and self._LastConnectionState == IsConnected:
            return

        self._LastConnectionState = IsConnected

        if IsConnected:
            # Client connecte: necessite deconnexion
            self.WorkDirNoteLabel.setText("(deconnectez-vous d'abord)")
            self.WorkDirNoteLabel.setProperty("class", "hint-warning")
            self.WorkDirInput.setToolTip(
                "Repertoire pour les fichiers temporaires de traitement\n"
                "Laissez vide pour utiliser le dossier par defaut\n\n"
                "ATTENTION: Vous etes actuellement connecte.\n"
                "Deconnectez-vous pour que le changement prenne effet."
            )
        else:
            # Client deconnecte: applique a la prochaine connexion
            self.WorkDirNoteLabel.setText("(applique a la connexion)")
            self.WorkDirNoteLabel.setProperty("class", "hint-success")
            self.WorkDirInput.setToolTip(
                "Repertoire pour les fichiers temporaires de traitement\n"
                "Laissez vide pour utiliser le dossier par defaut\n\n"
                "Le changement sera applique a la prochaine connexion."
            )

        # Refresh le style
        self.WorkDirNoteLabel.style().unpolish(self.WorkDirNoteLabel)
        self.WorkDirNoteLabel.style().polish(self.WorkDirNoteLabel)

    def UpdateDiskSpaceDisplay(self):
        """Met a jour l'affichage de l'espace disque disponible"""
        import shutil
        import os

        WorkDir = self.WorkDirInput.text() or self.ConfigManager.GetDefaultWorkDirectory()

        try:
            # Verifie si le chemin existe, sinon utilise le parent
            CheckPath = WorkDir
            while CheckPath and not os.path.exists(CheckPath):
                CheckPath = os.path.dirname(CheckPath)

            if CheckPath:
                Usage = shutil.disk_usage(CheckPath)
                FreeGb = Usage.free / (1024 ** 3)
                TotalGb = Usage.total / (1024 ** 3)

                if FreeGb < 10:
                    self.DiskSpaceLabel.setProperty("class", "hint-danger")
                    self.DiskSpaceLabel.setText(f"{FreeGb:.1f} GB libre sur {TotalGb:.0f} GB (ATTENTION: espace faible!)")
                elif FreeGb < 50:
                    self.DiskSpaceLabel.setProperty("class", "hint-warning")
                    self.DiskSpaceLabel.setText(f"{FreeGb:.1f} GB libre sur {TotalGb:.0f} GB")
                else:
                    self.DiskSpaceLabel.setProperty("class", "hint-success")
                    self.DiskSpaceLabel.setText(f"{FreeGb:.1f} GB libre sur {TotalGb:.0f} GB")

                # Refresh le style
                self.DiskSpaceLabel.style().unpolish(self.DiskSpaceLabel)
                self.DiskSpaceLabel.style().polish(self.DiskSpaceLabel)
            else:
                self.DiskSpaceLabel.setText("Chemin invalide")
                self.DiskSpaceLabel.setProperty("class", "hint-danger")

        except Exception as e:
            self.DiskSpaceLabel.setText(f"Erreur: {str(e)}")
            self.DiskSpaceLabel.setProperty("class", "hint-danger")

    # =========================================================================
    # RAM Storage Management
    # =========================================================================

    def OnRamModeChanged(self, Index: int):
        """Appele quand le mode RAM disk change"""
        if self.IsLoading:
            return

        Mode = self.RamModeCombo.currentData()

        # Affiche/masque le champ de chemin manuel
        self.RamDiskPathWidget.setVisible(Mode == "manual")

        # Met a jour les infos
        self.UpdateRamDiskInfo()

        # Sur Windows, active/desactive les options ImDisk selon le mode
        if platform.system() == "Windows":
            IsAuto = Mode == "auto"
            if hasattr(self, 'DriveLetterCombo'):
                self.DriveLetterCombo.setEnabled(IsAuto)
            if hasattr(self, 'RamDiskSizeSpinBox'):
                self.RamDiskSizeSpinBox.setEnabled(IsAuto)
            if hasattr(self, 'AutoCreateCheckBox'):
                self.AutoCreateCheckBox.setEnabled(IsAuto)
            if hasattr(self, 'AutoRemoveCheckBox'):
                self.AutoRemoveCheckBox.setEnabled(IsAuto)

        # Declenche l'auto-save
        self.OnConfigChanged()

    def UpdateRamDiskInfo(self):
        """Met a jour l'affichage des informations du RAM disk"""
        from shared.utils.ramdisk_detector import RamDiskDetector

        Mode = self.RamModeCombo.currentData()

        if Mode == "disabled":
            self.RamDiskInfoLabel.setText("Mode desactive - utilise le disque classique")
            self.RamDiskInfoLabel.setProperty("class", "hint")
        elif Mode == "auto":
            # Detecte les RAM disks disponibles
            RamDisks = RamDiskDetector.DetectAvailable()
            if RamDisks:
                BestRamDisk = RamDiskDetector.GetBestRamDisk(self.RamMinSpaceSpinBox.value())
                if BestRamDisk:
                    self.RamDiskInfoLabel.setText(
                        f"Detecte: {BestRamDisk.path}\n"
                        f"Espace: {BestRamDisk.available_mb} MB disponible sur {BestRamDisk.total_mb} MB\n"
                        f"Source: {BestRamDisk.source}"
                    )
                    self.RamDiskInfoLabel.setProperty("class", "hint-success")
                else:
                    self.RamDiskInfoLabel.setText(
                        f"RAM disk trouve mais espace insuffisant\n"
                        f"({RamDisks[0].available_mb} MB < {self.RamMinSpaceSpinBox.value()} MB requis)"
                    )
                    self.RamDiskInfoLabel.setProperty("class", "hint-warning")
            else:
                if platform.system() == "Windows":
                    self.RamDiskInfoLabel.setText(
                        "Aucun RAM disk detecte\n"
                        "ImDisk peut creer un RAM disk automatiquement\n"
                        "(voir parametres Windows ci-dessous)"
                    )
                    self.RamDiskInfoLabel.setProperty("class", "hint-warning")
                else:
                    self.RamDiskInfoLabel.setText("Aucun RAM disk detecte sur ce systeme")
                    self.RamDiskInfoLabel.setProperty("class", "hint-warning")
        elif Mode == "manual":
            ManualPath = self.RamDiskPathInput.text().strip()
            if not ManualPath:
                self.RamDiskInfoLabel.setText("Veuillez specifier un chemin")
                self.RamDiskInfoLabel.setProperty("class", "hint-warning")
            else:
                # Valide le chemin
                ValidationResult = RamDiskDetector.ValidateRamDiskPath(ManualPath)
                if ValidationResult.is_valid:
                    RamDiskStatus = "RAM disk" if ValidationResult.is_ramdisk else "disque standard"
                    self.RamDiskInfoLabel.setText(
                        f"Chemin valide ({RamDiskStatus})\n"
                        f"Espace disponible: {ValidationResult.available_mb} MB"
                    )
                    if ValidationResult.is_ramdisk:
                        self.RamDiskInfoLabel.setProperty("class", "hint-success")
                    else:
                        self.RamDiskInfoLabel.setProperty("class", "hint-warning")
                else:
                    self.RamDiskInfoLabel.setText(f"Invalide: {ValidationResult.error_message}")
                    self.RamDiskInfoLabel.setProperty("class", "hint-danger")

        # Refresh le style
        self.RamDiskInfoLabel.style().unpolish(self.RamDiskInfoLabel)
        self.RamDiskInfoLabel.style().polish(self.RamDiskInfoLabel)

    def CheckImDiskStatus(self):
        """Verifie si ImDisk est installe (Windows uniquement)"""
        if platform.system() != "Windows":
            return

        from shared.utils.ramdisk_detector import WindowsRamDiskManager

        if not hasattr(self, 'ImDiskStatusLabel'):
            return

        # Verifie si la bibliotheque ramdisk est disponible
        if not WindowsRamDiskManager.IsImDiskLibraryAvailable():
            self.ImDiskStatusLabel.setText(
                "Bibliotheque 'ramdisk' non installee\n"
                "Installez avec: pip install ramdisk"
            )
            self.ImDiskStatusLabel.setProperty("class", "hint-danger")
        elif WindowsRamDiskManager.IsImDiskInstalled():
            self.ImDiskStatusLabel.setText("ImDisk installe et fonctionnel")
            self.ImDiskStatusLabel.setProperty("class", "hint-success")
        else:
            self.ImDiskStatusLabel.setText(
                "ImDisk non installe\n"
                "Telechargez depuis: sourceforge.net/projects/imdisk-toolkit/"
            )
            self.ImDiskStatusLabel.setProperty("class", "hint-warning")

        # Refresh le style
        self.ImDiskStatusLabel.style().unpolish(self.ImDiskStatusLabel)
        self.ImDiskStatusLabel.style().polish(self.ImDiskStatusLabel)

    def OnRamDiskPathChanged(self, Text: str):
        """Appele quand le chemin du RAM disk manuel change"""
        if self.IsLoading:
            return

        # Met a jour l'affichage des infos
        self.UpdateRamDiskInfo()

        # Declenche l'auto-save
        self.OnConfigChanged()

    def BrowseRamDiskPath(self):
        """Ouvre un dialogue pour selectionner le chemin du RAM disk"""
        CurrentPath = self.RamDiskPathInput.text() or "/dev/shm"

        Directory = QFileDialog.getExistingDirectory(
            self,
            "Selectionner le chemin du RAM disk",
            CurrentPath
        )

        if Directory:
            self.RamDiskPathInput.setText(Directory)

    def CreateActionBar(self) -> QWidget:
        """Cree la barre d'actions"""
        ActionWidget = QWidget()
        ActionLayout = QHBoxLayout(ActionWidget)

        # Auto-configurer
        self.AutoConfigButton = QPushButton("Configuration automatique")
        self.AutoConfigButton.setObjectName("AutoConfigButton")
        self.AutoConfigButton.setProperty("class", "info")
        self.AutoConfigButton.setToolTip(
            "Configure automatiquement selon le materiel detecte\n"
            "Selectionne les meilleurs GPU et optimise les parametres"
        )
        self.AutoConfigButton.clicked.connect(self.AutoConfigure)
        ActionLayout.addWidget(self.AutoConfigButton)

        ActionLayout.addStretch()

        # Restaurer defauts
        self.ResetButton = QPushButton("Reinitialiser")
        self.ResetButton.setToolTip("Restaure tous les parametres par defaut")
        self.ResetButton.clicked.connect(self.ResetConfig)
        ActionLayout.addWidget(self.ResetButton)

        return ActionWidget

    # =========================================================================
    # GPU Mode Synchronization
    # =========================================================================

    def _OnGpuModeChanged(self, Index: int):
        """Appele quand le mode GPU change"""
        if self.IsLoading:
            return

        if Index == self.GPU_MODE_AUTO:
            # Mode Auto: desactive les checkboxes, decoche tout
            self._SetAllGpuCheckboxesEnabled(False)
            self._UncheckAllGpus()
        elif Index == self.GPU_MODE_SINGLE:
            # Mode Single: active les checkboxes, force 1 seul
            self._SetAllGpuCheckboxesEnabled(True)
            self._EnforceSingleGpuSelection()
        elif Index == self.GPU_MODE_MULTI:
            # Mode Multi: active les checkboxes, coche tous les GPU dedies
            self._SetAllGpuCheckboxesEnabled(True)
            self._CheckAllDedicatedGpus()

        # Sauvegarde
        self.OnConfigChanged()

    def _OnGpuCheckboxChanged(self, State):
        """Appele quand une checkbox GPU change"""
        if self.IsLoading:
            return

        Mode = self.GpuModeCombo.currentIndex()

        if Mode == self.GPU_MODE_SINGLE:
            # En mode Single, comportement radio (1 seul selectionne)
            Sender = self.sender()
            if State == Qt.Checked:
                self._UncheckOtherGpus(Sender)

        self.OnConfigChanged()

    def _SetAllGpuCheckboxesEnabled(self, Enabled: bool):
        """Active ou desactive toutes les checkboxes GPU"""
        for Checkbox in self.GpuCheckboxes:
            Checkbox.setEnabled(Enabled)

    def _UncheckAllGpus(self):
        """Decoche tous les GPU"""
        WasLoading = self.IsLoading
        self.IsLoading = True
        for Checkbox in self.GpuCheckboxes:
            Checkbox.setChecked(False)
        self.IsLoading = WasLoading

    def _UncheckOtherGpus(self, ExceptCheckbox: QCheckBox):
        """Decoche tous les GPU sauf celui specifie"""
        WasLoading = self.IsLoading
        self.IsLoading = True
        for Checkbox in self.GpuCheckboxes:
            if Checkbox != ExceptCheckbox:
                Checkbox.setChecked(False)
        self.IsLoading = WasLoading

    def _EnforceSingleGpuSelection(self):
        """Force la selection d'un seul GPU (le meilleur)"""
        if not self.DetectedHardware:
            return

        WasLoading = self.IsLoading
        self.IsLoading = True

        # Trouve le meilleur GPU
        BestIndex = self._GetBestGpuIndex()

        for i, Checkbox in enumerate(self.GpuCheckboxes):
            Checkbox.setChecked(i == BestIndex)

        self.IsLoading = WasLoading

    def _CheckAllDedicatedGpus(self):
        """Coche tous les GPU dedies"""
        if not self.DetectedHardware:
            return

        WasLoading = self.IsLoading
        self.IsLoading = True

        Gpus = self.DetectedHardware.get("gpu", [])
        for i, Checkbox in enumerate(self.GpuCheckboxes):
            if i < len(Gpus):
                GpuName = Gpus[i].get("name", "")
                IsDedicated = not self.ConfigManager._IsIntegratedGpu(GpuName)
                Checkbox.setChecked(IsDedicated and Gpus[i].get("id", -1) >= 0)
            else:
                Checkbox.setChecked(False)

        self.IsLoading = WasLoading

    def _GetBestGpuIndex(self) -> int:
        """Retourne l'index du meilleur GPU"""
        if not self.DetectedHardware:
            return 0

        Gpus = self.DetectedHardware.get("gpu", [])
        if not Gpus:
            return 0

        BestIndex = 0
        BestScore = -1

        for i, Gpu in enumerate(Gpus):
            if Gpu.get("id", -1) < 0:
                continue
            Score = self.ConfigManager._GetGpuScore(Gpu)
            if Score > BestScore:
                BestScore = Score
                BestIndex = i

        return BestIndex

    def _GetDedicatedGpuCount(self) -> int:
        """Retourne le nombre de GPU dedies"""
        if not self.DetectedHardware:
            return 0

        Gpus = self.DetectedHardware.get("gpu", [])
        Count = 0
        for Gpu in Gpus:
            if Gpu.get("id", -1) >= 0:
                GpuName = Gpu.get("name", "")
                if not self.ConfigManager._IsIntegratedGpu(GpuName):
                    Count += 1
        return Count

    def _CountCheckedGpus(self) -> int:
        """Compte le nombre de GPU coches"""
        return sum(1 for Cb in self.GpuCheckboxes if Cb.isChecked())

    def _UpdateGpuModeAvailability(self):
        """Desactive Multi-GPU si pas assez de GPUs"""
        DedicatedCount = self._GetDedicatedGpuCount()
        Model = self.GpuModeCombo.model()

        # Index 2 = Multi-GPU
        if Model.rowCount() > 2:
            Item = Model.item(2)
            if Item:
                Item.setEnabled(DedicatedCount >= 2)
                if DedicatedCount < 2:
                    Item.setToolTip("Necessite au moins 2 GPUs dedies")
                else:
                    Item.setToolTip("")

    def _ValidateGpuConfig(self) -> Tuple[bool, str]:
        """Valide la configuration GPU avant sauvegarde"""
        Mode = self.GpuModeCombo.currentIndex()
        CheckedCount = self._CountCheckedGpus()

        if Mode == self.GPU_MODE_SINGLE and CheckedCount != 1:
            return False, "Mode 'GPU unique' necessite exactement 1 GPU selectionne"
        if Mode == self.GPU_MODE_MULTI and CheckedCount < 2:
            return False, "Mode 'Multi-GPU' necessite au moins 2 GPUs selectionnes"

        return True, ""

    # =========================================================================
    # Hardware Detection
    # =========================================================================

    def TryUseCachedHardware(self):
        """Essaie d'utiliser le cache hardware du parent"""
        if hasattr(self.ParentWindow, 'GetCachedHardware'):
            CachedHardware = self.ParentWindow.GetCachedHardware()
            if CachedHardware:
                self.OnHardwareCacheReady(CachedHardware)

    def OnHardwareCacheReady(self, Hardware: dict):
        """Appele quand le cache hardware du parent est pret"""
        if Hardware and not self.DetectedHardware:
            self.DetectedHardware = Hardware
            self.UpdateHardwareDisplay()

            # Auto-configure au premier lancement si necessaire
            if self.ConfigManager.IsFirstRun():
                self.AutoConfigureQuiet()

    def DetectHardware(self):
        """Lance la re-detection du materiel"""
        self.HardwareLoadingLabel.setText("Detection en cours...")
        self.HardwareLoadingLabel.setVisible(True)

        # Lance la detection dans un thread
        self.DetectionThread = HardwareDetectionThread()
        self.DetectionThread.Finished.connect(self.OnHardwareDetected)
        self.DetectionThread.Error.connect(self.OnHardwareError)
        self.DetectionThread.start()

    def OnHardwareDetected(self, Hardware: dict):
        """Appele quand la detection est terminee"""
        self.HardwareLoadingLabel.setVisible(False)
        self.DetectedHardware = Hardware
        self.UpdateHardwareDisplay()

    def OnHardwareError(self, ErrorMsg: str):
        """Appele si une erreur survient pendant la detection"""
        self.HardwareLoadingLabel.setText(f"Erreur: {ErrorMsg}")
        self.HardwareLoadingLabel.setProperty("class", "hint-danger")
        self.HardwareLoadingLabel.style().unpolish(self.HardwareLoadingLabel)
        self.HardwareLoadingLabel.style().polish(self.HardwareLoadingLabel)

    def UpdateHardwareDisplay(self):
        """Met a jour l'affichage du materiel detecte"""
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
        self.GpuCheckboxes.clear()

        # Bloque les signaux pendant la mise a jour
        WasLoading = self.IsLoading
        self.IsLoading = True

        # Charge la config pour connaitre le mode et les GPU selectionnes
        Config = self.ConfigManager.GetAll()
        GpuMode = Config.get("gpu_mode", "auto")
        SavedGpuIds = Config.get("gpu_ids", [])

        # Determine l'index du mode
        if GpuMode == "auto":
            ModeIndex = self.GPU_MODE_AUTO
        elif GpuMode == "single":
            ModeIndex = self.GPU_MODE_SINGLE
        elif GpuMode == "multi":
            ModeIndex = self.GPU_MODE_MULTI
        else:
            ModeIndex = self.GPU_MODE_AUTO

        BestGpuIndex = self._GetBestGpuIndex() if Gpus else 0

        for Row, Gpu in enumerate(Gpus):
            GpuId = Gpu.get("id", -1)
            GpuName = Gpu.get("name", "")
            IsDedicated = not self.ConfigManager._IsIntegratedGpu(GpuName)

            # Checkbox
            CheckBox = QCheckBox()
            CheckBox.stateChanged.connect(self._OnGpuCheckboxChanged)
            self.GpuCheckboxes.append(CheckBox)

            # Determine l'etat de la checkbox selon le mode
            if ModeIndex == self.GPU_MODE_AUTO:
                CheckBox.setChecked(False)
                CheckBox.setEnabled(False)
            elif ModeIndex == self.GPU_MODE_SINGLE:
                if SavedGpuIds:
                    CheckBox.setChecked(GpuId in SavedGpuIds)
                else:
                    CheckBox.setChecked(Row == BestGpuIndex)
                CheckBox.setEnabled(True)
            elif ModeIndex == self.GPU_MODE_MULTI:
                if SavedGpuIds:
                    CheckBox.setChecked(GpuId in SavedGpuIds)
                else:
                    CheckBox.setChecked(IsDedicated and GpuId >= 0)
                CheckBox.setEnabled(True)

            self.GpuTable.setCellWidget(Row, 0, CheckBox)

            # ID
            IdItem = QTableWidgetItem(str(GpuId))
            IdItem.setFlags(IdItem.flags() & ~Qt.ItemIsEditable)
            self.GpuTable.setItem(Row, 1, IdItem)

            # Nom (avec indication dedie/integre)
            TypeSuffix = " (integre)" if not IsDedicated else ""
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

        # Met a jour le mode GPU dans le combo
        self.GpuModeCombo.setCurrentIndex(ModeIndex)

        # Met a jour la disponibilite du mode Multi-GPU
        self._UpdateGpuModeAvailability()

        # Met a jour la recommandation de tile size
        self.UpdateTileSizeRecommendation()

        # Met a jour le badge du panneau
        DedicatedCount = self._GetDedicatedGpuCount()
        if DedicatedCount > 0:
            self.GpuHardwarePanel.SetBadge(f"{DedicatedCount} GPU{'s' if DedicatedCount > 1 else ''}")
        else:
            self.GpuHardwarePanel.SetBadge("")

    def UpdateTileSizeRecommendation(self):
        """Met a jour la recommandation de tile size"""
        if not self.DetectedHardware:
            self.TileSizeRecommendLabel.setText("")
            return

        Gpus = self.DetectedHardware.get("gpu", [])
        if not Gpus:
            self.TileSizeRecommendLabel.setText("")
            return

        # Trouve la plus petite VRAM parmi les GPU selectionnes
        MinVram = None
        GpuName = ""
        for i, Gpu in enumerate(Gpus):
            if Gpu.get("id", -1) >= 0:
                # Verifie si ce GPU est selectionne
                if i < len(self.GpuCheckboxes) and self.GpuCheckboxes[i].isChecked():
                    VramMb = Gpu.get("vram_mb", 0)
                    if VramMb and (MinVram is None or VramMb < MinVram):
                        MinVram = VramMb
                        GpuName = Gpu.get("name", "")

        # Si aucun GPU selectionne, utilise le premier GPU valide
        if MinVram is None:
            for Gpu in Gpus:
                if Gpu.get("id", -1) >= 0:
                    VramMb = Gpu.get("vram_mb", 0)
                    if VramMb and (MinVram is None or VramMb < MinVram):
                        MinVram = VramMb
                        GpuName = Gpu.get("name", "")

        if MinVram:
            RecommendedTileSize = self.ConfigManager.GetTileSizeForVram(MinVram, GpuName)
            self.TileSizeRecommendLabel.setText(f"(Recommande: {RecommendedTileSize})")
        else:
            self.TileSizeRecommendLabel.setText("")

    # =========================================================================
    # Configuration
    # =========================================================================

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
            GpuMode = Config.get("gpu_mode", "auto")
            if GpuMode == "auto":
                self.GpuModeCombo.setCurrentIndex(self.GPU_MODE_AUTO)
            elif GpuMode == "single":
                self.GpuModeCombo.setCurrentIndex(self.GPU_MODE_SINGLE)
            elif GpuMode == "multi":
                self.GpuModeCombo.setCurrentIndex(self.GPU_MODE_MULTI)
            else:
                self.GpuModeCombo.setCurrentIndex(self.GPU_MODE_AUTO)

            # Threads
            Threads = Config.get("threads", {})
            self.LoadThreadsSpinBox.setValue(Threads.get("load", 1))
            self.ProcessThreadsSpinBox.setValue(Threads.get("process", 2))
            self.SaveThreadsSpinBox.setValue(Threads.get("save", 2))

            # Compression level
            CompressionLevel = Config.get("compression_level", CompressionConfig.LEVEL_DEFAULT)
            self.CompressionLevelSpinBox.setValue(CompressionLevel)

            # Theme
            ThemeValue = Config.get("theme", ThemeManager.THEME_AUTO)
            ThemeIndex = self.ThemeComboBox.findData(ThemeValue)
            if ThemeIndex >= 0:
                self.ThemeComboBox.setCurrentIndex(ThemeIndex)

            # Repertoire de travail
            WorkDir = Config.get("work_directory", "")
            self.WorkDirInput.setText(WorkDir)

            # Pipeline multi-batch
            MaxConcurrentBatches = Config.get("max_concurrent_batches", 2)
            self.MaxConcurrentBatchesSpinBox.setValue(MaxConcurrentBatches)

            # Mode RAM disk
            RamMode = Config.get("ram_mode", "disabled")
            RamModeIndex = self.RamModeCombo.findData(RamMode)
            if RamModeIndex >= 0:
                self.RamModeCombo.setCurrentIndex(RamModeIndex)

            # Chemin manuel du RAM disk
            RamDiskPath = Config.get("ram_disk_path", "")
            self.RamDiskPathInput.setText(RamDiskPath)

            # Espace minimum requis
            RamMinSpace = Config.get("ram_disk_min_size_mb", 500)
            self.RamMinSpaceSpinBox.setValue(RamMinSpace)

            # Parametres Windows (si disponibles)
            if platform.system() == "Windows":
                if hasattr(self, 'DriveLetterCombo'):
                    DriveLetter = Config.get("ram_disk_drive_letter", "R")
                    DriveIndex = self.DriveLetterCombo.findData(DriveLetter)
                    if DriveIndex >= 0:
                        self.DriveLetterCombo.setCurrentIndex(DriveIndex)

                if hasattr(self, 'RamDiskSizeSpinBox'):
                    RamDiskSize = Config.get("ram_disk_size_mb", 2048)
                    self.RamDiskSizeSpinBox.setValue(RamDiskSize)

                if hasattr(self, 'AutoCreateCheckBox'):
                    AutoCreate = Config.get("ram_disk_auto_create", True)
                    self.AutoCreateCheckBox.setChecked(AutoCreate)

                if hasattr(self, 'AutoRemoveCheckBox'):
                    AutoRemove = Config.get("ram_disk_auto_remove", True)
                    self.AutoRemoveCheckBox.setChecked(AutoRemove)

            # Met a jour l'affichage de l'espace disque
            self.UpdateDiskSpaceDisplay()

            # Met a jour l'affichage du RAM disk
            self.UpdateRamDiskInfo()

        finally:
            # Reactive l'auto-save
            self.IsLoading = False

    def OnConfigChanged(self):
        """Appele quand une valeur de configuration change - declenche l'auto-save"""
        if self.IsLoading:
            return

        # Redemarre le timer de debounce
        self.AutoSaveTimer.stop()
        self.AutoSaveTimer.start(self.AUTOSAVE_DELAY_MS)

    def OnGpuSelectionChanged(self, State):
        """Appele quand la selection GPU change"""
        self.OnConfigChanged()

    def DoAutoSave(self):
        """Effectue la sauvegarde automatique"""
        # Valide la config GPU
        IsValid, ErrorMsg = self._ValidateGpuConfig()
        if not IsValid:
            # Affiche un avertissement mais sauvegarde quand meme
            if hasattr(self.ParentWindow, 'Logger'):
                self.ParentWindow.Logger.warning(f"Config GPU: {ErrorMsg}")

        # Valide le répertoire de travail
        WorkDir = self.WorkDirInput.text().strip()
        if WorkDir:  # Uniquement si l'utilisateur a spécifié un chemin
            WorkDir = NormalizePath(WorkDir)
            validation = ValidateWorkDirectory(WorkDir, create_if_missing=False)

            if not validation.is_valid:
                # Affiche un message d'erreur et ne sauvegarde pas
                error_msg = validation.error_message
                if validation.suggested_fix:
                    error_msg += f"\n\n{validation.suggested_fix}"

                QMessageBox.warning(
                    self,
                    "Répertoire de travail invalide",
                    f"Le répertoire de travail spécifié est invalide:\n\n{error_msg}\n\n"
                    "Veuillez corriger le chemin ou laisser vide pour utiliser le répertoire par défaut."
                )

                # Remets le focus sur le champ pour correction
                self.WorkDirInput.setFocus()
                return

            # Mise à jour avec le chemin normalisé
            if self.WorkDirInput.text() != WorkDir:
                self.IsLoading = True
                self.WorkDirInput.setText(WorkDir)
                self.IsLoading = False

        Config = self.BuildConfigFromUI()

        if self.ConfigManager.Save(Config):
            # Determine le message selon ce qui a change
            self.ShowSavedIndicator()

            # Propage la config au processeur actif
            if hasattr(self.ParentWindow, 'ReloadPerformanceConfig'):
                self.ParentWindow.ReloadPerformanceConfig()

    def ShowSavedIndicator(self, Message: str = None):
        """Affiche brievement l'indicateur de sauvegarde"""
        if Message:
            self.SavedIndicator.setText(Message)
        else:
            self.SavedIndicator.setText("Sauvegarde")
        self.SavedIndicatorTimer.start(2000)  # Masque apres 2 secondes

    def HideSavedIndicator(self):
        """Masque l'indicateur de sauvegarde"""
        self.SavedIndicator.setText("")

    def BuildConfigFromUI(self) -> dict:
        """Construit la configuration depuis l'UI"""
        # GPU IDs
        GpuIds = []
        GpuMode = self.GpuModeCombo.currentIndex()

        # Convertit l'index en string
        if GpuMode == self.GPU_MODE_AUTO:
            GpuModeStr = "auto"
        elif GpuMode == self.GPU_MODE_SINGLE:
            GpuModeStr = "single"
        elif GpuMode == self.GPU_MODE_MULTI:
            GpuModeStr = "multi"
        else:
            GpuModeStr = "auto"

        if self.DetectedHardware and GpuMode != self.GPU_MODE_AUTO:
            Gpus = self.DetectedHardware.get("gpu", [])
            for Row, Checkbox in enumerate(self.GpuCheckboxes):
                if Checkbox.isChecked():
                    if Row < len(Gpus):
                        GpuId = Gpus[Row].get("id", -1)
                        if GpuId >= 0:
                            GpuIds.append(GpuId)

        Config = {
            "auto_detect": GpuMode == self.GPU_MODE_AUTO,
            "tile_size": self.TileSizeSpinBox.value(),
            "gpu_ids": GpuIds,
            "gpu_mode": GpuModeStr,
            "threads": {
                "load": self.LoadThreadsSpinBox.value(),
                "process": self.ProcessThreadsSpinBox.value(),
                "save": self.SaveThreadsSpinBox.value()
            },
            "output_format": "png",
            "first_run": False,
            "compression_level": self.CompressionLevelSpinBox.value(),
            "work_directory": self.WorkDirInput.text().strip(),
            "max_concurrent_batches": self.MaxConcurrentBatchesSpinBox.value(),
            # Parametres RAM disk
            "ram_mode": self.RamModeCombo.currentData(),
            "ram_disk_path": self.RamDiskPathInput.text().strip(),
            "ram_disk_min_size_mb": self.RamMinSpaceSpinBox.value()
        }

        # Parametres Windows (si disponibles)
        if platform.system() == "Windows":
            if hasattr(self, 'DriveLetterCombo'):
                Config["ram_disk_drive_letter"] = self.DriveLetterCombo.currentData()
            if hasattr(self, 'RamDiskSizeSpinBox'):
                Config["ram_disk_size_mb"] = self.RamDiskSizeSpinBox.value()
            if hasattr(self, 'AutoCreateCheckBox'):
                Config["ram_disk_auto_create"] = self.AutoCreateCheckBox.isChecked()
            if hasattr(self, 'AutoRemoveCheckBox'):
                Config["ram_disk_auto_remove"] = self.AutoRemoveCheckBox.isChecked()

        return Config

    def AutoConfigureQuiet(self):
        """Auto-configure sans afficher de message (pour le premier lancement)"""
        if not self.DetectedHardware:
            return

        UseMultiGpu = False
        Config = self.ConfigManager.AutoConfigure(self.DetectedHardware, UseMultiGpu=UseMultiGpu)
        Config["gpu_mode"] = "auto"  # Force mode auto au premier lancement
        self.ApplyConfigToUI(Config)

    def AutoConfigure(self):
        """Applique la configuration automatique avec selection intelligente des GPU"""
        if not self.DetectedHardware:
            # Detecte d'abord le materiel
            self.DetectHardware()
            return

        # Determine si on utilise le multi-GPU base sur la selection actuelle
        UseMultiGpu = self.GpuModeCombo.currentIndex() == self.GPU_MODE_MULTI

        # Auto-configure avec selection intelligente (prefere les GPU dedies)
        Config = self.ConfigManager.AutoConfigure(self.DetectedHardware, UseMultiGpu=UseMultiGpu)

        # Met a jour le mode GPU
        if UseMultiGpu:
            Config["gpu_mode"] = "multi"
        elif len(Config.get("gpu_ids", [])) == 1:
            Config["gpu_mode"] = "single"
        else:
            Config["gpu_mode"] = "auto"

        # Applique a l'UI (declenchera auto-save)
        self.ApplyConfigToUI(Config)

        # Affiche les GPU selectionnes dans le message
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
        """Applique une configuration a l'UI"""
        # Bloque temporairement pour eviter multiple saves
        WasLoading = self.IsLoading
        self.IsLoading = True

        try:
            # Met a jour l'UI
            self.TileSizeSpinBox.setValue(Config.get("tile_size", 0))

            Threads = Config.get("threads", {})
            self.LoadThreadsSpinBox.setValue(Threads.get("load", 1))
            self.ProcessThreadsSpinBox.setValue(Threads.get("process", 2))
            self.SaveThreadsSpinBox.setValue(Threads.get("save", 2))

            # Met a jour le mode GPU
            GpuMode = Config.get("gpu_mode", "auto")
            if GpuMode == "auto":
                self.GpuModeCombo.setCurrentIndex(self.GPU_MODE_AUTO)
            elif GpuMode == "single":
                self.GpuModeCombo.setCurrentIndex(self.GPU_MODE_SINGLE)
            elif GpuMode == "multi":
                self.GpuModeCombo.setCurrentIndex(self.GPU_MODE_MULTI)

            # Selectionne les GPU selon le mode
            SelectedGpuIds = Config.get("gpu_ids", [])

            for Row, Checkbox in enumerate(self.GpuCheckboxes):
                if self.DetectedHardware:
                    Gpus = self.DetectedHardware.get("gpu", [])
                    if Row < len(Gpus):
                        GpuId = Gpus[Row].get("id", -1)
                        if GpuMode == "auto":
                            Checkbox.setChecked(False)
                            Checkbox.setEnabled(False)
                        else:
                            Checkbox.setChecked(GpuId in SelectedGpuIds)
                            Checkbox.setEnabled(True)

        finally:
            self.IsLoading = WasLoading

        # Declenche une sauvegarde manuelle (car IsLoading etait True)
        self.DoAutoSave()

    def ResetConfig(self):
        """Reinitialise la configuration"""
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

            # Remet le mode auto et rafraichit l'affichage
            if self.DetectedHardware:
                self.UpdateHardwareDisplay()

            self.ShowSavedIndicator()

            # Propage la config
            if hasattr(self.ParentWindow, 'ReloadPerformanceConfig'):
                self.ParentWindow.ReloadPerformanceConfig()

    def Refresh(self):
        """Rafraichit l'onglet"""
        # Ne recharge pas la config pour eviter de perdre les changements non sauves
        if self.DetectedHardware:
            self.UpdateHardwareDisplay()

        # Met a jour la note du repertoire de travail selon l'etat de connexion
        self._UpdateWorkDirNote()
