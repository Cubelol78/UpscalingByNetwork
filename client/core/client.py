"""
Client principal d'upscaling distribué
Connecte au serveur, reçoit et traite les batches d'images
"""

import asyncio
import threading
import time
import os
import json
from typing import Optional
from asyncio import Queue, PriorityQueue
from pathlib import Path
from dataclasses import dataclass, field

from client.core.connection import ConnectionManager, DualConnectionManager
from client.core.processor import LocalProcessor
from client.utils.error_analyzer import GetErrorAnalyzer
from shared.protocol.messages import (
    MessageFactory, BatchAssignment, HeartbeatPing, HeartbeatPong,
    BatchResult, StatusUpdate, DisconnectMessage
)
from shared.utils.logger import GetClientLogger
from shared.utils.constants import ClientStatus, NetworkConfig


@dataclass(order=True)
class PrioritizedMessage:
    """Message avec priorité pour la queue d'envoi"""
    Priority: int
    Message: str = field(compare=False)
    # Priorité: 0 = haute (heartbeat), 1 = normale (status), 2 = basse (batch result)


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
        # Utilise DualConnectionManager pour l'architecture dual-port
        self.ConnectionManager = DualConnectionManager()
        # Fallback ConnectionManager pour compatibilité avec anciens serveurs
        self._UseDualPort = True  # Sera mis à False si connexion dual échoue

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

        # Pipeline multi-batch : permet de recevoir un batch pendant l'envoi du précédent
        self.ActiveBatches = {}       # {BatchId: {"status": str, "progress": int, "total": int}}
        self.ProcessingTasks = {}     # {BatchId: asyncio.Task}
        self.MaxConcurrentBatches = 2 # Chargé depuis config dans Start()
        self.GpuLock = None           # asyncio.Lock() - Un seul upscaling GPU à la fois

        # Rétrocompatibilité pour GUI existant (pointe vers le premier batch actif)
        self.CurrentBatch = None
        self.CurrentBatchProgress = 0
        self.CurrentBatchTotal = 0

        # Statistiques de session
        self.BatchesProcessed = 0  # Nombre de batches traités avec succès
        self.BatchesFailed = 0     # Nombre de batches échoués
        self.ImagesProcessed = 0   # Nombre total d'images traitées

        # File d'attente pour les résultats à envoyer (découplage traitement/envoi)
        # La queue contient des chemins de fichiers (pas les données en RAM)
        self.ResultQueue: Queue = None
        self.SenderTask = None  # Tâche d'envoi en arrière-plan

        # Queue d'envoi prioritaire pour les messages légers (heartbeats, status)
        # Les gros messages (batch results) passent directement avec un Lock
        self.OutgoingQueue: PriorityQueue = None
        self.OutgoingTask = None  # Tâche d'envoi des messages prioritaires
        self.SendLock: asyncio.Lock = None  # Lock pour synchroniser les envois

        # Callback appelé lors d'une déconnexion demandée par le serveur
        self.OnServerDisconnect = None

        # Callback appelé lors d'une erreur critique nécessitant déconnexion
        self.OnCriticalError = None

        # Callback appelé lors des tentatives de reconnexion (attempt, delay)
        self.OnReconnecting = None

        # Tâche de réception sur le canal Data
        self.DataReceiveTask = None

        # Event loop du client (pour arrêt thread-safe)
        self._Loop: asyncio.AbstractEventLoop = None
        self._StopRequested = False
        self._StopComplete = threading.Event()

        # État de reconnexion automatique
        self.IsReconnecting = False  # True si en cours de reconnexion
        self.ReconnectEnabled = NetworkConfig.RECONNECT_ENABLED  # Active/désactive la reconnexion auto
        self.DisconnectedByServer = False  # True si déconnexion demandée par serveur (pas de reconnexion)

        self.Logger.info(f"Client initialisé avec répertoire de travail: {self.WorkDirectory}")

    async def Start(self, Host: str, Port: int, Password: str = "",
                    DataPort: int = None) -> bool:
        """
        Démarre le client et connecte au serveur (dual-port)

        Args:
            Host: Adresse du serveur
            Port: Port de contrôle du serveur (handshake, heartbeat)
            Password: Mot de passe (optionnel)
            DataPort: Port de données du serveur (batches). Si None, utilise Port + 1

        Returns:
            True si démarrage réussi
        """
        try:
            self.Logger.info("Demarrage du client...")

            # Sauvegarde l'event loop pour l'arret thread-safe
            self._Loop = asyncio.get_event_loop()
            self._StopRequested = False
            self._StopComplete.clear()

            # Par defaut, le port Data est le port Control + 1
            if DataPort is None:
                DataPort = Port + 1

            # Charge la configuration max_concurrent_batches AVANT la connexion
            # (pour l'envoyer au serveur lors de l'authentification)
            try:
                from client.utils.performance_config import PerformanceConfigManager
                ConfigManager = PerformanceConfigManager()
                Config = ConfigManager.Load()
                self.MaxConcurrentBatches = Config.get('max_concurrent_batches', 2)
                self.Logger.info(f"Pipeline multi-batch: max {self.MaxConcurrentBatches} batches simultanés")
            except Exception as e:
                self.Logger.warning(f"Config multi-batch non chargée, défaut: 2 ({e})")
                self.MaxConcurrentBatches = 2

            # Connecte aux deux ports (Control + Data) en communiquant la capacité du pipeline
            if not await self.ConnectionManager.ConnectToDualPorts(
                Host, Port, DataPort, Password, self.MaxConcurrentBatches
            ):
                self.Logger.error("Impossible de se connecter au serveur (dual-port)")
                return False

            self._UseDualPort = True
            self.Running = True
            self.Status = ClientStatus.IDLE

            # Lock pour synchroniser les envois (évite conflits heartbeats/batch results)
            self.SendLock = asyncio.Lock()

            # Lock GPU pour pipeline multi-batch (un seul upscaling à la fois)
            self.GpuLock = asyncio.Lock()

            # Initialise la queue d'envoi prioritaire (heartbeats > status)
            self.OutgoingQueue = asyncio.PriorityQueue()
            self.OutgoingTask = asyncio.create_task(self._OutgoingMessageLoop())

            # Initialise la queue de résultats et démarre le sender en arrière-plan
            self.ResultQueue = asyncio.Queue()
            self.SenderTask = asyncio.create_task(self._SenderLoop())

            # Démarre la réception des batches sur le canal Data
            self.DataReceiveTask = asyncio.create_task(self._DataReceiveLoop())

            self.Logger.info("✓ Client démarré et connecté (dual-port)")

            # Lance la boucle principale (Control: heartbeats)
            await self.MainLoop()

            return True

        except Exception as e:
            self.Logger.error(f"Erreur lors du démarrage: {e}")
            return False

    async def Stop(self):
        """Arrête le client proprement"""
        self.Logger.info("Arrêt du client...")

        self.Running = False

        # Annule toutes les tâches de traitement en cours
        if self.ProcessingTasks:
            self.Logger.info(f"Annulation de {len(self.ProcessingTasks)} tâche(s) de traitement...")
            for BatchId, Task in list(self.ProcessingTasks.items()):
                if not Task.done():
                    Task.cancel()
                    try:
                        await Task
                    except asyncio.CancelledError:
                        pass
            self.ProcessingTasks.clear()
            self.ActiveBatches.clear()
            self.Logger.info("Tâches de traitement annulées")

        # Attend que la queue d'envoi soit vidée (avec timeout)
        if self.ResultQueue and not self.ResultQueue.empty():
            self.Logger.info(f"Attente de l'envoi des {self.ResultQueue.qsize()} résultat(s) en attente...")
            try:
                await asyncio.wait_for(self.ResultQueue.join(), timeout=30.0)
                self.Logger.info("Queue d'envoi vidée")
            except asyncio.TimeoutError:
                self.Logger.warning("Timeout lors de l'attente de la queue, arrêt forcé")

        # Annule la tâche d'envoi des résultats
        if self.SenderTask and not self.SenderTask.done():
            self.SenderTask.cancel()
            try:
                await self.SenderTask
            except asyncio.CancelledError:
                pass

        # Annule la tâche d'envoi des messages prioritaires
        if self.OutgoingTask and not self.OutgoingTask.done():
            self.OutgoingTask.cancel()
            try:
                await self.OutgoingTask
            except asyncio.CancelledError:
                pass

        # Annule la tâche de réception Data
        if self.DataReceiveTask and not self.DataReceiveTask.done():
            self.DataReceiveTask.cancel()
            try:
                await self.DataReceiveTask
            except asyncio.CancelledError:
                pass

        # Déconnecte du serveur
        await self.ConnectionManager.Disconnect()

        # Nettoie les fichiers temporaires
        self.LocalProcessor.CleanupAll()

        # Nettoie le cache des resultats en attente
        self._CleanupResultCache()

        self.Logger.info("Client arrete")

        # Signale que l'arret est termine
        self._StopComplete.set()

    def RequestStop(self, Timeout: float = 10.0) -> bool:
        """
        Demande l'arret du client de maniere thread-safe.
        Peut etre appele depuis n'importe quel thread.

        Args:
            Timeout: Temps max d'attente en secondes

        Returns:
            True si l'arret s'est termine dans le delai
        """
        if not self.Running:
            return True

        if self._StopRequested:
            # Deja en cours d'arret, attend juste la fin
            return self._StopComplete.wait(timeout=Timeout)

        self._StopRequested = True

        # Si on a une reference a l'event loop, planifie Stop() dessus
        if self._Loop and self._Loop.is_running():
            # Planifie l'arret sur l'event loop du client
            asyncio.run_coroutine_threadsafe(self.Stop(), self._Loop)
        else:
            # Pas d'event loop, met juste Running a False
            self.Running = False

        # Attend que l'arret soit termine
        return self._StopComplete.wait(timeout=Timeout)

    async def MainLoop(self):
        """
        Boucle principale du client (canal Control).
        Reçoit les heartbeats et status du serveur.
        Les batches sont reçus via _DataReceiveLoop().
        Gère la reconnexion automatique en cas de perte de connexion.
        """
        while self.Running:
            try:
                while self.Running and not self._StopRequested:
                    # Determine le timeout adapte :
                    # - Si en PROCESSING ou envoi en cours : timeout long (5 min)
                    # - Sinon : timeout court (60s)
                    # - Mais jamais plus de 5s si arret demande (pour reagir vite)
                    if self._StopRequested:
                        break

                    if self.Status == ClientStatus.PROCESSING or (self.ResultQueue and not self.ResultQueue.empty()):
                        CommunicationTimeout = NetworkConfig.BATCH_TIMEOUT
                    else:
                        CommunicationTimeout = NetworkConfig.HEARTBEAT_TIMEOUT * 2

                    # Utilise un timeout court (5s) pour verifier regulierement _StopRequested
                    ActualTimeout = min(CommunicationTimeout, 5.0)

                    # Recoit un message du serveur via Control
                    try:
                        MessageData = await asyncio.wait_for(
                            self.ConnectionManager.ReceiveControlMessage(Decrypt=True),
                            timeout=ActualTimeout
                        )
                    except asyncio.TimeoutError:
                        # Verifie si arret demande
                        if self._StopRequested:
                            break
                        # Sinon continue (c'est juste le timeout court qui a expire)
                        continue

                    if not MessageData:
                        self.Logger.warning("Message Control vide reçu, déconnexion probable")
                        break

                    # Parse le message
                    Message = MessageFactory.CreateFromJson(MessageData)

                    # Traite le message (Control: heartbeats, disconnect, status)
                    await self._HandleControlMessage(Message)

            except Exception as e:
                if not self._StopRequested:
                    self.Logger.error(f"Erreur dans la boucle principale Control: {e}")

            # Si on arrive ici, c'est qu'il y a eu une deconnexion ou un arret demande
            # Verifie si on doit tenter une reconnexion automatique
            if not self.Running or self._StopRequested:
                # Client arrêté volontairement, on sort
                break

            if self.DisconnectedByServer:
                # Déconnexion demandée par le serveur, on ne reconnecte pas
                self.Logger.info("Déconnexion demandée par le serveur, pas de reconnexion")
                break

            if not self.ReconnectEnabled:
                # Reconnexion automatique désactivée
                self.Logger.info("Reconnexion automatique désactivée")
                break

            # Annule les batches en cours si nécessaire
            if self.ProcessingTasks:
                self.Logger.warning(f"Annulation de {len(self.ProcessingTasks)} batch(s) en cours suite à la déconnexion")
                for BatchId, Task in list(self.ProcessingTasks.items()):
                    if not Task.done():
                        Task.cancel()
                        try:
                            await Task
                        except asyncio.CancelledError:
                            pass
                self.ProcessingTasks.clear()
                self.ActiveBatches.clear()
                self.CurrentBatch = None

            # Tente la reconnexion automatique
            self.IsReconnecting = True
            self.Logger.warning("🔄 Déconnexion détectée, tentative de reconnexion automatique...")

            ReconnectSuccess = await self.ConnectionManager.ReconnectWithRetry(
                MaxAttempts=NetworkConfig.RECONNECT_INFINITE,
                OnAttempt=self._OnReconnectAttempt
            )

            self.IsReconnecting = False

            if ReconnectSuccess:
                self.Logger.info("✓ Reconnexion réussie, reprise du service")
                # Redémarre les tâches annexes
                await self._RestartTasks()
                # Continue la boucle principale
            else:
                self.Logger.error("✗ Échec de la reconnexion automatique")
                break

        # Arrêt final du client
        await self.Stop()

    async def _DataReceiveLoop(self):
        """
        Boucle de reception sur le canal Data.
        Recoit les BatchAssignment du serveur.
        """
        try:
            while self.Running and not self._StopRequested:
                # Recoit un batch via le canal Data (timeout court pour reagir vite)
                MessageData = await self.ConnectionManager.ReceiveDataMessage(
                    Decrypt=True,
                    Timeout=5.0  # Timeout court pour verifier self.Running regulierement
                )

                if not MessageData:
                    # Timeout ou erreur de connexion
                    if self._StopRequested:
                        break
                    if not self.ConnectionManager.IsDataConnected():
                        self.Logger.warning("Canal Data deconnecte")
                        break
                    continue

                # Parse le message
                Message = MessageFactory.CreateFromJson(MessageData)

                # On s'attend à recevoir des BatchAssignment sur le canal Data
                if isinstance(Message, BatchAssignment):
                    await self._HandleBatchAssignment(Message)
                else:
                    self.Logger.warning(f"Message inattendu sur canal Data: {Message.MessageType}")

        except asyncio.CancelledError:
            self.Logger.info("DataReceiveLoop annulé")
        except Exception as e:
            self.Logger.error(f"Erreur dans DataReceiveLoop: {e}")

    async def _HandleControlMessage(self, Message):
        """
        Traite un message reçu via le canal Control

        Args:
            Message: Message parsé
        """
        try:
            MessageType = Message.MessageType

            # Heartbeat ping
            if isinstance(Message, HeartbeatPing):
                await self._HandleHeartbeatPing(Message)

            # Déconnexion demandée par le serveur
            elif isinstance(Message, DisconnectMessage):
                await self._HandleDisconnect(Message)

            # Autres types
            else:
                self.Logger.debug(f"Message Control reçu: {MessageType}")

        except Exception as e:
            self.Logger.error(f"Erreur lors du traitement du message Control: {e}")

    async def _HandleHeartbeatPing(self, PingMessage: HeartbeatPing):
        """
        Répond au heartbeat ping via la queue prioritaire.
        Les heartbeats ont la priorité la plus haute (0) pour ne jamais être bloqués.

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

            # Met dans la queue prioritaire (priorité 0 = haute)
            await self.OutgoingQueue.put(PrioritizedMessage(
                Priority=0,
                Message=Pong.ToJson()
            ))
            self.Logger.debug("Heartbeat pong mis en queue (priorité haute)")

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

        # Marque qu'il s'agit d'une déconnexion voulue par le serveur (pas de reconnexion auto)
        self.DisconnectedByServer = True

        # Marque le client comme devant s'arrêter
        self.Running = False

        # Notifie via callback si disponible (pour l'interface GUI)
        if hasattr(self, 'OnServerDisconnect') and self.OnServerDisconnect:
            try:
                self.OnServerDisconnect(Reason)
            except Exception as e:
                self.Logger.error(f"Erreur dans le callback de déconnexion: {e}")

    def _OnReconnectAttempt(self, Attempt: int, Delay: float):
        """
        Callback appelé lors de chaque tentative de reconnexion

        Args:
            Attempt: Numéro de la tentative
            Delay: Délai avant cette tentative
        """
        # Notifie via callback si disponible (pour l'interface GUI)
        if self.OnReconnecting:
            try:
                self.OnReconnecting(Attempt, Delay)
            except Exception as e:
                self.Logger.error(f"Erreur dans le callback OnReconnecting: {e}")

    async def _RestartTasks(self):
        """
        Redémarre les tâches annexes après une reconnexion réussie
        """
        try:
            # Redémarre la tâche de réception Data si elle n'est pas active
            if not self.DataReceiveTask or self.DataReceiveTask.done():
                self.DataReceiveTask = asyncio.create_task(self._DataReceiveLoop())
                self.Logger.debug("✓ Tâche DataReceiveLoop redémarrée")

            # Redémarre la tâche d'envoi de résultats si elle n'est pas active
            if not self.SenderTask or self.SenderTask.done():
                self.SenderTask = asyncio.create_task(self._SenderLoop())
                self.Logger.debug("✓ Tâche SenderLoop redémarrée")

            # Redémarre la tâche d'envoi de messages prioritaires si elle n'est pas active
            if not self.OutgoingTask or self.OutgoingTask.done():
                self.OutgoingTask = asyncio.create_task(self._OutgoingMessageLoop())
                self.Logger.debug("✓ Tâche OutgoingMessageLoop redémarrée")

            # Remet le client en IDLE pour pouvoir recevoir de nouveaux batches
            self.Status = ClientStatus.IDLE
            self.CurrentBatch = None
            self.Logger.info("✓ Client remis en état IDLE, prêt à recevoir des batches")

        except Exception as e:
            self.Logger.error(f"Erreur lors du redémarrage des tâches: {e}")

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
        Traite un batch d'images assigné (mode pipeline multi-batch)
        Lance le traitement en arrière-plan pour ne pas bloquer les heartbeats

        Args:
            Assignment: Message BatchAssignment
        """
        try:
            BatchId = Assignment.GetBatchId()
            ImageCount = Assignment.Payload.get('image_count', 0)

            # Vérifie si on peut accepter un nouveau batch (pipeline)
            if len(self.ActiveBatches) >= self.MaxConcurrentBatches:
                self.Logger.warning(f"Limite de batches atteinte ({self.MaxConcurrentBatches}), "
                                  f"batch {BatchId} refusé")
                return

            # Debug: verifie le contenu du batch recu
            Images = Assignment.Payload.get('images', [])
            ImagesWithData = sum(1 for img in Images if img.get('data'))
            TotalDataSize = sum(len(img.get('data', '')) for img in Images)

            self.Logger.info(f"Nouveau batch recu: {BatchId} "
                           f"(actifs: {len(self.ActiveBatches) + 1}/{self.MaxConcurrentBatches})")
            self.Logger.info(f"  Nombre d'images declarees: {ImageCount}")
            self.Logger.info(f"  Nombre d'images recues: {len(Images)}")
            self.Logger.info(f"  Images avec donnees: {ImagesWithData}")
            self.Logger.info(f"  Taille totale base64: {TotalDataSize / 1024:.1f} KB")

            if ImagesWithData == 0:
                self.Logger.error(f"ERREUR: Aucune image avec donnees dans le batch!")
                # Log les premiers champs de la premiere image pour debug
                if Images:
                    FirstImg = Images[0]
                    self.Logger.error(f"  Premiere image - cles: {list(FirstImg.keys())}")
                    self.Logger.error(f"  Premiere image - id: {FirstImg.get('id')}, data vide: {not FirstImg.get('data')}")

            # Ajoute le batch aux batches actifs
            self.ActiveBatches[BatchId] = {
                "status": "received",
                "progress": 0,
                "total": ImageCount
            }

            # Rétrocompatibilité GUI : pointe vers le premier batch actif
            if self.CurrentBatch is None:
                self.CurrentBatch = BatchId
                self.CurrentBatchTotal = ImageCount
                self.CurrentBatchProgress = 0

            # Met à jour le statut global
            self.Status = ClientStatus.PROCESSING

            # Lance le traitement en tâche de fond
            Task = asyncio.create_task(
                self._ProcessBatchAsync(BatchId, Assignment.Payload)
            )
            self.ProcessingTasks[BatchId] = Task

        except Exception as e:
            self.Logger.error(f"Erreur lors du traitement du batch: {e}")
            # Nettoie si erreur
            if BatchId in self.ActiveBatches:
                del self.ActiveBatches[BatchId]
            if BatchId in self.ProcessingTasks:
                del self.ProcessingTasks[BatchId]
            # Passe à IDLE si plus de batches actifs
            if not self.ActiveBatches:
                self.Status = ClientStatus.IDLE
                self.CurrentBatch = None

    async def _ProcessBatchAsync(self, BatchId: str, Payload: dict):
        """
        Traite un batch de manière asynchrone avec pipeline multi-batch.
        Utilise GpuLock pour garantir un seul upscaling GPU à la fois.
        Sauvegarde le résultat sur disque et ajoute le chemin à la queue.
        Analyse les erreurs et déclenche une déconnexion si critique.

        Args:
            BatchId: ID du batch
            Payload: Données du batch
        """
        try:
            # Initialise la progression du batch
            Images = Payload.get("images", [])
            ImageCount = len(Images)

            # Met à jour le statut dans ActiveBatches
            if BatchId in self.ActiveBatches:
                self.ActiveBatches[BatchId]["status"] = "waiting_gpu"
                self.ActiveBatches[BatchId]["total"] = ImageCount

            # Rétrocompatibilité GUI
            if self.CurrentBatch == BatchId:
                self.CurrentBatchTotal = ImageCount
                self.CurrentBatchProgress = 0

            # Callback de progression
            def ProgressCallback(Current, Total):
                if BatchId in self.ActiveBatches:
                    self.ActiveBatches[BatchId]["progress"] = Current
                # Rétrocompatibilité GUI (pour le premier batch)
                if self.CurrentBatch == BatchId:
                    self.CurrentBatchProgress = Current
                    self.CurrentBatchTotal = Total

            # ACQUIERT LE LOCK GPU (pipeline: attend si un autre batch upscale)
            self.Logger.debug(f"Batch {BatchId}: attente du GPU...")
            UpscaledPaths = None

            async with self.GpuLock:
                if BatchId in self.ActiveBatches:
                    self.ActiveBatches[BatchId]["status"] = "upscaling"
                self.Logger.info(f"Batch {BatchId}: upscaling GPU en cours...")

                # Phase GPU uniquement (Real-ESRGAN)
                UpscaledPaths = await asyncio.to_thread(
                    self.LocalProcessor.ProcessBatchGpuOnly,
                    Payload,
                    ProgressCallback
                )

            # GPU LIBÉRÉ ! Un autre batch peut commencer son upscaling
            # Phase CPU : conversion AVIF et encodage base64 (parallélisable)
            if BatchId in self.ActiveBatches:
                self.ActiveBatches[BatchId]["status"] = "converting"

            if UpscaledPaths:
                self.Logger.info(f"Batch {BatchId}: conversion CPU en cours...")
                Result = await asyncio.to_thread(
                    self.LocalProcessor.ConvertAndEncode,
                    BatchId,
                    UpscaledPaths,
                    Payload.get("images", [])
                )
            else:
                Result = None

            # Passe à l'envoi
            if BatchId in self.ActiveBatches:
                self.ActiveBatches[BatchId]["status"] = "sending"

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
            await self._HandleBatchError(str(e))
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
            # Nettoie le batch des structures multi-batch
            if BatchId in self.ActiveBatches:
                del self.ActiveBatches[BatchId]
            if BatchId in self.ProcessingTasks:
                del self.ProcessingTasks[BatchId]

            # Met à jour CurrentBatch pour pointer vers le prochain batch actif
            if self.CurrentBatch == BatchId:
                if self.ActiveBatches:
                    # Pointe vers le premier batch restant
                    NextBatch = next(iter(self.ActiveBatches))
                    self.CurrentBatch = NextBatch
                    self.CurrentBatchProgress = self.ActiveBatches[NextBatch].get("progress", 0)
                    self.CurrentBatchTotal = self.ActiveBatches[NextBatch].get("total", 0)
                else:
                    self.CurrentBatch = None
                    self.CurrentBatchProgress = 0
                    self.CurrentBatchTotal = 0

            # Passe à IDLE seulement si plus aucun batch actif ET queue vide
            # (le _SenderLoop gère aussi le passage à IDLE après envoi)
            if not self.ActiveBatches and (not self.ResultQueue or self.ResultQueue.empty()):
                self.Status = ClientStatus.IDLE
                self.Logger.debug("Plus de batches actifs, passage à IDLE")

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
        Boucle d'envoi des resultats en arriere-plan.
        Consomme la queue (chemins de fichiers) et envoie les resultats un par un (FIFO).
        Charge les donnees depuis le disque pour eviter de remplir la RAM.
        Utilise un Lock pour synchroniser avec les heartbeats.
        Passe le client a IDLE apres l'envoi reussi.
        """
        while self.Running and not self._StopRequested:
            try:
                # Attend un chemin de fichier dans la queue (timeout pour verifier self.Running)
                try:
                    CachePath = await asyncio.wait_for(
                        self.ResultQueue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    if self._StopRequested:
                        break
                    continue

                # Charge le résultat depuis le disque
                Result = await self._LoadResultFromCache(CachePath)

                if not Result:
                    self.Logger.error(f"Impossible de charger le résultat depuis {CachePath}")
                    self.ResultQueue.task_done()
                    continue

                BatchId = Result.Payload.get("batch_id", "unknown")
                self.Logger.info(f"Envoi du résultat batch {BatchId}...")

                # Envoie via le canal Data (gros transferts)
                async def SendResult():
                    return await self.ConnectionManager.SendDataMessage(
                        Result.ToJson(),
                        Encrypted=True
                    )

                Success = await self._RetryWithBackoff(SendResult)

                if Success:
                    if Result.IsSuccess():
                        self.Logger.info(f"✓ Résultat batch {BatchId} envoyé avec succès")
                        # Incrémente les statistiques
                        self.BatchesProcessed += 1
                        # Utilise image_count du Payload (déjà calculé dans BatchResult)
                        ImageCount = Result.Payload.get("image_count", 0)
                        self.ImagesProcessed += ImageCount
                        self.Logger.debug(f"Images traitées: +{ImageCount} (total: {self.ImagesProcessed})")
                    else:
                        self.Logger.warning(f"✗ Résultat batch {BatchId} (échec) envoyé")
                        self.BatchesFailed += 1

                    # Supprime le fichier cache après envoi réussi
                    self._DeleteCacheFile(CachePath)

                    # Passe à IDLE et notifie le serveur APRÈS l'envoi réussi
                    # Cela garantit que le serveur ne timeout pas pendant l'envoi
                    # Multi-batch: ne passe à IDLE que si plus aucun batch actif
                    if self.ResultQueue.empty() and not self.ActiveBatches:
                        self.Status = ClientStatus.IDLE
                        await self._SendStatusUpdate()
                        self.Logger.debug("Queue vide et plus de batches actifs, passage à IDLE")
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

    async def _OutgoingMessageLoop(self):
        """
        Boucle d'envoi des messages prioritaires via le canal Control.
        Gere les heartbeats et status updates.
        Les messages sont traites par ordre de priorite (0 = haute, 1 = normale).
        """
        while self.Running and not self._StopRequested:
            try:
                # Attend un message dans la queue (bloquant async)
                try:
                    PrioMsg = await asyncio.wait_for(
                        self.OutgoingQueue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    if self._StopRequested:
                        break
                    continue

                # Envoie via le canal Control (heartbeats, status)
                async def DoSend():
                    return await self.ConnectionManager.SendControlMessage(
                        PrioMsg.Message,
                        Encrypted=True
                    )

                Success = await self._RetryWithBackoff(DoSend)

                if not Success:
                    PriorityName = {0: "heartbeat", 1: "status"}.get(PrioMsg.Priority, "unknown")
                    self.Logger.warning(f"Échec envoi message {PriorityName} après retries")

                self.OutgoingQueue.task_done()

            except asyncio.CancelledError:
                self.Logger.info("OutgoingMessageLoop annulé")
                break
            except Exception as e:
                self.Logger.error(f"Erreur dans OutgoingMessageLoop: {e}")

    async def _SendStatusUpdate(self) -> bool:
        """
        Envoie une notification de statut au serveur via la queue prioritaire.
        Permet au serveur de savoir immédiatement quand le client est disponible
        pour un nouveau batch, sans attendre le prochain heartbeat.

        Returns:
            True (toujours, car mis en queue)
        """
        try:
            Update = StatusUpdate(Status=self.Status)

            # Met dans la queue prioritaire (priorité 1 = normale)
            await self.OutgoingQueue.put(PrioritizedMessage(
                Priority=1,
                Message=Update.ToJson()
            ))
            self.Logger.debug(f"StatusUpdate mis en queue: {self.Status}")
            return True

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

        # Calcule la taille de la queue d'envoi
        QueueSize = self.ResultQueue.qsize() if self.ResultQueue else 0

        return {
            "running": self.Running,
            "connected": self.ConnectionManager.IsConnected(),
            "control_connected": self.ConnectionManager.IsControlConnected(),
            "data_connected": self.ConnectionManager.IsDataConnected(),
            "status": self.Status,
            "current_batch": self.CurrentBatch,
            "server_address": ServerInfo[0],
            "control_port": ServerInfo[1],
            "data_port": ServerInfo[2] if len(ServerInfo) > 2 else None,
            "client_id": self.ConnectionManager.ClientId,
            # Statistiques
            "batches_processed": self.BatchesProcessed,
            "batches_failed": self.BatchesFailed,
            "images_processed": self.ImagesProcessed,
            "queue_size": QueueSize,  # Batches en attente d'envoi
            # Progression du batch en cours
            "batch_progress": self.CurrentBatchProgress,
            "batch_total": self.CurrentBatchTotal
        }

    def GetRecentLogs(self, Count: int = 20) -> list:
        """
        Récupère les logs récents du client

        Args:
            Count: Nombre de logs à retourner

        Returns:
            Liste des logs récents
        """
        from shared.utils.logger import LoggerManager
        return LoggerManager.GetRecentLogs("Client", Count)


# ============================================================================
# FONCTION D'AIDE POUR LANCER LE CLIENT
# ============================================================================

async def RunClient(Host: str, Port: int, Password: str = "", DataPort: int = None):
    """
    Lance le client avec les paramètres donnés (dual-port)

    Args:
        Host: Adresse du serveur
        Port: Port de contrôle du serveur
        Password: Mot de passe (optionnel)
        DataPort: Port de données (optionnel, défaut: Port + 1)
    """
    Client = UpscalingClient()

    try:
        await Client.Start(Host, Port, Password, DataPort)

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
        print("Usage: python client.py <host> <control_port> [password] [data_port]")
        sys.exit(1)

    Host = sys.argv[1]
    Port = int(sys.argv[2])
    Password = sys.argv[3] if len(sys.argv) > 3 else ""
    DataPort = int(sys.argv[4]) if len(sys.argv) > 4 else None

    # Lance le client
    asyncio.run(RunClient(Host, Port, Password, DataPort))
