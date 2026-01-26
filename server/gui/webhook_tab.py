"""
Onglet Webhooks Discord - Configuration des notifications Discord (Serveur)
Permet de configurer l'URL du webhook et les événements à notifier
"""

import json
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QGroupBox, QFormLayout,
    QCheckBox, QScrollArea, QFrame, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QFont

from shared.utils.discord_webhook import (
    WebhookEventType, DEFAULT_WEBHOOK_MESSAGES,
    EVENT_LABELS, EVENT_CATEGORIES, DiscordWebhook
)


class WebhookTestWorker(QThread):
    """Thread pour tester le webhook sans bloquer l'UI"""
    Finished = pyqtSignal(bool, str)

    def __init__(self, Url: str):
        super().__init__()
        self.Url = Url

    def run(self):
        try:
            Webhook = DiscordWebhook(self.Url)
            Success, Message = Webhook.Test()
            self.Finished.emit(Success, Message)
        except Exception as e:
            self.Finished.emit(False, str(e))


class EventConfigWidget(QFrame):
    """Widget pour configurer un événement individuel"""

    Changed = pyqtSignal()

    def __init__(self, EventType: str, Parent=None):
        super().__init__(Parent)
        self.EventType = EventType
        self.IsLoading = False

        # Récupère les valeurs par défaut
        Default = DEFAULT_WEBHOOK_MESSAGES.get(EventType, {})
        self.DefaultTitle = Default.get("title", "")
        self.DefaultMessage = Default.get("message", "")
        self.DefaultEnabled = Default.get("enabled", False)

        self.SetupUI()

    def SetupUI(self):
        """Configure l'interface"""
        Layout = QVBoxLayout(self)
        Layout.setContentsMargins(10, 5, 10, 5)
        Layout.setSpacing(5)

        # Checkbox + Label
        HeaderLayout = QHBoxLayout()
        self.EnabledCheckbox = QCheckBox(EVENT_LABELS.get(self.EventType, self.EventType))
        self.EnabledCheckbox.setChecked(self.DefaultEnabled)
        self.EnabledCheckbox.stateChanged.connect(self.OnChanged)
        HeaderLayout.addWidget(self.EnabledCheckbox)
        HeaderLayout.addStretch()
        Layout.addLayout(HeaderLayout)

        # Champs titre et message (indentés)
        FieldsWidget = QWidget()
        FieldsLayout = QFormLayout(FieldsWidget)
        FieldsLayout.setContentsMargins(20, 0, 0, 0)

        self.TitleInput = QLineEdit()
        self.TitleInput.setPlaceholderText(self.DefaultTitle)
        self.TitleInput.setText(self.DefaultTitle)
        self.TitleInput.textChanged.connect(self.OnChanged)
        FieldsLayout.addRow("Titre:", self.TitleInput)

        self.MessageInput = QLineEdit()
        self.MessageInput.setPlaceholderText(self.DefaultMessage)
        self.MessageInput.setText(self.DefaultMessage)
        self.MessageInput.textChanged.connect(self.OnChanged)
        FieldsLayout.addRow("Message:", self.MessageInput)

        Layout.addWidget(FieldsWidget)

        # Bordure légère
        self.setFrameStyle(QFrame.StyledPanel)

    def OnChanged(self):
        """Appelé quand une valeur change"""
        if not self.IsLoading:
            self.Changed.emit()

    def GetConfig(self) -> dict:
        """Retourne la configuration de cet événement"""
        return {
            "enabled": self.EnabledCheckbox.isChecked(),
            "title": self.TitleInput.text() or self.DefaultTitle,
            "message": self.MessageInput.text() or self.DefaultMessage,
            "color": DEFAULT_WEBHOOK_MESSAGES.get(self.EventType, {}).get("color", "info")
        }

    def SetConfig(self, Config: dict):
        """Définit la configuration de cet événement"""
        self.IsLoading = True
        try:
            self.EnabledCheckbox.setChecked(Config.get("enabled", self.DefaultEnabled))
            self.TitleInput.setText(Config.get("title", self.DefaultTitle))
            self.MessageInput.setText(Config.get("message", self.DefaultMessage))
        finally:
            self.IsLoading = False


