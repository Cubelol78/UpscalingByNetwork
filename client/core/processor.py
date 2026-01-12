"""
Processeur local pour le traitement des batches d'images
Reçoit des images, les upscale et renvoie les résultats
Supporte la configuration de performance pour Real-ESRGAN
"""

import os
import base64
import shutil
import concurrent.futures
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from client.utils.realesrgan_handler import RealESRGANHandler
from client.utils.performance_config import PerformanceConfigManager
from shared.utils.logger import GetClientLogger
from shared.protocol.messages import BatchResult


class LocalProcessor:
    """Processeur local de batches d'images avec support des performances"""

    def __init__(self, TempDirectory: Optional[str] = None, PerformanceConfig: Optional[Dict] = None):
        """
        Initialise le processeur local

        Args:
            TempDirectory: Répertoire temporaire (défaut: ~/.upscaling_client/temp)
            PerformanceConfig: Configuration de performance (optionnel)
        """
        self.Logger = GetClientLogger()

        # Répertoire temporaire
        if TempDirectory:
            self.TempDir = TempDirectory
        else:
            self.TempDir = os.path.join(Path.home(), '.upscaling_client', 'temp')

        os.makedirs(self.TempDir, exist_ok=True)

        # Charge la configuration de performance
        self.PerformanceConfigManager = PerformanceConfigManager()
        if PerformanceConfig:
            self.PerformanceConfig = PerformanceConfig
        else:
            self.PerformanceConfig = self.PerformanceConfigManager.Load()

        # Handler Real-ESRGAN avec configuration de performance
        self.RealESRGANHandler = RealESRGANHandler(PerformanceConfig=self.PerformanceConfig)

        self.Logger.info("Processeur local initialisé")
        self._LogPerformanceConfig()

    def _LogPerformanceConfig(self):
        """Affiche la configuration de performance active"""
        TileSize = self.PerformanceConfig.get('tile_size', 0)
        GpuIds = self.PerformanceConfig.get('gpu_ids', [])

        ConfigStr = []
        if TileSize:
            ConfigStr.append(f"tile={TileSize}")
        if GpuIds:
            ConfigStr.append(f"GPU={','.join(map(str, GpuIds))}")
        # Note: TTA est configuré par le serveur, pas en local

        if ConfigStr:
            self.Logger.info(f"Config performance: {', '.join(ConfigStr)}")

    def UpdatePerformanceConfig(self, NewConfig: Dict):
        """
        Met à jour la configuration de performance

        Args:
            NewConfig: Nouvelle configuration
        """
        self.PerformanceConfig = NewConfig
        self.RealESRGANHandler.SetPerformanceConfig(NewConfig)
        self.Logger.info("Configuration de performance mise à jour")
        self._LogPerformanceConfig()

    def ReloadPerformanceConfig(self):
        """Recharge la configuration de performance depuis le fichier"""
        self.PerformanceConfig = self.PerformanceConfigManager.Load()
        self.RealESRGANHandler.SetPerformanceConfig(self.PerformanceConfig)
        self.Logger.info("Configuration de performance rechargée")
        self._LogPerformanceConfig()

    def _ApplyServerTtaMode(self, TtaMode: bool):
        """
        Applique le mode TTA défini par le serveur (override la config locale)

        Args:
            TtaMode: Mode TTA à appliquer
        """
        # Crée une copie de la config avec le TTA du serveur
        CurrentConfig = self.RealESRGANHandler.PerformanceConfig.copy()
        CurrentConfig['tta_mode'] = TtaMode
        self.RealESRGANHandler.SetPerformanceConfig(CurrentConfig)

    def ProcessBatch(self, BatchData: Dict[str, Any], ProgressCallback=None) -> Optional[BatchResult]:
        """
        Traite un batch d'images

        Args:
            BatchData: Données du batch (depuis BatchAssignment)
            ProgressCallback: Callback optionnel appelé avec (current, total) pour la progression

        Returns:
            BatchResult ou None si erreur
        """
        BatchId: str = ""
        try:
            BatchId = BatchData.get("batch_id", "")
            if not BatchId:
                self.Logger.error("BatchId manquant dans les données du batch")
                return None

            VideoId = BatchData.get("video_id", "")
            Images = BatchData.get("images", [])
            UpscaleFactor = BatchData.get("upscale_factor", 4)
            Model = BatchData.get("model", "realesr-animevideov3")
            TtaMode = BatchData.get("tta_mode", False)  # TTA défini par le serveur

            self.Logger.info(f"Traitement du batch {BatchId}")
            self.Logger.info(f"  Vidéo: {VideoId}")
            self.Logger.info(f"  Images: {len(Images)}")
            self.Logger.info(f"  Facteur: x{UpscaleFactor}")
            self.Logger.info(f"  Modèle: {Model}")
            self.Logger.info(f"  Mode TTA: {'Oui' if TtaMode else 'Non'}")

            # Applique le TtaMode du serveur (override la config locale)
            self._ApplyServerTtaMode(TtaMode)

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
            UpscaledImages, UpscaleError = self._UpscaleImages(
                SavedImages,
                OutputDir,
                UpscaleFactor,
                Model,
                ProgressCallback
            )

            if not UpscaledImages:
                self.Logger.error("Échec de l'upscaling")
                # Propage les détails de l'erreur Real-ESRGAN pour analyse
                ErrorMsg = UpscaleError if UpscaleError else "Échec de l'upscaling"
                return self._CreateErrorResult(BatchId, ErrorMsg)

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
        Sauvegarde les images reçues en base64 (parallélisé)

        Args:
            Images: Liste d'images [{id, number, data, filename}]
            OutputDir: Répertoire de sortie

        Returns:
            Liste des chemins des images sauvegardées
        """
        def SaveSingleImage(ImageData: Dict) -> Optional[str]:
            """Décode et sauvegarde une seule image"""
            try:
                ImageId = ImageData.get("id", "unknown")
                ImageB64 = ImageData.get("data")
                Filename = ImageData.get("filename", f"frame_{ImageId}.png")

                if not ImageB64:
                    self.Logger.warning(f"Image {ImageId} sans données, ignorée")
                    return None

                # Décode l'image
                ImageBytes = base64.b64decode(ImageB64)

                # Sauvegarde
                OutputPath = os.path.join(OutputDir, Filename)
                with open(OutputPath, 'wb') as f:
                    f.write(ImageBytes)

                return OutputPath

            except Exception as e:
                self.Logger.error(f"Erreur lors de la sauvegarde de l'image {ImageData.get('id', 'unknown')}: {e}")
                return None

        try:
            # Parallélise le décodage et l'écriture avec ThreadPoolExecutor
            # Utilise min(32, nb_cpu * 2) workers pour éviter de surcharger le système
            MaxWorkers = min(32, (os.cpu_count() or 4) * 2)

            SavedPaths = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=MaxWorkers) as executor:
                # Soumet toutes les tâches
                Futures = [executor.submit(SaveSingleImage, ImageData) for ImageData in Images]

                # Récupère les résultats
                for Future in concurrent.futures.as_completed(Futures):
                    Result = Future.result()
                    if Result:
                        SavedPaths.append(Result)

            self.Logger.info(f"✓ {len(SavedPaths)} images sauvegardées (décodage parallèle avec {MaxWorkers} threads)")
            return SavedPaths

        except Exception as e:
            self.Logger.error(f"Erreur lors de la sauvegarde des images: {e}")
            return []

    def _UpscaleImages(self, ImagePaths: List[str], OutputDir: str,
                      UpscaleFactor: int, Model: str, ExternalProgressCallback=None) -> Tuple[List[str], str]:
        """
        Upscale les images avec Real-ESRGAN

        Args:
            ImagePaths: Liste des chemins d'images à upscaler
            OutputDir: Répertoire de sortie
            UpscaleFactor: Facteur d'upscaling
            Model: Modèle à utiliser
            ExternalProgressCallback: Callback externe pour la progression (pour le GUI)

        Returns:
            Tuple (UpscaledPaths, ErrorDetails):
                - UpscaledPaths: Liste des chemins des images upscalées
                - ErrorDetails: Détails de l'erreur si échec, chaîne vide sinon
        """
        try:
            self.Logger.info(f"Upscaling de {len(ImagePaths)} images...")

            # Upscale les images avec le callback externe pour le GUI
            UpscaledPaths, ErrorDetails = self.RealESRGANHandler.UpscaleBatchList(
                ImagePaths,
                OutputDir,
                UpscaleFactor,
                Model,
                ExternalProgressCallback  # Passe directement le callback du client
            )

            return UpscaledPaths, ErrorDetails

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'upscaling: {e}")
            return [], str(e)

    def _LoadUpscaledImages(self, UpscaledPaths: List[str],
                           OriginalImages: List[Dict]) -> List[Dict]:
        """
        Charge les images upscalées et les encode en base64 (parallélisé)

        Args:
            UpscaledPaths: Chemins des images upscalées
            OriginalImages: Images originales (pour récupérer les métadonnées)

        Returns:
            Liste d'images [{id, number, data, filename}]
        """
        # Crée un mapping filename -> original data
        FilenameMap = {
            img.get("filename"): img
            for img in OriginalImages
        }

        def LoadAndEncodeSingleImage(UpscaledPath: str) -> Optional[Dict]:
            """Charge et encode une seule image"""
            try:
                Filename = os.path.basename(UpscaledPath)

                # Récupère les métadonnées originales
                OriginalData = FilenameMap.get(Filename, {})

                # Lit l'image upscalée
                with open(UpscaledPath, 'rb') as f:
                    ImageBytes = f.read()

                # Encode en base64
                ImageB64 = base64.b64encode(ImageBytes).decode('utf-8')

                # Crée l'objet résultat
                return {
                    "id": OriginalData.get("id"),
                    "number": OriginalData.get("number"),
                    "data": ImageB64,
                    "filename": Filename
                }

            except Exception as e:
                self.Logger.error(f"Erreur lors du chargement de l'image {UpscaledPath}: {e}")
                return None

        try:
            # Parallélise le chargement et l'encodage avec ThreadPoolExecutor
            MaxWorkers = min(32, (os.cpu_count() or 4) * 2)

            ResultImages = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=MaxWorkers) as executor:
                # Soumet toutes les tâches
                Futures = [executor.submit(LoadAndEncodeSingleImage, Path) for Path in UpscaledPaths]

                # Récupère les résultats
                for Future in concurrent.futures.as_completed(Futures):
                    Result = Future.result()
                    if Result:
                        ResultImages.append(Result)

            self.Logger.info(f"✓ {len(ResultImages)} images chargées (encodage parallèle avec {MaxWorkers} threads)")
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
