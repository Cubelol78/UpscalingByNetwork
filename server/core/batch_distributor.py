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
from shared.utils.constants import BatchStatus, ClientStatus, NetworkConfig, Limits


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
        """Arrête la distribution"""
        self.Running = False
        if self.DistributionTask:
            self.DistributionTask.cancel()
            try:
                await self.DistributionTask
            except asyncio.CancelledError:
                pass
        self.Logger.info("Distribution arrêtée")

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

                    if CompletedCount == len(AllBatches):
                        self.Logger.info(f"Tous les batches complétés pour {VideoId}")
                        break

                    # Attend un peu avant de revérifier
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
                    AssignmentTasks.append(Task)

                    if not AvailableClients:
                        break

                # Attend que tous les envois se terminent (avec gestion d'erreurs)
                if AssignmentTasks:
                    Results = await asyncio.gather(*AssignmentTasks, return_exceptions=True)

                    # Log les erreurs sans arrêter la boucle
                    for Index, Result in enumerate(Results):
                        if isinstance(Result, Exception):
                            self.Logger.error(f"Erreur lors de l'assignation du batch #{Index}: {Result}")

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
                    self.Database.UpdateBatch(Batch)
                    RecoveredCount += 1

            if RecoveredCount > 0:
                self.Logger.info(f"✓ {RecoveredCount} batch(es) bloqué(s) récupéré(s)")
            else:
                self.Logger.debug("Aucun batch bloqué détecté")

        except Exception as e:
            self.Logger.error(f"Erreur lors de la récupération des batches bloqués: {e}")

    def _GetAvailableClients(self) -> List[str]:
        """
        Récupère les clients disponibles (idle avec canal Data connecté)

        Returns:
            Liste des IDs des clients disponibles
        """
        AvailableClients = []

        for ClientId in self.ClientManager.GetConnectedClients():
            Status = self.ClientManager.GetClientStatus(ClientId)

            # Vérifie que le client est IDLE ET que son canal Data est connecté
            if Status == ClientStatus.IDLE:
                ClientInfo = self.ClientManager.Clients.get(ClientId)

                # Vérifie que le canal Data est connecté (requis pour envoyer les batches)
                if ClientInfo and ClientInfo.IsDataConnected():
                    AvailableClients.append(ClientId)
                else:
                    self.Logger.debug(f"Client {ClientId} IDLE mais canal Data non connecté, ignoré")

        return AvailableClients

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

            # Met à jour le statut du batch
            BatchObj.Status = BatchStatus.ASSIGNED
            BatchObj.AssignedClientId = ClientId
            BatchObj.AssignedAt = datetime.now()
            self.Database.UpdateBatch(BatchObj)

            # Met à jour le statut du client
            self.ClientManager.UpdateClientStatus(ClientId, ClientStatus.RECEIVING)

            # Envoie le batch au client
            Success = await self.SendBatchToClient(BatchObj, VideoObj, ClientId)

            if Success:
                # Marque comme processing
                BatchObj.Status = BatchStatus.PROCESSING
                self.Database.UpdateBatch(BatchObj)
                self.ClientManager.UpdateClientStatus(ClientId, ClientStatus.PROCESSING)

                # Track le batch actif
                self.ActiveBatches[BatchId] = {
                    "client_id": ClientId,
                    "start_time": time.time(),
                    "retry_count": BatchObj.RetryCount
                }

                return True
            else:
                # Échec, remet en pending
                BatchObj.Status = BatchStatus.PENDING
                BatchObj.AssignedClientId = None
                self.Database.UpdateBatch(BatchObj)
                self.ClientManager.UpdateClientStatus(ClientId, ClientStatus.IDLE)
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
                Model=VideoObj.Model,
                TtaMode=VideoObj.TtaMode
            )

            # Envoie via le canal Data
            Success = await self.ClientManager.SendDataMessage(
                ClientId,
                Message.ToJson(),
                Encrypted=True
            )

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
                Model=VideoObj.Model,
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

            # Sauvegarde les images upscalées
            VideoId = BatchObj.VideoId
            UpscaledDir = self.VideoProcessor.GetUpscaledDir(VideoId)
            os.makedirs(UpscaledDir, exist_ok=True)

            SavedCount = 0
            FailedImages = []

            # Traite les images en parallèle pour ne pas bloquer l'event loop
            SaveTasks = []
            for ImageData in UpscaledImages:
                SaveTasks.append(self._SaveUpscaledImage(ImageData, UpscaledDir))

            # Attend que toutes les sauvegardes se terminent
            SaveResults = await asyncio.gather(*SaveTasks, return_exceptions=True)

            # Compte les succès/échecs
            for Index, Result in enumerate(SaveResults):
                if isinstance(Result, Exception):
                    FailedImages.append(UpscaledImages[Index].get("number", "?"))
                    self.Logger.error(f"Erreur lors de la sauvegarde de l'image: {Result}")
                elif Result:
                    SavedCount += 1
                else:
                    FailedImages.append(UpscaledImages[Index].get("number", "?"))

            # Vérification du résultat de sauvegarde
            if SavedCount == 0:
                # Échec total - aucune image sauvegardée
                self.Logger.error(f"Batch {BatchId}: Échec total - 0/{ReceivedCount} images sauvegardées")

                # Incrémente le compteur de retry (statistiques uniquement)
                BatchObj.RetryCount += 1
                BatchObj.ErrorMessage = "Aucune image sauvegardée sur le serveur"

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

            elif SavedCount < ExpectedCount:
                # Succès partiel - certaines images manquantes
                self.Logger.warning(
                    f"Batch {BatchId}: Succès partiel - {SavedCount}/{ExpectedCount} images sauvegardées. "
                    f"Images manquantes: {FailedImages}"
                )

            self.Logger.info(f"✓ {SavedCount}/{ExpectedCount} images upscalées sauvegardées")

            # Marque le batch comme complété (même si partiel, on continue)
            BatchObj.Status = BatchStatus.COMPLETED
            BatchObj.CompletedAt = datetime.now()
            self.Database.UpdateBatch(BatchObj)

            # Met à jour la progression de la vidéo
            VideoObj = self.Database.GetVideo(VideoId)
            if VideoObj:
                VideoObj.CompletedBatches += 1
                VideoObj.UpdateProgress()
                self.Database.UpdateVideo(VideoObj)

                self.Logger.info(f"Progression vidéo: {VideoObj.CompletedBatches}/{VideoObj.TotalBatches} ({VideoObj.Progress*100:.1f}%)")

            # Retire du tracking
            if BatchId in self.ActiveBatches:
                del self.ActiveBatches[BatchId]

            # Remet le client en idle si pas d'autres batches
            self._SetClientIdleIfNoOtherBatches(ClientId)

            return True

        except Exception as e:
            self.Logger.error(f"Erreur lors de la réception du résultat: {e}")
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
                raise e

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

            # Gère les timeouts
            for BatchId in TimeoutBatches:
                await self.HandleTimeout(BatchId)

        except Exception as e:
            self.Logger.error(f"Erreur lors de la vérification des timeouts: {e}")

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

            # Récupère le batch
            BatchObj = self.Database.GetBatch(BatchId)
            if not BatchObj:
                del self.ActiveBatches[BatchId]
                return

            # Incrémente le compteur de retry (statistiques uniquement)
            BatchObj.RetryCount += 1

            # Retire du tracking
            del self.ActiveBatches[BatchId]

            # Remet le client en IDLE au lieu de le déconnecter
            # Le heartbeat monitoring se charge de déconnecter les clients inactifs
            self._SetClientIdleIfNoOtherBatches(ClientId)

            # Toujours remettre en PENDING pour retry (pas de limite)
            self.Logger.warning(f"⟳ Batch {BatchId} remis en file d'attente après timeout (tentative #{BatchObj.RetryCount})")
            await asyncio.sleep(Limits.RETRY_DELAY)
            BatchObj.Status = BatchStatus.PENDING
            BatchObj.AssignedClientId = None
            self.Database.UpdateBatch(BatchObj)

        except Exception as e:
            self.Logger.error(f"Erreur lors de la gestion du timeout: {e}")

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

                # Remet le batch en PENDING dans la base de données
                BatchObj = self.Database.GetBatch(BatchId)
                if BatchObj:
                    BatchObj.Status = BatchStatus.PENDING
                    BatchObj.AssignedClientId = None
                    # Pas d'incrément de RetryCount car ce n'est pas une erreur
                    self.Database.UpdateBatch(BatchObj)
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
        ClientHasOtherBatches = any(
            Info.get("client_id") == ClientId
            for Info in self.ActiveBatches.values()
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

            # Crée un nouveau semaphore avec la nouvelle limite
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

            # Retire tous les batches actifs de cette vidéo du tracking
            BatchesToRemove = []
            for BatchId, BatchInfo in self.ActiveBatches.items():
                BatchObj = self.Database.GetBatch(BatchId)
                if BatchObj and BatchObj.VideoId == VideoId:
                    BatchesToRemove.append(BatchId)
                    # Remet le client en idle
                    ClientId = BatchInfo.get("client_id")
                    if ClientId:
                        self.ClientManager.UpdateClientStatus(ClientId, ClientStatus.IDLE)

            for BatchId in BatchesToRemove:
                del self.ActiveBatches[BatchId]
                self.Logger.info(f"Batch {BatchId} retiré du tracking actif")

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
