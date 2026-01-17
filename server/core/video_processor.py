"""
Processeur vidéo pour l'orchestration du traitement complet
Gère l'extraction, le découpage, le packaging et le réassemblage
"""

import os
import uuid
import shutil
from typing import Optional, List, Tuple
from datetime import datetime
from pathlib import Path

from server.utils.ffmpeg_handler import FFmpegHandler
from server.utils.realesrgan_handler import RealESRGANHandler
from server.database.db_manager import DatabaseManager
from server.database.models import Video, Batch
from shared.utils.logger import GetModuleLogger
from shared.utils.constants import JobStatus, BatchStatus, PathConfig


class VideoProcessor:
    """Processeur vidéo orchestrant le pipeline complet"""

    def __init__(self, WorkDirectory: str, Database: DatabaseManager):
        """
        Initialise le processeur vidéo

        Args:
            WorkDirectory: Répertoire de travail
            Database: Gestionnaire de base de données
        """
        self.WorkDirectory = WorkDirectory
        self.Database = Database
        self.Logger = GetModuleLogger("VideoProcessor")

        # Handlers
        self.FfmpegHandler = FFmpegHandler()
        self.RealESRGANHandler = RealESRGANHandler()

        # Crée la structure des répertoires
        self._EnsureDirectories()

    def _EnsureDirectories(self):
        """S'assure que tous les répertoires nécessaires existent"""
        Directories = [
            PathConfig.INPUT_DIR,
            PathConfig.FRAMES_DIR,
            PathConfig.AUDIO_DIR,
            PathConfig.SUBTITLES_DIR,
            PathConfig.UPSCALED_DIR,
            PathConfig.OUTPUT_DIR,
            PathConfig.TEMP_DIR
        ]

        for Directory in Directories:
            FullPath = os.path.join(self.WorkDirectory, Directory)
            os.makedirs(FullPath, exist_ok=True)

    def GetVideoWorkDir(self, VideoId: str) -> str:
        """Récupère le répertoire de travail d'une vidéo"""
        return os.path.join(self.WorkDirectory, PathConfig.FRAMES_DIR, VideoId)

    def GetAudioDir(self, VideoId: str) -> str:
        """Récupère le répertoire audio d'une vidéo"""
        return os.path.join(self.WorkDirectory, PathConfig.AUDIO_DIR, VideoId)

    def GetSubtitlesDir(self, VideoId: str) -> str:
        """Récupère le répertoire sous-titres d'une vidéo"""
        return os.path.join(self.WorkDirectory, PathConfig.SUBTITLES_DIR, VideoId)

    def GetUpscaledDir(self, VideoId: str) -> str:
        """Récupère le répertoire des images upscalées"""
        return os.path.join(self.WorkDirectory, PathConfig.UPSCALED_DIR, VideoId)

    def ExtractVideoData(self, VideoPath: str, VideoId: str) -> Optional[dict]:
        """
        Extrait les métadonnées et les données d'une vidéo

        Args:
            VideoPath: Chemin vers la vidéo
            VideoId: ID de la vidéo

        Returns:
            Dictionnaire avec les informations extraites ou None
        """
        try:
            self.Logger.info(f"Extraction des données de {os.path.basename(VideoPath)}...")

            # Extrait les métadonnées
            Metadata = self.FfmpegHandler.ExtractVideoMetadata(VideoPath)
            if not Metadata:
                self.Logger.error("Impossible d'extraire les métadonnées")
                return None

            # Extrait le framerate
            Fps = self.FfmpegHandler.ExtractFramerate(VideoPath)
            if not Fps:
                self.Logger.error("Impossible d'extraire le framerate")
                return None

            # Extrait le nombre de frames
            TotalFrames = self.FfmpegHandler.GetTotalFrames(VideoPath)

            # Extrait la durée
            Duration = self.FfmpegHandler.GetVideoDuration(VideoPath)

            # Extrait les pistes audio
            AudioDir = self.GetAudioDir(VideoId)
            AudioTracks = self.FfmpegHandler.ExtractAudioTracks(VideoPath, AudioDir)
            self.Logger.info(f"✓ {len(AudioTracks)} pistes audio extraites")

            # Extrait les sous-titres
            SubtitlesDir = self.GetSubtitlesDir(VideoId)
            Subtitles = self.FfmpegHandler.ExtractSubtitles(VideoPath, SubtitlesDir)
            self.Logger.info(f"✓ {len(Subtitles)} sous-titres extraits")

            return {
                "metadata": Metadata,
                "fps": Fps,
                "total_frames": TotalFrames,
                "duration": Duration,
                "audio_tracks": AudioTracks,
                "subtitles": Subtitles
            }

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'extraction des données: {e}")
            return None

    def VideoToFrames(self, VideoPath: str, VideoId: str) -> bool:
        """
        Découpe une vidéo en images individuelles

        Args:
            VideoPath: Chemin vers la vidéo
            VideoId: ID de la vidéo

        Returns:
            True si succès
        """
        try:
            FramesDir = self.GetVideoWorkDir(VideoId)
            os.makedirs(FramesDir, exist_ok=True)

            self.Logger.info(f"Découpage de la vidéo en images...")
            Success = self.FfmpegHandler.VideoToFrames(VideoPath, FramesDir)

            if Success:
                # Compte les frames créées
                FrameCount = len([f for f in os.listdir(FramesDir) if f.endswith('.png')])
                self.Logger.info(f"✓ {FrameCount} images extraites")

            return Success

        except Exception as e:
            self.Logger.error(f"Erreur lors du découpage: {e}")
            return False

    def CreateBatches(self, VideoId: str, BatchSize: int) -> List[Batch]:
        """
        Crée les paquets d'images pour le traitement distribué

        Args:
            VideoId: ID de la vidéo
            BatchSize: Nombre d'images par paquet

        Returns:
            Liste des batches créés
        """
        try:
            FramesDir = self.GetVideoWorkDir(VideoId)

            # Liste toutes les images
            Frames = sorted([f for f in os.listdir(FramesDir) if f.endswith('.png')])
            TotalFrames = len(Frames)

            self.Logger.info(f"Création des batches ({BatchSize} images/batch)...")

            Batches = []
            for i in range(0, TotalFrames, BatchSize):
                StartFrame = i
                EndFrame = min(i + BatchSize - 1, TotalFrames - 1)
                FrameCount = EndFrame - StartFrame + 1

                # Crée l'objet Batch
                BatchObj = Batch(
                    BatchId=str(uuid.uuid4()),
                    VideoId=VideoId,
                    Status=BatchStatus.PENDING,
                    StartFrame=StartFrame,
                    EndFrame=EndFrame,
                    FrameCount=FrameCount
                )

                # Ajoute à la base de données
                self.Database.AddBatch(BatchObj)
                Batches.append(BatchObj)

            self.Logger.info(f"✓ {len(Batches)} batches créés")
            return Batches

        except Exception as e:
            self.Logger.error(f"Erreur lors de la création des batches: {e}")
            return []

    def GetBatchFrames(self, VideoId: str, Batch: Batch) -> List[str]:
        """
        Récupère les chemins des images d'un batch

        Args:
            VideoId: ID de la vidéo
            Batch: Objet Batch

        Returns:
            Liste des chemins d'images
        """
        try:
            FramesDir = self.GetVideoWorkDir(VideoId)

            # Liste toutes les images
            AllFrames = sorted([f for f in os.listdir(FramesDir) if f.endswith('.png')])

            # Extrait les images du batch
            BatchFrames = AllFrames[Batch.StartFrame:Batch.EndFrame + 1]

            # Construit les chemins complets
            FramePaths = [os.path.join(FramesDir, f) for f in BatchFrames]

            return FramePaths

        except Exception as e:
            self.Logger.error(f"Erreur lors de la récupération des frames du batch: {e}")
            return []

    def ReassembleVideo(self, VideoId: str, Fps: float, UpscaleFactor: int, OriginalVideoName: str = None) -> Optional[str]:
        """
        Réassemble les images upscalées en vidéo finale

        Args:
            VideoId: ID de la vidéo
            Fps: Framerate de la vidéo
            UpscaleFactor: Facteur d'upscaling utilisé
            OriginalVideoName: Nom original de la vidéo (sans extension)

        Returns:
            Chemin de la vidéo finale ou None
        """
        try:
            self.Logger.info(f"Réassemblage de la vidéo {VideoId}...")

            UpscaledDir = self.GetUpscaledDir(VideoId)

            # Vérifie que les images existent
            UpscaledFrames = sorted([f for f in os.listdir(UpscaledDir) if f.endswith('.png')])
            if not UpscaledFrames:
                self.Logger.error("Aucune image upscalée trouvée")
                return None

            self.Logger.info(f"Nombre d'images upscalées: {len(UpscaledFrames)}")

            # Crée une vidéo temporaire (sans audio/sous-titres)
            TempVideoPath = os.path.join(
                self.WorkDirectory,
                PathConfig.TEMP_DIR,
                f"{VideoId}_temp.mp4"
            )

            Success = self.FfmpegHandler.FramesToVideo(
                UpscaledDir,
                TempVideoPath,
                Fps
            )

            if not Success:
                self.Logger.error("Échec du réassemblage")
                return None

            # Récupère les pistes audio et sous-titres
            AudioDir = self.GetAudioDir(VideoId)
            SubtitlesDir = self.GetSubtitlesDir(VideoId)

            AudioTracks = []
            if os.path.exists(AudioDir):
                AudioTracks = [
                    os.path.join(AudioDir, f)
                    for f in os.listdir(AudioDir)
                    if f.startswith('audio_track_')
                ]

            Subtitles = []
            if os.path.exists(SubtitlesDir):
                Subtitles = [
                    os.path.join(SubtitlesDir, f)
                    for f in os.listdir(SubtitlesDir)
                    if f.startswith('subtitle_')
                ]

            # Réintègre audio et sous-titres
            # Construit le nom de fichier avec le nom original si disponible
            if OriginalVideoName:
                OutputFileName = f"{OriginalVideoName}_{VideoId}_x{UpscaleFactor}.mp4"
            else:
                OutputFileName = f"{VideoId}_x{UpscaleFactor}.mp4"

            FinalVideoPath = os.path.join(
                self.WorkDirectory,
                PathConfig.OUTPUT_DIR,
                OutputFileName
            )

            if AudioTracks or Subtitles:
                self.Logger.info("Réintégration audio et sous-titres...")
                Success = self.FfmpegHandler.MergeAudioSubtitles(
                    TempVideoPath,
                    AudioTracks,
                    Subtitles,
                    FinalVideoPath
                )

                # Supprime la vidéo temporaire
                if os.path.exists(TempVideoPath):
                    os.remove(TempVideoPath)

                if not Success:
                    self.Logger.error("Échec de la réintégration audio/sous-titres")
                    return None
            else:
                # Pas d'audio/sous-titres, renomme simplement
                shutil.move(TempVideoPath, FinalVideoPath)

            self.Logger.info(f"✓ Vidéo réassemblée: {FinalVideoPath}")
            return FinalVideoPath

        except Exception as e:
            self.Logger.error(f"Erreur lors du réassemblage: {e}")
            return None

    def EncodeToAV1(self, InputPath: str, VideoId: str, OriginalVideoName: str = None) -> Optional[str]:
        """
        Encode la vidéo finale en AV1

        Args:
            InputPath: Chemin de la vidéo d'entrée
            VideoId: ID de la vidéo
            OriginalVideoName: Nom original de la vidéo (sans extension)

        Returns:
            Chemin de la vidéo AV1 ou None
        """
        try:
            # Construit le nom de fichier avec le nom original si disponible
            if OriginalVideoName:
                OutputFileName = f"{OriginalVideoName}_{VideoId}_av1.mp4"
            else:
                OutputFileName = f"{VideoId}_av1.mp4"

            OutputPath = os.path.join(
                self.WorkDirectory,
                PathConfig.OUTPUT_DIR,
                OutputFileName
            )

            self.Logger.info("Encodage en AV1...")
            Success = self.FfmpegHandler.EncodeToAV1(InputPath, OutputPath)

            if Success:
                self.Logger.info(f"✓ Vidéo encodée en AV1: {OutputPath}")
                return OutputPath

            return None

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'encodage AV1: {e}")
            return None

    def CleanupVideoData(self, VideoId: str, KeepOutput: bool = True):
        """
        Nettoie les données temporaires d'une vidéo

        Args:
            VideoId: ID de la vidéo
            KeepOutput: Garde la vidéo de sortie
        """
        try:
            self.Logger.info(f"Nettoyage des données de {VideoId}...")

            # Supprime les répertoires temporaires
            DirsToClean = [
                self.GetVideoWorkDir(VideoId),
                self.GetAudioDir(VideoId),
                self.GetSubtitlesDir(VideoId),
                self.GetUpscaledDir(VideoId)
            ]

            for Directory in DirsToClean:
                if os.path.exists(Directory):
                    shutil.rmtree(Directory)
                    self.Logger.debug(f"Supprimé: {Directory}")

            if not KeepOutput:
                OutputDir = os.path.join(self.WorkDirectory, PathConfig.OUTPUT_DIR)
                for File in os.listdir(OutputDir):
                    if File.startswith(VideoId):
                        FilePath = os.path.join(OutputDir, File)
                        os.remove(FilePath)
                        self.Logger.debug(f"Supprimé: {FilePath}")

            self.Logger.info("✓ Nettoyage terminé")

        except Exception as e:
            self.Logger.error(f"Erreur lors du nettoyage: {e}")

    def CleanupVideoFiles(self, VideoId: str):
        """
        Nettoie tous les fichiers temporaires d'une vidéo annulée

        Args:
            VideoId: ID de la vidéo
        """
        self.CleanupVideoData(VideoId, KeepOutput=False)

    def GetVideoProgress(self, VideoId: str) -> Tuple[int, int, float]:
        """
        Récupère la progression d'une vidéo

        Args:
            VideoId: ID de la vidéo

        Returns:
            Tuple (batches_complétés, batches_total, progression_%)
        """
        try:
            Video = self.Database.GetVideo(VideoId)
            if not Video:
                return (0, 0, 0.0)

            return (Video.CompletedBatches, Video.TotalBatches, Video.Progress * 100)

        except Exception as e:
            self.Logger.error(f"Erreur lors de la récupération de la progression: {e}")
            return (0, 0, 0.0)


