"""
Utilitaires de retry pour les opérations réseau et autres.
Supporte les fonctions synchrones et asynchrones avec délai fixe.
"""

import asyncio
import time
from functools import wraps
from typing import Callable, Type, Tuple, Optional, Any, TypeVar, Union
import logging

# Type variables pour les génériques
T = TypeVar('T')
F = TypeVar('F', bound=Callable[..., Any])


class RetryConfig:
    """Configuration par défaut pour les retries"""
    MAX_RETRIES = 5
    RETRY_DELAY = 5.0  # secondes entre chaque retry

    # Configurations spécifiques par type d'opération
    NETWORK_RETRIES = 5
    NETWORK_DELAY = 5.0

    DATABASE_RETRIES = 3
    DATABASE_DELAY = 1.0

    BATCH_SEND_RETRIES = 5
    BATCH_SEND_DELAY = 5.0


class RetryExhaustedError(Exception):
    """Exception levée quand tous les retries sont épuisés"""

    def __init__(self, attempts: int, last_exception: Exception):
        self.attempts = attempts
        self.last_exception = last_exception
        super().__init__(
            f"Tous les {attempts} essais ont échoué. Dernière erreur: {last_exception}"
        )


async def RetryAsync(
    func: Callable[[], Any],
    max_retries: int = RetryConfig.MAX_RETRIES,
    delay: float = RetryConfig.RETRY_DELAY,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    on_failure: Optional[Callable[[Exception], None]] = None,
    logger: Optional[logging.Logger] = None
) -> Any:
    """
    Exécute une fonction async avec logique de retry.

    Args:
        func: Fonction async à exécuter (sans arguments, utiliser lambda si besoin)
        max_retries: Nombre maximum de tentatives
        delay: Délai en secondes entre chaque tentative
        exceptions: Types d'exceptions à capturer et réessayer
        on_retry: Callback(attempt, exception) appelé avant chaque retry
        on_failure: Callback(exception) appelé après épuisement des retries
        logger: Logger optionnel pour les messages de debug

    Returns:
        Le résultat de func() en cas de succès

    Raises:
        RetryExhaustedError: Si tous les retries sont épuisés
        Exception: Si une exception non dans 'exceptions' est levée
    """
    last_exception: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            result = func()
            if asyncio.iscoroutine(result):
                return await result
            return result
        except exceptions as e:
            last_exception = e

            if logger:
                logger.debug(f"Tentative {attempt}/{max_retries} échouée: {e}")

            if attempt < max_retries:
                if on_retry:
                    try:
                        on_retry(attempt, e)
                    except Exception:
                        pass  # Ignorer les erreurs du callback

                await asyncio.sleep(delay)
            else:
                if on_failure:
                    try:
                        on_failure(e)
                    except Exception:
                        pass

    raise RetryExhaustedError(max_retries, last_exception)


def RetrySync(
    func: Callable[[], T],
    max_retries: int = RetryConfig.MAX_RETRIES,
    delay: float = RetryConfig.RETRY_DELAY,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    on_failure: Optional[Callable[[Exception], None]] = None,
    logger: Optional[logging.Logger] = None
) -> T:
    """
    Exécute une fonction synchrone avec logique de retry.

    Args:
        func: Fonction à exécuter (sans arguments, utiliser lambda si besoin)
        max_retries: Nombre maximum de tentatives
        delay: Délai en secondes entre chaque tentative
        exceptions: Types d'exceptions à capturer et réessayer
        on_retry: Callback(attempt, exception) appelé avant chaque retry
        on_failure: Callback(exception) appelé après épuisement des retries
        logger: Logger optionnel pour les messages de debug

    Returns:
        Le résultat de func() en cas de succès

    Raises:
        RetryExhaustedError: Si tous les retries sont épuisés
        Exception: Si une exception non dans 'exceptions' est levée
    """
    last_exception: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except exceptions as e:
            last_exception = e

            if logger:
                logger.debug(f"Tentative {attempt}/{max_retries} échouée: {e}")

            if attempt < max_retries:
                if on_retry:
                    try:
                        on_retry(attempt, e)
                    except Exception:
                        pass

                time.sleep(delay)
            else:
                if on_failure:
                    try:
                        on_failure(e)
                    except Exception:
                        pass

    raise RetryExhaustedError(max_retries, last_exception)


