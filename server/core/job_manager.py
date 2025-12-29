"""
Gestionnaire de jobs pour l'orchestration du traitement vidéo
Gère la file d'attente FIFO et le pipeline complet
"""

import asyncio
import os
import uuid
import time
from typing import Optional, List
from datetime import datetime

from server.core.video_processor import VideoProcessor
from server.core.batch_distributor import BatchDistributor
from server.database.db_manager import DatabaseManager
from server.database.models import Video
from shared.utils.logger import GetModuleLogger
from shared.utils.constants import JobStatus


class JobManager:
    """Gestionnaire de jobs vidéo"""

    def __init__(self, VideoProcessor: VideoProcessor,
                 BatchDistributor: BatchDistributor,
                 Database: DatabaseManager,
                 BatchSize: int = 100):
        """
        Initialise le gestionnaire de jobs

        Args:
            VideoProcessor: Processeur vidéo
            BatchDistributor: Distributeur de paquets
            Database: Gestionnaire de base de données
            BatchSize: Taille des paquets d'images
        """
        self.VideoProcessor = VideoProcessor
        self.BatchDistributor = BatchDistributor
        self.Database = Database
        self.BatchSize = BatchSize
        self.Logger = GetModuleLogger("JobManager")

        self.Running = False
        self.CurrentJobId = None
        self.JobTask = None

    async def Start(self):
        """Démarre le gestionnaire de jobs"""
        if self.Running:
            self.Logger.warning("JobManager déjà en cours d'exécution")
            return

        self.Running = True
        self.Logger.info("JobManager démarré")

        # Lance la boucle de traitement
        self.JobTask = asyncio.create_task(self._JobLoop())

    async def Stop(self):
        """Arrête le gestionnaire de jobs"""
        self.Running = False

        if self.JobTask:
            self.JobTask.cancel()
            try:
                await self.JobTask
            except asyncio.CancelledError:
                pass

        self.Logger.info("JobManager arrêté")

    async def _JobLoop(self):
        """Boucle principale de traitement des jobs"""
        try:
            while self.Running:
                # Vérifie s'il y a un job en cours
                if self.CurrentJobId:
                    # Attend que le job se termine
                    await asyncio.sleep(5)
                    continue

                # Récupère le prochain job en attente
                NextJob = self.GetNextQueuedJob()

                if not NextJob:
                    # Aucun job en attente
                    await asyncio.sleep(5)
                    continue

                # Traite le job
                await self.ProcessJob(NextJob.VideoId)

        except asyncio.CancelledError:
            self.Logger.info("Boucle de jobs annulée")
        except Exception as e:
            self.Logger.error(f"Erreur dans la boucle de jobs: {e}")

    def AddVideo(self, VideoPath: str, UpscaleFactor: int = 4,
                 Model: str = "realesr-animevideov3", TtaMode: bool = False) -> Optional[str]:
        """
        Ajoute une vidéo à la file d'attente

        Args:
            VideoPath: Chemin vers la vidéo
            UpscaleFactor: Facteur d'upscaling (2, 3, ou 4)
            Model: Modèle Real-ESRGAN
            TtaMode: Mode TTA pour meilleure qualité (plus lent)

        Returns:
            ID de la vidéo ou None si erreur
        """
        try:
            # Vérifie que la vidéo existe
            if not os.path.exists(VideoPath):
                self.Logger.error(f"Vidéo non trouvée: {VideoPath}")
                return None

            # Génère un ID
            VideoId = str(uuid.uuid4())

            # Crée l'objet Video
            VideoObj = Video(
                VideoId=VideoId,
                VideoPath=os.path.abspath(VideoPath),
                Status=JobStatus.QUEUED,
                UpscaleFactor=UpscaleFactor,
                Model=Model,
                TtaMode=TtaMode,
                CreatedAt=datetime.now()
            )

            # Ajoute à la base de données
            Success = self.Database.AddVideo(VideoObj)

            if Success:
                self.Logger.info(f"✓ Vidéo ajoutée à la file: {os.path.basename(VideoPath)} (ID: {VideoId})")
                return VideoId
            else:
                self.Logger.error("Échec de l'ajout de la vidéo")
                return None

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'ajout de la vidéo: {e}")
            return None

    def CancelVideo(self, VideoId: str) -> bool:
        """
        Annule le traitement d'une vidéo

        Args:
            VideoId: ID de la vidéo à annuler

        Returns:
            True si succès
        """
        try:
            # Récupère la vidéo
            VideoObj = self.Database.GetVideo(VideoId)
            if not VideoObj:
                self.Logger.error(f"Vidéo non trouvée: {VideoId}")
                return False

            # Vérifie si la vidéo peut être annulée
            if VideoObj.Status == JobStatus.COMPLETED:
                self.Logger.warning(f"Vidéo déjà terminée: {VideoId}")
                return False

            self.Logger.info(f"Annulation de la vidéo {VideoId}...")

            # Si c'est le job en cours, on l'arrête
            if self.CurrentJobId == VideoId:
                self.CurrentJobId = None
                # Annuler les batches en cours
                self.BatchDistributor.CancelVideoProcessing(VideoId)

            # Supprime les batches associés
            Batches = self.Database.GetBatchesByVideo(VideoId)
            for Batch in Batches:
                self.Database.DeleteBatch(Batch.BatchId)

            # Met à jour le statut de la vidéo
            VideoObj.Status = JobStatus.FAILED
            VideoObj.ErrorMessage = "Annulé par l'utilisateur"
            self.Database.UpdateVideo(VideoObj)

            # Supprime les fichiers temporaires
            self.VideoProcessor.CleanupVideoFiles(VideoId)

            self.Logger.info(f"✓ Vidéo annulée: {VideoId}")
            return True

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'annulation: {e}")
            return False

    def GetNextQueuedJob(self) -> Optional[Video]:
        """
        Récupère le prochain job en attente

        Returns:
            Objet Video ou None
        """
        QueuedVideos = self.Database.GetQueuedVideos()

        if QueuedVideos:
            return QueuedVideos[0]  # FIFO - première vidéo

        return None

    def GetCurrentJob(self) -> Optional[Video]:
        """
        Récupère le job en cours

        Returns:
            Objet Video ou None
        """
        if self.CurrentJobId:
            return self.Database.GetVideo(self.CurrentJobId)

        return None

    async def ProcessJob(self, VideoId: str) -> bool:
        """
        Traite une vidéo complètement

        Args:
            VideoId: ID de la vidéo

        Returns:
            True si succès
        """
        try:
            self.CurrentJobId = VideoId
            StartTime = time.time()

            self.Logger.info("="*60)
            self.Logger.info(f"DÉBUT DU TRAITEMENT - Vidéo {VideoId}")
            self.Logger.info("="*60)

            # Récupère la vidéo
            VideoObj = self.Database.GetVideo(VideoId)
            if not VideoObj:
                self.Logger.error(f"Vidéo {VideoId} non trouvée")
                self.CurrentJobId = None
                return False

            # Phase 1: EXTRACTION
            Success = await self._PhaseExtraction(VideoObj)
            if not Success:
                await self._MarkJobFailed(VideoObj, "Échec de l'extraction")
                self.CurrentJobId = None
                return False

            # Phase 2: DÉCOUPAGE
            Success = await self._PhaseDecoupage(VideoObj)
            if not Success:
                await self._MarkJobFailed(VideoObj, "Échec du découpage")
                self.CurrentJobId = None
                return False

            # Phase 3: DISTRIBUTION
            Success = await self._PhaseDistribution(VideoObj)
            if not Success:
                await self._MarkJobFailed(VideoObj, "Échec de la distribution")
                self.CurrentJobId = None
                return False

            # Phase 4: RÉASSEMBLAGE
            Success = await self._PhaseReassemblage(VideoObj)
            if not Success:
                await self._MarkJobFailed(VideoObj, "Échec du réassemblage")
                self.CurrentJobId = None
                return False

            # Phase 5: ENCODAGE (optionnel)
            # await self._PhaseEncodage(VideoObj)

            # Marque comme complété
            Duration = time.time() - StartTime
            VideoObj.Status = JobStatus.COMPLETED
            VideoObj.CompletedAt = datetime.now()
            self.Database.UpdateVideo(VideoObj)

            self.Logger.info("="*60)
            self.Logger.info(f"✓ TRAITEMENT TERMINÉ - Durée: {Duration:.1f}s")
            self.Logger.info(f"Sortie: {VideoObj.OutputPath}")
            self.Logger.info("="*60)

            # Cleanup optionnel
            # self.VideoProcessor.CleanupVideoData(VideoId, KeepOutput=True)

            self.CurrentJobId = None
            return True

        except Exception as e:
            self.Logger.error(f"Erreur lors du traitement du job: {e}")
            self.CurrentJobId = None
            return False

    async def _PhaseExtraction(self, VideoObj: Video) -> bool:
        """Phase 1: Extraction des données vidéo"""
        try:
            self.Logger.info("PHASE 1: EXTRACTION")
            VideoObj.Status = JobStatus.EXTRACTING
            VideoObj.StartedAt = datetime.now()
            self.Database.UpdateVideo(VideoObj)

            # Extrait les métadonnées, audio, sous-titres
            VideoData = self.VideoProcessor.ExtractVideoData(
                VideoObj.VideoPath,
                VideoObj.VideoId
            )

            if not VideoData:
                return False

            # Met à jour les informations
            VideoObj.Framerate = VideoData["fps"]
            VideoObj.TotalFrames = VideoData["total_frames"]
            self.Database.UpdateVideo(VideoObj)

            self.Logger.info(f"✓ Extraction terminée (FPS: {VideoData['fps']:.2f}, Frames: {VideoData['total_frames']})")
            return True

        except Exception as e:
            self.Logger.error(f"Erreur phase extraction: {e}")
            return False

    async def _PhaseDecoupage(self, VideoObj: Video) -> bool:
        """Phase 2: Découpage en images"""
        try:
            self.Logger.info("PHASE 2: DÉCOUPAGE EN IMAGES")
            VideoObj.Status = JobStatus.DISTRIBUTING
            self.Database.UpdateVideo(VideoObj)

            # Découpe la vidéo en images
            Success = self.VideoProcessor.VideoToFrames(
                VideoObj.VideoPath,
                VideoObj.VideoId
            )

            if not Success:
                return False

            # Crée les batches
            Batches = self.VideoProcessor.CreateBatches(
                VideoObj.VideoId,
                self.BatchSize
            )

            if not Batches:
                return False

            # Met à jour le nombre de batches
            VideoObj.TotalBatches = len(Batches)
            VideoObj.CompletedBatches = 0
            VideoObj.Progress = 0.0
            self.Database.UpdateVideo(VideoObj)

            self.Logger.info(f"✓ Découpage terminé ({len(Batches)} batches)")
            return True

        except Exception as e:
            self.Logger.error(f"Erreur phase découpage: {e}")
            return False

    async def _PhaseDistribution(self, VideoObj: Video) -> bool:
        """Phase 3: Distribution aux clients"""
        try:
            self.Logger.info("PHASE 3: DISTRIBUTION AUX CLIENTS")
            VideoObj.Status = JobStatus.PROCESSING
            self.Database.UpdateVideo(VideoObj)

            # Démarre la distribution
            await self.BatchDistributor.StartDistribution(VideoObj.VideoId)

            # Attend que tous les batches soient complétés
            while True:
                Stats = self.BatchDistributor.GetDistributionStats(VideoObj.VideoId)

                self.Logger.info(
                    f"Distribution: {Stats['completed']}/{Stats['total']} batches "
                    f"(Processing: {Stats['processing']}, Failed: {Stats['failed']})"
                )

                # Tous complétés?
                if Stats['completed'] == Stats['total']:
                    break

                # Trop d'échecs?
                if Stats['failed'] > Stats['total'] * 0.5:  # >50% échec
                    self.Logger.error("Trop de batches échoués")
                    await self.BatchDistributor.StopDistribution()
                    return False

                await asyncio.sleep(5)

            # Arrête la distribution
            await self.BatchDistributor.StopDistribution()

            self.Logger.info("✓ Distribution terminée")
            return True

        except Exception as e:
            self.Logger.error(f"Erreur phase distribution: {e}")
            return False

    async def _PhaseReassemblage(self, VideoObj: Video) -> bool:
        """Phase 4: Réassemblage de la vidéo"""
        try:
            self.Logger.info("PHASE 4: RÉASSEMBLAGE")
            VideoObj.Status = JobStatus.REASSEMBLING
            self.Database.UpdateVideo(VideoObj)

            # Réassemble la vidéo
            OutputPath = self.VideoProcessor.ReassembleVideo(
                VideoObj.VideoId,
                VideoObj.Framerate,
                VideoObj.UpscaleFactor
            )

            if not OutputPath:
                return False

            VideoObj.OutputPath = OutputPath
            self.Database.UpdateVideo(VideoObj)

            self.Logger.info(f"✓ Réassemblage terminé: {OutputPath}")
            return True

        except Exception as e:
            self.Logger.error(f"Erreur phase réassemblage: {e}")
            return False

    async def _PhaseEncodage(self, VideoObj: Video) -> bool:
        """Phase 5: Encodage en AV1 (optionnel)"""
        try:
            self.Logger.info("PHASE 5: ENCODAGE AV1")
            VideoObj.Status = JobStatus.ENCODING
            self.Database.UpdateVideo(VideoObj)

            if not VideoObj.OutputPath:
                return False

            # Encode en AV1
            AV1Path = self.VideoProcessor.EncodeToAV1(
                VideoObj.OutputPath,
                VideoObj.VideoId
            )

            if AV1Path:
                # Remplace le chemin de sortie
                VideoObj.OutputPath = AV1Path
                self.Database.UpdateVideo(VideoObj)
                self.Logger.info("✓ Encodage AV1 terminé")
                return True
            else:
                self.Logger.warning("Encodage AV1 échoué, garde la version H264")
                return True  # Pas bloquant

        except Exception as e:
            self.Logger.error(f"Erreur phase encodage: {e}")
            return True  # Pas bloquant

    async def _MarkJobFailed(self, VideoObj: Video, ErrorMessage: str):
        """Marque un job comme échoué"""
        VideoObj.Status = JobStatus.FAILED
        VideoObj.ErrorMessage = ErrorMessage
        VideoObj.CompletedAt = datetime.now()
        self.Database.UpdateVideo(VideoObj)

        self.Logger.error(f"✗ JOB ÉCHOUÉ: {ErrorMessage}")

    def GetJobProgress(self, VideoId: str) -> dict:
        """
        Récupère la progression d'un job

        Args:
            VideoId: ID de la vidéo

        Returns:
            Dictionnaire de progression
        """
        VideoObj = self.Database.GetVideo(VideoId)

        if not VideoObj:
            return {}

        return {
            "video_id": VideoId,
            "status": VideoObj.Status,
            "total_batches": VideoObj.TotalBatches,
            "completed_batches": VideoObj.CompletedBatches,
            "progress": VideoObj.Progress * 100,
            "output_path": VideoObj.OutputPath
        }

    def GetQueueStatus(self) -> dict:
        """
        Récupère le statut de la file d'attente

        Returns:
            Dictionnaire de statut
        """
        QueuedVideos = self.Database.GetQueuedVideos()
        CurrentJob = self.GetCurrentJob()

        return {
            "current_job": CurrentJob.VideoId if CurrentJob else None,
            "queued_count": len(QueuedVideos),
            "queued_videos": [
                {
                    "video_id": v.VideoId,
                    "video_path": v.VideoPath,
                    "created_at": v.CreatedAt.isoformat() if v.CreatedAt else None
                }
                for v in QueuedVideos
            ]
        }


# ============================================================================
# EXEMPLE D'UTILISATION
# ============================================================================

if __name__ == "__main__":
    print("JobManager - Gestionnaire de jobs pour traitement vidéo distribué")
    print("Doit être utilisé dans le contexte du serveur complet")
