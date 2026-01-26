"""
Gestionnaire centralisé des webhooks Discord
Gère la configuration et le déclenchement des webhooks
"""

import json
from typing import Optional, Dict, Any, Callable

from shared.utils.logger import GetModuleLogger
from shared.utils.discord_webhook import (
    DiscordWebhook,
    DEFAULT_WEBHOOK_MESSAGES,
    WEBHOOK_COLORS,
    GetColorForEvent
)


class WebhookManager:
    """Gestionnaire de webhooks avec configuration"""

    def __init__(self, ConfigGetter: Callable[[], Dict[str, Any]]):
        """
        Initialise le gestionnaire de webhooks

        Args:
            ConfigGetter: Fonction qui retourne la configuration webhook
                          Doit retourner un dict avec:
                          - webhook_enabled: bool
                          - webhook_url: str
                          - webhook_events: dict ou str (JSON)
        """
        self.GetConfig = ConfigGetter
        self.Logger = GetModuleLogger("WebhookManager")
        self._Webhook = None
        self._LastUrl = None

    def _GetWebhook(self) -> Optional[DiscordWebhook]:
        """
        Retourne l'instance du webhook (avec cache)

        Returns:
            Instance DiscordWebhook ou None si non configuré
        """
        Config = self.GetConfig()
        Url = Config.get("webhook_url", "")

        if not Url:
            return None

        # Recrée le webhook si l'URL a changé
        if Url != self._LastUrl:
            self._Webhook = DiscordWebhook(Url)
            self._LastUrl = Url

        return self._Webhook

    def IsEnabled(self) -> bool:
        """
        Vérifie si les webhooks sont activés globalement

        Returns:
            True si activé
        """
        Config = self.GetConfig()
        Enabled = Config.get("webhook_enabled", False)

        # Gère le cas où c'est une string (depuis la DB)
        if isinstance(Enabled, str):
            return Enabled.lower() in ("true", "1", "yes", "oui")

        return bool(Enabled)

    def GetWebhookUrl(self) -> str:
        """
        Retourne l'URL du webhook

        Returns:
            URL ou chaîne vide
        """
        Config = self.GetConfig()
        return Config.get("webhook_url", "")

    def GetEventsConfig(self) -> Dict[str, Dict[str, Any]]:
        """
        Retourne la configuration de tous les événements

        Returns:
            Dictionnaire {event_type: {enabled, title, message, color}}
        """
        Config = self.GetConfig()
        Events = Config.get("webhook_events", {})

        # Parse JSON si c'est une string
        if isinstance(Events, str):
            if Events:
                try:
                    Events = json.loads(Events)
                except json.JSONDecodeError:
                    Events = {}
            else:
                Events = {}

        # Fusionne avec les valeurs par défaut
        Result = {}
        for EventType, Default in DEFAULT_WEBHOOK_MESSAGES.items():
            EventConfig = Events.get(EventType, {})
            Result[EventType] = {
                "enabled": EventConfig.get("enabled", Default.get("enabled", False)),
                "title": EventConfig.get("title", Default.get("title", "")),
                "message": EventConfig.get("message", Default.get("message", "")),
                "color": EventConfig.get("color", Default.get("color", "info")),
            }

        return Result

    def IsEventEnabled(self, EventType: str) -> bool:
        """
        Vérifie si un événement spécifique est activé

        Args:
            EventType: Type d'événement

        Returns:
            True si l'événement est activé
        """
        if not self.IsEnabled():
            return False

        Events = self.GetEventsConfig()
        EventConfig = Events.get(EventType, {})
        return EventConfig.get("enabled", False)

    def GetEventConfig(self, EventType: str) -> Dict[str, Any]:
        """
        Récupère la configuration d'un événement spécifique

        Args:
            EventType: Type d'événement

        Returns:
            Dict avec enabled, title, message, color
        """
        Events = self.GetEventsConfig()
        return Events.get(EventType, DEFAULT_WEBHOOK_MESSAGES.get(EventType, {}))

    def Trigger(self, EventType: str, **Variables) -> bool:
        """
        Déclenche un webhook pour un événement si activé

        Args:
            EventType: Type d'événement
            **Variables: Variables à remplacer dans le message
                        Ex: video_name="test.mp4", duration="5m30s"

        Returns:
            True si le webhook a été envoyé (ou ignoré car désactivé)
        """
        # Vérifie si activé
        if not self.IsEventEnabled(EventType):
            self.Logger.debug(f"Webhook ignoré (désactivé): {EventType}")
            return True

        # Récupère le webhook
        Webhook = self._GetWebhook()
        if not Webhook:
            self.Logger.warning(f"Webhook non configuré pour: {EventType}")
            return False

        # Récupère la config de l'événement
        EventConfig = self.GetEventConfig(EventType)

        # Remplace les variables dans le titre et le message
        Title = self._ReplaceVariables(EventConfig.get("title", ""), Variables)
        Message = self._ReplaceVariables(EventConfig.get("message", ""), Variables)

        # Récupère la couleur
        ColorName = EventConfig.get("color", "info")
        Color = WEBHOOK_COLORS.get(ColorName, WEBHOOK_COLORS["info"])

        # Envoie de manière asynchrone
        self.Logger.debug(f"Déclenchement webhook: {EventType}")
        Webhook.SendAsync(Title, Message, Color)

        return True

    def TriggerSync(self, EventType: str, **Variables) -> bool:
        """
        Déclenche un webhook de manière synchrone (bloquant)

        Args:
            Mêmes que Trigger()

        Returns:
            True si envoi réussi
        """
        if not self.IsEventEnabled(EventType):
            return True

        Webhook = self._GetWebhook()
        if not Webhook:
            return False

        EventConfig = self.GetEventConfig(EventType)

        Title = self._ReplaceVariables(EventConfig.get("title", ""), Variables)
        Message = self._ReplaceVariables(EventConfig.get("message", ""), Variables)

        ColorName = EventConfig.get("color", "info")
        Color = WEBHOOK_COLORS.get(ColorName, WEBHOOK_COLORS["info"])

        return Webhook.Send(Title, Message, Color)

    def Test(self) -> tuple:
        """
        Teste la connexion au webhook

        Returns:
            Tuple (success: bool, message: str)
        """
        if not self.IsEnabled():
            return False, "Les webhooks sont désactivés"

        Webhook = self._GetWebhook()
        if not Webhook:
            return False, "URL du webhook non configurée"

        return Webhook.Test()

    def _ReplaceVariables(self, Template: str, Variables: Dict[str, Any]) -> str:
        """
        Remplace les variables {var} dans un template

        Args:
            Template: Chaîne avec placeholders {var}
            Variables: Dictionnaire de variables

        Returns:
            Chaîne avec variables remplacées
        """
        Result = Template
        for Key, Value in Variables.items():
            Placeholder = "{" + Key + "}"
            Result = Result.replace(Placeholder, str(Value))
        return Result


