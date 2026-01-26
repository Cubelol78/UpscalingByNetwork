"""
Gestionnaire de jobs pour l'orchestration du traitement vidéo
Gère la file d'attente FIFO et le pipeline complet
"""

import asyncio
import os
import shutil
import uuid
import time
from typing import Optional, List
from datetime import datetime

from server.core.video_processor import VideoProcessor
from server.core.batch_distributor import BatchDistributor
from server.database.db_manager import DatabaseManager
from server.database.models import Video
from shared.utils.logger import GetModuleLogger
from shared.utils.constants import JobStatus, ProcessingConfig
from shared.utils.webhook_manager import TriggerServerWebhook


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

        # HAUTE Problème 6: Lock pour protéger CurrentJobId des race conditions
        # Risque: CancelVideo et ProcessJob modifient CurrentJobId concurrentiellement
        self.CurrentJobIdLock = asyncio.Lock()

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
        """Arrête le gestionnaire de jobs avec sauvegarde de l'état"""
        self.Logger.info("Arrêt du gestionnaire de jobs...")

        self.Running = False

        # Sauvegarde l'état du job en cours
        await self._SaveCurrentJobState()

        # Annule la tâche de traitement
        if self.JobTask:
            self.JobTask.cancel()
            try:
                await self.JobTask
            except asyncio.CancelledError:
                self.Logger.debug("Tâche de traitement des jobs annulée")

        self.Logger.info("✓ JobManager arrêté")

    async def _SaveCurrentJobState(self):
        """
        Sauvegarde l'état du job en cours avant l'arrêt.
        Si un job est en cours de traitement, son état est sauvegardé dans la base
        de données pour permettre une reprise ultérieure.
        """
        try:
            # Protège l'accès à CurrentJobId
            async with self.CurrentJobIdLock:
                if not self.CurrentJobId:
                    self.Logger.debug("Aucun job en cours")
                    return

                CurrentJobIdCopy = self.CurrentJobId

            self.Logger.info(f"Sauvegarde de l'état du job en cours: {CurrentJobIdCopy}")

            # Récupère l'objet Video (qui contient l'état du job)
            video_obj = self.Database.GetVideo(CurrentJobIdCopy)

            if video_obj:
                # Log l'état actuel du job
                self.Logger.info(
                    f"Job {CurrentJobIdCopy}: status={video_obj.Status}, "
                    f"progress={video_obj.Progress*100:.1f}%, "
                    f"batches={video_obj.CompletedBatches}/{video_obj.TotalBatches}"
                )

                # La base de données contient déjà l'état à jour
                # Les batches ont été sauvegardés par BatchDistributor
                # Pas besoin de modifications supplémentaires

                self.Logger.info(
                    f"✓ État du job sauvegardé. "
                    f"Le traitement pourra reprendre au prochain démarrage."
                )
            else:
                self.Logger.warning(f"Job {CurrentJobIdCopy} introuvable dans la base de données")

            # Réinitialise l'état du JobManager (protégé par lock)
            async with self.CurrentJobIdLock:
                self.CurrentJobId = None

        except Exception as e:
            # MOYENNE Problème 7: WARNING au lieu d'ERROR (pas critique)
            self.Logger.warning(f"Erreur lors de la sauvegarde de l'état du job: {e}")

    async def _JobLoop(self):
        """Boucle principale de traitement des jobs"""
        try:
            while self.Running:
                # Vérifie s'il y a un job en cours (protégé par lock)
                async with self.CurrentJobIdLock:
                    HasCurrentJob = self.CurrentJobId is not None

                if HasCurrentJob:
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
                 Engine: str = "realesrgan", Model: str = "realesr-animevideov3",
                 DenoiseLevel: int = -1, TtaMode: bool = False) -> Optional[str]:
        """
        Ajoute une vidéo à la file d'attente

        Args:
            VideoPath: Chemin vers la vidéo
            UpscaleFactor: Facteur d'upscaling (2, 3, ou 4)
            Engine: Engine d'upscaling (realesrgan ou realcugan)
            Model: Modèle à utiliser
            DenoiseLevel: Niveau de débruitage pour Real-CUGAN (-1 = auto)
            TtaMode: Mode TTA pour meilleure qualité (plus lent)

        Returns:
            ID de la vidéo ou None si erreur
        """
        try:
            # Vérifie que la vidéo existe
            if not os.path.exists(VideoPath):
                self.Logger.error(f"Vidéo non trouvée: {VideoPath}")
                return None

            # Valide la combinaison modèle/scale
            if not ProcessingConfig.ValidateModelScale(Engine, Model, UpscaleFactor):
                SupportedScales = ProcessingConfig.GetSupportedScales(Engine, Model)
                self.Logger.error(
                    f"Combinaison invalide: {Model} ne supporte pas x{UpscaleFactor}. "
                    f"Scales supportés: {SupportedScales}"
                )
                return None

            # Valide le niveau de denoise pour Real-CUGAN
            if Engine == ProcessingConfig.ENGINE_REALCUGAN:
                if not ProcessingConfig.ValidateModelDenoise(Model, DenoiseLevel):
                    SupportedLevels = ProcessingConfig.GetSupportedDenoiseLevels(Model)
                    self.Logger.error(
                        f"Combinaison invalide: {Model} ne supporte pas denoise {DenoiseLevel}. "
                        f"Niveaux supportés: {SupportedLevels}"
                    )
                    return None

            # Génère un ID
            VideoId = str(uuid.uuid4())

            # Crée l'objet Video
            VideoObj = Video(
                VideoId=VideoId,
                VideoPath=os.path.abspath(VideoPath),
                Status=JobStatus.QUEUED,
                UpscaleFactor=UpscaleFactor,
                Engine=Engine,
                Model=Model,
                DenoiseLevel=DenoiseLevel,
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
            # Note: Petite race condition acceptable ici (fonction synchrone appelée du GUI)
            # La protection principale est dans ProcessJob (async)
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
            # Enregistre le job en cours (protégé par lock)
            async with self.CurrentJobIdLock:
                self.CurrentJobId = VideoId
            StartTime = time.time()

            self.Logger.info("="*60)
            self.Logger.info(f"DÉBUT DU TRAITEMENT - Vidéo {VideoId}")
            self.Logger.info("="*60)

            # Récupère la vidéo
            VideoObj = self.Database.GetVideo(VideoId)
            VideoName = os.path.basename(VideoObj.VideoPath) if VideoObj else VideoId

            # Webhook: job démarré
            TriggerServerWebhook("job_started", video_name=VideoName, video_id=VideoId)
            if not VideoObj:
                self.Logger.error(f"Vidéo {VideoId} non trouvée")
                async with self.CurrentJobIdLock:
                    self.CurrentJobId = None
                return False

            # Phase 1: EXTRACTION
            Success = await self._PhaseExtraction(VideoObj)
            if not Success:
                await self._MarkJobFailed(VideoObj, "Échec de l'extraction")
                async with self.CurrentJobIdLock:
                    self.CurrentJobId = None
                return False

            # Phase 2: DÉCOUPAGE
            Success = await self._PhaseDecoupage(VideoObj)
            if not Success:
                await self._MarkJobFailed(VideoObj, "Échec du découpage")
                async with self.CurrentJobIdLock:
                    self.CurrentJobId = None
                return False

            # Phase 3: DISTRIBUTION
            Success = await self._PhaseDistribution(VideoObj)
            if not Success:
                await self._MarkJobFailed(VideoObj, "Échec de la distribution")
                async with self.CurrentJobIdLock:
                    self.CurrentJobId = None
                return False

            # Phase 4: RÉASSEMBLAGE
            Success = await self._PhaseReassemblage(VideoObj)
            if not Success:
                await self._MarkJobFailed(VideoObj, "Échec du réassemblage")
                async with self.CurrentJobIdLock:
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

            # Webhook: job terminé
            VideoName = os.path.basename(VideoObj.VideoPath) if VideoObj else VideoId
            DurationStr = f"{int(Duration // 60)}m{int(Duration % 60)}s"
            TriggerServerWebhook(
                "job_completed",
                video_name=VideoName,
                video_id=VideoId,
                duration=DurationStr
            )

            # Nettoyage des fichiers temporaires (garde la vidéo de sortie)
            self.VideoProcessor.CleanupVideoData(VideoId, KeepOutput=True)

            async with self.CurrentJobIdLock:
                self.CurrentJobId = None
            return True

        except Exception as e:
            self.Logger.error(f"Erreur critique lors du traitement du job {VideoId}: {e}", exc_info=True)

            # Met à jour le statut en DB
            try:
                VideoObj = self.Database.GetVideo(VideoId)
                if VideoObj:
                    VideoObj.Status = JobStatus.FAILED
                    VideoObj.ErrorMessage = f"Erreur critique: {str(e)}"
                    VideoObj.CompletedAt = datetime.now()
                    self.Database.UpdateVideo(VideoObj)
            except Exception as db_error:
                self.Logger.error(f"Impossible de mettre à jour la DB après erreur: {db_error}")

            async with self.CurrentJobIdLock:
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
            # MODIFIÉ: Exécute dans un thread séparé pour ne pas bloquer l'event loop
            VideoData = await asyncio.to_thread(
                self.VideoProcessor.ExtractVideoData,
                VideoObj.VideoPath,
                VideoObj.VideoId
            )

            if not VideoData:
                self.Logger.error(f"Échec de l'extraction des données pour {VideoObj.VideoId}")
                VideoObj.Status = JobStatus.FAILED
                VideoObj.ErrorMessage = "Échec de l'extraction des données vidéo (codec non supporté ou fichier corrompu)"
                self.Database.UpdateVideo(VideoObj)
                return False

            # Met à jour les informations
            VideoObj.Framerate = VideoData["fps"]
            VideoObj.TotalFrames = VideoData["total_frames"]
            self.Database.UpdateVideo(VideoObj)

            self.Logger.info(f"✓ Extraction terminée (FPS: {VideoData['fps']:.2f}, Frames: {VideoData['total_frames']})")
            return True

        except Exception as e:
            self.Logger.error(f"Erreur phase extraction: {e}", exc_info=True)
            VideoObj.Status = JobStatus.FAILED
            VideoObj.ErrorMessage = f"Erreur lors de l'extraction: {str(e)}"
            self.Database.UpdateVideo(VideoObj)
            return False

    async def _PhaseDecoupage(self, VideoObj: Video) -> bool:
        """Phase 2: Découpage en images"""
        try:
            self.Logger.info("PHASE 2: DÉCOUPAGE EN IMAGES")
            VideoObj.Status = JobStatus.DISTRIBUTING
            self.Database.UpdateVideo(VideoObj)

            # Découpe la vidéo en images
            # MODIFIÉ: Exécute le découpage dans un thread séparé (opération la plus longue)
            Success = await asyncio.to_thread(
                self.VideoProcessor.VideoToFrames,
                VideoObj.VideoPath,
                VideoObj.VideoId
            )

            if not Success:
                self.Logger.error(f"Échec du découpage en frames pour {VideoObj.VideoId}")
                VideoObj.Status = JobStatus.FAILED
                VideoObj.ErrorMessage = "Échec du découpage de la vidéo en images (erreur FFmpeg)"
                self.Database.UpdateVideo(VideoObj)
                return False

            # Crée les batches
            # MODIFIÉ: CreateBatches est aussi CPU-bound, exécuter dans un thread
            Batches = await asyncio.to_thread(
                self.VideoProcessor.CreateBatches,
                VideoObj.VideoId,
                self.BatchSize
            )

            if not Batches:
                self.Logger.error(f"Échec de la création des batches pour {VideoObj.VideoId}")
                # Rollback: nettoie les frames créées
                try:
                    FramesDir = self.VideoProcessor.GetVideoFramesDir(VideoObj.VideoId)
                    if os.path.exists(FramesDir):
                        shutil.rmtree(FramesDir)
                        self.Logger.info(f"✓ Frames nettoyées après échec création batches")
                except Exception as cleanup_err:
                    self.Logger.error(f"Erreur lors du nettoyage des frames: {cleanup_err}")

                VideoObj.Status = JobStatus.FAILED
                VideoObj.ErrorMessage = "Échec de la création des batches (aucune frame valide trouvée)"
                self.Database.UpdateVideo(VideoObj)
                return False

            # Met à jour le nombre de batches
            VideoObj.TotalBatches = len(Batches)
            VideoObj.CompletedBatches = 0
            VideoObj.Progress = 0.0
            self.Database.UpdateVideo(VideoObj)

            self.Logger.info(f"✓ Découpage terminé ({len(Batches)} batches)")
            return True

        except Exception as e:
            self.Logger.error(f"Erreur phase découpage: {e}", exc_info=True)
            # Rollback: nettoie les frames créées
            try:
                FramesDir = self.VideoProcessor.GetVideoFramesDir(VideoObj.VideoId)
                if os.path.exists(FramesDir):
                    shutil.rmtree(FramesDir)
                    self.Logger.info(f"✓ Frames nettoyées après erreur")
            except Exception as cleanup_err:
                self.Logger.error(f"Erreur lors du nettoyage des frames: {cleanup_err}")

            VideoObj.Status = JobStatus.FAILED
            VideoObj.ErrorMessage = f"Erreur lors du découpage: {str(e)}"
            self.Database.UpdateVideo(VideoObj)
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
                    self.Logger.error(f"Trop de batches échoués ({Stats['failed']}/{Stats['total']})")
                    await self.BatchDistributor.StopDistribution()

                    # Met à jour le statut de la vidéo en DB
                    VideoObj.Status = JobStatus.FAILED
                    VideoObj.ErrorMessage = f"Trop de batches ont échoué: {Stats['failed']}/{Stats['total']} ({Stats['failed']/Stats['total']*100:.1f}%)"
                    self.Database.UpdateVideo(VideoObj)
                    return False

                await asyncio.sleep(5)

            # Arrête la distribution
            await self.BatchDistributor.StopDistribution()

            self.Logger.info("✓ Distribution terminée")
            return True

        except Exception as e:
            self.Logger.error(f"Erreur phase distribution: {e}", exc_info=True)
            await self.BatchDistributor.StopDistribution()
            VideoObj.Status = JobStatus.FAILED
            VideoObj.ErrorMessage = f"Erreur lors de la distribution: {str(e)}"
            self.Database.UpdateVideo(VideoObj)
            return False

    async def _PhaseReassemblage(self, VideoObj: Video) -> bool:
        """Phase 4: Réassemblage de la vidéo"""
        try:
            self.Logger.info("PHASE 4: RÉASSEMBLAGE")

            # VÉRIFICATION CRITIQUE: S'assure que TOUS les batches sont vraiment COMPLETED
            from server.database.models import Batch, BatchStatus
            AllBatches = self.Database.GetBatchesByVideo(VideoObj.VideoId)

            if not AllBatches:
                self.Logger.error(f"Aucun batch trouvé pour la vidéo {VideoObj.VideoId}")
                VideoObj.Status = JobStatus.FAILED
                VideoObj.ErrorMessage = "Aucun batch trouvé pour le réassemblage"
                self.Database.UpdateVideo(VideoObj)
                return False

            # Vérifie que tous les batches sont COMPLETED
            NonCompletedBatches = [b for b in AllBatches if b.Status != BatchStatus.COMPLETED]
            if NonCompletedBatches:
                BatchStatuses = {}
                for batch in NonCompletedBatches:
                    status = batch.Status.name if hasattr(batch.Status, 'name') else str(batch.Status)
                    BatchStatuses[batch.BatchId] = status

                self.Logger.error(f"{len(NonCompletedBatches)} batches non complétés: {BatchStatuses}")
                VideoObj.Status = JobStatus.FAILED
                VideoObj.ErrorMessage = f"{len(NonCompletedBatches)} batches non complétés, réassemblage impossible"
                self.Database.UpdateVideo(VideoObj)
                return False

            self.Logger.info(f"✓ Tous les {len(AllBatches)} batches sont COMPLETED, début réassemblage")

            VideoObj.Status = JobStatus.REASSEMBLING
            self.Database.UpdateVideo(VideoObj)

            # Réassemble la vidéo
            # MODIFIÉ: Exécute le réassemblage dans un thread séparé
            # Extrait le nom original de la vidéo (sans extension)
            OriginalVideoName = os.path.splitext(os.path.basename(VideoObj.VideoPath))[0]

            OutputPath = await asyncio.to_thread(
                self.VideoProcessor.ReassembleVideo,
                VideoObj.VideoId,
                VideoObj.Framerate,
                VideoObj.UpscaleFactor,
                OriginalVideoName
            )

            if not OutputPath:
                self.Logger.error(f"Échec du réassemblage pour {VideoObj.VideoId}")
                VideoObj.Status = JobStatus.FAILED
                VideoObj.ErrorMessage = "Échec du réassemblage de la vidéo (erreur FFmpeg ou images manquantes)"
                self.Database.UpdateVideo(VideoObj)
                return False

            VideoObj.OutputPath = OutputPath
            self.Database.UpdateVideo(VideoObj)

            self.Logger.info(f"✓ Réassemblage terminé: {OutputPath}")
            return True

        except Exception as e:
            self.Logger.error(f"Erreur phase réassemblage: {e}", exc_info=True)
            VideoObj.Status = JobStatus.FAILED
            VideoObj.ErrorMessage = f"Erreur lors du réassemblage: {str(e)}"
            self.Database.UpdateVideo(VideoObj)
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
            # MODIFIÉ: Encodage AV1 très long, exécuter dans un thread
            # Extrait le nom original de la vidéo (sans extension)
            OriginalVideoName = os.path.splitext(os.path.basename(VideoObj.VideoPath))[0]

            AV1Path = await asyncio.to_thread(
                self.VideoProcessor.EncodeToAV1,
                VideoObj.OutputPath,
                VideoObj.VideoId,
                OriginalVideoName
            )

            if AV1Path:
                # Remplace le chemin de sortie
                VideoObj.OutputPath = AV1Path
                self.Database.UpdateVideo(VideoObj)
                self.Logger.info("✓ Encodage AV1 terminé")
                return True
            else:
                self.Logger.warning("Encodage AV1 échoué, conservation de la version H264")
                # Ajoute un warning (non bloquant) dans ErrorMessage
                if VideoObj.ErrorMessage:
                    VideoObj.ErrorMessage += " | Warning: Encodage AV1 échoué, vidéo en H264"
                else:
                    VideoObj.ErrorMessage = "Warning: Encodage AV1 échoué, vidéo en H264"
                self.Database.UpdateVideo(VideoObj)
                return True  # Pas bloquant

        except Exception as e:
            self.Logger.error(f"Erreur phase encodage: {e}", exc_info=True)
            # Ajoute un warning (non bloquant) dans ErrorMessage
            if VideoObj.ErrorMessage:
                VideoObj.ErrorMessage += f" | Warning: Erreur encodage AV1: {str(e)}"
            else:
                VideoObj.ErrorMessage = f"Warning: Erreur encodage AV1: {str(e)}"
            self.Database.UpdateVideo(VideoObj)
            return True  # Pas bloquant

    async def _MarkJobFailed(self, VideoObj: Video, ErrorMessage: str):
        """Marque un job comme échoué"""
        VideoObj.Status = JobStatus.FAILED
        VideoObj.ErrorMessage = ErrorMessage
        VideoObj.CompletedAt = datetime.now()
        self.Database.UpdateVideo(VideoObj)

        self.Logger.error(f"✗ JOB ÉCHOUÉ: {ErrorMessage}")

        # Webhook: job échoué
        VideoName = os.path.basename(VideoObj.VideoPath) if VideoObj else "unknown"
        TriggerServerWebhook(
            "job_failed",
            video_name=VideoName,
            video_id=VideoObj.VideoId,
            error=ErrorMessage
        )

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
