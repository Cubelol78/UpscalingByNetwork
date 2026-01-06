"""
Serveur principal d'upscaling vidéo en réseau
Gère les connexions clients et orchestre le traitement distribué
"""

import asyncio
import os
import socket
import platform
from typing import Optional
from pathlib import Path

from server.core.client_manager import ClientManager
from server.core.network_manager import NetworkManager, DualNetworkManager
from server.database.db_manager import DatabaseManager
from shared.utils.logger import GetServerLogger
from shared.utils.constants import NetworkConfig, PathConfig, ClientStatus
from shared.protocol.messages import MessageFactory, HeartbeatPong, BatchResult, StatusUpdate


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
            Sock.ioctl(
                socket.SIO_KEEPALIVE_VALS,
                (1, 30000, 10000)  # 30s idle, 10s interval
            )
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

        # Augmente les buffers pour les gros transferts
        Sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 * 1024 * 1024)  # 2MB
        Sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 2 * 1024 * 1024)  # 2MB

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
        self.Host = Config.get("server", {}).get("ip", NetworkConfig.DEFAULT_HOST)
        self.Port = Config.get("server", {}).get("port", NetworkConfig.DEFAULT_PORT)
        self.DataPort = Config.get("server", {}).get("data_port", NetworkConfig.DEFAULT_DATA_PORT)
        self.Password = Config.get("server", {}).get("password", "")
        self.WorkDirectory = Config.get("server", {}).get("work_directory", PathConfig.WORK_DIR)

        # Base de données - utilise le chemin par défaut (indépendant du work_directory)
        self.Database = DatabaseManager()  # Utilise GetDefaultDbPath()

        # Gestionnaire de réseau dual-port (Control + Data)
        self.NetworkManager = DualNetworkManager(self.Host, self.Port, self.DataPort)

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
        self.Database.SetParameter("server_version", "1.0.0", "Version du serveur")

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
            self.Logger.info(f"Démarrage du serveur sur {self.Host}:{self.Port} (Control) / {self.DataPort} (Data)...")

            # Démarre les deux listeners TCP via DualNetworkManager
            if not await self.NetworkManager.Start(
                self._HandleControlConnection,
                self._HandleDataConnection
            ):
                self.Logger.error("Échec du démarrage des listeners TCP")
                return False

            self.Running = True

            # Démarre le monitoring des heartbeats
            await self.ClientManager.StartHeartbeatMonitoring()

            self.Logger.info(f"✓ Serveur démarré - Control: {self.Host}:{self.Port}, Data: {self.Host}:{self.DataPort}")

            # Affiche les informations
            self._PrintServerInfo()

            return True

        except Exception as e:
            self.Logger.error(f"Erreur lors du démarrage du serveur: {e}")
            return False

    async def Stop(self):
        """Arrête le serveur"""
        if not self.Running:
            self.Logger.warning("Le serveur n'est pas en cours d'exécution")
            return

        self.Logger.info("Arrêt du serveur...")

        self.Running = False

        # Arrête le monitoring des heartbeats
        if self.ClientManager:
            await self.ClientManager.StopHeartbeatMonitoring()

        # Ferme le listener TCP via NetworkManager
        if self.NetworkManager:
            await self.NetworkManager.Stop()

        # Déconnecte tous les clients
        if self.ClientManager:
            ClientIds = self.ClientManager.GetConnectedClients()
            for ClientId in ClientIds:
                await self.ClientManager.RemoveClient(ClientId)

        # Ferme la base de données
        if self.Database:
            self.Database.Close()

        self.Logger.info("✓ Serveur arrêté")

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
                # Reçoit un message via le canal Data (timeout long car les transfers sont lourds)
                MessageData = await self.ClientManager.ReceiveDataMessage(
                    ClientId,
                    Decrypt=True,
                    Timeout=NetworkConfig.BATCH_TIMEOUT
                )

                if not MessageData:
                    self.Logger.warning(f"Message Data vide du client {ClientId}")
                    break

                # Parse le message
                Message = MessageFactory.CreateFromJson(MessageData)

                # On s'attend à des BatchResult sur le canal Data
                if isinstance(Message, BatchResult):
                    self.Logger.info(f"BatchResult reçu via Data du client {ClientId}")
                    if self.BatchDistributor:
                        await self.BatchDistributor.ReceiveBatchResult(ClientId, Message)
                    else:
                        self.Logger.error("BatchDistributor non configuré - résultat ignoré")
                else:
                    self.Logger.warning(f"Message inattendu sur canal Data: {Message.MessageType}")

            except asyncio.TimeoutError:
                # Timeout normal, on continue d'écouter
                continue

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

    def _PrintServerInfo(self):
        """Affiche les informations du serveur"""
        Host, ControlPort = self.NetworkManager.GetControlAddress()
        _, DataPort = self.NetworkManager.GetDataAddress()
        self.Logger.info("="*60)
        self.Logger.info("SERVEUR D'UPSCALING VIDÉO EN RÉSEAU")
        self.Logger.info("="*60)
        self.Logger.info(f"Port Control: {Host}:{ControlPort} (handshake, heartbeat)")
        self.Logger.info(f"Port Data:    {Host}:{DataPort} (transferts de batches)")
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
            Host, ControlPort = self.NetworkManager.GetControlAddress()
            _, DataPort = self.NetworkManager.GetDataAddress()
        else:
            Host = self.Host
            ControlPort = self.Port
            DataPort = self.DataPort

        return {
            "running": self.Running,
            "host": Host,
            "port": ControlPort,
            "data_port": DataPort,
            "connected_clients": self.ClientManager.GetClientCount() if self.ClientManager else 0,
            "work_directory": self.WorkDirectory,
            "database": self.Database.DbPath if self.Database else None
        }

    async def RebindNetwork(self, NewHost: str, NewControlPort: int, NewDataPort: int = None) -> bool:
        """
        Change l'adresse IP/Ports du serveur à chaud sans perdre les clients connectés.

        Args:
            NewHost: Nouvelle adresse IP
            NewControlPort: Nouveau port de contrôle
            NewDataPort: Nouveau port de données (optionnel, garde l'actuel si None)

        Returns:
            True si succès
        """
        if not self.Running:
            self.Logger.warning("Le serveur n'est pas en cours d'exécution")
            return False

        if NewDataPort is None:
            NewDataPort = self.DataPort

        self.Logger.info(f"Rebind du serveur vers {NewHost}:{NewControlPort}/{NewDataPort}")

        Success = await self.NetworkManager.Rebind(NewHost, NewControlPort, NewDataPort)

        if Success:
            # Met à jour les propriétés internes
            self.Host = NewHost
            self.Port = NewControlPort
            self.DataPort = NewDataPort
            self.Logger.info(f"✓ Serveur rebind - Control: {NewHost}:{NewControlPort}, Data: {NewHost}:{NewDataPort}")
        else:
            self.Logger.error(f"✗ Échec du rebind vers {NewHost}:{NewControlPort}/{NewDataPort}")

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
            "ip": "0.0.0.0",
            "port": 8765,
            "password": "test123",
            "work_directory": "./test_work",
            "batch_size": 100
        }
    }

    # Lance le serveur
    asyncio.run(RunServer(TestConfig))
