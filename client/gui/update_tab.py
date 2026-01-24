"""
Onglet Mise à jour - Configuration et gestion des mises à jour (Client)
Permet de configurer le canal de mise à jour et de vérifier/appliquer les mises à jour
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QFormLayout, QComboBox,
    QCheckBox, QTextEdit, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QFont

from shared.utils.constants import AppMetadata, UpdateConfig


class UpdateCheckWorker(QThread):
    """Thread pour vérifier les mises à jour sans bloquer l'UI"""
    Finished = pyqtSignal(object)  # UpdateInfo ou Exception
    Error = pyqtSignal(str)

    def __init__(self, Channel: str):
        super().__init__()
        self.Channel = Channel

    def run(self):
        try:
            from shared.utils.updater import UpdateManager
            Manager = UpdateManager()
            Info = Manager.CheckUpdate(self.Channel)
            self.Finished.emit(Info)
        except Exception as e:
            self.Error.emit(str(e))


class UpdateApplyWorker(QThread):
    """Thread pour appliquer les mises à jour sans bloquer l'UI"""
    Finished = pyqtSignal(bool)
    Error = pyqtSignal(str)
    Progress = pyqtSignal(str)

    def __init__(self, UpdateInfo):
        super().__init__()
        self.UpdateInfo = UpdateInfo

    def run(self):
        try:
            from shared.utils.updater import UpdateManager
            Manager = UpdateManager()
            self.Progress.emit("Application de la mise à jour...")
            Success = Manager.ApplyUpdate(self.UpdateInfo)
            self.Finished.emit(Success)
        except Exception as e:
            self.Error.emit(str(e))


