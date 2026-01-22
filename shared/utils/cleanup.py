"""
Context managers et utilitaires pour le nettoyage automatique des ressources.
Assure que les fichiers temporaires et résultats partiels sont supprimés en cas d'erreur.
"""

import os
import shutil
import logging
from contextlib import contextmanager, asynccontextmanager
from typing import Optional, List, Callable, Any
from pathlib import Path


class CleanupManager:
    """
    Gestionnaire de nettoyage qui accumule les ressources à nettoyer
    et les supprime en cas d'erreur ou sur demande explicite.
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger
        self._directories: List[str] = []
        self._files: List[str] = []
        self._callbacks: List[Callable[[], None]] = []

    def AddDirectory(self, path: str) -> None:
        """Ajoute un répertoire à nettoyer en cas d'erreur"""
        if path and path not in self._directories:
            self._directories.append(path)

    def AddFile(self, path: str) -> None:
        """Ajoute un fichier à nettoyer en cas d'erreur"""
        if path and path not in self._files:
            self._files.append(path)

    def AddCallback(self, callback: Callable[[], None]) -> None:
        """Ajoute un callback de nettoyage personnalisé"""
        self._callbacks.append(callback)

    def Cleanup(self, suppress_errors: bool = True) -> List[str]:
        """
        Effectue le nettoyage de toutes les ressources enregistrées.

        Args:
            suppress_errors: Si True, les erreurs de nettoyage sont loggées mais non propagées

        Returns:
            Liste des chemins qui n'ont pas pu être nettoyés
        """
        failed: List[str] = []

        # Nettoyer les fichiers
        for filepath in self._files:
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
                    if self.logger:
                        self.logger.debug(f"Fichier nettoyé: {filepath}")
            except Exception as e:
                failed.append(filepath)
                if self.logger:
                    self.logger.warning(f"Impossible de supprimer {filepath}: {e}")
                if not suppress_errors:
                    raise

        # Nettoyer les répertoires
        for dirpath in self._directories:
            try:
                if os.path.exists(dirpath):
                    shutil.rmtree(dirpath)
                    if self.logger:
                        self.logger.debug(f"Répertoire nettoyé: {dirpath}")
            except Exception as e:
                failed.append(dirpath)
                if self.logger:
                    self.logger.warning(f"Impossible de supprimer {dirpath}: {e}")
                if not suppress_errors:
                    raise

        # Exécuter les callbacks
        for callback in self._callbacks:
            try:
                callback()
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Erreur dans callback de nettoyage: {e}")
                if not suppress_errors:
                    raise

        # Vider les listes
        self._directories.clear()
        self._files.clear()
        self._callbacks.clear()

        return failed

    def Clear(self) -> None:
        """Vide les listes sans effectuer de nettoyage (succès de l'opération)"""
        self._directories.clear()
        self._files.clear()
        self._callbacks.clear()


@contextmanager
def CleanupOnError(
    directory: Optional[str] = None,
    file: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    cleanup_on_success: bool = False
):
    """
    Context manager synchrone qui nettoie les ressources si une exception est levée.

    Usage:
        with CleanupOnError(directory="/tmp/batch_123"):
            # ... traitement qui peut échouer ...
            # Le répertoire est automatiquement supprimé si exception

    Args:
        directory: Répertoire à supprimer en cas d'erreur
        file: Fichier à supprimer en cas d'erreur
        logger: Logger optionnel pour les messages
        cleanup_on_success: Si True, nettoie aussi en cas de succès
    """
    manager = CleanupManager(logger)

    if directory:
        manager.AddDirectory(directory)
    if file:
        manager.AddFile(file)

    try:
        yield manager
        if cleanup_on_success:
            manager.Cleanup()
        else:
            manager.Clear()
    except Exception:
        manager.Cleanup()
        raise


@asynccontextmanager
async def CleanupOnErrorAsync(
    directory: Optional[str] = None,
    file: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    cleanup_on_success: bool = False
):
    """
    Context manager asynchrone qui nettoie les ressources si une exception est levée.

    Usage:
        async with CleanupOnErrorAsync(directory="/tmp/batch_123"):
            # ... traitement async qui peut échouer ...
            # Le répertoire est automatiquement supprimé si exception

    Args:
        directory: Répertoire à supprimer en cas d'erreur
        file: Fichier à supprimer en cas d'erreur
        logger: Logger optionnel pour les messages
        cleanup_on_success: Si True, nettoie aussi en cas de succès
    """
    manager = CleanupManager(logger)

    if directory:
        manager.AddDirectory(directory)
    if file:
        manager.AddFile(file)

    try:
        yield manager
        if cleanup_on_success:
            manager.Cleanup()
        else:
            manager.Clear()
    except Exception:
        manager.Cleanup()
        raise


