"""
Serveur principal d'upscaling vidéo en réseau
Gère les connexions clients et orchestre le traitement distribué
"""

import asyncio
import os
import socket
import platform
import signal
from typing import Optional
from pathlib import Path

from server.core.client_manager import ClientManager
from server.core.network_manager import NetworkManager, DualNetworkManager
from server.database.db_manager import DatabaseManager
from shared.utils.logger import GetServerLogger
from shared.utils.constants import NetworkConfig, PathConfig, ClientStatus, AppMetadata
from shared.protocol.messages import MessageFactory, HeartbeatPong, BatchResult, StatusUpdate, DisconnectMessage
from shared.utils.webhook_manager import InitServerWebhookManager, TriggerServerWebhook


def ConfigureSocket(Writer: asyncio.StreamWriter, Logger):
    """
    Configure le socket TCP avec des options adaptées pour éviter les timeouts

    Args:
        Writer: StreamWriter asyncio
        Logger: Logger pour les messages de debug
    """
    try:
        Sock = Writer.get_extra_info('socket')
        if not Sock:
            return

        # Active TCP keepalive pour détecter les connexions mortes
        Sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

        # Configure les paramètres keepalive selon la plateforme
        IsWindows = platform.system() == 'Windows'

        if IsWindows:
            # Windows: configure keepalive avec SIO_KEEPALIVE_VALS
            # Vérifie que le socket supporte ioctl (pas un TransportSocket)
            if hasattr(Sock, 'ioctl'):
                Sock.ioctl(
                    socket.SIO_KEEPALIVE_VALS,
                    (1, 30000, 10000)  # 30s idle, 10s interval
                )
            else:
                Logger.debug("Socket wrapper détecté, configuration keepalive Windows ignorée")
        else:
            # Linux/Unix: utilise les options TCP standard
            if hasattr(socket, 'TCP_KEEPIDLE'):
                Sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)
            if hasattr(socket, 'TCP_KEEPINTVL'):
                Sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
            if hasattr(socket, 'TCP_KEEPCNT'):
                Sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 6)

        # Désactive Nagle pour réduire la latence
        Sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        # Augmente les buffers pour les gros transferts (BatchResults avec images)
        Sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)  # 8MB (était 2MB)
        Sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8 * 1024 * 1024)  # 8MB (était 2MB)

    except Exception as e:
        Logger.debug(f"Configuration socket: {e}")


