"""
Module d'envoi de webhooks Discord
Permet d'envoyer des notifications vers un canal Discord via webhook
"""

import json
import urllib.request
import urllib.error
from datetime import datetime
from threading import Thread
from typing import Optional, List, Dict, Any

from shared.utils.logger import GetModuleLogger
from shared.utils.constants import AppMetadata


class WebhookEventType:
    """Types d'événements webhook"""

    # Événements Serveur
    SERVER_STARTED = "server_started"
    SERVER_STOPPED = "server_stopped"
    CLIENT_CONNECTED = "client_connected"
    CLIENT_DISCONNECTED = "client_disconnected"
    JOB_STARTED = "job_started"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    BATCH_RECEIVED = "batch_received"
    BATCH_FAILED = "batch_failed"

    # Événements Client
    CONNECTED_TO_SERVER = "connected_to_server"
    DISCONNECTED_FROM_SERVER = "disconnected_from_server"
    BATCH_PROCESSING = "batch_processing"
    BATCH_COMPLETED = "batch_completed"
    BATCH_ERROR = "batch_error"
    RECONNECTING = "reconnecting"
    CRITICAL_ERROR = "critical_error"

    @classmethod
    def GetServerEvents(cls) -> List[str]:
        """Retourne la liste des événements serveur"""
        return [
            cls.SERVER_STARTED,
            cls.SERVER_STOPPED,
            cls.CLIENT_CONNECTED,
            cls.CLIENT_DISCONNECTED,
            cls.JOB_STARTED,
            cls.JOB_COMPLETED,
            cls.JOB_FAILED,
            cls.BATCH_RECEIVED,
            cls.BATCH_FAILED,
        ]

    @classmethod
    def GetClientEvents(cls) -> List[str]:
        """Retourne la liste des événements client"""
        return [
            cls.CONNECTED_TO_SERVER,
            cls.DISCONNECTED_FROM_SERVER,
            cls.BATCH_PROCESSING,
            cls.BATCH_COMPLETED,
            cls.BATCH_ERROR,
            cls.RECONNECTING,
            cls.CRITICAL_ERROR,
        ]


# Couleurs Discord par type (format décimal)
WEBHOOK_COLORS = {
    "success": 0x27ae60,   # Vert
    "error": 0xe74c3c,     # Rouge
    "warning": 0xf39c12,   # Orange
    "info": 0x3498db,      # Bleu
    "start": 0x9b59b6,     # Violet
    "stop": 0x95a5a6,      # Gris
    "client": 0x1abc9c,    # Turquoise
    "job": 0xe91e63,       # Rose
}


# Messages par défaut pour chaque événement
DEFAULT_WEBHOOK_MESSAGES = {
    # Serveur
    WebhookEventType.SERVER_STARTED: {
        "title": "Serveur demarre",
        "message": "Le serveur d'upscaling est maintenant en ligne sur {ip}:{port}",
        "color": "start",
        "enabled": False,
    },
    WebhookEventType.SERVER_STOPPED: {
        "title": "Serveur arrete",
        "message": "Le serveur d'upscaling a ete arrete",
        "color": "stop",
        "enabled": False,
    },
    WebhookEventType.CLIENT_CONNECTED: {
        "title": "Client connecte",
        "message": "Le client **{client_id}** s'est connecte depuis {ip}",
        "color": "client",
        "enabled": False,
    },
    WebhookEventType.CLIENT_DISCONNECTED: {
        "title": "Client deconnecte",
        "message": "Le client **{client_id}** s'est deconnecte. Raison: {reason}",
        "color": "warning",
        "enabled": False,
    },
    WebhookEventType.JOB_STARTED: {
        "title": "Job demarre",
        "message": "Traitement de la video **{video_name}** en cours...",
        "color": "job",
        "enabled": False,
    },
    WebhookEventType.JOB_COMPLETED: {
        "title": "Job termine",
        "message": "La video **{video_name}** a ete traitee avec succes en {duration}",
        "color": "success",
        "enabled": True,
    },
    WebhookEventType.JOB_FAILED: {
        "title": "Job echoue",
        "message": "Erreur lors du traitement de **{video_name}**: {error}",
        "color": "error",
        "enabled": True,
    },
    WebhookEventType.BATCH_RECEIVED: {
        "title": "Batch recu",
        "message": "Batch {batch_id} recu du client {client_id} ({frame_count} images)",
        "color": "info",
        "enabled": False,
    },
    WebhookEventType.BATCH_FAILED: {
        "title": "Batch echoue",
        "message": "Le batch {batch_id} a echoue: {error}",
        "color": "error",
        "enabled": True,
    },

    # Client
    WebhookEventType.CONNECTED_TO_SERVER: {
        "title": "Connecte au serveur",
        "message": "Connexion etablie avec le serveur {server_ip}:{server_port}",
        "color": "success",
        "enabled": False,
    },
    WebhookEventType.DISCONNECTED_FROM_SERVER: {
        "title": "Deconnecte du serveur",
        "message": "Deconnexion du serveur. Raison: {reason}",
        "color": "warning",
        "enabled": False,
    },
    WebhookEventType.BATCH_PROCESSING: {
        "title": "Traitement en cours",
        "message": "Traitement du batch {batch_id} ({frame_count} images)...",
        "color": "info",
        "enabled": False,
    },
    WebhookEventType.BATCH_COMPLETED: {
        "title": "Batch termine",
        "message": "Batch {batch_id} traite avec succes en {duration}",
        "color": "success",
        "enabled": False,
    },
    WebhookEventType.BATCH_ERROR: {
        "title": "Erreur de batch",
        "message": "Erreur lors du traitement du batch {batch_id}: {error}",
        "color": "error",
        "enabled": True,
    },
    WebhookEventType.RECONNECTING: {
        "title": "Reconnexion",
        "message": "Tentative de reconnexion {attempt}/{max_attempts}...",
        "color": "warning",
        "enabled": False,
    },
    WebhookEventType.CRITICAL_ERROR: {
        "title": "Erreur critique",
        "message": "Erreur critique: {error}",
        "color": "error",
        "enabled": True,
    },
}