# Instance globale pour le serveur (initialisée plus tard)
_ServerWebhookManager: Optional[WebhookManager] = None

# Instance globale pour le client (initialisée plus tard)
_ClientWebhookManager: Optional[WebhookManager] = None


def InitServerWebhookManager(ConfigGetter: Callable[[], Dict[str, Any]]):
    """
    Initialise le gestionnaire de webhooks du serveur

    Args:
        ConfigGetter: Fonction retournant la config webhook
    """
    global _ServerWebhookManager
    _ServerWebhookManager = WebhookManager(ConfigGetter)


def InitClientWebhookManager(ConfigGetter: Callable[[], Dict[str, Any]]):
    """
    Initialise le gestionnaire de webhooks du client

    Args:
        ConfigGetter: Fonction retournant la config webhook
    """
    global _ClientWebhookManager
    _ClientWebhookManager = WebhookManager(ConfigGetter)


def GetServerWebhookManager() -> Optional[WebhookManager]:
    """Retourne le gestionnaire de webhooks du serveur"""
    return _ServerWebhookManager


def GetClientWebhookManager() -> Optional[WebhookManager]:
    """Retourne le gestionnaire de webhooks du client"""
    return _ClientWebhookManager


def TriggerServerWebhook(EventType: str, **Variables) -> bool:
    """
    Raccourci pour déclencher un webhook serveur

    Args:
        EventType: Type d'événement
        **Variables: Variables à remplacer

    Returns:
        True si succès ou ignoré
    """
    if _ServerWebhookManager:
        return _ServerWebhookManager.Trigger(EventType, **Variables)
    return True


def TriggerClientWebhook(EventType: str, **Variables) -> bool:
    """
    Raccourci pour déclencher un webhook client

    Args:
        EventType: Type d'événement
        **Variables: Variables à remplacer

    Returns:
        True si succès ou ignoré
    """
    if _ClientWebhookManager:
        return _ClientWebhookManager.Trigger(EventType, **Variables)
    return True