class UpscalingServer:
    """Serveur principal d'upscaling distribué"""

    def __init__(self, Config: dict):
        """
        Initialise le serveur

        Args:
            Config: Configuration du serveur (depuis JSON)
        """
        self.Config = Config
        self.Logger = GetServerLogger()
        self.Running = False

        # Configuration
        ServerCfg = Config.get("server", {})
        self.HostV4 = ServerCfg.get("ipv4", NetworkConfig.DEFAULT_HOST)
        self.HostV6 = ServerCfg.get("ipv6", "")
        self.Port = ServerCfg.get("port", NetworkConfig.DEFAULT_PORT)
        self.DataPort = ServerCfg.get("data_port", NetworkConfig.DEFAULT_DATA_PORT)
        self.Password = ServerCfg.get("password", "")
        self.WorkDirectory = ServerCfg.get("work_directory", PathConfig.WORK_DIR)

        # Base de données - utilise le chemin par défaut (indépendant du work_directory)
        self.Database = DatabaseManager()  # Utilise GetDefaultDbPath()

        # Gestionnaire de réseau dual-port (Control + Data)
        self.NetworkManager = DualNetworkManager(self.HostV4, self.Port, self.DataPort, self.HostV6)

        # Gestionnaire de clients
        self.ClientManager = None

        # Distributeur de batches (sera défini après initialisation)
        self.BatchDistributor = None

        self.Logger.info("Serveur initialisé")

    def SetBatchDistributor(self, Distributor):
        """
        Définit le distributeur de batches et configure les callbacks

        Args:
            Distributor: Instance de BatchDistributor
        """
        self.BatchDistributor = Distributor

        # Enregistre le callback de réallocation des batches
        # Quand un client est déconnecté, ses batches seront réalloués
        if self.ClientManager and Distributor:
            self.ClientManager.SetDisconnectCallback(Distributor.ReassignClientBatches)

    def Initialize(self) -> bool:
        """
        Initialise le serveur (base de données, répertoires, etc.)

        Returns:
            True si succès
        """
        try:
            # Crée les répertoires de travail
            self._CreateWorkDirectories()

            # Connecte à la base de données
            if not self.Database.Connect():
                self.Logger.error("Impossible de se connecter à la base de données")
                return False

            # Initialise les paramètres par défaut
            self._InitializeDefaultParameters()

            # Crée le gestionnaire de clients
            self.ClientManager = ClientManager(self.Password, self.Database)

            # Initialise le gestionnaire de webhooks
            InitServerWebhookManager(self._GetWebhookConfig)

            self.Logger.info("Serveur initialisé avec succès")
            return True

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'initialisation du serveur: {e}")
            return False

    def _CreateWorkDirectories(self):
        """Crée la structure des répertoires de travail"""
        Directories = [
            self.WorkDirectory,
            os.path.join(self.WorkDirectory, PathConfig.INPUT_DIR),
            os.path.join(self.WorkDirectory, PathConfig.FRAMES_DIR),
            os.path.join(self.WorkDirectory, PathConfig.AUDIO_DIR),
            os.path.join(self.WorkDirectory, PathConfig.SUBTITLES_DIR),
            os.path.join(self.WorkDirectory, PathConfig.UPSCALED_DIR),
            os.path.join(self.WorkDirectory, PathConfig.OUTPUT_DIR),
            os.path.join(self.WorkDirectory, PathConfig.TEMP_DIR)
        ]

        for Directory in Directories:
            os.makedirs(Directory, exist_ok=True)
            self.Logger.debug(f"Répertoire créé/vérifié: {Directory}")

    def _InitializeDefaultParameters(self):
        """Initialise les paramètres par défaut dans la base de données"""
        # Utilise InitializeDefaultParameters() qui ne remplace pas les valeurs existantes
        self.Database.InitializeDefaultParameters()
        # Ajoute/met à jour la version du serveur
        self.Database.SetParameter("server_version", AppMetadata.VERSION, "Version du serveur")

    async def Start(self) -> bool:
        """
        Démarre le serveur

        Returns:
            True si succès
        """
        if self.Running:
            self.Logger.warning("Le serveur est déjà en cours d'exécution")
            return False

        try:
            self.Logger.info(f"Démarrage du serveur - IPv4={self.HostV4} IPv6={self.HostV6} Control:{self.Port} Data:{self.DataPort}...")

            # Démarre les deux listeners TCP via DualNetworkManager
            if not await self.NetworkManager.Start(
                self._HandleControlConnection,
                self._HandleDataConnection
            ):
                self.Logger.error("Échec du démarrage des listeners TCP")
                return False

            # Configure les handlers de signaux pour un arrêt gracieux
            self._SetupSignalHandlers()

            self.Running = True

            # Démarre le monitoring des heartbeats
            await self.ClientManager.StartHeartbeatMonitoring()

            self.Logger.info(f"✓ Serveur démarré - Control:{self.Port}, Data:{self.DataPort}")

            # Affiche les informations
            self._PrintServerInfo()

            # Webhook: serveur démarré
            TriggerServerWebhook("server_started", ip=self.HostV4 or self.HostV6, port=self.Port)

            return True

        except Exception as e:
            self.Logger.error(f"Erreur lors du démarrage du serveur: {e}")
            return False

    async def Stop(self, timeout: float = 30.0):
        """
        Arrête le serveur avec un arrêt gracieux.

        Args:
            timeout: Timeout global en secondes (défaut: 30s)
        """
        if not self.Running:
            self.Logger.warning("Le serveur n'est pas en cours d'exécution")
            return

        self.Logger.info(f"Arrêt gracieux du serveur (timeout: {timeout}s)...")

        # Webhook: serveur arrêté (avant fermeture DB)
        TriggerServerWebhook("server_stopped", ip=self.HostV4 or self.HostV6, port=self.Port)

        self.Running = False

        try:
            # Enveloppe toute la séquence d'arrêt dans un timeout global
            await asyncio.wait_for(
                self._GracefulShutdown(),
                timeout=timeout
            )
            self.Logger.info("✓ Serveur arrêté avec succès")

        except asyncio.TimeoutError:
            self.Logger.error(
                f"Timeout de {timeout}s atteint lors de l'arrêt gracieux. "
                "Forçage de la fermeture..."
            )
            # Force la fermeture de la base de données même en cas de timeout
            if self.Database:
                try:
                    self.Database.Close()
                except Exception as e:
                    self.Logger.error(f"Erreur lors de la fermeture forcée de la DB: {e}")

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'arrêt du serveur: {e}")
            # Force la fermeture de la base de données même en cas d'erreur
            if self.Database:
                try:
                    self.Database.Close()
                except Exception:
                    pass

    def _SetupSignalHandlers(self):
        """
        Configure les handlers de signaux pour un arrêt gracieux.
        Gère SIGINT (Ctrl+C) et SIGTERM (kill).
        """
        # Note: Windows ne supporte que SIGINT
        if platform.system() == 'Windows':
            signals = [signal.SIGINT]
        else:
            signals = [signal.SIGINT, signal.SIGTERM]

        loop = asyncio.get_event_loop()

        def signal_handler(signum, frame):
            """Handler appelé lors de la réception d'un signal"""
            signal_name = signal.Signals(signum).name
            self.Logger.info(f"Signal {signal_name} reçu, arrêt gracieux du serveur...")

            # Planifie l'arrêt dans la boucle asyncio
            if self.Running:
                asyncio.create_task(self.Stop())

        # Enregistre les handlers
        for sig in signals:
            try:
                signal.signal(sig, signal_handler)
                self.Logger.debug(f"Handler installé pour {signal.Signals(sig).name}")
            except (OSError, ValueError) as e:
                # Certains signaux ne peuvent pas être capturés sur certaines plateformes
                self.Logger.debug(f"Impossible d'installer le handler pour {sig}: {e}")

    async def _GracefulShutdown(self):
        """
        Séquence d'arrêt gracieux du serveur.
        Cette méthode est appelée avec un timeout global par Stop().
        """
        # Étape 1: Notifie tous les clients que le serveur va s'arrêter
        if self.ClientManager:
            ClientIds = self.ClientManager.GetConnectedClients()
            if ClientIds:
                self.Logger.info(f"Notification d'arrêt à {len(ClientIds)} clients...")

                # Crée le message de déconnexion
                disconnect_msg = DisconnectMessage(Reason="server_shutdown")
                disconnect_json = disconnect_msg.ToJson()

                # Envoie le message à tous les clients en parallèle
                notification_tasks = []
                for client_id in ClientIds:
                    task = self.ClientManager.SendMessage(client_id, disconnect_json, Encrypted=True)
                    notification_tasks.append(task)

                # Attend que toutes les notifications soient envoyées (avec timeout de 5s)
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*notification_tasks, return_exceptions=True),
                        timeout=5.0
                    )
                    self.Logger.info("✓ Notifications envoyées aux clients")
                except asyncio.TimeoutError:
                    self.Logger.warning("Timeout lors de l'envoi des notifications (5s)")

                # Attend 2 secondes pour que les clients traitent le message
                self.Logger.info("Attente de déconnexion gracieuse des clients (2s)...")
                await asyncio.sleep(2)

        # Étape 2: Arrête la distribution des batches et sauvegarde l'état
        if self.BatchDistributor:
            await self.BatchDistributor.StopDistribution()

        # Étape 3: Arrête le monitoring des heartbeats
        if self.ClientManager:
            await self.ClientManager.StopHeartbeatMonitoring()

        # Étape 4: Ferme le listener TCP pour empêcher de nouvelles connexions
        if self.NetworkManager:
            self.Logger.info("Fermeture des listeners réseau...")
            await self.NetworkManager.Stop()

        # Étape 4: Déconnecte tous les clients restants
        if self.ClientManager:
            ClientIds = self.ClientManager.GetConnectedClients()
            if ClientIds:
                self.Logger.info(f"Déconnexion de {len(ClientIds)} clients restants...")

                # Déconnecte en parallèle avec timeout
                disconnect_tasks = []
                for ClientId in ClientIds:
                    task = self.ClientManager.RemoveClient(ClientId)
                    disconnect_tasks.append(task)

                try:
                    await asyncio.wait_for(
                        asyncio.gather(*disconnect_tasks, return_exceptions=True),
                        timeout=10.0
                    )
                    self.Logger.info("✓ Tous les clients déconnectés")
                except asyncio.TimeoutError:
                    self.Logger.warning("Timeout lors de la déconnexion des clients (10s)")

        # Étape 5: Ferme la base de données
        if self.Database:
            self.Logger.info("Fermeture de la base de données...")
            self.Database.Close()

    async def _HandleControlConnection(self, Reader: asyncio.StreamReader,
                                        Writer: asyncio.StreamWriter):
        """
        Gère une nouvelle connexion sur le port Control (handshake, heartbeat, status)

        Args:
            Reader: StreamReader asyncio
            Writer: StreamWriter asyncio
        """
        ClientId = None

        try:
            # Configure le socket TCP pour éviter les timeouts
            ConfigureSocket(Writer, self.Logger)

            # Handshake et authentification
            ClientId = await self.ClientManager.HandleNewConnection(Reader, Writer)

            if not ClientId:
                self.Logger.warning("Échec de la connexion du client (Control)")
                return

            # Boucle de communication Control (heartbeat, status)
            await self._ClientCommunicationLoop(ClientId)

        except Exception as e:
            self.Logger.error(f"Erreur lors de la gestion du client (Control): {e}")

        finally:
            # Nettoie la connexion
            if ClientId:
                await self.ClientManager.RemoveClient(ClientId)

    async def _HandleDataConnection(self, Reader: asyncio.StreamReader,
                                    Writer: asyncio.StreamWriter):
        """
        Gère une nouvelle connexion sur le port Data (transferts de batches)

        Args:
            Reader: StreamReader asyncio
            Writer: StreamWriter asyncio
        """
        ClientId = None
        try:
            # Configure le socket TCP pour éviter les timeouts
            ConfigureSocket(Writer, self.Logger)

            # Le client doit s'identifier avec DataChannelAuth
            Success = await self.ClientManager.HandleDataConnection(Reader, Writer)

            if not Success:
                self.Logger.warning("Échec de l'association du canal Data")
                return

            # Trouve le ClientId associé à cette connexion Data
            for Cid, ClientInfo in self.ClientManager.Clients.items():
                if ClientInfo.DataWriter == Writer:
                    ClientId = Cid
                    break

            if not ClientId:
                self.Logger.error("Impossible de trouver le client pour le canal Data")
                return

            self.Logger.info(f"Canal Data connecté pour le client {ClientId}")

            # Démarre la boucle d'écoute pour les BatchResults
            await self._DataCommunicationLoop(ClientId)

        except Exception as e:
            self.Logger.error(f"Erreur lors de la gestion de connexion Data: {e}")

    async def _DataCommunicationLoop(self, ClientId: str):
        """
        Boucle de communication Data pour recevoir les BatchResults

        Args:
            ClientId: ID du client
        """
        self.Logger.info(f"Démarrage de la boucle Data pour le client {ClientId}")

        while self.Running:
            try:
                # Reçoit un résultat binaire tar via le canal Data
                # Timeout raisonnable pour les transferts Data (images volumineuses)
                DataTimeout = NetworkConfig.BATCH_TIMEOUT
                try:
                    TarBytes = await asyncio.wait_for(
                        self.ClientManager.ReceiveDataBinary(ClientId),
                        timeout=DataTimeout
                    )
                except asyncio.TimeoutError:
                    self.Logger.warning(f"Timeout réception Data pour client {ClientId} ({DataTimeout}s)")
                    await self.ClientManager.DisconnectClient(ClientId, "Timeout Data")
                    break

                if not TarBytes:
                    # Client déconnecté proprement (connexion fermée)
                    self.Logger.info(f"Connexion Data fermée par le client {ClientId}")
                    break

                # Désérialise le tar binaire (BatchResult)
                try:
                    MetaDict, ImagesBytesDict = BatchResult.ParseBinary(TarBytes)
                except Exception as ParseErr:
                    self.Logger.error(f"Erreur désérialisation BatchResult tar du client {ClientId}: {ParseErr}")
                    continue

                BatchId = MetaDict.get("batch_id", "inconnu")
                self.Logger.info(
                    f"BatchResult binaire reçu du client {ClientId}: "
                    f"batch {BatchId}, {len(ImagesBytesDict)} images, {len(TarBytes)/1024:.1f} KB"
                )

                if self.BatchDistributor:
                    # Traite dans une tâche séparée pour ne pas bloquer la lecture
                    asyncio.create_task(
                        self.BatchDistributor.ReceiveBatchResultBinary(ClientId, MetaDict, ImagesBytesDict)
                    )
                else:
                    self.Logger.error("BatchDistributor non configuré - résultat binaire ignoré")

            except Exception as e:
                self.Logger.error(f"Erreur dans la boucle Data du client {ClientId}: {e}")
                break

        self.Logger.info(f"Fin de la boucle Data pour le client {ClientId}")

    async def _ClientCommunicationLoop(self, ClientId: str):
        """
        Boucle de communication avec un client

        Args:
            ClientId: ID du client
        """
        self.Logger.info(f"Début de la communication avec le client {ClientId}")

        while self.Running:
            try:
                # Détermine le timeout en fonction du statut du client
                # Les clients en traitement ont besoin de plus de temps car Real-ESRGAN bloque
                ClientStatus = self.ClientManager.GetClientStatus(ClientId)
                if ClientStatus in ["processing", "receiving"]:
                    CommunicationTimeout = NetworkConfig.BATCH_TIMEOUT
                else:
                    CommunicationTimeout = NetworkConfig.HEARTBEAT_TIMEOUT * 2

                # Reçoit un message du client (avec timeout adapté)
                MessageData = await asyncio.wait_for(
                    self.ClientManager.ReceiveMessage(ClientId, Decrypt=True),
                    timeout=CommunicationTimeout
                )

                if not MessageData:
                    self.Logger.warning(f"Message vide reçu du client {ClientId}")
                    break

                # Parse le message
                Message = MessageFactory.CreateFromJson(MessageData)

                # Traite le message
                await self._HandleClientMessage(ClientId, Message)

            except asyncio.TimeoutError:
                self.Logger.warning(f"Timeout de communication avec le client {ClientId}")
                break

            except Exception as e:
                self.Logger.error(f"Erreur dans la boucle de communication: {e}")
                break

    async def _HandleClientMessage(self, ClientId: str, Message):
        """
        Traite un message reçu d'un client

        Args:
            ClientId: ID du client
            Message: Message parsé
        """
        MessageType = Message.MessageType

        # Heartbeat pong
        if isinstance(Message, HeartbeatPong):
            await self.ClientManager.UpdateHeartbeat(ClientId)

            # Mise à jour du statut client depuis le heartbeat
            # Permet de détecter qu'un client a fini de traiter avant de recevoir le BatchResult
            ReportedStatus = Message.Payload.get("client_status")
            if ReportedStatus:
                CurrentStatus = self.ClientManager.GetClientStatus(ClientId)
                # Seulement si le client rapporte IDLE et qu'on pensait qu'il était PROCESSING
                if ReportedStatus == ClientStatus.IDLE and CurrentStatus == ClientStatus.PROCESSING:
                    self.ClientManager.UpdateClientStatus(ClientId, ClientStatus.IDLE)
                    self.Logger.debug(f"Client {ClientId} passe en IDLE (via heartbeat)")

            self.Logger.debug(f"Heartbeat pong reçu du client {ClientId}")

        # Mise à jour de statut (notification push du client)
        elif isinstance(Message, StatusUpdate):
            NewStatus = Message.Payload.get("status")
            if NewStatus:
                self.ClientManager.UpdateClientStatus(ClientId, NewStatus)
                self.Logger.info(f"Client {ClientId} signale statut: {NewStatus}")

        # Résultat de batch
        elif isinstance(Message, BatchResult):
            self.Logger.info(f"Résultat de batch reçu du client {ClientId}")
            if self.BatchDistributor:
                await self.BatchDistributor.ReceiveBatchResult(ClientId, Message)
            else:
                self.Logger.error("BatchDistributor non configuré - résultat ignoré")

        # Autres types de messages
        else:
            self.Logger.debug(f"Message reçu du client {ClientId}: {MessageType}")

    def _GetWebhookConfig(self) -> dict:
        """
        Retourne la configuration webhook depuis la base de données

        Returns:
            Dict avec webhook_enabled, webhook_url, webhook_events
        """
        if not self.Database:
            return {}

        return {
            "webhook_enabled": self.Database.GetParameterBool("webhook_enabled", False),
            "webhook_url": self.Database.GetParameter("webhook_url", ""),
            "webhook_events": self.Database.GetParameter("webhook_events", "")
        }

    def _PrintServerInfo(self):
        """Affiche les informations du serveur"""
        HostV4, HostV6, ControlPort = self.NetworkManager.GetControlAddress()
        _, _, DataPort = self.NetworkManager.GetDataAddress()
        self.Logger.info("="*60)
        self.Logger.info("SERVEUR D'UPSCALING VIDÉO EN RÉSEAU")
        self.Logger.info("="*60)
        if HostV4:
            self.Logger.info(f"IPv4 Control: {HostV4}:{ControlPort} (handshake, heartbeat)")
            self.Logger.info(f"IPv4 Data:    {HostV4}:{DataPort} (transferts de batches)")
        if HostV6:
            self.Logger.info(f"IPv6 Control: [{HostV6}]:{ControlPort} (handshake, heartbeat)")
            self.Logger.info(f"IPv6 Data:    [{HostV6}]:{DataPort} (transferts de batches)")
        self.Logger.info(f"Répertoire de travail: {self.WorkDirectory}")
        self.Logger.info(f"Mot de passe configuré: {'Oui' if self.Password else 'Non'}")
        self.Logger.info(f"Base de données: {self.Database.DbPath}")
        self.Logger.info("="*60)

    def GetStatus(self) -> dict:
        """
        Récupère le statut du serveur

        Returns:
            Dictionnaire avec le statut
        """
        if self.NetworkManager:
            HostV4, HostV6, ControlPort = self.NetworkManager.GetControlAddress()
            _, _, DataPort = self.NetworkManager.GetDataAddress()
        else:
            HostV4 = self.HostV4
            HostV6 = self.HostV6
            ControlPort = self.Port
            DataPort = self.DataPort

        return {
            "running": self.Running,
            "ipv4": HostV4,
            "ipv6": HostV6,
            "port": ControlPort,
            "data_port": DataPort,
            "connected_clients": self.ClientManager.GetClientCount() if self.ClientManager else 0,
            "work_directory": self.WorkDirectory,
            "database": self.Database.DbPath if self.Database else None
        }

    async def RebindNetwork(self, NewHostV4: str, NewControlPort: int, NewDataPort: int = None,
                            NewHostV6: str = None) -> bool:
        """
        Change l'adresse IP/Ports du serveur à chaud sans perdre les clients connectés.

        Args:
            NewHostV4: Nouvelle adresse IPv4 (vide pour désactiver)
            NewControlPort: Nouveau port de contrôle
            NewDataPort: Nouveau port de données (optionnel, garde l'actuel si None)
            NewHostV6: Nouvelle adresse IPv6 (None = inchangée)

        Returns:
            True si succès
        """
        if not self.Running:
            self.Logger.warning("Le serveur n'est pas en cours d'exécution")
            return False

        if NewDataPort is None:
            NewDataPort = self.DataPort

        Success = await self.NetworkManager.Rebind(NewHostV4, NewControlPort, NewDataPort, NewHostV6)

        if Success:
            self.HostV4 = NewHostV4
            if NewHostV6 is not None:
                self.HostV6 = NewHostV6
            self.Port = NewControlPort
            self.DataPort = NewDataPort
        else:
            self.Logger.error(f"✗ Échec du rebind vers v4={NewHostV4} v6={NewHostV6}")

        return Success

    async def Serve(self):
        """
        Sert indéfiniment (bloque jusqu'à arrêt)
        """
        if not self.NetworkManager or not self.NetworkManager.IsRunning():
            self.Logger.error("Serveur non démarré")
            return

        # Attend que le serveur soit arrêté
        while self.Running:
            await asyncio.sleep(1)


# ============================================================================
# FONCTION D'AIDE POUR LANCER LE SERVEUR
# ============================================================================

async def RunServer(Config: dict):
    """
    Lance le serveur avec la configuration donnée

    Args:
        Config: Configuration du serveur
    """
    Server = UpscalingServer(Config)

    if not Server.Initialize():
        print("✗ Échec de l'initialisation du serveur")
        return

    if not await Server.Start():
        print("✗ Échec du démarrage du serveur")
        return

    try:
        # Sert indéfiniment
        await Server.Serve()

    except KeyboardInterrupt:
        print("\n\nInterruption utilisateur")

    finally:
        await Server.Stop()


# ============================================================================
# EXEMPLE D'UTILISATION
# ============================================================================

if __name__ == "__main__":
    import json

    # Configuration de test
    TestConfig = {
        "server": {
            "ipv4": "0.0.0.0",
            "ipv6": "",
            "port": 8765,
            "password": "test123",
            "work_directory": "./test_work",
            "batch_size": 100
        }
    }

    # Lance le serveur
    asyncio.run(RunServer(TestConfig))
