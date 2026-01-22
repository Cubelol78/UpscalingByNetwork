"""
Système d'événements d'erreur avec callbacks.
Permet aux composants d'enregistrer des callbacks pour des types d'erreurs spécifiques.
"""

import asyncio
import threading
from enum import Enum
from typing import Callable, Dict, List, Any, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime


class ErrorSeverity(Enum):
    """Niveaux de sévérité des erreurs"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Catégories d'erreurs"""
    NETWORK = "network"
    PROCESSING = "processing"
    DATABASE = "database"
    ENCRYPTION = "encryption"
    CLEANUP = "cleanup"
    BATCH = "batch"
    CLIENT = "client"


@dataclass
class ErrorEvent:
    """Représente un événement d'erreur"""
    timestamp: datetime
    category: ErrorCategory
    severity: ErrorSeverity
    exception: Exception
    context: Dict[str, Any]
    source_module: str
    recoverable: bool
    suggested_action: str
    message: str = ""

    def __post_init__(self):
        if not self.message:
            self.message = str(self.exception)

    def ToDict(self) -> Dict[str, Any]:
        """Convertit l'événement en dictionnaire pour sérialisation"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "category": self.category.value,
            "severity": self.severity.value,
            "exception_type": type(self.exception).__name__,
            "message": self.message,
            "context": self.context,
            "source_module": self.source_module,
            "recoverable": self.recoverable,
            "suggested_action": self.suggested_action
        }


# Type pour les callbacks
ErrorCallback = Callable[[ErrorEvent], None]
AsyncErrorCallback = Callable[[ErrorEvent], Any]  # Coroutine


class ErrorEventManager:
    """
    Gestionnaire singleton pour les événements d'erreur.
    Thread-safe et supporte les callbacks synchrones et asynchrones.
    """
    _instance: Optional["ErrorEventManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ErrorEventManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialize()
            return cls._instance

    def _initialize(self):
        """Initialise les structures de données"""
        self._callbacks: Dict[ErrorCategory, List[ErrorCallback]] = {
            category: [] for category in ErrorCategory
        }
        self._async_callbacks: Dict[ErrorCategory, List[AsyncErrorCallback]] = {
            category: [] for category in ErrorCategory
        }
        self._global_callbacks: List[ErrorCallback] = []
        self._global_async_callbacks: List[AsyncErrorCallback] = []
        self._severity_callbacks: Dict[ErrorSeverity, List[ErrorCallback]] = {
            severity: [] for severity in ErrorSeverity
        }
        self._event_history: List[ErrorEvent] = []
        self._max_history_size = 1000
        self._callbacks_lock = threading.Lock()

    def RegisterCallback(
        self,
        callback: ErrorCallback,
        category: Optional[ErrorCategory] = None,
        severity: Optional[ErrorSeverity] = None
    ) -> None:
        """
        Enregistre un callback synchrone pour une catégorie ou sévérité spécifique.

        Args:
            callback: Fonction appelée avec ErrorEvent
            category: Catégorie d'erreur (None = toutes)
            severity: Sévérité minimale (None = toutes)
        """
        with self._callbacks_lock:
            if category is not None:
                self._callbacks[category].append(callback)
            elif severity is not None:
                self._severity_callbacks[severity].append(callback)
            else:
                self._global_callbacks.append(callback)

    def RegisterAsyncCallback(
        self,
        callback: AsyncErrorCallback,
        category: Optional[ErrorCategory] = None
    ) -> None:
        """
        Enregistre un callback asynchrone pour une catégorie spécifique.

        Args:
            callback: Coroutine appelée avec ErrorEvent
            category: Catégorie d'erreur (None = toutes)
        """
        with self._callbacks_lock:
            if category is not None:
                self._async_callbacks[category].append(callback)
            else:
                self._global_async_callbacks.append(callback)

    def UnregisterCallback(
        self,
        callback: Union[ErrorCallback, AsyncErrorCallback],
        category: Optional[ErrorCategory] = None
    ) -> bool:
        """
        Désenregistre un callback.

        Returns:
            True si le callback a été trouvé et supprimé
        """
        with self._callbacks_lock:
            removed = False

            if category is not None:
                if callback in self._callbacks[category]:
                    self._callbacks[category].remove(callback)
                    removed = True
                if callback in self._async_callbacks[category]:
                    self._async_callbacks[category].remove(callback)
                    removed = True
            else:
                if callback in self._global_callbacks:
                    self._global_callbacks.remove(callback)
                    removed = True
                if callback in self._global_async_callbacks:
                    self._global_async_callbacks.remove(callback)
                    removed = True

            return removed

    def Emit(self, event: ErrorEvent) -> None:
        """
        Émet un événement d'erreur aux callbacks synchrones.

        Args:
            event: Événement d'erreur à émettre
        """
        # Ajouter à l'historique
        self._add_to_history(event)

        # Récupérer les callbacks de manière thread-safe
        with self._callbacks_lock:
            category_callbacks = list(self._callbacks.get(event.category, []))
            severity_callbacks = list(self._severity_callbacks.get(event.severity, []))
            global_callbacks = list(self._global_callbacks)

        # Appeler tous les callbacks pertinents
        all_callbacks = category_callbacks + severity_callbacks + global_callbacks

        for callback in all_callbacks:
            try:
                callback(event)
            except Exception as e:
                # Ne pas propager les erreurs des callbacks
                # pour éviter les boucles infinies
                pass

    async def EmitAsync(self, event: ErrorEvent) -> None:
        """
        Émet un événement d'erreur aux callbacks asynchrones et synchrones.

        Args:
            event: Événement d'erreur à émettre
        """
        # Ajouter à l'historique
        self._add_to_history(event)

        # Récupérer les callbacks de manière thread-safe
        with self._callbacks_lock:
            category_callbacks = list(self._callbacks.get(event.category, []))
            category_async_callbacks = list(self._async_callbacks.get(event.category, []))
            global_callbacks = list(self._global_callbacks)
            global_async_callbacks = list(self._global_async_callbacks)

        # Appeler les callbacks synchrones
        for callback in category_callbacks + global_callbacks:
            try:
                callback(event)
            except Exception:
                pass

        # Appeler les callbacks asynchrones
        for callback in category_async_callbacks + global_async_callbacks:
            try:
                result = callback(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass

    def _add_to_history(self, event: ErrorEvent) -> None:
        """Ajoute un événement à l'historique avec limite de taille"""
        self._event_history.append(event)
        if len(self._event_history) > self._max_history_size:
            self._event_history = self._event_history[-self._max_history_size:]

    def GetHistory(
        self,
        category: Optional[ErrorCategory] = None,
        severity: Optional[ErrorSeverity] = None,
        limit: int = 100
    ) -> List[ErrorEvent]:
        """
        Récupère l'historique des événements avec filtres optionnels.

        Args:
            category: Filtrer par catégorie
            severity: Filtrer par sévérité minimale
            limit: Nombre maximum d'événements à retourner

        Returns:
            Liste des événements correspondants (plus récents en premier)
        """
        events = self._event_history.copy()

        if category is not None:
            events = [e for e in events if e.category == category]

        if severity is not None:
            severity_order = list(ErrorSeverity)
            min_index = severity_order.index(severity)
            events = [e for e in events if severity_order.index(e.severity) >= min_index]

        # Retourner les plus récents en premier
        return list(reversed(events[-limit:]))

    def ClearHistory(self) -> None:
        """Vide l'historique des événements"""
        self._event_history.clear()

    def SetMaxHistorySize(self, size: int) -> None:
        """Définit la taille maximale de l'historique"""
        self._max_history_size = max(1, size)