class UpdateTab(QWidget):
    """Onglet de gestion des mises à jour (Client)"""

    def __init__(self, ParentWindow):
        super().__init__()
        self.ParentWindow = ParentWindow
        self.IsLoading = False
        self.CurrentUpdateInfo = None
        self.CheckWorker = None
        self.ApplyWorker = None

        # Timer pour l'indicateur de sauvegarde
        self.SavedIndicatorTimer = QTimer()
        self.SavedIndicatorTimer.setSingleShot(True)
        self.SavedIndicatorTimer.timeout.connect(self.HideSavedIndicator)

        self.SetupUI()
        self.LoadConfiguration()

    def SetupUI(self):
        """Configure l'interface utilisateur"""
        Layout = QVBoxLayout(self)

        # En-tête avec titre et indicateur de sauvegarde
        HeaderLayout = QHBoxLayout()

        Title = QLabel("Mise a jour")
        TitleFont = QFont()
        TitleFont.setPointSize(16)
        TitleFont.setBold(True)
        Title.setFont(TitleFont)
        HeaderLayout.addWidget(Title)

        HeaderLayout.addStretch()

        self.SavedIndicator = QLabel("")
        self.SavedIndicator.setProperty("class", "hint-success")
        HeaderLayout.addWidget(self.SavedIndicator)

        Layout.addLayout(HeaderLayout)

        # Groupe Version
        VersionGroup = self.CreateVersionGroup()
        Layout.addWidget(VersionGroup)

        # Groupe Configuration
        ConfigGroup = self.CreateConfigGroup()
        Layout.addWidget(ConfigGroup)

        # Bouton vérifier
        CheckLayout = QHBoxLayout()
        self.CheckButton = QPushButton("Verifier maintenant")
        self.CheckButton.clicked.connect(self.OnCheckUpdateClicked)
        CheckLayout.addWidget(self.CheckButton)
        CheckLayout.addStretch()
        Layout.addLayout(CheckLayout)

        # Groupe Mise à jour disponible (caché par défaut)
        self.UpdateAvailableGroup = self.CreateUpdateAvailableGroup()
        self.UpdateAvailableGroup.setVisible(False)
        Layout.addWidget(self.UpdateAvailableGroup)

        Layout.addStretch()

    def CreateVersionGroup(self) -> QGroupBox:
        """Crée le groupe d'affichage de la version"""
        Group = QGroupBox("Version")
        FormLayout = QFormLayout()

        # Version actuelle
        self.VersionLabel = QLabel(AppMetadata.VERSION)
        self.VersionLabel.setProperty("class", "hint")
        FormLayout.addRow("Version actuelle:", self.VersionLabel)

        # Commit local (si repo git)
        self.CommitLabel = QLabel("")
        self.CommitLabel.setProperty("class", "hint")
        FormLayout.addRow("Commit local:", self.CommitLabel)

        # Charger le commit local
        self.LoadLocalCommit()

        Group.setLayout(FormLayout)
        return Group

    def CreateConfigGroup(self) -> QGroupBox:
        """Crée le groupe de configuration"""
        Group = QGroupBox("Configuration")
        FormLayout = QFormLayout()

        # Canal de mise à jour
        ChannelLayout = QHBoxLayout()
        self.ChannelCombo = QComboBox()
        self.ChannelCombo.addItem("release (stable)", UpdateConfig.CHANNEL_RELEASE)
        self.ChannelCombo.addItem("dev (derniers commits)", UpdateConfig.CHANNEL_DEV)
        self.ChannelCombo.currentIndexChanged.connect(self.OnChannelChanged)
        ChannelLayout.addWidget(self.ChannelCombo)
        ChannelLayout.addStretch()
        FormLayout.addRow("Canal:", ChannelLayout)

        # Checkbox auto-check
        self.AutoCheckBox = QCheckBox("Verifier les mises a jour au demarrage")
        self.AutoCheckBox.stateChanged.connect(self.OnAutoCheckChanged)
        FormLayout.addRow("", self.AutoCheckBox)

        Group.setLayout(FormLayout)
        return Group

    def CreateUpdateAvailableGroup(self) -> QGroupBox:
        """Crée le groupe de mise à jour disponible"""
        Group = QGroupBox("Mise a jour disponible")
        Layout = QVBoxLayout()

        # Version disponible
        VersionLayout = QHBoxLayout()
        VersionLayout.addWidget(QLabel("Nouvelle version:"))
        self.NewVersionLabel = QLabel("")
        self.NewVersionLabel.setStyleSheet("font-weight: bold; color: #27ae60;")
        VersionLayout.addWidget(self.NewVersionLabel)
        VersionLayout.addStretch()
        Layout.addLayout(VersionLayout)

        # Changelog
        Layout.addWidget(QLabel("Nouveautes:"))
        self.ChangelogText = QTextEdit()
        self.ChangelogText.setReadOnly(True)
        self.ChangelogText.setMaximumHeight(150)
        Layout.addWidget(self.ChangelogText)

        # Bouton appliquer
        ButtonLayout = QHBoxLayout()
        self.ApplyButton = QPushButton("Mettre a jour")
        self.ApplyButton.setProperty("class", "primary")
        self.ApplyButton.clicked.connect(self.OnApplyUpdateClicked)
        ButtonLayout.addWidget(self.ApplyButton)
        ButtonLayout.addStretch()
        Layout.addLayout(ButtonLayout)

        # Statut
        self.StatusLabel = QLabel("")
        self.StatusLabel.setProperty("class", "hint")
        Layout.addWidget(self.StatusLabel)

        Group.setLayout(Layout)
        return Group

    def LoadLocalCommit(self):
        """Charge le SHA du commit local"""
        try:
            from shared.utils.updater import GitHubClient
            Client = GitHubClient()
            Sha = Client.GetLocalCommitSha()
            if Sha:
                self.CommitLabel.setText(Sha[:8])
            else:
                self.CommitLabel.setText("N/A (pas un repo git)")
        except Exception:
            self.CommitLabel.setText("N/A")

    def GetConfigManager(self):
        """Récupère le gestionnaire de configuration du client"""
        try:
            from client.utils.performance_config import PerformanceConfigManager
            return PerformanceConfigManager()
        except Exception:
            return None

    def LoadConfiguration(self):
        """Charge la configuration depuis le fichier JSON"""
        self.IsLoading = True
        try:
            ConfigManager = self.GetConfigManager()
            if ConfigManager:
                ConfigManager.Load()

                # Canal
                Channel = ConfigManager.Get("update_channel", UpdateConfig.DEFAULT_CHANNEL)
                Index = self.ChannelCombo.findData(Channel)
                if Index >= 0:
                    self.ChannelCombo.setCurrentIndex(Index)

                # Auto-check
                AutoCheck = ConfigManager.Get("update_auto_check", False)
                self.AutoCheckBox.setChecked(AutoCheck)
        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur chargement config mise à jour: {e}")
        finally:
            self.IsLoading = False

    def OnChannelChanged(self, Index: int):
        """Appelé quand le canal change"""
        if self.IsLoading:
            return

        Channel = self.ChannelCombo.currentData()
        ConfigManager = self.GetConfigManager()
        if ConfigManager:
            ConfigManager.Load()
            ConfigManager.Set("update_channel", Channel)
            self.ShowSavedIndicator()

        # Cache le groupe de mise à jour disponible si visible
        self.UpdateAvailableGroup.setVisible(False)
        self.CurrentUpdateInfo = None

    def OnAutoCheckChanged(self, State: int):
        """Appelé quand la checkbox auto-check change"""
        if self.IsLoading:
            return

        IsChecked = State == Qt.Checked
        ConfigManager = self.GetConfigManager()
        if ConfigManager:
            ConfigManager.Load()
            ConfigManager.Set("update_auto_check", IsChecked)
            self.ShowSavedIndicator()

    def OnCheckUpdateClicked(self):
        """Appelé quand on clique sur vérifier"""
        if self.CheckWorker and self.CheckWorker.isRunning():
            return

        self.CheckButton.setEnabled(False)
        self.CheckButton.setText("Verification en cours...")
        self.UpdateAvailableGroup.setVisible(False)

        Channel = self.ChannelCombo.currentData()
        self.CheckWorker = UpdateCheckWorker(Channel)
        self.CheckWorker.Finished.connect(self.OnCheckFinished)
        self.CheckWorker.Error.connect(self.OnCheckError)
        self.CheckWorker.start()

    def OnCheckFinished(self, Info):
        """Appelé quand la vérification est terminée"""
        self.CheckButton.setEnabled(True)
        self.CheckButton.setText("Verifier maintenant")

        self.CurrentUpdateInfo = Info

        if Info.Available:
            self.NewVersionLabel.setText(Info.NewVersion)
            self.ChangelogText.setPlainText(Info.Changelog or "Pas de changelog disponible")
            self.StatusLabel.setText("")
            self.UpdateAvailableGroup.setVisible(True)
        else:
            QMessageBox.information(
                self,
                "Mise a jour",
                f"Vous utilisez deja la derniere version ({Info.CurrentVersion})"
            )

    def OnCheckError(self, ErrorMsg: str):
        """Appelé en cas d'erreur lors de la vérification"""
        self.CheckButton.setEnabled(True)
        self.CheckButton.setText("Verifier maintenant")

        if "hors ligne" in ErrorMsg.lower() or "network" in ErrorMsg.lower():
            QMessageBox.warning(
                self,
                "Erreur reseau",
                "Impossible de verifier les mises a jour.\nVerifiez votre connexion internet."
            )
        elif "rate limit" in ErrorMsg.lower():
            QMessageBox.warning(
                self,
                "Limite atteinte",
                "Limite de requetes GitHub atteinte.\nReessayez dans quelques minutes."
            )
        else:
            QMessageBox.critical(
                self,
                "Erreur",
                f"Erreur lors de la verification:\n{ErrorMsg}"
            )

    def OnApplyUpdateClicked(self):
        """Appelé quand on clique sur appliquer la mise à jour"""
        if not self.CurrentUpdateInfo or not self.CurrentUpdateInfo.Available:
            return

        if self.ApplyWorker and self.ApplyWorker.isRunning():
            return

        # Confirmation
        Reply = QMessageBox.question(
            self,
            "Confirmation",
            f"Voulez-vous mettre a jour vers la version {self.CurrentUpdateInfo.NewVersion} ?\n\n"
            "L'application sera redemarree apres la mise a jour.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if Reply != QMessageBox.Yes:
            return

        self.ApplyButton.setEnabled(False)
        self.StatusLabel.setText("Application de la mise a jour...")

        self.ApplyWorker = UpdateApplyWorker(self.CurrentUpdateInfo)
        self.ApplyWorker.Finished.connect(self.OnApplyFinished)
        self.ApplyWorker.Error.connect(self.OnApplyError)
        self.ApplyWorker.Progress.connect(self.OnApplyProgress)
        self.ApplyWorker.start()

    def OnApplyProgress(self, Message: str):
        """Appelé pour afficher la progression"""
        self.StatusLabel.setText(Message)

    def OnApplyFinished(self, Success: bool):
        """Appelé quand la mise à jour est terminée"""
        self.ApplyButton.setEnabled(True)

        if Success:
            self.StatusLabel.setText("Mise a jour terminee. Redemarrage...")
            QMessageBox.information(
                self,
                "Mise a jour terminee",
                "La mise a jour a ete appliquee avec succes.\n"
                "L'application va redemarrer."
            )
            # Redémarrage
            try:
                from shared.utils.updater import UpdateManager
                Manager = UpdateManager()
                Manager.RequestRestart()
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Redemarrage",
                    f"Impossible de redemarrer automatiquement.\n"
                    f"Veuillez relancer l'application manuellement.\n\nErreur: {e}"
                )
        else:
            self.StatusLabel.setText("Echec de la mise a jour")
            QMessageBox.critical(
                self,
                "Erreur",
                "La mise a jour a echoue.\nVerifiez les logs pour plus de details."
            )

    def OnApplyError(self, ErrorMsg: str):
        """Appelé en cas d'erreur lors de l'application"""
        self.ApplyButton.setEnabled(True)
        self.StatusLabel.setText(f"Erreur: {ErrorMsg}")
        QMessageBox.critical(
            self,
            "Erreur",
            f"Erreur lors de la mise a jour:\n{ErrorMsg}"
        )

    def ShowSavedIndicator(self):
        """Affiche l'indicateur de sauvegarde"""
        self.SavedIndicator.setText("Sauvegarde")
        self.SavedIndicatorTimer.start(2000)

    def HideSavedIndicator(self):
        """Cache l'indicateur de sauvegarde"""
        self.SavedIndicator.setText("")

    def Refresh(self):
        """Rafraîchit l'onglet (appelé périodiquement)"""
        # Pas besoin de rafraîchissement périodique pour cet onglet
        pass
