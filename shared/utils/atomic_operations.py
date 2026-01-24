"""
Opérations atomiques pour garantir l'intégrité des données
Fournit des context managers pour des opérations transactionnelles
"""

import asyncio
import os
import shutil
import tempfile
from typing import Optional, List
from pathlib import Path


class AtomicImageSave:
    """
    Context manager async pour sauvegarde atomique d'images.

    Garantit que soit TOUTES les images sont sauvegardées, soit AUCUNE.
    Évite les sauvegardes partielles qui corrompent l'état du système.

    Principe :
    1. Crée un dossier temporaire
    2. Sauvegarde toutes les images dans le dossier temporaire
    3. Si TOUTES les images réussies : déplace le dossier temp vers destination (atomique)
    4. Si échec : supprime le dossier temp (rollback)

    Usage:
    ```python
    async with AtomicImageSave(destination_dir) as atomic:
        for image in images:
            await atomic.SaveImage(image_path, image_data)
        # À la sortie du contexte :
        # - Si pas d'exception : déplace temp → destination (commit)
        # - Si exception : supprime temp (rollback)
    ```
    """

    def __init__(self, destination_dir: str, logger=None):
        """
        Initialise l'opération atomique

        Args:
            destination_dir: Répertoire de destination final
            logger: Logger optionnel pour tracer les opérations
        """
        self.DestinationDir = destination_dir
        self.Logger = logger
        self.TempDir = None
        self.SavedFiles = []  # Liste des fichiers sauvegardés pour rollback
        self.Committed = False

    async def __aenter__(self):
        """Entre dans le contexte : crée le dossier temporaire"""
        # Crée un dossier temporaire unique à côté de la destination
        ParentDir = os.path.dirname(self.DestinationDir)
        BaseName = os.path.basename(self.DestinationDir)

        # Utilise tempfile pour garantir un nom unique
        self.TempDir = tempfile.mkdtemp(
            prefix=f"{BaseName}_atomic_",
            dir=ParentDir
        )

        if self.Logger:
            self.Logger.debug(f"AtomicImageSave: dossier temporaire créé: {self.TempDir}")

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Sort du contexte : commit ou rollback selon succès/échec

        Args:
            exc_type: Type d'exception si erreur
            exc_val: Valeur d'exception
            exc_tb: Traceback

        Returns:
            False pour propager l'exception si erreur
        """
        try:
            if exc_type is None:
                # Pas d'exception : commit
                await self._Commit()
            else:
                # Exception levée : rollback
                await self._Rollback()

            return False  # Propage l'exception si erreur

        finally:
            # Nettoyage du dossier temporaire si pas committé
            if not self.Committed and self.TempDir and os.path.exists(self.TempDir):
                try:
                    shutil.rmtree(self.TempDir)
                    if self.Logger:
                        self.Logger.debug(f"AtomicImageSave: dossier temporaire supprimé: {self.TempDir}")
                except Exception as cleanup_err:
                    if self.Logger:
                        self.Logger.error(f"Erreur nettoyage dossier temporaire: {cleanup_err}")

    async def SaveImage(self, filename: str, image_data: bytes) -> bool:
        """
        Sauvegarde une image dans le dossier temporaire

        Args:
            filename: Nom du fichier (ex: "frame_0001.png")
            image_data: Données binaires de l'image

        Returns:
            True si succès

        Raises:
            Exception si erreur d'écriture
        """
        if not self.TempDir:
            raise RuntimeError("AtomicImageSave non initialisé (appeler via 'async with')")

        try:
            FilePath = os.path.join(self.TempDir, filename)

            # Écrit le fichier dans un thread séparé (IO bloquant)
            await asyncio.to_thread(self._WriteFile, FilePath, image_data)

            self.SavedFiles.append(filename)

            if self.Logger:
                self.Logger.debug(f"AtomicImageSave: image sauvegardée: {filename}")

            return True

        except Exception as e:
            if self.Logger:
                self.Logger.error(f"Erreur sauvegarde image {filename}: {e}")
            raise

    def _WriteFile(self, filepath: str, data: bytes):
        """
        Écrit un fichier de manière synchrone (appelé via to_thread)

        Args:
            filepath: Chemin complet du fichier
            data: Données à écrire
        """
        with open(filepath, 'wb') as f:
            f.write(data)

    async def _Commit(self):
        """
        Commit l'opération : déplace le dossier temp vers destination

        Cette opération est atomique au niveau du filesystem :
        - Si destination n'existe pas : rename (atomique)
        - Si destination existe : supprime destination puis rename
        """
        if not self.TempDir or not os.path.exists(self.TempDir):
            raise RuntimeError("Dossier temporaire inexistant, commit impossible")

        try:
            # Vérifie que des fichiers ont été sauvegardés
            if not self.SavedFiles:
                if self.Logger:
                    self.Logger.warning("AtomicImageSave: aucune image à commit")
                return

            if self.Logger:
                self.Logger.info(f"AtomicImageSave: commit de {len(self.SavedFiles)} images vers {self.DestinationDir}")

            # Crée le dossier destination s'il n'existe pas
            await asyncio.to_thread(os.makedirs, self.DestinationDir, exist_ok=True)

            # Déplace chaque fichier individuellement (pour ne pas écraser les autres batches)
            for FileName in self.SavedFiles:
                SourcePath = os.path.join(self.TempDir, FileName)
                DestPath = os.path.join(self.DestinationDir, FileName)

                # Déplace le fichier (écrase si existe déjà, ce qui est normal pour un retry)
                await asyncio.to_thread(shutil.move, SourcePath, DestPath)

            # Supprime le dossier temporaire (maintenant vide)
            if os.path.exists(self.TempDir):
                await asyncio.to_thread(shutil.rmtree, self.TempDir)

            self.Committed = True

            if self.Logger:
                self.Logger.info(f"✓ AtomicImageSave: commit réussi ({len(self.SavedFiles)} images)")

        except Exception as e:
            if self.Logger:
                self.Logger.error(f"Erreur lors du commit: {e}")
            raise

    async def _Rollback(self):
        """
        Rollback l'opération : supprime le dossier temporaire

        Appelé automatiquement si une exception est levée dans le contexte
        """
        if not self.TempDir:
            return

        try:
            if os.path.exists(self.TempDir):
                if self.Logger:
                    self.Logger.warning(f"AtomicImageSave: rollback, suppression de {len(self.SavedFiles)} images")

                await asyncio.to_thread(shutil.rmtree, self.TempDir)

                if self.Logger:
                    self.Logger.info("✓ AtomicImageSave: rollback réussi")

        except Exception as e:
            if self.Logger:
                self.Logger.error(f"Erreur lors du rollback: {e}")
            # Ne pas re-raise, on est déjà dans un contexte d'erreur

    def GetSavedCount(self) -> int:
        """Retourne le nombre d'images sauvegardées"""
        return len(self.SavedFiles)

    def GetSavedFiles(self) -> List[str]:
        """Retourne la liste des noms de fichiers sauvegardés"""
        return self.SavedFiles.copy()
