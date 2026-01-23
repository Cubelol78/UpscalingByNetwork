"""
Validation et vérification de chemins pour les répertoires de travail.
Assure que les chemins sont accessibles, utilisables et ont les permissions nécessaires.
"""

import os
import stat
import tempfile
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class PathValidationResult:
    """Résultat de la validation d'un chemin"""
    is_valid: bool
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    suggested_fix: Optional[str] = None


class PathValidationError:
    """Codes d'erreur pour la validation de chemins"""
    PATH_EMPTY = "path_empty"
    PATH_TOO_LONG = "path_too_long"
    PATH_INVALID_CHARS = "path_invalid_chars"
    PATH_IS_FILE = "path_is_file"
    PATH_NOT_ABSOLUTE = "path_not_absolute"
    PERMISSION_DENIED = "permission_denied"
    DISK_FULL = "disk_full"
    DISK_READ_ONLY = "disk_read_only"
    PARENT_NOT_EXISTS = "parent_not_exists"
    PARENT_NOT_ACCESSIBLE = "parent_not_accessible"
    UNKNOWN_ERROR = "unknown_error"


def ValidateWorkDirectory(path: str, create_if_missing: bool = False) -> PathValidationResult:
    """
    Valide un chemin de répertoire de travail.

    Args:
        path: Chemin à valider
        create_if_missing: Si True, tente de créer le répertoire s'il n'existe pas

    Returns:
        PathValidationResult avec le résultat de la validation
    """
    # Vérification 1: Chemin non vide
    if not path or not path.strip():
        return PathValidationResult(
            is_valid=False,
            error_code=PathValidationError.PATH_EMPTY,
            error_message="Le chemin est vide",
            suggested_fix="Spécifiez un chemin valide ou utilisez le répertoire par défaut"
        )

    path = path.strip()

    # Vérification 2: Longueur maximale (Windows: 260, Linux: 4096)
    max_length = 260 if os.name == 'nt' else 4096
    if len(path) > max_length:
        return PathValidationResult(
            is_valid=False,
            error_code=PathValidationError.PATH_TOO_LONG,
            error_message=f"Le chemin dépasse la longueur maximale ({len(path)}/{max_length} caractères)",
            suggested_fix="Utilisez un chemin plus court"
        )

    # Vérification 3: Caractères invalides
    invalid_chars = _GetInvalidPathChars()
    if any(char in path for char in invalid_chars):
        found_chars = [char for char in invalid_chars if char in path]
        return PathValidationResult(
            is_valid=False,
            error_code=PathValidationError.PATH_INVALID_CHARS,
            error_message=f"Le chemin contient des caractères invalides: {', '.join(repr(c) for c in found_chars)}",
            suggested_fix="Supprimez les caractères spéciaux du chemin"
        )

    # Vérification 4: Chemin absolu recommandé
    if not os.path.isabs(path):
        return PathValidationResult(
            is_valid=False,
            error_code=PathValidationError.PATH_NOT_ABSOLUTE,
            error_message="Le chemin doit être absolu (commencer par / ou une lettre de lecteur)",
            suggested_fix=f"Utilisez le chemin absolu: {os.path.abspath(path)}"
        )

    # Vérification 5: Le chemin existe-t-il déjà ?
    if os.path.exists(path):
        # Vérification 5a: Est-ce un fichier ?
        if os.path.isfile(path):
            return PathValidationResult(
                is_valid=False,
                error_code=PathValidationError.PATH_IS_FILE,
                error_message="Le chemin pointe vers un fichier, pas un répertoire",
                suggested_fix="Choisissez un répertoire ou supprimez le fichier existant"
            )

        # Vérification 5b: Permissions de lecture
        if not os.access(path, os.R_OK):
            return PathValidationResult(
                is_valid=False,
                error_code=PathValidationError.PERMISSION_DENIED,
                error_message="Vous n'avez pas la permission de lire ce répertoire",
                suggested_fix="Changez les permissions ou choisissez un autre répertoire"
            )

        # Vérification 5c: Permissions d'écriture
        if not os.access(path, os.W_OK):
            # Vérifie si le système de fichiers est en lecture seule
            if _IsReadOnlyFilesystem(path):
                return PathValidationResult(
                    is_valid=False,
                    error_code=PathValidationError.DISK_READ_ONLY,
                    error_message="Le système de fichiers est en lecture seule",
                    suggested_fix="Choisissez un répertoire sur un disque accessible en écriture"
                )
            else:
                return PathValidationResult(
                    is_valid=False,
                    error_code=PathValidationError.PERMISSION_DENIED,
                    error_message="Vous n'avez pas la permission d'écrire dans ce répertoire",
                    suggested_fix="Changez les permissions ou choisissez un autre répertoire"
                )

        # Vérification 5d: Permissions d'exécution (nécessaire pour lister le contenu)
        if not os.access(path, os.X_OK):
            return PathValidationResult(
                is_valid=False,
                error_code=PathValidationError.PERMISSION_DENIED,
                error_message="Vous n'avez pas la permission d'accéder à ce répertoire",
                suggested_fix="Changez les permissions ou choisissez un autre répertoire"
            )

        # Vérification 5e: Espace disque disponible
        disk_space_result = _CheckDiskSpace(path)
        if not disk_space_result.is_valid:
            return disk_space_result

        # Répertoire existe et est accessible
        return PathValidationResult(is_valid=True)

    # Le répertoire n'existe pas
    if not create_if_missing:
        # Vérification 6: Le répertoire parent existe-t-il ?
        parent_dir = os.path.dirname(path)
        if not parent_dir:
            parent_dir = "/"

        if not os.path.exists(parent_dir):
            return PathValidationResult(
                is_valid=False,
                error_code=PathValidationError.PARENT_NOT_EXISTS,
                error_message=f"Le répertoire parent n'existe pas: {parent_dir}",
                suggested_fix="Créez d'abord le répertoire parent ou choisissez un autre emplacement"
            )

        # Vérification 7: Peut-on accéder au parent ?
        if not os.access(parent_dir, os.W_OK):
            return PathValidationResult(
                is_valid=False,
                error_code=PathValidationError.PARENT_NOT_ACCESSIBLE,
                error_message=f"Pas de permission d'écriture dans le répertoire parent: {parent_dir}",
                suggested_fix="Changez les permissions ou choisissez un autre répertoire"
            )

        return PathValidationResult(is_valid=True)

    # Tentative de création
    try:
        os.makedirs(path, exist_ok=True)

        # Vérifie que le répertoire est bien créé et accessible
        if not os.path.isdir(path):
            return PathValidationResult(
                is_valid=False,
                error_code=PathValidationError.UNKNOWN_ERROR,
                error_message="Le répertoire a été créé mais n'est pas accessible",
                suggested_fix="Vérifiez les permissions du système de fichiers"
            )

        # Teste l'écriture avec un fichier temporaire
        test_result = _TestWriteAccess(path)
        if not test_result.is_valid:
            # Cleanup: supprime le répertoire créé si l'accès en écriture échoue
            try:
                os.rmdir(path)
            except Exception:
                pass
            return test_result

        return PathValidationResult(is_valid=True)

    except PermissionError as e:
        return PathValidationResult(
            is_valid=False,
            error_code=PathValidationError.PERMISSION_DENIED,
            error_message=f"Permission refusée lors de la création: {e}",
            suggested_fix="Vérifiez vos permissions ou choisissez un autre répertoire"
        )
    except OSError as e:
        if e.errno == 28:  # ENOSPC - No space left on device
            return PathValidationResult(
                is_valid=False,
                error_code=PathValidationError.DISK_FULL,
                error_message="Espace disque insuffisant",
                suggested_fix="Libérez de l'espace disque ou choisissez un autre emplacement"
            )
        elif e.errno == 30:  # EROFS - Read-only file system
            return PathValidationResult(
                is_valid=False,
                error_code=PathValidationError.DISK_READ_ONLY,
                error_message="Le système de fichiers est en lecture seule",
                suggested_fix="Choisissez un emplacement sur un disque accessible en écriture"
            )
        else:
            return PathValidationResult(
                is_valid=False,
                error_code=PathValidationError.UNKNOWN_ERROR,
                error_message=f"Erreur lors de la création: {e}",
                suggested_fix="Vérifiez le chemin et les permissions"
            )
    except Exception as e:
        return PathValidationResult(
            is_valid=False,
            error_code=PathValidationError.UNKNOWN_ERROR,
            error_message=f"Erreur inattendue: {e}",
            suggested_fix="Choisissez un autre répertoire"
        )