def CleanupDirectory(
    directory: str,
    logger: Optional[logging.Logger] = None,
    ignore_errors: bool = True
) -> bool:
    """
    Nettoie un répertoire et tout son contenu.

    Args:
        directory: Chemin du répertoire à supprimer
        logger: Logger optionnel
        ignore_errors: Si True, les erreurs sont loggées mais non propagées

    Returns:
        True si le nettoyage a réussi, False sinon
    """
    try:
        if os.path.exists(directory):
            shutil.rmtree(directory)
            if logger:
                logger.info(f"Répertoire nettoyé: {directory}")
            return True
        return True  # N'existe pas = déjà nettoyé
    except Exception as e:
        if logger:
            logger.error(f"Impossible de nettoyer {directory}: {e}")
        if not ignore_errors:
            raise
        return False


def CleanupFile(
    filepath: str,
    logger: Optional[logging.Logger] = None,
    ignore_errors: bool = True
) -> bool:
    """
    Supprime un fichier.

    Args:
        filepath: Chemin du fichier à supprimer
        logger: Logger optionnel
        ignore_errors: Si True, les erreurs sont loggées mais non propagées

    Returns:
        True si le nettoyage a réussi, False sinon
    """
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            if logger:
                logger.debug(f"Fichier supprimé: {filepath}")
            return True
        return True  # N'existe pas = déjà supprimé
    except Exception as e:
        if logger:
            logger.error(f"Impossible de supprimer {filepath}: {e}")
        if not ignore_errors:
            raise
        return False


def CleanupPartialFrames(
    directory: str,
    start_frame: int,
    end_frame: int,
    frame_pattern: str = "frame_{:08d}.png",
    logger: Optional[logging.Logger] = None
) -> int:
    """
    Supprime les frames partiels d'un batch échoué.

    Args:
        directory: Répertoire contenant les frames
        start_frame: Numéro du premier frame
        end_frame: Numéro du dernier frame
        frame_pattern: Pattern de nommage des frames
        logger: Logger optionnel

    Returns:
        Nombre de frames supprimés
    """
    deleted_count = 0

    for frame_num in range(start_frame, end_frame + 1):
        frame_name = frame_pattern.format(frame_num)
        frame_path = os.path.join(directory, frame_name)

        if os.path.exists(frame_path):
            try:
                os.remove(frame_path)
                deleted_count += 1
            except Exception as e:
                if logger:
                    logger.warning(f"Impossible de supprimer {frame_path}: {e}")

    if logger and deleted_count > 0:
        logger.info(f"Nettoyage: {deleted_count} frames supprimés dans {directory}")

    return deleted_count


def CleanupOldTempFiles(
    temp_dir: str,
    max_age_hours: float = 24.0,
    logger: Optional[logging.Logger] = None
) -> int:
    """
    Supprime les fichiers temporaires plus anciens que max_age_hours.

    Args:
        temp_dir: Répertoire temporaire à nettoyer
        max_age_hours: Âge maximum en heures
        logger: Logger optionnel

    Returns:
        Nombre d'éléments supprimés
    """
    import time

    if not os.path.exists(temp_dir):
        return 0

    deleted_count = 0
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600

    try:
        for item in os.listdir(temp_dir):
            item_path = os.path.join(temp_dir, item)
            try:
                # Vérifier l'âge du fichier/dossier
                mtime = os.path.getmtime(item_path)
                age = current_time - mtime

                if age > max_age_seconds:
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                    else:
                        os.remove(item_path)
                    deleted_count += 1

                    if logger:
                        logger.debug(f"Nettoyage ancien: {item_path}")

            except Exception as e:
                if logger:
                    logger.warning(f"Impossible de nettoyer {item_path}: {e}")

    except Exception as e:
        if logger:
            logger.error(f"Erreur lors du nettoyage de {temp_dir}: {e}")

    if logger and deleted_count > 0:
        logger.info(f"Nettoyage: {deleted_count} éléments anciens supprimés de {temp_dir}")

    return deleted_count


class TempDirectory:
    """
    Crée un répertoire temporaire qui est automatiquement supprimé.

    Usage:
        with TempDirectory("/tmp/batch_123") as temp_dir:
            # Utiliser temp_dir.path
            pass
        # Le répertoire est supprimé automatiquement
    """

    def __init__(
        self,
        path: str,
        logger: Optional[logging.Logger] = None,
        cleanup_on_error: bool = True,
        cleanup_on_success: bool = True
    ):
        self.path = path
        self.logger = logger
        self.cleanup_on_error = cleanup_on_error
        self.cleanup_on_success = cleanup_on_success
        self._created = False

    def __enter__(self) -> "TempDirectory":
        os.makedirs(self.path, exist_ok=True)
        self._created = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        should_cleanup = (
            (exc_type is not None and self.cleanup_on_error) or
            (exc_type is None and self.cleanup_on_success)
        )

        if should_cleanup and self._created:
            CleanupDirectory(self.path, self.logger)

        return False  # Ne pas supprimer l'exception

    async def __aenter__(self) -> "TempDirectory":
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self.__exit__(exc_type, exc_val, exc_tb)