def WithRetry(
    max_retries: int = RetryConfig.MAX_RETRIES,
    delay: float = RetryConfig.RETRY_DELAY,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    on_failure: Optional[Callable[[Exception], None]] = None
) -> Callable[[F], F]:
    """
    Décorateur pour ajouter une logique de retry à une fonction synchrone.

    Usage:
        @WithRetry(max_retries=3, delay=2.0)
        def ma_fonction():
            ...

    Args:
        max_retries: Nombre maximum de tentatives
        delay: Délai en secondes entre chaque tentative
        exceptions: Types d'exceptions à capturer et réessayer
        on_retry: Callback(attempt, exception) appelé avant chaque retry
        on_failure: Callback(exception) appelé après épuisement des retries
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return RetrySync(
                lambda: func(*args, **kwargs),
                max_retries=max_retries,
                delay=delay,
                exceptions=exceptions,
                on_retry=on_retry,
                on_failure=on_failure
            )
        return wrapper  # type: ignore
    return decorator


def WithRetryAsync(
    max_retries: int = RetryConfig.MAX_RETRIES,
    delay: float = RetryConfig.RETRY_DELAY,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    on_failure: Optional[Callable[[Exception], None]] = None
) -> Callable[[F], F]:
    """
    Décorateur pour ajouter une logique de retry à une fonction async.

    Usage:
        @WithRetryAsync(max_retries=3, delay=2.0)
        async def ma_fonction():
            ...

    Args:
        max_retries: Nombre maximum de tentatives
        delay: Délai en secondes entre chaque tentative
        exceptions: Types d'exceptions à capturer et réessayer
        on_retry: Callback(attempt, exception) appelé avant chaque retry
        on_failure: Callback(exception) appelé après épuisement des retries
    """
    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await RetryAsync(
                lambda: func(*args, **kwargs),
                max_retries=max_retries,
                delay=delay,
                exceptions=exceptions,
                on_retry=on_retry,
                on_failure=on_failure
            )
        return wrapper  # type: ignore
    return decorator


class RetryContext:
    """
    Contexte de retry pour suivre les tentatives et statistiques.

    Usage:
        context = RetryContext(max_retries=5, delay=5.0)
        while context.ShouldRetry():
            try:
                result = do_something()
                context.Success()
                break
            except Exception as e:
                context.RecordFailure(e)
                if context.HasRetriesLeft():
                    await context.WaitForRetry()
    """

    def __init__(
        self,
        max_retries: int = RetryConfig.MAX_RETRIES,
        delay: float = RetryConfig.RETRY_DELAY,
        logger: Optional[logging.Logger] = None
    ):
        self.max_retries = max_retries
        self.delay = delay
        self.logger = logger
        self.attempt = 0
        self.failures: list = []
        self._succeeded = False

    def ShouldRetry(self) -> bool:
        """Retourne True si on doit tenter (première fois ou retry)"""
        return self.attempt < self.max_retries and not self._succeeded

    def HasRetriesLeft(self) -> bool:
        """Retourne True s'il reste des retries après l'échec actuel"""
        return self.attempt < self.max_retries

    def RecordFailure(self, exception: Exception) -> None:
        """Enregistre un échec"""
        self.attempt += 1
        self.failures.append({
            "attempt": self.attempt,
            "exception": exception,
            "timestamp": time.time()
        })
        if self.logger:
            self.logger.debug(
                f"Tentative {self.attempt}/{self.max_retries} échouée: {exception}"
            )

    def Success(self) -> None:
        """Marque le contexte comme réussi"""
        self._succeeded = True
        self.attempt += 1

    def Wait(self) -> None:
        """Attend le délai de retry (synchrone)"""
        time.sleep(self.delay)

    async def WaitAsync(self) -> None:
        """Attend le délai de retry (asynchrone)"""
        await asyncio.sleep(self.delay)

    def GetLastException(self) -> Optional[Exception]:
        """Retourne la dernière exception enregistrée"""
        if self.failures:
            return self.failures[-1]["exception"]
        return None

    def GetStats(self) -> dict:
        """Retourne les statistiques de retry"""
        return {
            "total_attempts": self.attempt,
            "max_retries": self.max_retries,
            "succeeded": self._succeeded,
            "failures_count": len(self.failures),
            "last_exception": str(self.GetLastException()) if self.failures else None
        }