# Labels d'affichage pour les événements (pour l'interface)
EVENT_LABELS = {
    # Serveur
    WebhookEventType.SERVER_STARTED: "Demarrage du serveur",
    WebhookEventType.SERVER_STOPPED: "Arret du serveur",
    WebhookEventType.CLIENT_CONNECTED: "Connexion d'un client",
    WebhookEventType.CLIENT_DISCONNECTED: "Deconnexion d'un client",
    WebhookEventType.JOB_STARTED: "Debut d'un job",
    WebhookEventType.JOB_COMPLETED: "Job termine",
    WebhookEventType.JOB_FAILED: "Job echoue",
    WebhookEventType.BATCH_RECEIVED: "Batch recu",
    WebhookEventType.BATCH_FAILED: "Batch echoue",

    # Client
    WebhookEventType.CONNECTED_TO_SERVER: "Connexion au serveur",
    WebhookEventType.DISCONNECTED_FROM_SERVER: "Deconnexion du serveur",
    WebhookEventType.BATCH_PROCESSING: "Traitement d'un batch",
    WebhookEventType.BATCH_COMPLETED: "Batch termine",
    WebhookEventType.BATCH_ERROR: "Erreur de batch",
    WebhookEventType.RECONNECTING: "Tentative de reconnexion",
    WebhookEventType.CRITICAL_ERROR: "Erreur critique",
}


# Catégories d'événements pour l'interface
EVENT_CATEGORIES = {
    "server": {
        "label": "Serveur",
        "events": [
            WebhookEventType.SERVER_STARTED,
            WebhookEventType.SERVER_STOPPED,
        ]
    },
    "clients": {
        "label": "Clients",
        "events": [
            WebhookEventType.CLIENT_CONNECTED,
            WebhookEventType.CLIENT_DISCONNECTED,
        ]
    },
    "jobs": {
        "label": "Jobs",
        "events": [
            WebhookEventType.JOB_STARTED,
            WebhookEventType.JOB_COMPLETED,
            WebhookEventType.JOB_FAILED,
        ]
    },
    "batches_server": {
        "label": "Batches",
        "events": [
            WebhookEventType.BATCH_RECEIVED,
            WebhookEventType.BATCH_FAILED,
        ]
    },
    "connection": {
        "label": "Connexion",
        "events": [
            WebhookEventType.CONNECTED_TO_SERVER,
            WebhookEventType.DISCONNECTED_FROM_SERVER,
            WebhookEventType.RECONNECTING,
        ]
    },
    "batches_client": {
        "label": "Batches",
        "events": [
            WebhookEventType.BATCH_PROCESSING,
            WebhookEventType.BATCH_COMPLETED,
            WebhookEventType.BATCH_ERROR,
        ]
    },
    "errors": {
        "label": "Erreurs",
        "events": [
            WebhookEventType.CRITICAL_ERROR,
        ]
    },
}


