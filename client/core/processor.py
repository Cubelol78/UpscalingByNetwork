"""
Processeur local pour le traitement des batches d'images
Reçoit des images, les upscale et renvoie les résultats
"""

import os
import base64
import shutil
from typing import List, Dict, Any, Optional
from pathlib import Path

from client.utils.realesrgan_handler import RealESRGANHandler
from shared.utils.logger import GetClientLogger
from shared.protocol.messages import BatchResult


class LocalProcessor:
    """Processeur local de batches d'images"""

    def __init__(self, TempDirectory: str = None):
        """
        Initialise le processeur local

        Args:
            TempDirectory: Répertoire temporaire (défaut: ~/.upscaling_client/temp)
        """
        self.Logger = GetClientLogger()

        # Répertoire temporaire
        if TempDirectory:
            self.TempDir = TempDirectory
        else:
            self.TempDir = os.path.join(Path.home(), '.upscaling_client', 'temp')

        os.makedirs(self.TempDir, exist_ok=True)

        # Handler Real-ESRGAN
        self.RealESRGANHandler = RealESRGANHandler()

        self.Logger.info("Processeur local initialisé")

    def ProcessBatch(self, BatchData: Dict[str, Any]) -> Optional[BatchResult]:
        """
        Traite un batch d'images

        Args:
            BatchData: Données du batch (depuis BatchAssignment)

        Returns:
            BatchResult ou None si erreur
        """
        try:
            BatchId = BatchData.get("batch_id")
            VideoId = BatchData.get("video_id")
            Images = BatchData.get("images", [])
            UpscaleFactor = BatchData.get("upscale_factor", 4)
            Model = BatchData.get("model", "realesr-animevideov3")

            self.Logger.info(f"Traitement du batch {BatchId}")
            self.Logger.info(f"  Vidéo: {VideoId}")
            self.Logger.info(f"  Images: {len(Images)}")
            self.Logger.info(f"  Facteur: x{UpscaleFactor}")
            self.Logger.info(f"  Modèle: {Model}")

            # Crée les répertoires temporaires
            InputDir = os.path.join(self.TempDir, BatchId, 'input')
            OutputDir = os.path.join(self.TempDir, BatchId, 'output')
            os.makedirs(InputDir, exist_ok=True)
            os.makedirs(OutputDir, exist_ok=True)

            # Sauvegarde les images reçues
            SavedImages = self._SaveImages(Images, InputDir)

            if not SavedImages:
                self.Logger.error("Aucune image sauvegardée")
                return self._CreateErrorResult(BatchId, "Aucune image sauvegardée")

            # Upscale les images
            UpscaledImages = self._UpscaleImages(
                SavedImages,
                OutputDir,
                UpscaleFactor,
                Model
            )

            if not UpscaledImages:
                self.Logger.error("Échec de l'upscaling")
                return self._CreateErrorResult(BatchId, "Échec de l'upscaling")

            # Charge les images upscalées
            ResultImages = self._LoadUpscaledImages(UpscaledImages, Images)

            # Nettoie les fichiers temporaires
            self._Cleanup(BatchId)

            # Crée le résultat
            Result = BatchResult(
                BatchId=BatchId,
                Success=True,
                UpscaledImages=ResultImages
            )

            self.Logger.info(f"✓ Batch {BatchId} traité avec succès ({len(ResultImages)} images)")

            return Result

        except Exception as e:
            self.Logger.error(f"Erreur lors du traitement du batch: {e}")
            return self._CreateErrorResult(BatchId, str(e))

    def _SaveImages(self, Images: List[Dict], OutputDir: str) -> List[str]:
        """
        Sauvegarde les images reçues en base64

        Args:
            Images: Liste d'images [{id, number, data, filename}]
            OutputDir: Répertoire de sortie

        Returns:
            Liste des chemins des images sauvegardées
        """
        SavedPaths = []

        try:
            for ImageData in Images:
                ImageId = ImageData.get("id")
                ImageB64 = ImageData.get("data")
                Filename = ImageData.get("filename", f"frame_{ImageId}.png")

                # Décode l'image
                ImageBytes = base64.b64decode(ImageB64)

                # Sauvegarde
                OutputPath = os.path.join(OutputDir, Filename)
                with open(OutputPath, 'wb') as f:
                    f.write(ImageBytes)

                SavedPaths.append(OutputPath)

            self.Logger.info(f"✓ {len(SavedPaths)} images sauvegardées")
            return SavedPaths

        except Exception as e:
            self.Logger.error(f"Erreur lors de la sauvegarde des images: {e}")
            return []

    def _UpscaleImages(self, ImagePaths: List[str], OutputDir: str,
                      UpscaleFactor: int, Model: str) -> List[str]:
        """
        Upscale les images avec Real-ESRGAN

        Args:
            ImagePaths: Liste des chemins d'images à upscaler
            OutputDir: Répertoire de sortie
            UpscaleFactor: Facteur d'upscaling
            Model: Modèle à utiliser

        Returns:
            Liste des chemins des images upscalées
        """
        try:
            self.Logger.info(f"Upscaling de {len(ImagePaths)} images...")

            # Définit le callback de progression
            def ProgressCallback(Current, Total):
                Progress = (Current / Total) * 100
                self.Logger.info(f"Progression: {Current}/{Total} ({Progress:.1f}%)")

            # Upscale les images
            UpscaledPaths = self.RealESRGANHandler.UpscaleBatchList(
                ImagePaths,
                OutputDir,
                UpscaleFactor,
                Model,
                ProgressCallback
            )

            return UpscaledPaths

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'upscaling: {e}")
            return []

    def _LoadUpscaledImages(self, UpscaledPaths: List[str],
                           OriginalImages: List[Dict]) -> List[Dict]:
        """
        Charge les images upscalées et les encode en base64

        Args:
            UpscaledPaths: Chemins des images upscalées
            OriginalImages: Images originales (pour récupérer les métadonnées)

        Returns:
            Liste d'images [{id, number, data, filename}]
        """
        ResultImages = []

        try:
            # Crée un mapping filename -> original data
            FilenameMap = {
                img.get("filename"): img
                for img in OriginalImages
            }

            for UpscaledPath in UpscaledPaths:
                Filename = os.path.basename(UpscaledPath)

                # Récupère les métadonnées originales
                OriginalData = FilenameMap.get(Filename, {})

                # Lit l'image upscalée
                with open(UpscaledPath, 'rb') as f:
                    ImageBytes = f.read()

                # Encode en base64
                ImageB64 = base64.b64encode(ImageBytes).decode('utf-8')

                # Crée l'objet résultat
                ResultImages.append({
                    "id": OriginalData.get("id"),
                    "number": OriginalData.get("number"),
                    "data": ImageB64,
                    "filename": Filename
                })

            self.Logger.info(f"✓ {len(ResultImages)} images chargées")
            return ResultImages

        except Exception as e:
            self.Logger.error(f"Erreur lors du chargement des images: {e}")
            return []

    def _Cleanup(self, BatchId: str):
        """
        Nettoie les fichiers temporaires d'un batch

        Args:
            BatchId: ID du batch
        """
        try:
            BatchDir = os.path.join(self.TempDir, BatchId)

            if os.path.exists(BatchDir):
                shutil.rmtree(BatchDir)
                self.Logger.debug(f"Nettoyage: {BatchDir}")

        except Exception as e:
            self.Logger.error(f"Erreur lors du nettoyage: {e}")

    def _CreateErrorResult(self, BatchId: str, ErrorMessage: str) -> BatchResult:
        """
        Crée un résultat d'erreur

        Args:
            BatchId: ID du batch
            ErrorMessage: Message d'erreur

        Returns:
            BatchResult avec erreur
        """
        return BatchResult(
            BatchId=BatchId,
            Success=False,
            UpscaledImages=[],
            ErrorMessage=ErrorMessage
        )

    def CleanupAll(self):
        """Nettoie tous les fichiers temporaires"""
        try:
            if os.path.exists(self.TempDir):
                shutil.rmtree(self.TempDir)
                os.makedirs(self.TempDir, exist_ok=True)
                self.Logger.info("Tous les fichiers temporaires nettoyés")

        except Exception as e:
            self.Logger.error(f"Erreur lors du nettoyage complet: {e}")


# ============================================================================
# EXEMPLE D'UTILISATION
# ============================================================================

if __name__ == "__main__":
    import json

    # Crée un processeur
    Processor = LocalProcessor()

    print("LocalProcessor - Processeur local de batches d'images")
    print(f"Répertoire temporaire: {Processor.TempDir}")
    print(f"Real-ESRGAN: {Processor.RealESRGANHandler.ExecutablePath}")

    # Test avec des données simulées
    TestBatch = {
        "batch_id": "test-123",
        "video_id": "video-456",
        "images": [],  # Vide pour cet exemple
        "upscale_factor": 4,
        "model": "realesr-animevideov3"
    }

    print(f"\nTest de traitement (batch vide):")
    # Result = Processor.ProcessBatch(TestBatch)
    # if Result:
    #     print(f"Résultat: Success={Result.IsSuccess()}")