def _GetInvalidPathChars() -> str:
    """Retourne les caractères invalides pour un chemin"""
    if os.name == 'nt':  # Windows
        return '<>:"|?*\x00'
    else:  # Unix/Linux
        return '\x00'


def _IsReadOnlyFilesystem(path: str) -> bool:
    """Vérifie si le système de fichiers est en lecture seule"""
    try:
        # Tente de récupérer les stats du système de fichiers
        st = os.statvfs(path)
        # ST_RDONLY flag sur Unix
        return bool(st.f_flag & os.ST_RDONLY) if hasattr(os, 'ST_RDONLY') else False
    except (AttributeError, OSError):
        # statvfs n'existe pas sur Windows
        return False


def _CheckDiskSpace(path: str, min_space_mb: int = 100) -> PathValidationResult:
    """
    Vérifie l'espace disque disponible.

    Args:
        path: Chemin à vérifier
        min_space_mb: Espace minimum requis en Mo

    Returns:
        PathValidationResult
    """
    try:
        stat_info = os.statvfs(path) if hasattr(os, 'statvfs') else None

        if stat_info:
            # Unix/Linux
            available_bytes = stat_info.f_bavail * stat_info.f_frsize
        else:
            # Windows
            import shutil
            _, _, available_bytes = shutil.disk_usage(path)

        available_mb = available_bytes / (1024 * 1024)

        if available_mb < min_space_mb:
            return PathValidationResult(
                is_valid=False,
                error_code=PathValidationError.DISK_FULL,
                error_message=f"Espace disque insuffisant: {available_mb:.0f} Mo disponibles (minimum: {min_space_mb} Mo)",
                suggested_fix="Libérez de l'espace disque ou choisissez un autre emplacement"
            )

        return PathValidationResult(is_valid=True)

    except Exception as e:
        # Si on ne peut pas vérifier, on considère que c'est OK
        return PathValidationResult(is_valid=True)


