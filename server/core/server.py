"""
Serveur principal d'upscaling vidéo en réseau
Gère les connexions clients et orchestre le traitement distribué
"""

import asyncio
import os
from typing import Optional
from pathlib import Path

from server.core.client_manager import ClientManager
from server.core.network_manager import NetworkManager
from server.database.db_manager import DatabaseManager
from shared.utils.logger import GetServerLogger
from shared.utils.constants import NetworkConfig, PathConfig, ClientStatus
from shared.protocol.messages import MessageFactory, HeartbeatPong, BatchResult


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
        self.Password = Config.get("server", {}).get("password", "")
        self.WorkDirectory = Config.get("server", {}).get("work_directory", PathConfig.WORK_DIR)

        # Base de données - utilise le chemin par défaut (indépendant du work_directory)
        self.Database = DatabaseManager()  # Utilise GetDefaultDbPath()

        # Gestionnaire de réseau (permet le rebind dynamique IP/Port)
        self.NetworkManager = NetworkManager(self.Host, self.Port)

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
            self.Logger.info(f"Démarrage du serveur sur {self.Host}:{self.Port}...")

            # Démarre le serveur TCP via NetworkManager
            if not await self.NetworkManager.Start(self._HandleClientConnection):
                self.Logger.error("Échec du démarrage du listener TCP")
                return False

            self.Running = True

            # Démarre le monitoring des heartbeats
            await self.ClientManager.StartHeartbeatMonitoring()

            self.Logger.info(f"✓ Serveur démarré et en écoute sur {self.Host}:{self.Port}")

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

    async def _HandleClientConnection(self, Reader: asyncio.StreamReader,
                                     Writer: asyncio.StreamWriter):
        """
        Gère une nouvelle connexion client

        Args:
            Reader: StreamReader asyncio
            Writer: StreamWriter asyncio
        """
        ClientId = None

        try:
            # Handshake et authentification
            ClientId = await self.ClientManager.HandleNewConnection(Reader, Writer)

            if not ClientId:
                self.Logger.warning("Échec de la connexion du client")
                return

            # Boucle de communication avec le client
            await self._ClientCommunicationLoop(ClientId)

        except Exception as e:
            self.Logger.error(f"Erreur lors de la gestion du client: {e}")

        finally:
            # Nettoie la connexion
            if ClientId:
                await self.ClientManager.RemoveClient(ClientId)

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
        Host, Port = self.NetworkManager.GetAddress()
        self.Logger.info("="*60)
        self.Logger.info("SERVEUR D'UPSCALING VIDÉO EN RÉSEAU")
        self.Logger.info("="*60)
        self.Logger.info(f"Adresse: {Host}:{Port}")
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
        Host, Port = self.NetworkManager.GetAddress() if self.NetworkManager else (self.Host, self.Port)
        return {
            "running": self.Running,
            "host": Host,
            "port": Port,
            "connected_clients": self.ClientManager.GetClientCount() if self.ClientManager else 0,
            "work_directory": self.WorkDirectory,
            "database": self.Database.DbPath if self.Database else None
        }

    async def RebindNetwork(self, NewHost: str, NewPort: int) -> bool:
        """
        Change l'adresse IP/Port du serveur à chaud sans perdre les clients connectés.

        Args:
            NewHost: Nouvelle adresse IP
            NewPort: Nouveau port

        Returns:
            True si succès
        """
        if not self.Running:
            self.Logger.warning("Le serveur n'est pas en cours d'exécution")
            return False

        self.Logger.info(f"Rebind du serveur vers {NewHost}:{NewPort}")

        Success = await self.NetworkManager.Rebind(NewHost, NewPort)

        if Success:
            # Met à jour les propriétés internes
            self.Host = NewHost
            self.Port = NewPort
            self.Logger.info(f"✓ Serveur rebind sur {NewHost}:{NewPort}")
        else:
            self.Logger.error(f"✗ Échec du rebind vers {NewHost}:{NewPort}")

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