class WebhookTab(QWidget):
    """Onglet de configuration des webhooks Discord (Serveur)"""

    AUTOSAVE_DELAY_MS = 500

    def __init__(self, ParentWindow):
        super().__init__()
        self.ParentWindow = ParentWindow
        self.IsLoading = False
        self.EventWidgets = {}
        self.TestWorker = None

        # Timer pour l'auto-save
        self.AutoSaveTimer = QTimer()
        self.AutoSaveTimer.setSingleShot(True)
        self.AutoSaveTimer.timeout.connect(self.SaveConfiguration)

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

        Title = QLabel("Webhooks Discord")
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

        # Groupe Configuration
        ConfigGroup = self.CreateConfigGroup()
        Layout.addWidget(ConfigGroup)

        # Groupe Événements (scrollable)
        EventsGroup = self.CreateEventsGroup()
        Layout.addWidget(EventsGroup, 1)  # Stretch

        # Variables disponibles
        VarsLabel = QLabel(
            "Variables disponibles: {ip}, {port}, {client_id}, {video_name}, "
            "{duration}, {error}, {batch_id}, {frame_count}, {reason}"
        )
        VarsLabel.setProperty("class", "hint")
        VarsLabel.setWordWrap(True)
        Layout.addWidget(VarsLabel)

    def CreateConfigGroup(self) -> QGroupBox:
        """Crée le groupe de configuration principale"""
        Group = QGroupBox("Configuration")
        Layout = QVBoxLayout()

        # Checkbox activer
        self.EnabledCheckbox = QCheckBox("Activer les webhooks Discord")
        self.EnabledCheckbox.stateChanged.connect(self.OnEnabledChanged)
        Layout.addWidget(self.EnabledCheckbox)

        # URL du webhook
        UrlLayout = QHBoxLayout()
        UrlLayout.addWidget(QLabel("URL du webhook:"))
        self.UrlInput = QLineEdit()
        self.UrlInput.setPlaceholderText("https://discord.com/api/webhooks/...")
        self.UrlInput.textChanged.connect(self.OnUrlChanged)
        UrlLayout.addWidget(self.UrlInput, 1)
        Layout.addLayout(UrlLayout)

        # Bouton test
        ButtonLayout = QHBoxLayout()
        self.TestButton = QPushButton("Tester le webhook")
        self.TestButton.clicked.connect(self.OnTestClicked)
        ButtonLayout.addWidget(self.TestButton)
        ButtonLayout.addStretch()
        Layout.addLayout(ButtonLayout)

        Group.setLayout(Layout)
        return Group

    def CreateEventsGroup(self) -> QGroupBox:
        """Crée le groupe des événements"""
        Group = QGroupBox("Evenements")
        Layout = QVBoxLayout()

        # Zone scrollable
        ScrollArea = QScrollArea()
        ScrollArea.setWidgetResizable(True)
        ScrollArea.setFrameShape(QFrame.NoFrame)

        ScrollContent = QWidget()
        ScrollLayout = QVBoxLayout(ScrollContent)
        ScrollLayout.setSpacing(10)

        # Catégories d'événements serveur
        ServerCategories = ["server", "clients", "jobs", "batches_server"]

        for CategoryKey in ServerCategories:
            Category = EVENT_CATEGORIES.get(CategoryKey)
            if not Category:
                continue

            # Label de catégorie
            CategoryLabel = QLabel(Category["label"])
            CategoryFont = QFont()
            CategoryFont.setBold(True)
            CategoryLabel.setFont(CategoryFont)
            ScrollLayout.addWidget(CategoryLabel)

            # Événements de la catégorie
            for EventType in Category["events"]:
                Widget = EventConfigWidget(EventType)
                Widget.Changed.connect(self.OnEventChanged)
                self.EventWidgets[EventType] = Widget
                ScrollLayout.addWidget(Widget)

        ScrollLayout.addStretch()
        ScrollArea.setWidget(ScrollContent)
        Layout.addWidget(ScrollArea)

        Group.setLayout(Layout)
        return Group

    def LoadConfiguration(self):
        """Charge la configuration depuis la base de données"""
        self.IsLoading = True
        try:
            Database = self.ParentWindow.GetDatabase()
            if not Database:
                return

            # Activer
            Enabled = Database.GetParameterBool("webhook_enabled", False)
            self.EnabledCheckbox.setChecked(Enabled)

            # URL
            Url = Database.GetParameter("webhook_url", "")
            self.UrlInput.setText(Url)

            # Événements
            EventsJson = Database.GetParameter("webhook_events", "")
            if EventsJson:
                try:
                    Events = json.loads(EventsJson)
                    for EventType, Widget in self.EventWidgets.items():
                        if EventType in Events:
                            Widget.SetConfig(Events[EventType])
                except json.JSONDecodeError:
                    pass

        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur chargement config webhook: {e}")
        finally:
            self.IsLoading = False

    def SaveConfiguration(self):
        """Sauvegarde la configuration dans la base de données"""
        if self.IsLoading:
            return

        try:
            Database = self.ParentWindow.GetDatabase()
            if not Database:
                return

            # Activer
            Database.SetParameter(
                "webhook_enabled",
                "true" if self.EnabledCheckbox.isChecked() else "false",
                "Activer les webhooks Discord"
            )

            # URL
            Database.SetParameter(
                "webhook_url",
                self.UrlInput.text(),
                "URL du webhook Discord"
            )

            # Événements
            Events = {}
            for EventType, Widget in self.EventWidgets.items():
                Events[EventType] = Widget.GetConfig()

            Database.SetParameter(
                "webhook_events",
                json.dumps(Events),
                "Configuration JSON des événements webhook"
            )

            self.ShowSavedIndicator()

        except Exception as e:
            self.ParentWindow.Logger.error(f"Erreur sauvegarde config webhook: {e}")

    def OnEnabledChanged(self, State: int):
        """Appelé quand la checkbox activer change"""
        if not self.IsLoading:
            self.ScheduleSave()

    def OnUrlChanged(self, Text: str):
        """Appelé quand l'URL change"""
        if not self.IsLoading:
            self.ScheduleSave()

    def OnEventChanged(self):
        """Appelé quand un événement change"""
        if not self.IsLoading:
            self.ScheduleSave()

    def ScheduleSave(self):
        """Programme une sauvegarde avec debounce"""
        self.AutoSaveTimer.stop()
        self.AutoSaveTimer.start(self.AUTOSAVE_DELAY_MS)

    def OnTestClicked(self):
        """Appelé quand on clique sur tester"""
        Url = self.UrlInput.text().strip()
        if not Url:
            QMessageBox.warning(
                self,
                "URL manquante",
                "Veuillez entrer l'URL du webhook Discord."
            )
            return

        if self.TestWorker and self.TestWorker.isRunning():
            return

        self.TestButton.setEnabled(False)
        self.TestButton.setText("Test en cours...")

        self.TestWorker = WebhookTestWorker(Url)
        self.TestWorker.Finished.connect(self.OnTestFinished)
        self.TestWorker.start()

    def OnTestFinished(self, Success: bool, Message: str):
        """Appelé quand le test est terminé"""
        self.TestButton.setEnabled(True)
        self.TestButton.setText("Tester le webhook")

        if Success:
            QMessageBox.information(
                self,
                "Test reussi",
                "Le webhook Discord fonctionne correctement.\n"
                "Verifiez votre canal Discord."
            )
        else:
            QMessageBox.warning(
                self,
                "Test echoue",
                f"Impossible d'envoyer le webhook:\n{Message}"
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
        # Pas besoin de rafraîchissement périodique
        pass
