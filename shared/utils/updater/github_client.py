"""
Client GitHub pour récupérer les informations de release et gérer les mises à jour
Utilise urllib.request pour éviter les dépendances externes
"""

import json
import os
import subprocess
import urllib.request
import urllib.error
from typing import Optional, Dict, Any
from pathlib import Path

from shared.utils.logger import GetModuleLogger
from shared.utils.constants import UpdateConfig


class GitHubClientError(Exception):
    """Exception de base pour les erreurs du client GitHub"""
    pass


class NetworkError(GitHubClientError):
    """Erreur réseau (pas d'internet, timeout)"""
    pass


class RateLimitError(GitHubClientError):
    """Rate limit GitHub atteint (60 req/h pour API non authentifiée)"""
    pass


class GitHubClient:
    """Client pour interagir avec l'API GitHub et Git"""

    def __init__(self, Owner: str = None, Repo: str = None):
        """
        Initialise le client GitHub

        Args:
            Owner: Propriétaire du repository (défaut: UpdateConfig.GITHUB_OWNER)
            Repo: Nom du repository (défaut: UpdateConfig.GITHUB_REPO)
        """
        self.Owner = Owner or UpdateConfig.GITHUB_OWNER
        self.Repo = Repo or UpdateConfig.GITHUB_REPO
        self.ApiUrl = f"https://api.github.com/repos/{self.Owner}/{self.Repo}"
        self.Logger = GetModuleLogger("GitHubClient")

    def _MakeApiRequest(self, Endpoint: str) -> Dict[str, Any]:
        """
        Effectue une requête vers l'API GitHub

        Args:
            Endpoint: Endpoint de l'API (ex: /releases/latest)

        Returns:
            Réponse JSON décodée

        Raises:
            NetworkError: Si erreur réseau
            RateLimitError: Si rate limit atteint
            GitHubClientError: Pour autres erreurs
        """
        Url = f"{self.ApiUrl}{Endpoint}"
        self.Logger.debug(f"Requête API: {Url}")

        Request = urllib.request.Request(
            Url,
            headers={
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": f"{UpdateConfig.GITHUB_REPO}-updater"
            }
        )

        try:
            with urllib.request.urlopen(Request, timeout=UpdateConfig.API_TIMEOUT) as Response:
                Data = json.loads(Response.read().decode("utf-8"))
                return Data

        except urllib.error.HTTPError as e:
            if e.code == 403:
                # Vérifie si c'est un rate limit
                RateLimitRemaining = e.headers.get("X-RateLimit-Remaining", "unknown")
                if RateLimitRemaining == "0":
                    raise RateLimitError(
                        "Limite de requêtes GitHub atteinte (60/heure). "
                        "Réessayez plus tard."
                    )
            elif e.code == 404:
                raise GitHubClientError(f"Resource non trouvée: {Endpoint}")
            raise GitHubClientError(f"Erreur HTTP {e.code}: {e.reason}")

        except urllib.error.URLError as e:
            raise NetworkError(f"Erreur réseau: {e.reason}")

        except TimeoutError:
            raise NetworkError("Timeout lors de la connexion à GitHub")

    def GetLatestRelease(self) -> Optional[Dict[str, Any]]:
        """
        Récupère la dernière release via l'API GitHub

        Returns:
            Dictionnaire avec les informations de la release:
            - tag_name: Version (ex: "v1.2.0")
            - name: Nom de la release
            - body: Description/changelog
            - zipball_url: URL du ZIP source
            - published_at: Date de publication

        Raises:
            NetworkError, RateLimitError, GitHubClientError
        """
        try:
            Data = self._MakeApiRequest("/releases/latest")
            self.Logger.info(f"Dernière release: {Data.get('tag_name', 'N/A')}")
            return Data

        except GitHubClientError as e:
            if "404" in str(e):
                self.Logger.warning("Aucune release trouvée sur le repository")
                return None
            raise

    def GetLatestCommitSha(self, Branch: str = "main") -> Optional[str]:
        """
        Récupère le SHA du dernier commit sur une branche via git ls-remote

        Args:
            Branch: Nom de la branche (défaut: main)

        Returns:
            SHA du dernier commit ou None si erreur
        """
        try:
            RemoteUrl = f"https://github.com/{self.Owner}/{self.Repo}.git"
            Result = subprocess.run(
                ["git", "ls-remote", RemoteUrl, f"refs/heads/{Branch}"],
                capture_output=True,
                text=True,
                timeout=UpdateConfig.API_TIMEOUT
            )

            if Result.returncode == 0 and Result.stdout.strip():
                Sha = Result.stdout.split()[0]
                self.Logger.debug(f"Dernier commit {Branch}: {Sha[:8]}")
                return Sha
            else:
                self.Logger.warning(f"Impossible de récupérer le SHA de {Branch}: {Result.stderr}")
                return None

        except subprocess.TimeoutExpired:
            raise NetworkError("Timeout lors de la récupération du SHA distant")
        except FileNotFoundError:
            raise GitHubClientError("Git n'est pas installé ou non accessible")
        except Exception as e:
            self.Logger.error(f"Erreur lors de la récupération du SHA: {e}")
            return None

    def GetLatestCommitShaViaAPI(self, Branch: str = "main") -> Optional[str]:
        """
        Récupère le SHA du dernier commit via l'API GitHub (sans git)

        Args:
            Branch: Branche à vérifier (défaut: main)

        Returns:
            SHA du dernier commit ou None si erreur
        """
        try:
            CommitData = self._MakeApiRequest(f"/commits/{Branch}")
            Sha = CommitData["sha"]
            self.Logger.debug(f"Dernier commit {Branch} (API): {Sha[:8]}")
            return Sha
        except Exception as e:
            self.Logger.error(f"Impossible de récupérer le SHA distant via API: {e}")
            return None

    def GetLocalCommitSha(self, ProjectRoot: str = None) -> Optional[str]:
        """
        Récupère le SHA du commit local actuel

        Args:
            ProjectRoot: Racine du projet (défaut: détection automatique)

        Returns:
            SHA du commit local ou None si pas un repo git
        """
        try:
            Cwd = ProjectRoot or self._GetProjectRoot()
            Result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=Cwd,
                timeout=10
            )

            if Result.returncode == 0:
                Sha = Result.stdout.strip()
                self.Logger.debug(f"Commit local: {Sha[:8]}")
                return Sha
            else:
                self.Logger.debug("Ce n'est pas un repository git")
                return None

        except FileNotFoundError:
            self.Logger.debug("Git n'est pas installé")
            return None
        except Exception as e:
            self.Logger.error(f"Erreur lors de la récupération du SHA local: {e}")
            return None

    def IsGitRepo(self, ProjectRoot: str = None) -> bool:
        """
        Vérifie si le répertoire est un dépôt git

        Args:
            ProjectRoot: Racine du projet

        Returns:
            True si c'est un repo git
        """
        Cwd = ProjectRoot or self._GetProjectRoot()
        GitDir = Path(Cwd) / ".git"
        return GitDir.exists()

    def GitPull(self, ProjectRoot: str = None, Remote: str = "origin", Branch: str = "main") -> bool:
        """
        Exécute git pull pour mettre à jour le code

        Args:
            ProjectRoot: Racine du projet
            Remote: Remote git (défaut: origin)
            Branch: Branche à pull (défaut: main)

        Returns:
            True si succès
        """
        Cwd = ProjectRoot or self._GetProjectRoot()

        try:
            # Stash les modifications locales
            StashResult = subprocess.run(
                ["git", "stash", "--include-untracked"],
                capture_output=True,
                text=True,
                cwd=Cwd,
                timeout=30
            )
            HasStash = "No local changes" not in StashResult.stdout

            self.Logger.info(f"Exécution de git pull {Remote} {Branch}")

            # Pull
            Result = subprocess.run(
                ["git", "pull", Remote, Branch],
                capture_output=True,
                text=True,
                cwd=Cwd,
                timeout=UpdateConfig.DOWNLOAD_TIMEOUT
            )

            if Result.returncode != 0:
                self.Logger.error(f"git pull a échoué: {Result.stderr}")
                # Restaure le stash en cas d'échec
                if HasStash:
                    subprocess.run(["git", "stash", "pop"], cwd=Cwd, timeout=30)
                return False

            self.Logger.info("git pull réussi")

            # Restaure les modifications locales
            if HasStash:
                PopResult = subprocess.run(
                    ["git", "stash", "pop"],
                    capture_output=True,
                    text=True,
                    cwd=Cwd,
                    timeout=30
                )
                if PopResult.returncode != 0:
                    self.Logger.warning(
                        f"Impossible de restaurer les modifications locales: {PopResult.stderr}"
                    )

            return True

        except subprocess.TimeoutExpired:
            raise NetworkError("Timeout lors du git pull")
        except FileNotFoundError:
            raise GitHubClientError("Git n'est pas installé")
        except Exception as e:
            self.Logger.error(f"Erreur lors du git pull: {e}")
            return False

    def DownloadFile(self, Url: str, DestPath: str) -> bool:
        """
        Télécharge un fichier depuis une URL

        Args:
            Url: URL du fichier à télécharger
            DestPath: Chemin de destination

        Returns:
            True si succès
        """
        self.Logger.info(f"Téléchargement: {Url}")

        Request = urllib.request.Request(
            Url,
            headers={"User-Agent": f"{UpdateConfig.GITHUB_REPO}-updater"}
        )

        try:
            with urllib.request.urlopen(Request, timeout=UpdateConfig.DOWNLOAD_TIMEOUT) as Response:
                # Crée le répertoire parent si nécessaire
                os.makedirs(os.path.dirname(DestPath), exist_ok=True)

                # Télécharge par chunks
                TotalSize = int(Response.headers.get("Content-Length", 0))
                Downloaded = 0
                ChunkSize = 8192

                with open(DestPath, "wb") as f:
                    while True:
                        Chunk = Response.read(ChunkSize)
                        if not Chunk:
                            break
                        f.write(Chunk)
                        Downloaded += len(Chunk)

                        # Log de progression
                        if TotalSize > 0:
                            Percent = (Downloaded / TotalSize) * 100
                            if Downloaded % (ChunkSize * 100) == 0:
                                self.Logger.debug(f"Progression: {Percent:.1f}%")

            self.Logger.info(f"Téléchargement terminé: {DestPath}")
            return True

        except urllib.error.HTTPError as e:
            self.Logger.error(f"Erreur HTTP lors du téléchargement: {e.code}")
            return False

        except urllib.error.URLError as e:
            raise NetworkError(f"Erreur réseau: {e.reason}")

        except TimeoutError:
            raise NetworkError("Timeout lors du téléchargement")

        except Exception as e:
            self.Logger.error(f"Erreur lors du téléchargement: {e}")
            return False

    def _GetProjectRoot(self) -> str:
        """
        Détecte la racine du projet

        Returns:
            Chemin absolu vers la racine du projet
        """
        # Remonte depuis ce fichier jusqu'à la racine
        CurrentFile = Path(__file__).resolve()
        # shared/utils/updater/github_client.py -> racine
        return str(CurrentFile.parent.parent.parent.parent)
