"""
Serveur principal d'upscaling vidéo en réseau
Gère les connexions clients et orchestre le traitement distribué
"""

import asyncio
import os
from typing import Optional
from pathlib import Path

from server.core.client_manager import ClientManager
from server.database.db_manager import DatabaseManager
from shared.utils.logger import GetServerLogger
from shared.utils.constants import NetworkConfig, PathConfig
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
        self.Server = None

        # Configuration
        self.Host = Config.get("server", {}).get("ip", NetworkConfig.DEFAULT_HOST)
        self.Port = Config.get("server", {}).get("port", NetworkConfig.DEFAULT_PORT)
        self.Password = Config.get("server", {}).get("password", "")
        self.WorkDirectory = Config.get("server", {}).get("work_directory", PathConfig.WORK_DIR)

        # Base de données
        DbPath = os.path.join(self.WorkDirectory, PathConfig.DATABASE_NAME)
        self.Database = DatabaseManager(DbPath)

        # Gestionnaire de clients
        self.ClientManager = None

        # Distributeur de batches (sera défini après initialisation)
        self.BatchDistributor = None

        self.Logger.info("Serveur initialisé")

    def SetBatchDistributor(self, Distributor):
        """
        Définit le distributeur de batches

        Args:
            Distributor: Instance de BatchDistributor
        """
        self.BatchDistributor = Distributor

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
        self.Database.SetParameter("server_version", "1.0.0", "Version du serveur")
        self.Database.SetParameter("batch_size", str(self.Config.get("server", {}).get("batch_size", 100)), "Taille des paquets d'images")
        self.Database.SetParameter("work_directory", self.WorkDirectory, "Répertoire de travail")

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

            # Démarre le serveur TCP
            self.Server = await asyncio.start_server(
                self._HandleClientConnection,
                self.Host,
                self.Port
            )

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

        # Ferme le serveur
        if self.Server:
            self.Server.close()
            await self.Server.wait_closed()

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
                # Reçoit un message du client (avec timeout)
                MessageData = await asyncio.wait_for(
                    self.ClientManager.ReceiveMessage(ClientId, Decrypt=True),
                    timeout=NetworkConfig.HEARTBEAT_TIMEOUT * 2
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
        self.Logger.info("="*60)
        self.Logger.info("SERVEUR D'UPSCALING VIDÉO EN RÉSEAU")
        self.Logger.info("="*60)
        self.Logger.info(f"Adresse: {self.Host}:{self.Port}")
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
        return {
            "running": self.Running,
            "host": self.Host,
            "port": self.Port,
            "connected_clients": self.ClientManager.GetClientCount() if self.ClientManager else 0,
            "work_directory": self.WorkDirectory,
            "database": self.Database.DbPath if self.Database else None
        }

    async def Serve(self):
        """
        Sert indéfiniment (bloque jusqu'à arrêt)
        """
        if not self.Server:
            self.Logger.error("Serveur non démarré")
            return

        async with self.Server:
            await self.Server.serve_forever()


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
