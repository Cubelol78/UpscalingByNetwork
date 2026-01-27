"""
Gestionnaire principal des mises à jour
Coordonne la vérification et l'application des mises à jour
"""

import os
import sys
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

from shared.utils.logger import GetModuleLogger
from shared.utils.constants import UpdateConfig, AppMetadata
from .github_client import GitHubClient, GitHubClientError, NetworkError, RateLimitError
from .version_checker import VersionChecker, UpdateInfo


class UpdateError(Exception):
    """Exception lors de l'application d'une mise à jour"""
    pass


class UpdateManager:
    """Gestionnaire principal des mises à jour"""

    def __init__(self, ProjectRoot: str = None):
        """
        Initialise le gestionnaire de mise à jour

        Args:
            ProjectRoot: Racine du projet (détection automatique si non fourni)
        """
        self.ProjectRoot = ProjectRoot or self._GetProjectRoot()
        self.Client = GitHubClient()
        self.Checker = VersionChecker(self.Client)
        self.Logger = GetModuleLogger("UpdateManager")

    def CheckUpdate(self, Channel: str = None) -> UpdateInfo:
        """
        Vérifie si une mise à jour est disponible

        Args:
            Channel: Canal de mise à jour (dev ou release)

        Returns:
            UpdateInfo avec les détails
        """
        return self.Checker.CheckForUpdate(
            Channel=Channel,
            ProjectRoot=self.ProjectRoot
        )

    def GetReleaseVersionInfo(self, VersionTag: str) -> UpdateInfo:
        """
        Récupère les infos d'une version release spécifique

        Args:
            VersionTag: Tag de version (ex: "1.5.0")

        Returns:
            UpdateInfo avec les détails de cette version
        """
        from shared.utils.constants import AppMetadata

        # Récupère toutes les releases
        Releases = self.Checker.Client.GetReleases()

        # Cherche la release correspondante
        for Release in Releases:
            if Release["tag_name"].lstrip("v") == VersionTag:
                return UpdateInfo(
                    Available=True,
                    CurrentVersion=AppMetadata.VERSION,
                    NewVersion=VersionTag,
                    Channel="release",
                    Changelog=Release.get("body", ""),
                    DownloadUrl=Release["zipball_url"]
                )

        return UpdateInfo(Available=False)

    def GetDevVersionInfo(self, CommitSha: str) -> UpdateInfo:
        """
        Récupère les infos d'un commit dev spécifique

        Args:
            CommitSha: SHA du commit (court ou complet)

        Returns:
            UpdateInfo avec les détails de ce commit
        """
        from shared.utils.constants import AppMetadata

        # Vérifie que le commit existe via API
        Url = f"{UpdateConfig.GITHUB_API_URL}/commits/{CommitSha}"

        try:
            Response = self.Checker.Client._Request(Url)
            CommitData = Response.json()

            return UpdateInfo(
                Available=True,
                CurrentVersion=AppMetadata.VERSION,
                NewVersion=f"dev-{CommitSha[:7]}",
                Channel="dev",
                Changelog=CommitData["commit"]["message"],
                DownloadUrl=f"https://github.com/{UpdateConfig.GITHUB_OWNER}/{UpdateConfig.GITHUB_REPO}/archive/{CommitSha}.zip"
            )
        except Exception:
            return UpdateInfo(Available=False)

    def ApplyUpdate(self, Info: UpdateInfo) -> bool:
        """
        Applique une mise à jour

        Args:
            Info: Informations de la mise à jour (de CheckUpdate)

        Returns:
            True si succès

        Raises:
            UpdateError: Si erreur lors de l'application
        """
        if not Info.Available:
            self.Logger.info("Aucune mise à jour à appliquer")
            return True

        self.Logger.info(f"Application de la mise à jour: {Info}")

        if Info.Channel == UpdateConfig.CHANNEL_DEV:
            return self._ApplyDevUpdate()
        elif Info.Channel == UpdateConfig.CHANNEL_RELEASE:
            return self._ApplyReleaseUpdate(Info.DownloadUrl)
        else:
            raise UpdateError(f"Canal inconnu: {Info.Channel}")

    def _ApplyDevUpdate(self) -> bool:
        """
        Applique une mise à jour via git pull (si repo git) ou téléchargement ZIP

        Returns:
            True si succès
        """
        self.Logger.info("Application de la mise à jour (canal dev)")

        if self.Client.IsGitRepo(self.ProjectRoot):
            # Méthode préférée: git pull
            self.Logger.info("Repository git détecté, utilisation de git pull")
            Success = self.Client.GitPull(self.ProjectRoot)
            if not Success:
                raise UpdateError("git pull a échoué")
            self.Logger.info("Mise à jour dev appliquée avec succès (git pull)")
            return True
        else:
            # Fallback: télécharge le ZIP du dernier commit
            self.Logger.info("Pas de repository git local, téléchargement du ZIP...")
            ZipUrl = f"https://github.com/{UpdateConfig.GITHUB_OWNER}/{UpdateConfig.GITHUB_REPO}/archive/refs/heads/main.zip"
            Success = self._ApplyReleaseUpdate(ZipUrl)
            if Success:
                self.Logger.info("Mise à jour dev appliquée avec succès (téléchargement ZIP)")
            return Success

    def _ApplyReleaseUpdate(self, DownloadUrl: str) -> bool:
        """
        Applique une mise à jour via téléchargement de release

        Args:
            DownloadUrl: URL du ZIP à télécharger

        Returns:
            True si succès
        """
        if not DownloadUrl:
            raise UpdateError("URL de téléchargement manquante")

        self.Logger.info("Application de la mise à jour (canal release)")

        # Crée un répertoire temporaire
        TempDir = tempfile.mkdtemp(prefix="upscaling_update_")
        ZipPath = os.path.join(TempDir, "update.zip")
        ExtractDir = os.path.join(TempDir, "extracted")

        try:
            # 1. Télécharge le ZIP
            self.Logger.info("Téléchargement de la mise à jour...")
            if not self.Client.DownloadFile(DownloadUrl, ZipPath):
                raise UpdateError("Échec du téléchargement")

            # 2. Extrait le ZIP
            self.Logger.info("Extraction de la mise à jour...")
            with zipfile.ZipFile(ZipPath, "r") as Zip:
                Zip.extractall(ExtractDir)

            # Le ZIP GitHub contient un dossier racine avec le nom du repo
            # Trouve ce dossier
            ExtractedItems = os.listdir(ExtractDir)
            if len(ExtractedItems) == 1:
                SourceDir = os.path.join(ExtractDir, ExtractedItems[0])
            else:
                SourceDir = ExtractDir

            # 3. Backup des fichiers à préserver
            self.Logger.info("Sauvegarde des fichiers de configuration...")
            Backup = self._BackupPreservedPaths(TempDir)

            # 4. Copie les nouveaux fichiers
            self.Logger.info("Installation des nouveaux fichiers...")
            self._CopyUpdateFiles(SourceDir)

            # 5. Restaure les fichiers préservés
            self.Logger.info("Restauration de la configuration...")
            self._RestorePreservedPaths(Backup)

            self.Logger.info("Mise à jour release appliquée avec succès")
            return True

        except zipfile.BadZipFile:
            raise UpdateError("Archive corrompue")
        except Exception as e:
            self.Logger.error(f"Erreur lors de l'application de la mise à jour: {e}")
            raise UpdateError(str(e))
        finally:
            # Nettoie le répertoire temporaire
            try:
                shutil.rmtree(TempDir, ignore_errors=True)
            except Exception:
                pass

    def _BackupPreservedPaths(self, TempDir: str) -> Dict[str, str]:
        """
        Sauvegarde les fichiers/dossiers à préserver

        Args:
            TempDir: Répertoire temporaire pour le backup

        Returns:
            Dictionnaire {chemin_original: chemin_backup}
        """
        Backup = {}
        BackupDir = os.path.join(TempDir, "backup")
        os.makedirs(BackupDir, exist_ok=True)

        for RelPath in UpdateConfig.PRESERVE_PATHS:
            FullPath = os.path.join(self.ProjectRoot, RelPath.rstrip("/"))

            if os.path.exists(FullPath):
                BackupPath = os.path.join(BackupDir, RelPath.rstrip("/"))

                if os.path.isdir(FullPath):
                    shutil.copytree(FullPath, BackupPath, dirs_exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(BackupPath), exist_ok=True)
                    shutil.copy2(FullPath, BackupPath)

                Backup[FullPath] = BackupPath
                self.Logger.debug(f"Sauvegardé: {RelPath}")

        return Backup

    def _RestorePreservedPaths(self, Backup: Dict[str, str]):
        """
        Restaure les fichiers préservés

        Args:
            Backup: Dictionnaire {chemin_original: chemin_backup}
        """
        for FullPath, BackupPath in Backup.items():
            try:
                if os.path.isdir(BackupPath):
                    # Supprime le répertoire destination s'il existe
                    if os.path.exists(FullPath):
                        shutil.rmtree(FullPath)
                    shutil.copytree(BackupPath, FullPath)
                else:
                    os.makedirs(os.path.dirname(FullPath), exist_ok=True)
                    shutil.copy2(BackupPath, FullPath)

                self.Logger.debug(f"Restauré: {FullPath}")

            except Exception as e:
                self.Logger.warning(f"Impossible de restaurer {FullPath}: {e}")

    def _CopyUpdateFiles(self, SourceDir: str):
        """
        Copie les fichiers de mise à jour vers le projet

        Args:
            SourceDir: Répertoire source contenant les fichiers mis à jour
        """
        for Item in os.listdir(SourceDir):
            SrcPath = os.path.join(SourceDir, Item)
            DstPath = os.path.join(self.ProjectRoot, Item)

            # Ignore les fichiers/dossiers à préserver
            ShouldSkip = False
            for PreservePath in UpdateConfig.PRESERVE_PATHS:
                if Item == PreservePath.rstrip("/"):
                    ShouldSkip = True
                    break

            if ShouldSkip:
                self.Logger.debug(f"Ignoré (préservé): {Item}")
                continue

            try:
                if os.path.isdir(SrcPath):
                    if os.path.exists(DstPath):
                        shutil.rmtree(DstPath)
                    shutil.copytree(SrcPath, DstPath)
                else:
                    # Gestion spéciale pour main.py
                    if Item == "main.py":
                        # Écrit dans un fichier temporaire
                        TempMain = DstPath + ".new"
                        shutil.copy2(SrcPath, TempMain)
                        self.Logger.debug(f"main.py écrit dans {TempMain}")
                    else:
                        shutil.copy2(SrcPath, DstPath)

            except Exception as e:
                self.Logger.warning(f"Impossible de copier {Item}: {e}")

    def FinalizeSelfUpdate(self) -> bool:
        """
        Finalise la mise à jour de main.py lui-même

        Cette méthode doit être appelée au tout début du démarrage,
        avant tout autre code.

        Returns:
            True si une mise à jour a été finalisée
        """
        MainPath = os.path.join(self.ProjectRoot, "main.py")
        NewMainPath = MainPath + ".new"
        BackupPath = MainPath + ".bak"

        if not os.path.exists(NewMainPath):
            return False

        self.Logger.info("Finalisation de la mise à jour de main.py...")

        try:
            # Backup de l'ancien main.py
            if os.path.exists(MainPath):
                shutil.copy2(MainPath, BackupPath)

            # Remplace main.py (atomique sur le même filesystem)
            os.replace(NewMainPath, MainPath)

            self.Logger.info("main.py mis à jour avec succès")
            return True

        except Exception as e:
            self.Logger.error(f"Erreur lors de la finalisation: {e}")
            # Tente de restaurer
            if os.path.exists(BackupPath):
                try:
                    shutil.copy2(BackupPath, MainPath)
                except Exception:
                    pass
            return False

    def ShouldRestart(self) -> bool:
        """
        Indique si un redémarrage est nécessaire après mise à jour

        Returns:
            True (toujours redémarrer après mise à jour)
        """
        return True

    def RequestRestart(self):
        """
        Redémarre l'application

        Utilise os.execv pour remplacer le processus actuel
        """
        self.Logger.info("Redémarrage de l'application...")

        # Finalise d'abord si nécessaire
        self.FinalizeSelfUpdate()

        PythonPath = sys.executable
        ScriptPath = os.path.join(self.ProjectRoot, "main.py")

        # Filtre les arguments qui ne doivent pas être préservés après une mise à jour
        FILTERED_ARGS = {"--update", "--check-update", "--install-version"}
        Args = [
            arg for arg in sys.argv[1:]
            if not any(arg.startswith(f) for f in FILTERED_ARGS)
        ]

        self.Logger.info(f"Exécution: {PythonPath} {ScriptPath} {' '.join(Args)}")

        try:
            os.execv(PythonPath, [PythonPath, ScriptPath] + Args)
        except Exception as e:
            self.Logger.error(f"Impossible de redémarrer: {e}")
            print(f"\n⚠ Veuillez relancer manuellement l'application")
            sys.exit(0)

    def _GetProjectRoot(self) -> str:
        """
        Détecte la racine du projet

        Returns:
            Chemin absolu vers la racine du projet
        """
        # Remonte depuis ce fichier jusqu'à la racine
        CurrentFile = Path(__file__).resolve()
        # shared/utils/updater/update_manager.py -> racine
        return str(CurrentFile.parent.parent.parent.parent)


# Messages utilisateur
UPDATE_MESSAGES = {
    "checking": "Vérification des mises à jour...",
    "available": "Nouvelle version {version} disponible ({channel})",
    "changelog": "Nouveautés:\n{changelog}",
    "confirm": "Voulez-vous mettre à jour maintenant ? (oui/non)",
    "downloading": "Téléchargement de la mise à jour...",
    "applying": "Application de la mise à jour...",
    "success": "Mise à jour terminée. Redémarrage...",
    "failed": "Erreur lors de la mise à jour: {error}",
    "offline": "Impossible de vérifier les mises à jour (hors ligne)",
    "rate_limit": "Limite API GitHub atteinte. Réessayez plus tard.",
    "up_to_date": "Vous utilisez déjà la dernière version ({version})",
    "skipped": "Mise à jour ignorée.",
}
