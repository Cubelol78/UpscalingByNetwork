"""
Vérificateur de version pour détecter les mises à jour disponibles
Supporte les canaux dev (commits) et release (releases GitHub)
"""

import re
from dataclasses import dataclass
from typing import Optional

from shared.utils.logger import GetModuleLogger
from shared.utils.constants import UpdateConfig, AppMetadata
from .github_client import GitHubClient, GitHubClientError, NetworkError, RateLimitError


@dataclass
class UpdateInfo:
    """Informations sur une mise à jour disponible"""
    Available: bool
    Channel: str
    CurrentVersion: str
    NewVersion: str
    Changelog: Optional[str] = None
    DownloadUrl: Optional[str] = None
    CommitSha: Optional[str] = None

    def __str__(self) -> str:
        if not self.Available:
            return f"Aucune mise à jour disponible (version actuelle: {self.CurrentVersion})"
        return (
            f"Mise à jour disponible ({self.Channel}): "
            f"{self.CurrentVersion} → {self.NewVersion}"
        )


class VersionChecker:
    """Vérifie si une nouvelle version est disponible"""

    def __init__(self, Client: GitHubClient = None):
        """
        Initialise le vérificateur de version

        Args:
            Client: Client GitHub (créé automatiquement si non fourni)
        """
        self.Client = Client or GitHubClient()
        self.Logger = GetModuleLogger("VersionChecker")

    def CheckForUpdate(
        self,
        Channel: str = None,
        CurrentVersion: str = None,
        ProjectRoot: str = None
    ) -> UpdateInfo:
        """
        Vérifie si une mise à jour est disponible

        Args:
            Channel: Canal de mise à jour (dev ou release)
            CurrentVersion: Version actuelle (défaut: AppMetadata.VERSION)
            ProjectRoot: Racine du projet pour le canal dev

        Returns:
            UpdateInfo avec les détails de la mise à jour

        Raises:
            NetworkError: Si erreur réseau
            RateLimitError: Si rate limit GitHub atteint
        """
        Channel = Channel or UpdateConfig.DEFAULT_CHANNEL
        CurrentVersion = CurrentVersion or AppMetadata.VERSION

        self.Logger.info(f"Vérification des mises à jour (canal: {Channel})")

        if Channel == UpdateConfig.CHANNEL_RELEASE:
            return self._CheckReleaseChannel(CurrentVersion)
        elif Channel == UpdateConfig.CHANNEL_DEV:
            return self._CheckDevChannel(CurrentVersion, ProjectRoot)
        else:
            self.Logger.error(f"Canal inconnu: {Channel}")
            return UpdateInfo(
                Available=False,
                Channel=Channel,
                CurrentVersion=CurrentVersion,
                NewVersion=CurrentVersion
            )

    def _CheckReleaseChannel(self, CurrentVersion: str) -> UpdateInfo:
        """
        Vérifie les mises à jour via le canal release

        Args:
            CurrentVersion: Version actuelle

        Returns:
            UpdateInfo
        """
        try:
            Release = self.Client.GetLatestRelease()

            if not Release:
                self.Logger.info("Aucune release disponible")
                return UpdateInfo(
                    Available=False,
                    Channel=UpdateConfig.CHANNEL_RELEASE,
                    CurrentVersion=CurrentVersion,
                    NewVersion=CurrentVersion
                )

            # Extrait la version du tag (enlève le préfixe 'v' si présent)
            TagName = Release.get("tag_name", "")
            RemoteVersion = TagName.lstrip("v")

            # Compare les versions
            Comparison = self.CompareVersions(CurrentVersion, RemoteVersion)

            if Comparison < 0:
                # Nouvelle version disponible
                self.Logger.info(f"Nouvelle version disponible: {RemoteVersion}")
                return UpdateInfo(
                    Available=True,
                    Channel=UpdateConfig.CHANNEL_RELEASE,
                    CurrentVersion=CurrentVersion,
                    NewVersion=RemoteVersion,
                    Changelog=Release.get("body", ""),
                    DownloadUrl=Release.get("zipball_url")
                )
            else:
                self.Logger.info(f"Version à jour ({CurrentVersion})")
                return UpdateInfo(
                    Available=False,
                    Channel=UpdateConfig.CHANNEL_RELEASE,
                    CurrentVersion=CurrentVersion,
                    NewVersion=RemoteVersion
                )

        except (NetworkError, RateLimitError):
            raise
        except GitHubClientError as e:
            self.Logger.error(f"Erreur lors de la vérification release: {e}")
            raise

    def _CheckDevChannel(self, CurrentVersion: str, ProjectRoot: str = None) -> UpdateInfo:
        """
        Vérifie les mises à jour via le canal dev (commits)

        Args:
            CurrentVersion: Version actuelle
            ProjectRoot: Racine du projet

        Returns:
            UpdateInfo
        """
        try:
            # Tente d'abord via git local (méthode préférée)
            if self.Client.IsGitRepo(ProjectRoot):
                LocalSha = self.Client.GetLocalCommitSha(ProjectRoot)
                self.Logger.debug("Repository git détecté, utilisation de git local")
            else:
                # Fallback: utilise AppMetadata.COMMIT_SHA (détecté au démarrage)
                from shared.utils.constants import AppMetadata
                LocalSha = AppMetadata.COMMIT_SHA_FULL
                self.Logger.debug("Pas de repository git, utilisation de AppMetadata.COMMIT_SHA")

                if not LocalSha:
                    # Pas de SHA local du tout, impossible de comparer
                    self.Logger.warning(
                        "Aucun SHA local disponible. "
                        "Le canal dev nécessite un repository git ou une version déployée depuis git."
                    )
                    return UpdateInfo(
                        Available=False,
                        Channel=UpdateConfig.CHANNEL_DEV,
                        CurrentVersion=CurrentVersion,
                        NewVersion=CurrentVersion,
                        Changelog="Impossible de déterminer la version locale"
                    )

            # Récupère SHA distant via API GitHub (sans git)
            RemoteSha = self.Client.GetLatestCommitShaViaAPI()

            if not RemoteSha:
                self.Logger.warning("Impossible de récupérer le SHA distant")
                return UpdateInfo(
                    Available=False,
                    Channel=UpdateConfig.CHANNEL_DEV,
                    CurrentVersion=CurrentVersion,
                    NewVersion=CurrentVersion
                )

            # Compare les SHA
            if LocalSha != RemoteSha:
                self.Logger.info(f"Nouveaux commits disponibles: {LocalSha[:8]} → {RemoteSha[:8]}")
                return UpdateInfo(
                    Available=True,
                    Channel=UpdateConfig.CHANNEL_DEV,
                    CurrentVersion=f"{CurrentVersion} ({LocalSha[:8]})",
                    NewVersion=f"dev ({RemoteSha[:8]})",
                    CommitSha=RemoteSha,
                    Changelog=f"Mise à jour vers le commit {RemoteSha[:8]}"
                )
            else:
                self.Logger.info(f"Code à jour (commit {LocalSha[:8]})")
                return UpdateInfo(
                    Available=False,
                    Channel=UpdateConfig.CHANNEL_DEV,
                    CurrentVersion=f"{CurrentVersion} ({LocalSha[:8]})",
                    NewVersion=f"{CurrentVersion} ({LocalSha[:8]})"
                )

        except (NetworkError, RateLimitError):
            raise
        except GitHubClientError as e:
            self.Logger.error(f"Erreur lors de la vérification dev: {e}")
            raise

    def CompareVersions(self, Current: str, Remote: str) -> int:
        """
        Compare deux versions semver

        Args:
            Current: Version actuelle (ex: "1.2.3")
            Remote: Version distante (ex: "1.3.0")

        Returns:
            -1 si Current < Remote (mise à jour disponible)
             0 si Current == Remote
             1 si Current > Remote
        """
        def ParseVersion(Version: str) -> tuple:
            """Parse une version en tuple de nombres"""
            # Nettoie la version (enlève préfixes, suffixes)
            Clean = re.sub(r"[^\d.]", "", Version)
            Parts = Clean.split(".")

            # Convertit en entiers, remplit avec des 0
            Numbers = []
            for Part in Parts[:3]:  # Major.Minor.Patch
                try:
                    Numbers.append(int(Part))
                except ValueError:
                    Numbers.append(0)

            # Assure qu'on a 3 éléments
            while len(Numbers) < 3:
                Numbers.append(0)

            return tuple(Numbers)

        try:
            CurrentParts = ParseVersion(Current)
            RemoteParts = ParseVersion(Remote)

            if CurrentParts < RemoteParts:
                return -1
            elif CurrentParts > RemoteParts:
                return 1
            else:
                return 0

        except Exception as e:
            self.Logger.warning(f"Erreur de comparaison de version: {e}")
            # En cas de doute, considère qu'il y a une mise à jour
            return -1