def _TestWriteAccess(path: str) -> PathValidationResult:
    """
    Teste l'accès en écriture en créant un fichier temporaire.

    Args:
        path: Chemin du répertoire à tester

    Returns:
        PathValidationResult
    """
    try:
        test_file = os.path.join(path, '.write_test_temp')

        # Tente de créer un fichier
        with open(test_file, 'w') as f:
            f.write('test')

        # Tente de le lire
        with open(test_file, 'r') as f:
            content = f.read()

        # Supprime le fichier de test
        os.remove(test_file)

        if content != 'test':
            return PathValidationResult(
                is_valid=False,
                error_code=PathValidationError.UNKNOWN_ERROR,
                error_message="Le test de lecture/écriture a échoué",
                suggested_fix="Vérifiez les permissions du répertoire"
            )

        return PathValidationResult(is_valid=True)

    except PermissionError:
        return PathValidationResult(
            is_valid=False,
            error_code=PathValidationError.PERMISSION_DENIED,
            error_message="Pas de permission d'écriture dans ce répertoire",
            suggested_fix="Changez les permissions ou choisissez un autre répertoire"
        )
    except OSError as e:
        if e.errno == 28:  # ENOSPC
            return PathValidationResult(
                is_valid=False,
                error_code=PathValidationError.DISK_FULL,
                error_message="Espace disque insuffisant",
                suggested_fix="Libérez de l'espace disque"
            )
        return PathValidationResult(
            is_valid=False,
            error_code=PathValidationError.UNKNOWN_ERROR,
            error_message=f"Erreur lors du test d'écriture: {e}",
            suggested_fix="Vérifiez les permissions"
        )
    except Exception as e:
        return PathValidationResult(
            is_valid=False,
            error_code=PathValidationError.UNKNOWN_ERROR,
            error_message=f"Erreur inattendue: {e}",
            suggested_fix="Choisissez un autre répertoire"
        )


def GetDefaultWorkDirectory() -> str:
    """
    Retourne le répertoire de travail par défaut.

    Returns:
        Chemin du répertoire par défaut
    """
    return os.path.join(str(Path.home()), ".upscaling_client")


def NormalizePath(path: str) -> str:
    """
    Normalise un chemin (expand ~, résout .., supprime / finaux, etc.)

    Args:
        path: Chemin à normaliser

    Returns:
        Chemin normalisé
    """
    if not path:
        return ""

    # Expand ~ et variables d'environnement
    path = os.path.expanduser(path)
    path = os.path.expandvars(path)

    # Normalise le chemin (résout .., ., etc.)
    path = os.path.normpath(path)

    # Convertit en chemin absolu
    path = os.path.abspath(path)

    return path