# ============================================================================
# EXEMPLE D'UTILISATION
# ============================================================================

if __name__ == "__main__":
    import json
    from server.database.db_manager import DatabaseManager

    # Configuration de test
    WorkDir = "./test_work"
    DbPath = os.path.join(WorkDir, "test.db")

    # Crée la base de données
    Db = DatabaseManager(DbPath)
    Db.Connect()

    # Crée le processeur
    Processor = VideoProcessor(WorkDir, Db)

    print("\n=== Test VideoProcessor ===")
    print(f"Répertoire de travail: {WorkDir}")
    print(f"FFmpeg: {Processor.FfmpegHandler.FfmpegPath}")
    print(f"Real-ESRGAN: {Processor.RealESRGANHandler.ExecutablePath}")

    # Test avec une vidéo (si disponible)
    TestVideo = "test.mp4"
    if os.path.exists(TestVideo):
        print(f"\nTest avec {TestVideo}")

        VideoId = str(uuid.uuid4())
        print(f"ID vidéo: {VideoId}")

        # Extrait les données
        Data = Processor.ExtractVideoData(TestVideo, VideoId)
        if Data:
            print(f"FPS: {Data['fps']}")
            print(f"Frames: {Data['total_frames']}")
            print(f"Audio: {len(Data['audio_tracks'])} pistes")
            print(f"Sous-titres: {len(Data['subtitles'])}")
    else:
        print(f"\n⚠ Vidéo de test {TestVideo} non trouvée")

    # Ferme la base de données
    Db.Close()
