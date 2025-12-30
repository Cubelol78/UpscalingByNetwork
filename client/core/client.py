"""
Client principal d'upscaling distribué
Connecte au serveur, reçoit et traite les batches d'images
"""

import asyncio
import time
from typing import Optional
from asyncio import Queue

from client.core.connection import ConnectionManager
from client.core.processor import LocalProcessor
from shared.protocol.messages import (
    MessageFactory, BatchAssignment, HeartbeatPing, HeartbeatPong,
    BatchResult
)
from shared.utils.logger import GetClientLogger
from shared.utils.constants import ClientStatus, NetworkConfig


class UpscalingClient:
    """Client d'upscaling distribué"""

    def __init__(self):
        """Initialise le client"""
        self.Logger = GetClientLogger()
        self.ConnectionManager = ConnectionManager()
        self.LocalProcessor = LocalProcessor()
        self.Running = False
        self.Status = ClientStatus.IDLE
        self.CurrentBatch = None
        self.ProcessingTask = None  # Tâche de traitement en arrière-plan

        # File d'attente pour les résultats à envoyer (découplage traitement/envoi)
        self.ResultQueue: Queue = None
        self.SenderTask = None  # Tâche d'envoi en arrière-plan

    async def Start(self, Host: str, Port: int, Password: str = "") -> bool:
        """
        Démarre le client et connecte au serveur

        Args:
            Host: Adresse du serveur
            Port: Port du serveur
            Password: Mot de passe (optionnel)

        Returns:
            True si démarrage réussi
        """
        try:
            self.Logger.info("Démarrage du client...")

            # Connecte au serveur
            if not await self.ConnectionManager.ConnectToServer(Host, Port, Password):
                self.Logger.error("Impossible de se connecter au serveur")
                return False

            self.Running = True
            self.Status = ClientStatus.IDLE

            # Initialise la queue de résultats et démarre le sender en arrière-plan
            self.ResultQueue = asyncio.Queue()
            self.SenderTask = asyncio.create_task(self._SenderLoop())

            self.Logger.info("✓ Client démarré et connecté")

            # Lance la boucle principale
            await self.MainLoop()

            return True

        except Exception as e:
            self.Logger.error(f"Erreur lors du démarrage: {e}")
            return False

    async def Stop(self):
        """Arrête le client proprement"""
        self.Logger.info("Arrêt du client...")

        self.Running = False

        # Annule la tâche de traitement en cours si elle existe
        if self.ProcessingTask and not self.ProcessingTask.done():
            self.ProcessingTask.cancel()
            try:
                await self.ProcessingTask
            except asyncio.CancelledError:
                self.Logger.info("Tâche de traitement annulée")

        # Attend que la queue d'envoi soit vidée (avec timeout)
        if self.ResultQueue and not self.ResultQueue.empty():
            self.Logger.info(f"Attente de l'envoi des {self.ResultQueue.qsize()} résultat(s) en attente...")
            try:
                await asyncio.wait_for(self.ResultQueue.join(), timeout=30.0)
                self.Logger.info("Queue d'envoi vidée")
            except asyncio.TimeoutError:
                self.Logger.warning("Timeout lors de l'attente de la queue, arrêt forcé")

        # Annule la tâche d'envoi
        if self.SenderTask and not self.SenderTask.done():
            self.SenderTask.cancel()
            try:
                await self.SenderTask
            except asyncio.CancelledError:
                pass

        # Déconnecte du serveur
        await self.ConnectionManager.Disconnect()

        # Nettoie les fichiers temporaires
        self.LocalProcessor.CleanupAll()

        self.Logger.info("✓ Client arrêté")

    async def MainLoop(self):
        """Boucle principale du client"""
        try:
            while self.Running:
                # Reçoit un message du serveur
                MessageData = await asyncio.wait_for(
                    self.ConnectionManager.ReceiveMessage(Decrypt=True),
                    timeout=NetworkConfig.HEARTBEAT_TIMEOUT * 2
                )

                if not MessageData:
                    self.Logger.warning("Message vide reçu, déconnexion probable")
                    break

                # Parse le message
                Message = MessageFactory.CreateFromJson(MessageData)

                # Traite le message
                await self._HandleMessage(Message)

        except asyncio.TimeoutError:
            self.Logger.error("Timeout de communication avec le serveur")
        except Exception as e:
            self.Logger.error(f"Erreur dans la boucle principale: {e}")
        finally:
            await self.Stop()

    async def _HandleMessage(self, Message):
        """
        Traite un message reçu du serveur

        Args:
            Message: Message parsé
        """
        try:
            MessageType = Message.MessageType

            # Heartbeat ping
            if isinstance(Message, HeartbeatPing):
                await self._HandleHeartbeatPing(Message)

            # Batch assignment
            elif isinstance(Message, BatchAssignment):
                await self._HandleBatchAssignment(Message)

            # Autres types
            else:
                self.Logger.debug(f"Message reçu: {MessageType}")

        except Exception as e:
            self.Logger.error(f"Erreur lors du traitement du message: {e}")

    async def _HandleHeartbeatPing(self, PingMessage: HeartbeatPing):
        """
        Répond au heartbeat ping

        Args:
            PingMessage: Message HeartbeatPing
        """
        try:
            PingTimestamp = PingMessage.Payload.get("timestamp")

            # Crée la réponse pong
            Pong = HeartbeatPong(
                PingTimestamp=PingTimestamp,
                ClientStatus=self.Status
            )

            # Envoie au serveur
            await self.ConnectionManager.SendMessage(Pong.ToJson(), Encrypted=True)

            self.Logger.debug("Heartbeat pong envoyé")

        except Exception as e:
            self.Logger.error(f"Erreur lors de la réponse heartbeat: {e}")

    async def _HandleBatchAssignment(self, Assignment: BatchAssignment):
        """
        Traite un batch d'images assigné
        Lance le traitement en arrière-plan pour ne pas bloquer les heartbeats

        Args:
            Assignment: Message BatchAssignment
        """
        try:
            BatchId = Assignment.GetBatchId()
            self.CurrentBatch = BatchId

            self.Logger.info(f"Nouveau batch reçu: {BatchId}")
            self.Logger.info(f"  Nombre d'images: {Assignment.Payload.get('image_count')}")

            # Met à jour le statut
            self.Status = ClientStatus.PROCESSING

            # Lance le traitement en tâche de fond pour ne pas bloquer la réception des heartbeats
            self.ProcessingTask = asyncio.create_task(
                self._ProcessBatchAsync(BatchId, Assignment.Payload)
            )

        except Exception as e:
            self.Logger.error(f"Erreur lors du traitement du batch: {e}")
            self.Status = ClientStatus.IDLE
            self.CurrentBatch = None

    async def _ProcessBatchAsync(self, BatchId: str, Payload: dict):
        """
        Traite un batch de manière asynchrone dans un thread séparé.
        Ajoute le résultat à la queue d'envoi au lieu d'envoyer directement.
        Permet de recevoir un nouveau batch pendant l'envoi du précédent.

        Args:
            BatchId: ID du batch
            Payload: Données du batch
        """
        try:
            # Traite le batch dans un thread séparé (Real-ESRGAN est bloquant)
            Result = await asyncio.to_thread(
                self.LocalProcessor.ProcessBatch,
                Payload
            )

            if not Result:
                self.Logger.error(f"Échec du traitement du batch {BatchId}")
                Result = BatchResult(
                    BatchId=BatchId,
                    Success=False,
                    ErrorMessage="Erreur interne du processeur"
                )

            # Ajoute le résultat à la queue d'envoi (au lieu d'envoyer directement)
            await self.ResultQueue.put(Result)
            self.Logger.info(f"Batch {BatchId} traité, ajouté à la queue d'envoi")

        except Exception as e:
            self.Logger.error(f"Erreur lors du traitement async du batch: {e}")
            # En cas d'erreur, ajoute quand même un résultat d'échec à la queue
            try:
                ErrorResult = BatchResult(
                    BatchId=BatchId,
                    Success=False,
                    ErrorMessage=str(e)
                )
                await self.ResultQueue.put(ErrorResult)
            except Exception:
                pass

        finally:
            # Remet en idle immédiatement (avant l'envoi)
            # Permet de recevoir un nouveau batch pendant l'envoi
            self.Status = ClientStatus.IDLE
            self.CurrentBatch = None
            self.ProcessingTask = None

    async def _SenderLoop(self):
        """
        Boucle d'envoi des résultats en arrière-plan.
        Consomme la queue et envoie les résultats un par un (FIFO).
        Permet au client de recevoir de nouveaux batches pendant l'envoi.
        """
        while self.Running:
            try:
                # Attend un résultat dans la queue (bloquant async)
                Result = await self.ResultQueue.get()

                BatchId = Result.Payload.get("batch_id", "unknown")
                self.Logger.info(f"Envoi du résultat batch {BatchId}...")

                # Envoie le résultat au serveur
                Success = await self.ConnectionManager.SendMessage(
                    Result.ToJson(),
                    Encrypted=True
                )

                if Success:
                    if Result.IsSuccess():
                        self.Logger.info(f"✓ Résultat batch {BatchId} envoyé avec succès")
                    else:
                        self.Logger.warning(f"✗ Résultat batch {BatchId} (échec) envoyé")
                else:
                    self.Logger.error(f"Échec d'envoi du résultat batch {BatchId}")

                # Marque la tâche comme terminée dans la queue
                self.ResultQueue.task_done()

            except asyncio.CancelledError:
                self.Logger.info("SenderLoop annulé")
                break
            except Exception as e:
                self.Logger.error(f"Erreur dans SenderLoop: {e}")

    def GetStatus(self) -> dict:
        """
        Récupère le statut du client

        Returns:
            Dictionnaire de statut
        """
        ServerInfo = self.ConnectionManager.GetServerInfo()

        return {
            "running": self.Running,
            "connected": self.ConnectionManager.IsConnected(),
            "status": self.Status,
            "current_batch": self.CurrentBatch,
            "server_address": ServerInfo[0],
            "server_port": ServerInfo[1],
            "client_id": self.ConnectionManager.ClientId
        }


# ============================================================================
# FONCTION D'AIDE POUR LANCER LE CLIENT
# ============================================================================

async def RunClient(Host: str, Port: int, Password: str = ""):
    """
    Lance le client avec les paramètres donnés

    Args:
        Host: Adresse du serveur
        Port: Port du serveur
        Password: Mot de passe (optionnel)
    """
    Client = UpscalingClient()

    try:
        await Client.Start(Host, Port, Password)

    except KeyboardInterrupt:
        print("\n\nInterruption utilisateur")

    finally:
        await Client.Stop()


# ============================================================================
# EXEMPLE D'UTILISATION
# ============================================================================

if __name__ == "__main__":
    import sys

    # Arguments
    if len(sys.argv) < 3:
        print("Usage: python client.py <host> <port> [password]")
        sys.exit(1)

    Host = sys.argv[1]
    Port = int(sys.argv[2])
    Password = sys.argv[3] if len(sys.argv) > 3 else ""

    # Lance le client
    asyncio.run(RunClient(Host, Port, Password))