class DiscordWebhook:
    """Client pour envoyer des webhooks Discord"""

    TIMEOUT = 10  # Timeout en secondes

    def __init__(self, WebhookUrl: str):
        """
        Initialise le client webhook Discord

        Args:
            WebhookUrl: URL du webhook Discord
        """
        self.WebhookUrl = WebhookUrl
        self.Logger = GetModuleLogger("DiscordWebhook")

    def Send(
        self,
        Title: str,
        Message: str,
        Color: int = None,
        Fields: List[Dict[str, Any]] = None,
        Footer: str = None
    ) -> bool:
        """
        Envoie un message embed Discord

        Args:
            Title: Titre de l'embed
            Message: Description/contenu du message
            Color: Couleur de la barre latérale (format décimal)
            Fields: Liste de champs additionnels [{name, value, inline}]
            Footer: Texte du footer

        Returns:
            True si envoi réussi
        """
        if not self.WebhookUrl:
            self.Logger.warning("URL webhook non configurée")
            return False

        # Construit l'embed
        Embed = {
            "title": Title,
            "description": Message,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

        if Color is not None:
            Embed["color"] = Color

        if Fields:
            Embed["fields"] = Fields

        # Footer avec version
        FooterText = Footer or f"UpscalingByNetwork {AppMetadata.VERSION}"
        Embed["footer"] = {"text": FooterText}

        # Payload complet
        Payload = {"embeds": [Embed]}

        return self._SendPayload(Payload)

    def SendSimple(self, Content: str) -> bool:
        """
        Envoie un message simple (sans embed)

        Args:
            Content: Contenu du message

        Returns:
            True si envoi réussi
        """
        if not self.WebhookUrl:
            return False

        Payload = {"content": Content}
        return self._SendPayload(Payload)

    def SendAsync(
        self,
        Title: str,
        Message: str,
        Color: int = None,
        Fields: List[Dict[str, Any]] = None,
        Footer: str = None
    ):
        """
        Envoie un message de manière asynchrone (non-bloquant)

        Args:
            Mêmes que Send()
        """
        Thread(
            target=self.Send,
            args=(Title, Message, Color, Fields, Footer),
            daemon=True
        ).start()

    def Test(self) -> tuple:
        """
        Teste la connexion au webhook

        Returns:
            Tuple (success: bool, message: str)
        """
        if not self.WebhookUrl:
            return False, "URL webhook non configurée"

        Success = self.Send(
            Title="Test de webhook",
            Message="Ce message confirme que le webhook Discord fonctionne correctement.",
            Color=WEBHOOK_COLORS["info"],
            Footer="Test depuis UpscalingByNetwork"
        )

        if Success:
            return True, "Webhook envoyé avec succès"
        else:
            return False, "Échec de l'envoi du webhook"

    def _SendPayload(self, Payload: dict) -> bool:
        """
        Envoie un payload JSON au webhook Discord

        Args:
            Payload: Dictionnaire à envoyer en JSON

        Returns:
            True si envoi réussi
        """
        try:
            Data = json.dumps(Payload).encode("utf-8")

            Request = urllib.request.Request(
                self.WebhookUrl,
                data=Data,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": f"UpscalingByNetwork/{AppMetadata.VERSION}"
                },
                method="POST"
            )

            with urllib.request.urlopen(Request, timeout=self.TIMEOUT) as Response:
                # Discord retourne 204 No Content en cas de succès
                if Response.status in (200, 204):
                    self.Logger.debug("Webhook envoyé avec succès")
                    return True
                else:
                    self.Logger.warning(f"Webhook: réponse inattendue {Response.status}")
                    return False

        except urllib.error.HTTPError as e:
            if e.code == 429:
                self.Logger.warning("Webhook: rate limit atteint")
            else:
                self.Logger.error(f"Webhook HTTP error {e.code}: {e.reason}")
            return False

        except urllib.error.URLError as e:
            self.Logger.error(f"Webhook URL error: {e.reason}")
            return False

        except Exception as e:
            self.Logger.error(f"Webhook error: {e}")
            return False


def GetColorForEvent(EventType: str) -> int:
    """
    Retourne la couleur Discord pour un type d'événement

    Args:
        EventType: Type d'événement

    Returns:
        Couleur en format décimal
    """
    Default = DEFAULT_WEBHOOK_MESSAGES.get(EventType, {})
    ColorName = Default.get("color", "info")
    return WEBHOOK_COLORS.get(ColorName, WEBHOOK_COLORS["info"])
