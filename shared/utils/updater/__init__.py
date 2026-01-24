"""
Module de mise à jour automatique via GitHub
Permet de mettre à jour l'application depuis le canal dev (commits) ou release (releases GitHub)
"""

from .github_client import GitHubClient
from .version_checker import VersionChecker, UpdateInfo
from .update_manager import UpdateManager

__all__ = [
    "GitHubClient",
    "VersionChecker",
    "UpdateInfo",
    "UpdateManager"
]
