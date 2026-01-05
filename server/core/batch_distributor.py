"""
Distributeur de paquets pour l'upscaling distribué
Gère l'attribution, l'envoi et la réception des batches
"""

import asyncio
import os
import base64
import time
from typing import Optional, Dict, List
from datetime import datetime
from PIL import Image
import io

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

    async def StartDistribution(self, VideoId: str):
        """
        Démarre la distribution des batches pour une vidéo

        Args:
            VideoId: ID de la vidéo
        """
        self.Running = True
        self.Logger.info(f"Démarrage de la distribution pour la vidéo {VideoId}")

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

                # Distribue les batches aux clients disponibles
                for BatchObj in PendingBatches[:len(AvailableClients)]:
                    ClientId = AvailableClients.pop(0)

                    # Assigne le batch
                    await self.AssignBatch(BatchObj.BatchId, ClientId, VideoId)

                    if not AvailableClients:
                        break

                # Vérifie les timeouts
                await self._CheckTimeouts()

                await asyncio.sleep(1)

        except asyncio.CancelledError:
            self.Logger.info("Boucle de distribution annulée")
        except Exception as e:
            self.Logger.error(f"Erreur dans la boucle de distribution: {e}")

    def _GetAvailableClients(self) -> List[str]:
        """
        Récupère les clients disponibles (idle)

        Returns:
            Liste des IDs des clients disponibles
        """
        AvailableClients = []

        for ClientId in self.ClientManager.GetConnectedClients():
            Status = self.ClientManager.GetClientStatus(ClientId)
            if Status == ClientStatus.IDLE:
                AvailableClients.append(ClientId)

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

    async def SendBatchToClient(self, BatchObj: Batch, VideoObj: Video,
                               ClientId: str) -> bool:
        """
        Envoie un batch d'images à un client

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

            self.Logger.info(f"Envoi de {len(FramePaths)} images au client {ClientId}...")

            # Charge et encode les images en base64
            Images = []
            for Index, FramePath in enumerate(FramePaths):
                try:
                    # Lit l'image
                    with open(FramePath, 'rb') as f:
                        ImageData = f.read()

                    # Encode en base64
                    ImageB64 = base64.b64encode(ImageData).decode('utf-8')

                    # Numéro de frame absolu
                    FrameNumber = BatchObj.StartFrame + Index

                    Images.append({
                        "id": str(FrameNumber),
                        "number": FrameNumber,
                        "data": ImageB64,
                        "filename": os.path.basename(FramePath)
                    })

                except Exception as e:
                    self.Logger.error(f"Erreur lors du chargement de {FramePath}: {e}")
                    continue

            # Crée le message BatchAssignment
            Message = BatchAssignment(
                BatchId=BatchObj.BatchId,
                VideoId=VideoObj.VideoId,
                Images=Images,
                UpscaleFactor=VideoObj.UpscaleFactor,
                Model=VideoObj.Model,
                TtaMode=VideoObj.TtaMode
            )

            # Envoie au client
            Success = await self.ClientManager.SendMessage(
                ClientId,
                Message.ToJson(),
                Encrypted=True
            )

            if Success:
                self.Logger.info(f"✓ Batch {BatchObj.BatchId} envoyé au client {ClientId}")
            else:
                self.Logger.error(f"Échec de l'envoi du batch au client {ClientId}")

            return Success

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'envoi du batch: {e}")
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

                # Marque comme failed et retry
                BatchObj.Status = BatchStatus.FAILED
                BatchObj.ErrorMessage = ErrorMsg
                BatchObj.RetryCount += 1
                self.Database.UpdateBatch(BatchObj)

                # Retire du tracking
                if BatchId in self.ActiveBatches:
                    del self.ActiveBatches[BatchId]

                # Retry si possible
                if BatchObj.RetryCount < Limits.MAX_RETRY_ATTEMPTS:
                    self.Logger.info(f"Retry du batch {BatchId} ({BatchObj.RetryCount}/{Limits.MAX_RETRY_ATTEMPTS})")
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
                # Marque comme échec et retry
                BatchObj.Status = BatchStatus.FAILED
                BatchObj.ErrorMessage = "Aucune image reçue du client"
                BatchObj.RetryCount += 1
                self.Database.UpdateBatch(BatchObj)

                if BatchObj.RetryCount < Limits.MAX_RETRY_ATTEMPTS:
                    self.Logger.info(f"Retry du batch {BatchId} ({BatchObj.RetryCount}/{Limits.MAX_RETRY_ATTEMPTS})")
                    BatchObj.Status = BatchStatus.PENDING
                    BatchObj.AssignedClientId = None
                    self.Database.UpdateBatch(BatchObj)

                # Retire du tracking et remet le client en idle si pas d'autres batches
                if BatchId in self.ActiveBatches:
                    del self.ActiveBatches[BatchId]
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
            for ImageData in UpscaledImages:
                try:
                    FrameNumber = ImageData.get("number")
                    ImageB64 = ImageData.get("data")
                    Filename = ImageData.get("filename", f"frame_{FrameNumber:08d}.png")

                    # Décode l'image
                    ImageBytes = base64.b64decode(ImageB64)

                    # Sauvegarde
                    OutputPath = os.path.join(UpscaledDir, Filename)
                    with open(OutputPath, 'wb') as f:
                        f.write(ImageBytes)

                    SavedCount += 1

                except Exception as e:
                    FailedImages.append(ImageData.get("number", "?"))
                    self.Logger.error(f"Erreur lors de la sauvegarde de l'image {FrameNumber}: {e}")
                    continue

            # Vérification du résultat de sauvegarde
            if SavedCount == 0:
                # Échec total - aucune image sauvegardée
                self.Logger.error(f"Batch {BatchId}: Échec total - 0/{ReceivedCount} images sauvegardées")
                BatchObj.Status = BatchStatus.FAILED
                BatchObj.ErrorMessage = "Aucune image sauvegardée sur le serveur"
                BatchObj.RetryCount += 1
                self.Database.UpdateBatch(BatchObj)

                if BatchObj.RetryCount < Limits.MAX_RETRY_ATTEMPTS:
                    self.Logger.info(f"Retry du batch {BatchId} ({BatchObj.RetryCount}/{Limits.MAX_RETRY_ATTEMPTS})")
                    BatchObj.Status = BatchStatus.PENDING
                    BatchObj.AssignedClientId = None
                    self.Database.UpdateBatch(BatchObj)

                if BatchId in self.ActiveBatches:
                    del self.ActiveBatches[BatchId]
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

            # Marque comme timeout
            BatchObj.Status = BatchStatus.TIMEOUT
            BatchObj.RetryCount += 1
            self.Database.UpdateBatch(BatchObj)

            # Retire du tracking
            del self.ActiveBatches[BatchId]

            # Remet le client en IDLE au lieu de le déconnecter
            # Le heartbeat monitoring se charge de déconnecter les clients inactifs
            self._SetClientIdleIfNoOtherBatches(ClientId)

            # Retry si possible
            if BatchObj.RetryCount < Limits.MAX_RETRY_ATTEMPTS:
                self.Logger.info(f"Retry du batch {BatchId} ({BatchObj.RetryCount}/{Limits.MAX_RETRY_ATTEMPTS})")
                await asyncio.sleep(Limits.RETRY_DELAY)
                BatchObj.Status = BatchStatus.PENDING
                BatchObj.AssignedClientId = None
                self.Database.UpdateBatch(BatchObj)
            else:
                self.Logger.error(f"Batch {BatchId} a atteint le maximum de tentatives ({Limits.MAX_RETRY_ATTEMPTS})")

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
