"""
Distributeur de paquets pour l'upscaling distribué
Gère l'attribution, l'envoi et la réception des batches
"""

import asyncio
import os
import base64
import time
import concurrent.futures
from typing import Optional, Dict, List
from datetime import datetime
from PIL import Image
import io

# Enregistre le support AVIF/HEIF pour la réception des images
try:
    import pillow_heif
    pillow_heif.register_heif_opener()  # Inclut AVIF et HEIF
except (ImportError, AttributeError):
    pass  # Support AVIF non disponible, les images seront en PNG

from server.core.client_manager import ClientManager
from server.core.video_processor import VideoProcessor
from server.database.db_manager import DatabaseManager
from server.database.models import Batch, Video
from shared.protocol.messages import BatchAssignment, BatchResult, MessageFactory
from shared.utils.logger import GetModuleLogger
from shared.utils.constants import BatchStatus, ClientStatus, NetworkConfig, Limits, RetryConfig
from shared.utils.retry import RetryAsync, RetryExhaustedError
from shared.utils.atomic_operations import AtomicImageSave
from shared.utils.cleanup import CleanupPartialFrames
from shared.utils.error_events import EmitError, ErrorCategory, ErrorSeverity
from shared.exceptions import BatchTimeoutError


class BatchDistributor:
    """Distributeur de paquets d'images pour traitement distribué"""

    def __init__(self, ClientManager: ClientManager, VideoProcessor: VideoProcessor,
                 Database: DatabaseManager):
        """
        Initialise le distributeur

        Args:
            ClientManager: Gestionnaire de clients
            VideoProcessor: Processeur vidéo
            Database: Gestionnaire de base de données
        """
        self.ClientManager = ClientManager
        self.VideoProcessor = VideoProcessor
        self.Database = Database
        self.Logger = GetModuleLogger("BatchDistributor")

        # Tracking des batches en cours
        self.ActiveBatches: Dict[str, dict] = {}  # {batch_id: {client_id, start_time, retry_count}}
        self.Running = False
        self.DistributionTask = None

        # Semaphore pour limiter les envois concurrents
        from shared.utils.constants import Limits
        MaxConcurrent = self.Database.GetParameterInt('max_concurrent_batches', Limits.MAX_CONCURRENT_BATCH_SENDS)
        self.SendSemaphore = asyncio.Semaphore(MaxConcurrent)
        self.Logger.info(f"Distributeur initialisé avec max {MaxConcurrent} envois concurrents")

    async def StartDistribution(self, VideoId: str):
        """
        Démarre la distribution des batches pour une vidéo

        Args:
            VideoId: ID de la vidéo
        """
        self.Running = True
        self.Logger.info(f"Démarrage de la distribution pour la vidéo {VideoId}")

        # Récupération des batches bloqués (PROCESSING mais pas dans ActiveBatches)
        await self._RecoverStuckBatches(VideoId)

        # Lance la boucle de distribution
        self.DistributionTask = asyncio.create_task(
            self._DistributionLoop(VideoId)
        )

    async def StopDistribution(self):
        """Arrête la distribution avec sauvegarde de l'état"""
        self.Logger.info("Arrêt de la distribution des batches...")

        self.Running = False

        # Sauvegarde l'état des batches actifs
        await self._SaveActiveBatchesState()

        # Annule la tâche de distribution
        if self.DistributionTask:
            self.DistributionTask.cancel()
            try:
                await self.DistributionTask
            except asyncio.CancelledError:
                self.Logger.debug("Tâche de distribution annulée")

        self.Logger.info("✓ Distribution arrêtée")

    async def _SaveActiveBatchesState(self):
        """
        Sauvegarde l'état des batches actifs avant l'arrêt.
        Remet les batches ASSIGNED et PROCESSING en PENDING pour qu'ils soient
        réattribués au prochain démarrage.
        """
        try:
            if not self.ActiveBatches:
                return

            self.Logger.info(f"Sauvegarde de l'état de {len(self.ActiveBatches)} batches actifs...")

            saved_count = 0
            for batch_id, batch_info in self.ActiveBatches.items():
                batch_obj = self.Database.GetBatch(batch_id)

                if batch_obj and batch_obj.Status in [BatchStatus.ASSIGNED, BatchStatus.PROCESSING]:
                    # Remet le batch en PENDING pour qu'il soit réassigné
                    old_status = batch_obj.Status
                    batch_obj.Status = BatchStatus.PENDING
                    batch_obj.AssignedClientId = None
                    self.Database.UpdateBatch(batch_obj)

                    saved_count += 1
                    self.Logger.debug(
                        f"Batch {batch_id}: {old_status} → PENDING "
                        f"(client: {batch_info.get('client_id', 'unknown')})"
                    )

            # Vide le dictionnaire des batches actifs
            self.ActiveBatches.clear()

            if saved_count > 0:
                self.Logger.info(f"✓ {saved_count} batches remis en attente pour réattribution")

        except Exception as e:
            self.Logger.error(f"Erreur lors de la sauvegarde de l'état des batches: {e}")

    async def _DistributionLoop(self, VideoId: str):
        """
        Boucle principale de distribution

        Args:
            VideoId: ID de la vidéo
        """
        try:
            while self.Running:
                # Récupère les batches en attente
                PendingBatches = self.Database.GetPendingBatches(VideoId)

                if not PendingBatches:
                    # Vérifie si tous les batches sont complétés
                    AllBatches = self.Database.GetBatchesByVideo(VideoId)
                    CompletedCount = sum(1 for b in AllBatches if b.Status == BatchStatus.COMPLETED)

                    # MOYENNE Problème 29: Break immédiat si tous complétés
                    if CompletedCount == len(AllBatches) and len(AllBatches) > 0:
                        self.Logger.info(f"Tous les batches complétés pour {VideoId}")
                        break

                    # Attend un peu avant de revérifier (backoff pour réduire charge CPU)
                    await asyncio.sleep(5)
                    continue

                # Récupère les clients disponibles
                AvailableClients = self._GetAvailableClients()

                if not AvailableClients:
                    self.Logger.debug("Aucun client disponible, attente...")
                    await asyncio.sleep(2)
                    continue

                # Distribue les batches aux clients disponibles (concurrent)
                BatchesToAssign = PendingBatches[:len(AvailableClients)]
                AssignmentTasks = []

                for BatchObj in BatchesToAssign:
                    ClientId = AvailableClients.pop(0)
                    # Crée une tâche pour chaque assignation
                    Task = self._AssignBatchConcurrent(BatchObj.BatchId, ClientId, VideoId)
                    AssignmentTasks.append((Task, BatchObj))

                    if not AvailableClients:
                        break

                # Attend que tous les envois se terminent (avec gestion d'erreurs)
                if AssignmentTasks:
                    Tasks = [task for task, _ in AssignmentTasks]
                    Results = await asyncio.gather(*Tasks, return_exceptions=True)

                    # MOYENNE Problème 9: Remettre batches échoués en PENDING
                    for Index, Result in enumerate(Results):
                        BatchObj = AssignmentTasks[Index][1]
                        if isinstance(Result, Exception) or Result is False:
                            self.Logger.error(
                                f"Erreur lors de l'assignation du batch {BatchObj.BatchId}: {Result}"
                            )

                            # Remet le batch en PENDING pour retry
                            try:
                                BatchObj.Status = BatchStatus.PENDING
                                BatchObj.AssignedClientId = None
                                self.Database.UpdateBatch(BatchObj)

                                # Nettoie ActiveBatches si présent
                                if BatchObj.BatchId in self.ActiveBatches:
                                    del self.ActiveBatches[BatchObj.BatchId]

                                self.Logger.debug(f"Batch {BatchObj.BatchId} remis en PENDING après échec assignation")
                            except Exception as cleanup_err:
                                self.Logger.error(f"Échec nettoyage batch {BatchObj.BatchId}: {cleanup_err}")

                # Vérifie les timeouts
                await self._CheckTimeouts()

                await asyncio.sleep(1)

        except asyncio.CancelledError:
            self.Logger.info("Boucle de distribution annulée")
        except Exception as e:
            self.Logger.error(f"Erreur dans la boucle de distribution: {e}")

    async def _RecoverStuckBatches(self, VideoId: str):
        """
        Récupère les batches bloqués en PROCESSING qui ne sont pas dans ActiveBatches
        Cela peut arriver si le serveur crash ou si un batch est assigné alors que
        le canal Data n'était pas encore connecté

        Args:
            VideoId: ID de la vidéo
        """
        try:
            # Récupère tous les batches de cette vidéo
            AllBatches = self.Database.GetBatchesByVideo(VideoId)
            RecoveredCount = 0

            for Batch in AllBatches:
                # Vérifie si le batch est en PROCESSING mais pas dans ActiveBatches
                if Batch.Status == BatchStatus.PROCESSING and Batch.BatchId not in self.ActiveBatches:
                    self.Logger.warning(
                        f"Batch {Batch.BatchId} bloqué en PROCESSING (client: {Batch.AssignedClientId}), "
                        f"réinitialisation à PENDING"
                    )

                    # Réinitialise le batch
                    Batch.Status = BatchStatus.PENDING
                    Batch.AssignedClientId = None

                    # MOYENNE Problème 27: Vérifier succès UpdateBatch avant incrémenter
                    UpdateSuccess = self.Database.UpdateBatch(Batch)
                    if UpdateSuccess:
                        RecoveredCount += 1
                    else:
                        self.Logger.error(f"Échec mise à jour batch {Batch.BatchId} lors de la récupération")

            if RecoveredCount > 0:
                self.Logger.info(f"✓ {RecoveredCount} batch(es) bloqué(s) récupéré(s)")
            else:
                self.Logger.debug("Aucun batch bloqué détecté")

        except Exception as e:
            self.Logger.error(f"Erreur lors de la récupération des batches bloqués: {e}")

    def _GetAvailableClients(self) -> List[str]:
        """
        Récupère les clients disponibles pour recevoir un batch (pipeline multi-batch)

        Un client est disponible si:
        - Son canal Data est connecté
        - Il a moins de batches actifs que sa limite (MaxConcurrentBatches)

        Returns:
            Liste des IDs des clients disponibles
        """
        AvailableClients = []

        for ClientId in self.ClientManager.GetConnectedClients():
            ClientInfo = self.ClientManager.Clients.get(ClientId)

            # Vérifie que le canal Data est connecté (requis pour envoyer les batches)
            if not ClientInfo or not ClientInfo.IsDataConnected():
                self.Logger.debug(f"Client {ClientId}: canal Data non connecté, ignoré")
                continue

            # Compte les batches actifs pour ce client (pipeline multi-batch)
            ActiveCount = sum(1 for b in self.ActiveBatches.values()
                            if b.get("client_id") == ClientId)

            # Vérifie la capacité du client
            MaxBatches = ClientInfo.MaxConcurrentBatches or 2

            if ActiveCount < MaxBatches:
                AvailableClients.append(ClientId)
                self.Logger.debug(f"Client {ClientId}: disponible ({ActiveCount}/{MaxBatches} batches)")
            else:
                self.Logger.debug(f"Client {ClientId}: capacité atteinte ({ActiveCount}/{MaxBatches} batches)")

        return AvailableClients

    def GetClientBatchInfo(self, ClientId: str) -> dict:
        """
        Retourne les informations sur les batches actifs d'un client

        Args:
            ClientId: ID du client

        Returns:
            Dict avec:
            - active_count: Nombre de batches actifs
            - max_batches: Capacite maximale du client
            - batch_ids: Liste des IDs de batches actifs
        """
        ClientInfo = self.ClientManager.Clients.get(ClientId)
        MaxBatches = ClientInfo.MaxConcurrentBatches if ClientInfo else 2

        # Liste des batches actifs pour ce client
        ActiveBatchIds = [
            BatchId for BatchId, Info in self.ActiveBatches.items()
            if Info.get("client_id") == ClientId
        ]

        return {
            "active_count": len(ActiveBatchIds),
            "max_batches": MaxBatches,
            "batch_ids": ActiveBatchIds
        }

    def GetAllClientsBatchInfo(self) -> dict:
        """
        Retourne les informations de batches pour tous les clients connectes

        Returns:
            Dict {ClientId: {active_count, max_batches, batch_ids}}
        """
        Result = {}
        for ClientId in self.ClientManager.GetConnectedClients():
            Result[ClientId] = self.GetClientBatchInfo(ClientId)
        return Result

    async def AssignBatch(self, BatchId: str, ClientId: str, VideoId: str) -> bool:
        """
        Assigne un batch à un client

        Args:
            BatchId: ID du batch
            ClientId: ID du client
            VideoId: ID de la vidéo

        Returns:
            True si succès
        """
        try:
            # Récupère le batch
            BatchObj = self.Database.GetBatch(BatchId)
            if not BatchObj:
                self.Logger.error(f"Batch {BatchId} non trouvé")
                return False

            # Récupère la vidéo
            VideoObj = self.Database.GetVideo(VideoId)
            if not VideoObj:
                self.Logger.error(f"Vidéo {VideoId} non trouvée")
                return False

            self.Logger.info(f"Attribution du batch {BatchId} au client {ClientId}")

            # CRITIQUE: Met à jour le statut du batch de manière CONDITIONNELLE
            # Évite race condition : 2 processus ne peuvent pas assigner le même batch
            # UPDATE conditionnel : SET status=ASSIGNED WHERE batch_id=? AND status=PENDING
            AssignedAt = datetime.now()
            UpdateSuccess = self.Database.UpdateBatchConditional(
                BatchId=BatchId,
                NewStatus=BatchStatus.ASSIGNED,
                ExpectedStatus=BatchStatus.PENDING,
                AssignedClientId=ClientId,
                AssignedAt=AssignedAt
            )

            if not UpdateSuccess:
                # Race condition : batch déjà assigné par un autre processus
                self.Logger.warning(f"Batch {BatchId} n'est plus PENDING, assignation abandonnée (race condition évitée)")
                return False

            # Met à jour l'objet en mémoire pour refléter la DB
            BatchObj.Status = BatchStatus.ASSIGNED
            BatchObj.AssignedClientId = ClientId
            BatchObj.AssignedAt = AssignedAt

            # Met à jour le statut du client
            self.ClientManager.UpdateClientStatus(ClientId, ClientStatus.RECEIVING)

            # Envoie le batch au client
            Success = await self.SendBatchToClient(BatchObj, VideoObj, ClientId)

            if Success:
                # Marque comme processing
                BatchObj.Status = BatchStatus.PROCESSING
                self.Database.UpdateBatch(BatchObj)
                self.ClientManager.UpdateClientStatus(ClientId, ClientStatus.PROCESSING)

                # Track le batch actif SEULEMENT si l'envoi a réussi
                self.ActiveBatches[BatchId] = {
                    "client_id": ClientId,
                    "start_time": time.time(),
                    "retry_count": BatchObj.RetryCount
                }

                return True
            else:
                # Échec envoi, remet en pending
                self.Logger.warning(f"Échec envoi batch {BatchId} au client {ClientId}")
                BatchObj.Status = BatchStatus.PENDING
                BatchObj.AssignedClientId = None
                self.Database.UpdateBatch(BatchObj)
                self.ClientManager.UpdateClientStatus(ClientId, ClientStatus.IDLE)

                # IMPORTANT: Ne PAS ajouter à ActiveBatches puisque l'envoi a échoué
                # (le batch n'a jamais été ajouté à ActiveBatches à ce stade)
                return False

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'attribution du batch: {e}")
            return False

    async def _AssignBatchConcurrent(self, BatchId: str, ClientId: str, VideoId: str) -> bool:
        """
        Wrapper pour AssignBatch qui utilise le semaphore pour limiter la concurrence.

        Args:
            BatchId: ID du batch
            ClientId: ID du client
            VideoId: ID de la vidéo

        Returns:
            True si succès
        """
        async with self.SendSemaphore:
            return await self.AssignBatch(BatchId, ClientId, VideoId)

    async def SendBatchToClient(self, BatchObj: Batch, VideoObj: Video,
                               ClientId: str) -> bool:
        """
        Envoie un batch d'images à un client via le canal Data

        Args:
            BatchObj: Objet Batch
            VideoObj: Objet Video
            ClientId: ID du client

        Returns:
            True si succès
        """
        try:
            # Vérifie que le canal Data est connecté
            ClientInfo = self.ClientManager.Clients.get(ClientId)
            if not ClientInfo or not ClientInfo.IsDataConnected():
                # HAUTE Problème 15: Vérification connexion Control avant fallback
                # Risque : Fallback sur Control même si Control déconnecté
                if not ClientInfo or not ClientInfo.IsControlConnected():
                    self.Logger.error(
                        f"Impossible d'envoyer batch {BatchObj.BatchId} à {ClientId}: "
                        f"Data ET Control déconnectés"
                    )
                    return False

                self.Logger.warning(f"Canal Data non connecté pour {ClientId}, fallback sur Control")
                return await self._SendBatchViaControl(BatchObj, VideoObj, ClientId)

            # Récupère les chemins des images du batch
            FramePaths = self.VideoProcessor.GetBatchFrames(VideoObj.VideoId, BatchObj)

            if not FramePaths:
                self.Logger.error(f"Aucune image trouvée pour le batch {BatchObj.BatchId}")
                return False

            self.Logger.info(f"Envoi de {len(FramePaths)} images au client {ClientId} via Data...")

            # Charge et encode les images en base64 (parallélisé)
            def LoadAndEncodeImage(Index: int, FramePath: str) -> Optional[Dict]:
                """Charge et encode une seule image"""
                try:
                    # Lit l'image
                    with open(FramePath, 'rb') as f:
                        ImageData = f.read()

                    # Encode en base64
                    ImageB64 = base64.b64encode(ImageData).decode('utf-8')

                    # Numéro de frame absolu
                    FrameNumber = BatchObj.StartFrame + Index

                    return {
                        "id": str(FrameNumber),
                        "number": FrameNumber,
                        "data": ImageB64,
                        "filename": os.path.basename(FramePath)
                    }

                except Exception as e:
                    self.Logger.error(f"Erreur lors du chargement de {FramePath}: {e}")
                    return None

            # Parallélise le chargement et l'encodage
            MaxWorkers = min(32, (os.cpu_count() or 4) * 2)
            Images = []

            Loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=MaxWorkers) as executor:
                # Soumet toutes les tâches
                Tasks = [
                    Loop.run_in_executor(executor, LoadAndEncodeImage, Index, FramePath)
                    for Index, FramePath in enumerate(FramePaths)
                ]

                # Attend tous les résultats
                Results = await asyncio.gather(*Tasks)

                # Filtre les None (erreurs)
                Images = [img for img in Results if img is not None]

            self.Logger.debug(f"✓ {len(Images)} images encodées (parallèle avec {MaxWorkers} threads)")

            # Crée le message BatchAssignment
            Message = BatchAssignment(
                BatchId=BatchObj.BatchId,
                VideoId=VideoObj.VideoId,
                Images=Images,
                UpscaleFactor=VideoObj.UpscaleFactor,
                Engine=VideoObj.Engine,
                Model=VideoObj.Model,
                DenoiseLevel=VideoObj.DenoiseLevel,
                TtaMode=VideoObj.TtaMode
            )

            # Envoie via le canal Data avec retry
            MessageJson = Message.ToJson()

            def OnRetry(Attempt: int, Error: Exception):
                self.Logger.warning(
                    f"Retry {Attempt}/{RetryConfig.BATCH_SEND_MAX_RETRIES} "
                    f"pour batch {BatchObj.BatchId} vers {ClientId}: {Error}"
                )

            try:
                Success = await RetryAsync(
                    lambda: self.ClientManager.SendDataMessage(
                        ClientId,
                        MessageJson,
                        Encrypted=True
                    ),
                    max_retries=RetryConfig.BATCH_SEND_MAX_RETRIES,
                    delay=RetryConfig.BATCH_SEND_RETRY_DELAY,
                    exceptions=(ConnectionError, BrokenPipeError, OSError),
                    on_retry=OnRetry,
                    logger=self.Logger
                )
            except RetryExhaustedError as e:
                self.Logger.error(
                    f"Échec de l'envoi du batch {BatchObj.BatchId} après "
                    f"{RetryConfig.BATCH_SEND_MAX_RETRIES} tentatives: {e.last_exception}"
                )
                return False

            if Success:
                self.Logger.info(f"✓ Batch {BatchObj.BatchId} envoyé au client {ClientId} (Data)")
            else:
                self.Logger.error(f"Échec de l'envoi du batch au client {ClientId}")

            return Success

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'envoi du batch: {e}")
            return False

    async def _SendBatchViaControl(self, BatchObj: Batch, VideoObj: Video,
                                   ClientId: str) -> bool:
        """
        Fallback: Envoie un batch via le canal Control (compatibilité)

        Args:
            BatchObj: Objet Batch
            VideoObj: Objet Video
            ClientId: ID du client

        Returns:
            True si succès
        """
        try:
            # Récupère les chemins des images du batch
            FramePaths = self.VideoProcessor.GetBatchFrames(VideoObj.VideoId, BatchObj)

            if not FramePaths:
                self.Logger.error(f"Aucune image trouvée pour le batch {BatchObj.BatchId}")
                return False

            self.Logger.info(f"Envoi de {len(FramePaths)} images au client {ClientId} via Control (fallback)...")

            # Charge et encode les images en base64 (parallélisé)
            def LoadAndEncodeImage(Index: int, FramePath: str) -> Optional[Dict]:
                """Charge et encode une seule image"""
                try:
                    with open(FramePath, 'rb') as f:
                        ImageData = f.read()
                    ImageB64 = base64.b64encode(ImageData).decode('utf-8')
                    FrameNumber = BatchObj.StartFrame + Index
                    return {
                        "id": str(FrameNumber),
                        "number": FrameNumber,
                        "data": ImageB64,
                        "filename": os.path.basename(FramePath)
                    }
                except Exception as e:
                    self.Logger.error(f"Erreur lors du chargement de {FramePath}: {e}")
                    return None

            # Parallélise le chargement et l'encodage
            MaxWorkers = min(32, (os.cpu_count() or 4) * 2)
            Images = []

            Loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=MaxWorkers) as executor:
                # Soumet toutes les tâches
                Tasks = [
                    Loop.run_in_executor(executor, LoadAndEncodeImage, Index, FramePath)
                    for Index, FramePath in enumerate(FramePaths)
                ]

                # Attend tous les résultats
                Results = await asyncio.gather(*Tasks)

                # Filtre les None (erreurs)
                Images = [img for img in Results if img is not None]

            self.Logger.debug(f"✓ {len(Images)} images encodées (parallèle avec {MaxWorkers} threads)")

            Message = BatchAssignment(
                BatchId=BatchObj.BatchId,
                VideoId=VideoObj.VideoId,
                Images=Images,
                UpscaleFactor=VideoObj.UpscaleFactor,
                Engine=VideoObj.Engine,
                Model=VideoObj.Model,
                DenoiseLevel=VideoObj.DenoiseLevel,
                TtaMode=VideoObj.TtaMode
            )

            # Envoie via Control (fallback)
            Success = await self.ClientManager.SendMessage(
                ClientId,
                Message.ToJson(),
                Encrypted=True
            )

            if Success:
                self.Logger.info(f"✓ Batch {BatchObj.BatchId} envoyé au client {ClientId} (Control fallback)")
            else:
                self.Logger.error(f"Échec de l'envoi du batch au client {ClientId}")

            return Success

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'envoi du batch (Control): {e}")
            return False

    async def ReceiveBatchResult(self, ClientId: str, ResultMessage: BatchResult) -> bool:
        """
        Reçoit un résultat de batch d'un client

        Args:
            ClientId: ID du client
            ResultMessage: Message BatchResult

        Returns:
            True si succès
        """
        try:
            BatchId = ResultMessage.Payload.get("batch_id")

            if not BatchId:
                self.Logger.error("BatchId manquant dans le résultat")
                return False

            self.Logger.info(f"Réception du résultat du batch {BatchId} depuis {ClientId}")

            # Récupère le batch
            BatchObj = self.Database.GetBatch(BatchId)
            if not BatchObj:
                self.Logger.error(f"Batch {BatchId} non trouvé")
                return False

            # Vérifie le succès
            if not ResultMessage.IsSuccess():
                ErrorMsg = ResultMessage.Payload.get("error_message", "Erreur inconnue")
                self.Logger.error(f"Batch {BatchId} échoué: {ErrorMsg}")

                # Incrémente le compteur de retry (statistiques uniquement)
                BatchObj.RetryCount += 1
                BatchObj.ErrorMessage = ErrorMsg

                # Retire du tracking
                if BatchId in self.ActiveBatches:
                    del self.ActiveBatches[BatchId]

                # Toujours remettre en PENDING pour retry (pas de limite)
                self.Logger.warning(f"⟳ Batch {BatchId} remis en file d'attente (tentative #{BatchObj.RetryCount})")
                BatchObj.Status = BatchStatus.PENDING
                BatchObj.AssignedClientId = None
                self.Database.UpdateBatch(BatchObj)

                # Remet le client en idle si pas d'autres batches
                self._SetClientIdleIfNoOtherBatches(ClientId)
                return False

            # Récupère les images upscalées
            UpscaledImages = ResultMessage.GetUpscaledImages()

            if not UpscaledImages:
                self.Logger.error(f"Batch {BatchId}: Aucune image upscalée reçue")

                # Incrémente le compteur de retry (statistiques uniquement)
                BatchObj.RetryCount += 1
                BatchObj.ErrorMessage = "Aucune image reçue du client"

                # Retire du tracking
                if BatchId in self.ActiveBatches:
                    del self.ActiveBatches[BatchId]

                # Toujours remettre en PENDING pour retry (pas de limite)
                self.Logger.warning(f"⟳ Batch {BatchId} remis en file d'attente (tentative #{BatchObj.RetryCount})")
                BatchObj.Status = BatchStatus.PENDING
                BatchObj.AssignedClientId = None
                self.Database.UpdateBatch(BatchObj)

                # Remet le client en idle si pas d'autres batches
                self._SetClientIdleIfNoOtherBatches(ClientId)
                return False

            # Calcul du nombre d'images attendues
            ExpectedCount = BatchObj.EndFrame - BatchObj.StartFrame + 1
            ReceivedCount = len(UpscaledImages)

            self.Logger.info(f"Batch {BatchId}: {ReceivedCount}/{ExpectedCount} images reçues")

            # CRITIQUE Problème 16: Validation continuité des numéros de frames
            # Vérifie que toutes les frames attendues sont présentes (pas seulement le nombre)
            # Risque: Accepter batch incomplet (ex: frames 1,2,5,6 au lieu de 1-4)
            ExpectedFrames = set(range(BatchObj.StartFrame, BatchObj.EndFrame + 1))
            ReceivedFrames = {img.get("number") for img in UpscaledImages}

            if ExpectedFrames != ReceivedFrames:
                Missing = ExpectedFrames - ReceivedFrames
                Extra = ReceivedFrames - ExpectedFrames
                self.Logger.error(
                    f"Batch {BatchId}: Frames discontinues - "
                    f"Manquantes: {sorted(Missing) if Missing else 'aucune'}, "
                    f"Extra: {sorted(Extra) if Extra else 'aucune'}"
                )

                # Marque le batch en erreur avec message détaillé
                BatchObj.Status = BatchStatus.FAILED
                BatchObj.RetryCount += 1
                BatchObj.ErrorMessage = (
                    f"Frames discontinues - "
                    f"Manquantes: {sorted(Missing) if Missing else 'aucune'}, "
                    f"Extra: {sorted(Extra) if Extra else 'aucune'}"
                )
                self.Database.UpdateBatch(BatchObj)

                # Retire du tracking
                if BatchId in self.ActiveBatches:
                    del self.ActiveBatches[BatchId]

                # Remet le client en idle si pas d'autres batches
                self._SetClientIdleIfNoOtherBatches(ClientId)
                return False

            # Sauvegarde les images upscalées
            VideoId = BatchObj.VideoId
            UpscaledDir = self.VideoProcessor.GetUpscaledDir(VideoId)

            try:
                # CRITIQUE Problème 12: Transaction atomique pour sauvegarde images
                # Garantit que TOUTES les images sont sauvegardées ou AUCUNE
                # Risque : Sauvegarde partielle → images orphelines → FFmpeg échouera
                async with AtomicImageSave(UpscaledDir, logger=self.Logger) as atomic:
                    for ImageData in UpscaledImages:
                        # Extraction des données
                        FrameNumber = ImageData.get("number")
                        ImageB64 = ImageData.get("data")
                        ReceivedFormat = ImageData.get("format", "png")

                        if not ImageB64:
                            raise ValueError(f"Données manquantes pour frame {FrameNumber}")

                        # Décode l'image
                        ImageBytes = base64.b64decode(ImageB64)

                        # Convertit en PNG si nécessaire (FFmpeg compatibility)
                        if ReceivedFormat != "png":
                            try:
                                Buffer = io.BytesIO(ImageBytes)
                                with Image.open(Buffer) as Img:
                                    OutputBuffer = io.BytesIO()
                                    Img.save(OutputBuffer, format='PNG')
                                    ImageBytes = OutputBuffer.getvalue()
                            except Exception as conv_err:
                                raise ValueError(
                                    f"Échec conversion {ReceivedFormat}->PNG frame {FrameNumber}: {conv_err}"
                                )

                        # Sauvegarde dans le dossier temporaire atomique
                        Filename = f"frame_{FrameNumber:08d}.png"
                        await atomic.SaveImage(Filename, ImageBytes)

                # Si on arrive ici : toutes les images sauvegardées avec succès (commit auto)
                self.Logger.info(
                    f"✓ Batch {BatchId}: {len(UpscaledImages)} images sauvegardées (transaction atomique)"
                )

            except Exception as e:
                # Échec : rollback automatique du context manager
                self.Logger.error(f"Batch {BatchId}: Échec sauvegarde atomique - {e}", exc_info=True)

                # Marque le batch en erreur et remet en PENDING pour retry
                BatchObj.RetryCount += 1
                BatchObj.ErrorMessage = f"Échec sauvegarde images: {str(e)}"
                BatchObj.Status = BatchStatus.PENDING
                BatchObj.AssignedClientId = None
                self.Database.UpdateBatch(BatchObj)

                # Retire du tracking
                if BatchId in self.ActiveBatches:
                    del self.ActiveBatches[BatchId]

                # Remet le client en idle
                self._SetClientIdleIfNoOtherBatches(ClientId)
                return False

            # Marque le batch comme complété
            BatchObj.Status = BatchStatus.COMPLETED
            BatchObj.CompletedAt = datetime.now()
            self.Database.UpdateBatch(BatchObj)

            # Met à jour la progression de la vidéo
            VideoObj = self.Database.GetVideo(VideoId)
            if VideoObj:
                VideoObj.CompletedBatches += 1
                VideoObj.UpdateProgress()
                try:
                    self.Database.UpdateVideo(VideoObj)
                    self.Logger.info(f"Progression vidéo: {VideoObj.CompletedBatches}/{VideoObj.TotalBatches} ({VideoObj.Progress*100:.1f}%)")
                except Exception as db_error:
                    self.Logger.error(f"Erreur mise à jour progression vidéo {VideoId}: {db_error}")
            else:
                self.Logger.error(f"ERREUR: Vidéo {VideoId} introuvable dans la DB pour batch {BatchId}!")

            # Retire du tracking
            if BatchId in self.ActiveBatches:
                del self.ActiveBatches[BatchId]

            # Remet le client en idle si pas d'autres batches
            self._SetClientIdleIfNoOtherBatches(ClientId)

            return True

        except Exception as e:
            self.Logger.error(f"Erreur critique lors de la réception du résultat batch {ResultMessage.Payload.get('batch_id', 'unknown')}: {e}", exc_info=True)

            # Récupère le BatchId depuis le ResultMessage
            BatchId = ResultMessage.Payload.get("batch_id")

            if BatchId:
                # Met à jour le statut du batch en PENDING pour retry
                try:
                    BatchObj = self.Database.GetBatch(BatchId)
                    if BatchObj:
                        BatchObj.Status = BatchStatus.PENDING
                        BatchObj.AssignedClientId = None
                        BatchObj.RetryCount += 1
                        self.Database.UpdateBatch(BatchObj)
                        self.Logger.warning(f"Batch {BatchId} remis en PENDING après erreur")
                except Exception as db_error:
                    self.Logger.error(f"Impossible de mettre à jour le batch après erreur: {db_error}")

                # Nettoie ActiveBatches
                if BatchId in self.ActiveBatches:
                    del self.ActiveBatches[BatchId]

            # Remet le client en idle
            if ClientId:
                self._SetClientIdleIfNoOtherBatches(ClientId)

            return False

    async def _SaveUpscaledImage(self, ImageData: dict, UpscaledDir: str) -> bool:
        """
        Sauvegarde une image upscalée, en la reconvertissant en PNG si nécessaire
        pour la compatibilité avec FFmpeg

        Args:
            ImageData: Dictionnaire contenant les données de l'image
            UpscaledDir: Répertoire de destination

        Returns:
            True si succès
        """
        def _DoSave():
            """Fonction synchrone exécutée dans un thread"""
            try:
                FrameNumber = ImageData.get("number")
                ImageB64 = ImageData.get("data")
                ReceivedFormat = ImageData.get("format", "png")

                if not ImageB64:
                    raise ValueError("Données d'image manquantes")

                # Décode l'image (opération CPU intensive)
                ImageBytes = base64.b64decode(ImageB64)

                # Nom de fichier toujours en PNG pour FFmpeg
                Filename = f"frame_{FrameNumber:08d}.png"
                OutputPath = os.path.join(UpscaledDir, Filename)

                # Si le format reçu n'est pas PNG, convertit en PNG
                if ReceivedFormat != "png":
                    try:
                        Buffer = io.BytesIO(ImageBytes)
                        with Image.open(Buffer) as Img:
                            Img.save(OutputPath, format='PNG')
                        return True
                    except Exception as e:
                        self.Logger.warning(f"Échec conversion {ReceivedFormat}->PNG: {e}")

                # Sauvegarde directe (PNG ou fallback)
                with open(OutputPath, 'wb') as f:
                    f.write(ImageBytes)

                return True

            except Exception as e:
                # MOYENNE Problème 28: raise au lieu de raise e (préserve traceback)
                raise

        # Exécute la sauvegarde dans un thread séparé
        return await asyncio.to_thread(_DoSave)

    async def _CheckTimeouts(self):
        """Vérifie les batches en timeout"""
        try:
            CurrentTime = time.time()
            TimeoutBatches = []

            for BatchId, BatchInfo in self.ActiveBatches.items():
                ElapsedTime = CurrentTime - BatchInfo["start_time"]

                if ElapsedTime > NetworkConfig.BATCH_TIMEOUT:
                    self.Logger.warning(f"Batch {BatchId} en timeout ({ElapsedTime:.0f}s)")
                    TimeoutBatches.append(BatchId)

            # Gère les timeouts - CRITIQUE: wrapper individuel pour éviter qu'un échec bloque les autres
            for BatchId in TimeoutBatches:
                try:
                    await self.HandleTimeout(BatchId)
                except Exception as e:
                    self.Logger.error(f"Erreur HandleTimeout pour batch {BatchId}: {e}", exc_info=True)
                    # Continue avec les autres batches en timeout
                    continue

        except Exception as e:
            self.Logger.error(f"Erreur critique lors de la vérification des timeouts: {e}", exc_info=True)

    async def HandleTimeout(self, BatchId: str):
        """
        Gère le timeout d'un batch.
        Ne déconnecte PAS le client - le heartbeat monitoring s'en chargera
        si le client est vraiment inactif.

        Args:
            BatchId: ID du batch
        """
        try:
            if BatchId not in self.ActiveBatches:
                return

            BatchInfo = self.ActiveBatches[BatchId]
            ClientId = BatchInfo["client_id"]

            self.Logger.warning(f"Timeout du batch {BatchId} (client {ClientId})")

            # Émet un événement de timeout
            EmitError(
                BatchTimeoutError(BatchId, NetworkConfig.BATCH_TIMEOUT, ClientId),
                ErrorCategory.BATCH,
                ErrorSeverity.WARNING,
                "BatchDistributor",
                context={"batch_id": BatchId, "client_id": ClientId, "timeout": NetworkConfig.BATCH_TIMEOUT},
                recoverable=True,
                suggested_action="reassign"
            )

            # Récupère le batch
            BatchObj = self.Database.GetBatch(BatchId)
            if not BatchObj:
                # ALERTE CRITIQUE: batch dans ActiveBatches mais pas dans DB!
                self.Logger.critical(f"CORRUPTION: Batch {BatchId} dans ActiveBatches mais absent de la DB!")
                del self.ActiveBatches[BatchId]
                return

            # Incrémente le compteur de retry (statistiques uniquement)
            BatchObj.RetryCount += 1

            # CRITIQUE: Remettre en PENDING dans la DB D'ABORD, PUIS retirer de ActiveBatches
            # Ceci garantit la cohérence : le batch est toujours dans un état valide
            self.Logger.warning(f"⟳ Batch {BatchId} remis en file d'attente après timeout (tentative #{BatchObj.RetryCount})")
            BatchObj.Status = BatchStatus.PENDING
            BatchObj.AssignedClientId = None
            self.Database.UpdateBatch(BatchObj)

            # MAINTENANT on peut retirer du tracking en mémoire
            del self.ActiveBatches[BatchId]

            # Remet le client en IDLE au lieu de le déconnecter
            # Le heartbeat monitoring se charge de déconnecter les clients inactifs
            self._SetClientIdleIfNoOtherBatches(ClientId)

        except Exception as e:
            # MOYENNE Problème 25: Logger CRITICAL et remonter via ErrorEventManager
            self.Logger.critical(
                f"ERREUR CRITIQUE lors de la gestion du timeout pour batch {BatchId}: {e}",
                exc_info=True
            )

            # Émet un événement d'erreur critique
            EmitError(
                e,
                ErrorCategory.BATCH,
                ErrorSeverity.CRITICAL,
                "BatchDistributor.HandleTimeout",
                context={"batch_id": BatchId},
                recoverable=False
            )

            # Tente de nettoyer ActiveBatches même en cas d'erreur
            try:
                if BatchId in self.ActiveBatches:
                    del self.ActiveBatches[BatchId]
            except Exception:
                pass

    async def ReassignClientBatches(self, ClientId: str):
        """
        Réassigne les batches d'un client déconnecté.
        Appelé quand un client est retiré (manuellement ou par déconnexion).

        Args:
            ClientId: ID du client déconnecté
        """
        try:
            BatchesToReassign = []

            # Trouve les batches actifs assignés à ce client
            for BatchId, BatchInfo in list(self.ActiveBatches.items()):
                if BatchInfo.get("client_id") == ClientId:
                    BatchesToReassign.append(BatchId)

            if not BatchesToReassign:
                return

            self.Logger.info(f"Réallocation de {len(BatchesToReassign)} batch(es) du client {ClientId}")

            for BatchId in BatchesToReassign:
                # Retire du tracking actif
                del self.ActiveBatches[BatchId]

                # CRITIQUE Problème 20: Vérification état avant réallocation
                # Risque : Remettre batch COMPLETED en PENDING
                BatchObj = self.Database.GetBatch(BatchId)
                if BatchObj:
                    # Vérifie que le batch est dans un état valide pour réallocation
                    if BatchObj.Status in [BatchStatus.ASSIGNED, BatchStatus.PROCESSING]:
                        BatchObj.Status = BatchStatus.PENDING
                        BatchObj.AssignedClientId = None
                        # Pas d'incrément de RetryCount car ce n'est pas une erreur
                        self.Database.UpdateBatch(BatchObj)
                        self.Logger.debug(f"Batch {BatchId} remis en PENDING pour réallocation")
                    else:
                        # Le batch est déjà dans un état final (COMPLETED, FAILED)
                        self.Logger.warning(
                            f"Batch {BatchId} ignoré pour réallocation (état: {BatchObj.Status})"
                        )
                    self.Logger.info(f"Batch {BatchId} remis en file d'attente")

        except Exception as e:
            self.Logger.error(f"Erreur lors de la réallocation des batches: {e}")

    def _SetClientIdleIfNoOtherBatches(self, ClientId: str):
        """
        Remet le client à IDLE seulement s'il n'a pas d'autres batches actifs.
        Évite une race condition où le serveur a déjà assigné un nouveau batch.

        Args:
            ClientId: ID du client
        """
        # MOYENNE Problème 30: Copie pour éviter "dictionary changed size during iteration"
        ClientHasOtherBatches = any(
            Info.get("client_id") == ClientId
            for Info in list(self.ActiveBatches.values())
        )
        if not ClientHasOtherBatches:
            self.ClientManager.UpdateClientStatus(ClientId, ClientStatus.IDLE)
        else:
            self.Logger.debug(f"Client {ClientId} a d'autres batches actifs, conserve statut PROCESSING")

    def UpdateMaxConcurrentBatches(self, NewLimit: int):
        """
        Met à jour dynamiquement la limite d'envois concurrents.
        Pas de limite maximale technique imposée.

        Args:
            NewLimit: Nouvelle limite (minimum 1)
        """
        try:
            # Validation minimale
            NewLimit = max(1, NewLimit)

            # MOYENNE Problème 26: Créer nouveau semaphore sans bloquer tâches en cours
            # Les tâches qui ont déjà acquis l'ancien semaphore (via async with)
            # conservent leur référence locale et continueront normalement.
            # Seules les NOUVELLES tâches utiliseront le nouveau semaphore.
            self.SendSemaphore = asyncio.Semaphore(NewLimit)

            self.Logger.info(f"Limite d'envois concurrents mise à jour: {NewLimit}")

        except Exception as e:
            self.Logger.error(f"Erreur lors de la mise à jour de la limite concurrente: {e}")

    def CancelVideoProcessing(self, VideoId: str):
        """
        Annule le traitement de tous les batches d'une vidéo

        Args:
            VideoId: ID de la vidéo
        """
        try:
            self.Logger.info(f"Annulation du traitement pour la vidéo {VideoId}")

            # Arrête la distribution si elle concerne cette vidéo
            if self.Running:
                asyncio.create_task(self.StopDistribution())

            # HAUTE Problème 21: Thread-safe CancelVideoProcessing
            # Risque : Modification ActiveBatches pendant itération
            # Retire tous les batches actifs de cette vidéo du tracking
            BatchesToRemove = []
            # Copie pour éviter "dictionary changed size during iteration"
            for BatchId, BatchInfo in list(self.ActiveBatches.items()):
                BatchObj = self.Database.GetBatch(BatchId)
                if BatchObj and BatchObj.VideoId == VideoId:
                    BatchesToRemove.append((BatchId, BatchObj, BatchInfo))

            for BatchId, BatchObj, BatchInfo in BatchesToRemove:
                # Marque le batch comme FAILED dans la DB
                BatchObj.Status = BatchStatus.FAILED
                BatchObj.ErrorMessage = "Traitement annulé par l'utilisateur"
                self.Database.UpdateBatch(BatchObj)

                # Retire du tracking
                del self.ActiveBatches[BatchId]
                self.Logger.info(f"Batch {BatchId} annulé et retiré du tracking")

                # Remet le client en idle
                ClientId = BatchInfo.get("client_id")
                if ClientId:
                    self.ClientManager.UpdateClientStatus(ClientId, ClientStatus.IDLE)

            self.Logger.info(f"✓ Traitement annulé pour la vidéo {VideoId}")

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'annulation du traitement: {e}")

    def GetDistributionStats(self, VideoId: str) -> dict:
        """
        Récupère les statistiques de distribution

        Args:
            VideoId: ID de la vidéo

        Returns:
            Dictionnaire de statistiques
        """
        try:
            AllBatches = self.Database.GetBatchesByVideo(VideoId)

            Stats = {
                "total": len(AllBatches),
                "pending": sum(1 for b in AllBatches if b.Status == BatchStatus.PENDING),
                "assigned": sum(1 for b in AllBatches if b.Status == BatchStatus.ASSIGNED),
                "processing": sum(1 for b in AllBatches if b.Status == BatchStatus.PROCESSING),
                "completed": sum(1 for b in AllBatches if b.Status == BatchStatus.COMPLETED),
                "failed": sum(1 for b in AllBatches if b.Status == BatchStatus.FAILED),
                "timeout": sum(1 for b in AllBatches if b.Status == BatchStatus.TIMEOUT),
                "active": len(self.ActiveBatches)
            }

            return Stats

        except Exception as e:
            self.Logger.error(f"Erreur lors de la récupération des statistiques: {e}")
            return {}


# ============================================================================
# EXEMPLE D'UTILISATION
# ============================================================================

if __name__ == "__main__":
    print("BatchDistributor - Composant serveur pour distribution de paquets")
    print("Doit être utilisé dans le contexte du serveur complet")