# Instance singleton globale
_error_manager: Optional[ErrorEventManager] = None


def GetErrorEventManager() -> ErrorEventManager:
    """Retourne l'instance singleton du gestionnaire d'erreurs"""
    global _error_manager
    if _error_manager is None:
        _error_manager = ErrorEventManager()
    return _error_manager


def EmitError(
    exception: Exception,
    category: ErrorCategory,
    severity: ErrorSeverity,
    source_module: str,
    context: Optional[Dict[str, Any]] = None,
    recoverable: bool = False,
    suggested_action: str = "abort"
) -> ErrorEvent:
    """
    Helper pour émettre rapidement un événement d'erreur.

    Args:
        exception: L'exception à reporter
        category: Catégorie de l'erreur
        severity: Sévérité de l'erreur
        source_module: Module source de l'erreur
        context: Contexte additionnel (client_id, batch_id, etc.)
        recoverable: Si l'erreur est récupérable
        suggested_action: Action suggérée (retry, reassign, abort, cleanup)

    Returns:
        L'événement créé et émis
    """
    event = ErrorEvent(
        timestamp=datetime.now(),
        category=category,
        severity=severity,
        exception=exception,
        context=context or {},
        source_module=source_module,
        recoverable=recoverable,
        suggested_action=suggested_action
    )

    GetErrorEventManager().Emit(event)
    return event


async def EmitErrorAsync(
    exception: Exception,
    category: ErrorCategory,
    severity: ErrorSeverity,
    source_module: str,
    context: Optional[Dict[str, Any]] = None,
    recoverable: bool = False,
    suggested_action: str = "abort"
) -> ErrorEvent:
    """
    Helper async pour émettre rapidement un événement d'erreur.

    Args:
        Mêmes paramètres que EmitError

    Returns:
        L'événement créé et émis
    """
    event = ErrorEvent(
        timestamp=datetime.now(),
        category=category,
        severity=severity,
        exception=exception,
        context=context or {},
        source_module=source_module,
        recoverable=recoverable,
        suggested_action=suggested_action
    )

    await GetErrorEventManager().EmitAsync(event)
    return event
