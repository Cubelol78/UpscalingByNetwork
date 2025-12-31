"""
Client principal d'upscaling distribué
Connecte au serveur, reçoit et traite les batches d'images
"""

import asyncio
import time
import os
import json
from typing import Optional
from asyncio import Queue
from pathlib import Path

from client.core.connection import ConnectionManager
from client.core.processor import LocalProcessor
from client.utils.error_analyzer import GetErrorAnalyzer
from shared.protocol.messages import (
    MessageFactory, BatchAssignment, HeartbeatPing, HeartbeatPong,
    BatchResult, StatusUpdate, DisconnectMessage
)
from shared.utils.logger import GetClientLogger
from shared.utils.constants import ClientStatus, NetworkConfig


class UpscalingClient:
    """Client d'upscaling distribué"""

    # Configuration du retry avec backoff
    RETRY_MAX_ATTEMPTS = 3
    RETRY_BASE_DELAY = 0.5  # 0.5s, 1s, 1.5s

    def __init__(self, WorkDirectory: Optional[str] = None):
        """
        Initialise le client

        Args:
            WorkDirectory: Répertoire de travail (défaut: ~/.upscaling_client/)
        """
        self.Logger = GetClientLogger()
        self.ConnectionManager = ConnectionManager()

        # Détermine le répertoire de travail
        if WorkDirectory and WorkDirectory.strip():
            self.WorkDirectory = WorkDirectory.strip()
        else:
            self.WorkDirectory = os.path.join(Path.home(), '.upscaling_client')

        # Crée les sous-répertoires nécessaires
        TempDir = os.path.join(self.WorkDirectory, 'temp')
        self.ResultCacheDir = os.path.join(self.WorkDirectory, 'result_cache')
        os.makedirs(TempDir, exist_ok=True)
        os.makedirs(self.ResultCacheDir, exist_ok=True)

        # Initialise le processeur local avec le bon répertoire temp
        self.LocalProcessor = LocalProcessor(TempDirectory=TempDir)

        self.Running = False
        self.Status = ClientStatus.IDLE
        self.CurrentBatch = None
        self.ProcessingTask = None  # Tâche de traitement en arrière-plan

        # File d'attente pour les résultats à envoyer (découplage traitement/envoi)
        # La queue contient des chemins de fichiers (pas les données en RAM)
        self.ResultQueue: Queue = None
        self.SenderTask = None  # Tâche d'envoi en arrière-plan

        # Callback appelé lors d'une déconnexion demandée par le serveur
        self.OnServerDisconnect = None

        # Callback appelé lors d'une erreur critique nécessitant déconnexion
        self.OnCriticalError = None

        self.Logger.info(f"Client initialisé avec répertoire de travail: {self.WorkDirectory}")

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

        # Nettoie le cache des résultats en attente
        self._CleanupResultCache()

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

            # Déconnexion demandée par le serveur
            elif isinstance(Message, DisconnectMessage):
                await self._HandleDisconnect(Message)

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

            # Envoie au serveur avec retry
            async def SendPong():
                return await self.ConnectionManager.SendMessage(Pong.ToJson(), Encrypted=True)

            Success = await self._RetryWithBackoff(SendPong)
            if Success:
                self.Logger.debug("Heartbeat pong envoyé")
            else:
                self.Logger.warning("Échec de l'envoi du heartbeat pong après plusieurs tentatives")

        except Exception as e:
            self.Logger.error(f"Erreur lors de la réponse heartbeat: {e}")

    async def _HandleDisconnect(self, DisconnectMsg: DisconnectMessage):
        """
        Traite une demande de déconnexion du serveur

        Args:
            DisconnectMsg: Message DisconnectMessage
        """
        Reason = DisconnectMsg.Payload.get("reason", "Raison inconnue")
        self.Logger.warning(f"Déconnexion demandée par le serveur: {Reason}")

        # Marque le client comme devant s'arrêter
        self.Running = False

        # Notifie via callback si disponible (pour l'interface GUI)
        if hasattr(self, 'OnServerDisconnect') and self.OnServerDisconnect:
            try:
                self.OnServerDisconnect(Reason)
            except Exception as e:
                self.Logger.error(f"Erreur dans le callback de déconnexion: {e}")

    async def _RetryWithBackoff(self, AsyncFunc, MaxRetries: int = None,
                                BaseDelay: float = None) -> bool:
        """
        Helper pour exécuter une fonction async avec retry et backoff exponentiel.

        Args:
            AsyncFunc: Fonction async à exécuter (doit retourner bool)
            MaxRetries: Nombre maximum de tentatives (défaut: RETRY_MAX_ATTEMPTS)
            BaseDelay: Délai de base en secondes (défaut: RETRY_BASE_DELAY)

        Returns:
            True si succès, False après tous les échecs
        """
        if MaxRetries is None:
            MaxRetries = self.RETRY_MAX_ATTEMPTS
        if BaseDelay is None:
            BaseDelay = self.RETRY_BASE_DELAY

        for Attempt in range(MaxRetries):
            try:
                Success = await AsyncFunc()
                if Success:
                    return True

                # Backoff exponentiel: 0.5s, 1s, 1.5s
                if Attempt < MaxRetries - 1:
                    Delay = BaseDelay * (Attempt + 1)
                    self.Logger.debug(f"Tentative {Attempt + 1}/{MaxRetries} échouée, retry dans {Delay}s")
                    await asyncio.sleep(Delay)

            except Exception as e:
                self.Logger.error(f"Tentative {Attempt + 1}/{MaxRetries} - Exception: {e}")
                if Attempt < MaxRetries - 1:
                    Delay = BaseDelay * (Attempt + 1)
                    await asyncio.sleep(Delay)

        return False

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
        Sauvegarde le résultat sur disque et ajoute le chemin à la queue.
        Permet de recevoir un nouveau batch pendant l'envoi du précédent.
        Analyse les erreurs et déclenche une déconnexion si critique.

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

            # Analyse l'erreur si le traitement a échoué
            if not Result.IsSuccess():
                ErrorMessage = Result.Payload.get("error_message", "")
                await self._HandleBatchError(ErrorMessage)

            # Sauvegarde le résultat sur disque (au lieu de garder en RAM)
            CachePath = await self._SaveResultToCache(BatchId, Result)
            if CachePath:
                await self.ResultQueue.put(CachePath)
                self.Logger.info(f"Batch {BatchId} traité, sauvegardé dans le cache")
            else:
                self.Logger.error(f"Échec de la sauvegarde du batch {BatchId}")

        except Exception as e:
            self.Logger.error(f"Erreur lors du traitement async du batch: {e}")
            # Analyse l'erreur d'exception
            await self._HandleBatchError(str(e))
            # En cas d'erreur, ajoute quand même un résultat d'échec à la queue
            try:
                ErrorResult = BatchResult(
                    BatchId=BatchId,
                    Success=False,
                    ErrorMessage=str(e)
                )
                CachePath = await self._SaveResultToCache(BatchId, ErrorResult)
                if CachePath:
                    await self.ResultQueue.put(CachePath)
            except Exception:
                pass

        finally:
            # Remet en idle immédiatement (avant l'envoi)
            # Permet de recevoir un nouveau batch pendant l'envoi
            self.Status = ClientStatus.IDLE
            self.CurrentBatch = None
            self.ProcessingTask = None

            # Notifie le serveur immédiatement du changement de statut
            # Permet au serveur d'envoyer le prochain batch AVANT de recevoir le résultat
            await self._SendStatusUpdate()

    async def _HandleBatchError(self, ErrorMessage: str):
        """
        Analyse une erreur de batch et déclenche une déconnexion si critique.
        Les erreurs critiques (mémoire GPU, etc.) nécessitent un ajustement
        des paramètres, donc on déconnecte pour éviter de gaspiller la bande passante.

        Args:
            ErrorMessage: Message d'erreur du batch
        """
        if not ErrorMessage:
            return

        # Analyse l'erreur
        Analyzer = GetErrorAnalyzer()
        ErrorInfo = Analyzer.Analyze(ErrorMessage)

        if ErrorInfo.get("is_critical"):
            self.Logger.error(f"Erreur critique détectée: {ErrorInfo.get('message')}")
            self.Logger.error(f"Type: {ErrorInfo.get('type')}")

            # Notifie le GUI via callback (thread-safe)
            if self.OnCriticalError:
                try:
                    self.OnCriticalError(ErrorInfo)
                except Exception as e:
                    self.Logger.error(f"Erreur dans le callback OnCriticalError: {e}")

            # Déclenche la déconnexion automatique
            self.Logger.warning("Déconnexion automatique suite à une erreur critique")
            self.Running = False

    async def _SenderLoop(self):
        """
        Boucle d'envoi des résultats en arrière-plan.
        Consomme la queue (chemins de fichiers) et envoie les résultats un par un (FIFO).
        Charge les données depuis le disque pour éviter de remplir la RAM.
        Utilise retry avec backoff en cas d'échec.
        """
        while self.Running:
            try:
                # Attend un chemin de fichier dans la queue (bloquant async)
                CachePath = await self.ResultQueue.get()

                # Charge le résultat depuis le disque
                Result = await self._LoadResultFromCache(CachePath)

                if not Result:
                    self.Logger.error(f"Impossible de charger le résultat depuis {CachePath}")
                    self.ResultQueue.task_done()
                    continue

                BatchId = Result.Payload.get("batch_id", "unknown")
                self.Logger.info(f"Envoi du résultat batch {BatchId}...")

                # Envoie le résultat au serveur avec retry
                async def SendResult():
                    return await self.ConnectionManager.SendMessage(
                        Result.ToJson(),
                        Encrypted=True
                    )

                Success = await self._RetryWithBackoff(SendResult)

                if Success:
                    if Result.IsSuccess():
                        self.Logger.info(f"✓ Résultat batch {BatchId} envoyé avec succès")
                    else:
                        self.Logger.warning(f"✗ Résultat batch {BatchId} (échec) envoyé")

                    # Supprime le fichier cache après envoi réussi
                    self._DeleteCacheFile(CachePath)
                else:
                    # Échec définitif après tous les retries - conserver le cache pour diagnostic
                    self.Logger.error(
                        f"Échec définitif envoi batch {BatchId} après {self.RETRY_MAX_ATTEMPTS} tentatives. "
                        f"Cache conservé: {CachePath}"
                    )
                    # Ne pas supprimer le fichier cache pour permettre un diagnostic ou retry manuel

                # Marque la tâche comme terminée dans la queue
                self.ResultQueue.task_done()

            except asyncio.CancelledError:
                self.Logger.info("SenderLoop annulé")
                break
            except Exception as e:
                self.Logger.error(f"Erreur dans SenderLoop: {e}")

    async def _SendStatusUpdate(self) -> bool:
        """
        Envoie une notification de statut au serveur avec retry.
        Permet au serveur de savoir immédiatement quand le client est disponible
        pour un nouveau batch, sans attendre le prochain heartbeat.

        Returns:
            True si envoi réussi, False sinon
        """
        try:
            async def DoSend():
                Update = StatusUpdate(Status=self.Status)
                return await self.ConnectionManager.SendMessage(Update.ToJson(), Encrypted=True)

            Success = await self._RetryWithBackoff(DoSend)
            if Success:
                self.Logger.debug(f"StatusUpdate envoyé: {self.Status}")
            else:
                self.Logger.warning(f"Impossible d'envoyer StatusUpdate ({self.Status}) après {self.RETRY_MAX_ATTEMPTS} tentatives")
            return Success

        except Exception as e:
            self.Logger.error(f"Erreur envoi StatusUpdate: {e}")
            return False

    async def _SaveResultToCache(self, BatchId: str, Result: BatchResult) -> Optional[str]:
        """
        Sauvegarde un BatchResult sur disque pour éviter de remplir la RAM.

        Args:
            BatchId: ID du batch
            Result: Objet BatchResult à sauvegarder

        Returns:
            Chemin du fichier cache ou None si erreur
        """
        try:
            # Génère un nom de fichier unique
            CachePath = os.path.join(self.ResultCacheDir, f"{BatchId}.json")

            # Sérialise et sauvegarde dans un thread séparé (IO bloquant)
            def SaveToFile():
                with open(CachePath, 'w', encoding='utf-8') as f:
                    json.dump(Result.ToDict(), f)
                return CachePath

            return await asyncio.to_thread(SaveToFile)

        except Exception as e:
            self.Logger.error(f"Erreur lors de la sauvegarde du cache: {e}")
            return None

    async def _LoadResultFromCache(self, CachePath: str) -> Optional[BatchResult]:
        """
        Charge un BatchResult depuis le cache disque.

        Args:
            CachePath: Chemin du fichier cache

        Returns:
            Objet BatchResult ou None si erreur
        """
        try:
            def LoadFromFile():
                with open(CachePath, 'r', encoding='utf-8') as f:
                    Data = json.load(f)
                return BatchResult.FromDict(Data)

            return await asyncio.to_thread(LoadFromFile)

        except Exception as e:
            self.Logger.error(f"Erreur lors du chargement du cache: {e}")
            return None

    def _DeleteCacheFile(self, CachePath: str):
        """
        Supprime un fichier cache après envoi.

        Args:
            CachePath: Chemin du fichier à supprimer
        """
        try:
            if os.path.exists(CachePath):
                os.remove(CachePath)
                self.Logger.debug(f"Cache supprimé: {CachePath}")
        except Exception as e:
            self.Logger.error(f"Erreur lors de la suppression du cache: {e}")

    def _CleanupResultCache(self):
        """
        Nettoie tous les fichiers dans le répertoire de cache.
        Appelé lors de l'arrêt du client.
        """
        try:
            if os.path.exists(self.ResultCacheDir):
                for Filename in os.listdir(self.ResultCacheDir):
                    FilePath = os.path.join(self.ResultCacheDir, Filename)
                    if os.path.isfile(FilePath):
                        os.remove(FilePath)
                self.Logger.info("Cache des résultats nettoyé")
        except Exception as e:
            self.Logger.error(f"Erreur lors du nettoyage du cache: {e}")

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
