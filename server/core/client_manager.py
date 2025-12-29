"""
Gestionnaire de clients pour le serveur
Gère les connexions, authentification, heartbeat et états des clients
"""

import asyncio
import uuid
import time
from typing import Dict, Optional, List
from datetime import datetime

from shared.protocol.messages import (
    HandshakeRequest, HandshakeResponse, AuthRequest, AuthResponse,
    HeartbeatPing, HeartbeatPong, MessageFactory, ErrorMessage
)
from shared.protocol.encryption import EncryptionHandler, PasswordHasher
from shared.protocol.compression import NegotiateCompression
from shared.utils.logger import GetModuleLogger
from shared.utils.constants import ClientStatus, ErrorCode, NetworkConfig
from server.database.db_manager import DatabaseManager
from server.database.models import ClientHistory


class ClientInfo:
    """Information sur un client connecté"""

    def __init__(self, ClientId: str, Reader: asyncio.StreamReader,
                 Writer: asyncio.StreamWriter, IpAddress: str):
        """
        Initialise les informations client

        Args:
            ClientId: ID unique du client
            Reader: StreamReader asyncio
            Writer: StreamWriter asyncio
            IpAddress: Adresse IP du client
        """
        self.ClientId = ClientId
        self.Reader = Reader
        self.Writer = Writer
        self.IpAddress = IpAddress

        # Récupérer l'adresse complète (IP, Port) depuis le Writer
        PeerName = Writer.get_extra_info('peername')
        self.Address = PeerName if PeerName else (IpAddress, 0)

        self.EncryptionHandler = EncryptionHandler()
        self.Status = ClientStatus.CONNECTING
        self.CurrentBatch = None
        self.LastHeartbeat = time.time()
        self.ConnectedAt = datetime.now()
        self.Authenticated = False


class ClientManager:
    """Gestionnaire de clients connectés"""

    def __init__(self, ServerPassword: str, Database: DatabaseManager):
        """
        Initialise le gestionnaire de clients

        Args:
            ServerPassword: Mot de passe du serveur
            Database: Gestionnaire de base de données
        """
        self.ServerPassword = ServerPassword
        self.Database = Database
        self.Clients: Dict[str, ClientInfo] = {}
        self.Logger = GetModuleLogger("ClientManager")
        self.HeartbeatTask = None
        self.Running = False
        self.OnClientDisconnected = None  # Callback async appelé lors d'une déconnexion

    async def HandleNewConnection(self, Reader: asyncio.StreamReader,
                                  Writer: asyncio.StreamWriter) -> Optional[str]:
        """
        Gère une nouvelle connexion client

        Args:
            Reader: StreamReader asyncio
            Writer: StreamWriter asyncio

        Returns:
            ID du client si succès, None sinon
        """
        PeerName = Writer.get_extra_info('peername')
        IpAddress = PeerName[0] if PeerName else "unknown"

        self.Logger.info(f"Nouvelle connexion depuis {IpAddress}")

        # Génère un ID unique pour le client
        ClientId = str(uuid.uuid4())

        # Crée l'objet ClientInfo
        ClientInfo_obj = ClientInfo(ClientId, Reader, Writer, IpAddress)
        self.Clients[ClientId] = ClientInfo_obj

        try:
            # Effectue le handshake
            if not await self.PerformHandshake(ClientInfo_obj):
                self.Logger.error(f"Handshake échoué pour {IpAddress}")
                await self.RemoveClient(ClientId)
                return None

            # Effectue l'authentification
            if not await self.Authenticate(ClientInfo_obj):
                self.Logger.error(f"Authentification échouée pour {IpAddress}")
                await self.RemoveClient(ClientId)
                return None

            # Client connecté avec succès
            ClientInfo_obj.Status = ClientStatus.IDLE
            ClientInfo_obj.Authenticated = True

            self.Logger.info(f"Client {ClientId} connecté et authentifié depuis {IpAddress}")

            # Ajoute à l'historique
            History = ClientHistory(
                ClientId=ClientId,
                IpAddress=IpAddress,
                ConnectedAt=ClientInfo_obj.ConnectedAt
            )
            self.Database.AddClientHistory(History)

            return ClientId

        except Exception as e:
            self.Logger.error(f"Erreur lors de la gestion de la connexion: {e}")
            await self.RemoveClient(ClientId)
            return None

    async def PerformHandshake(self, ClientInfo: ClientInfo) -> bool:
        """
        Effectue le handshake avec un client

        Args:
            ClientInfo: Information du client

        Returns:
            True si succès
        """
        try:
            # Attend la demande de handshake du client (timeout 30s)
            RequestData = await asyncio.wait_for(
                self._ReceiveMessage(ClientInfo),
                timeout=NetworkConfig.CONNECTION_TIMEOUT
            )

            if not RequestData:
                return False

            # Parse la demande
            Request = MessageFactory.CreateFromJson(RequestData)

            if not isinstance(Request, HandshakeRequest):
                self.Logger.error("Message de handshake invalide")
                return False

            # Récupère la clé publique du client
            ClientPublicKey = Request.GetPublicKey()

            # Génère la clé publique du serveur
            ServerPublicKey = ClientInfo.EncryptionHandler.GenerateKeyPair()

            # Calcule la clé partagée
            if not ClientInfo.EncryptionHandler.ComputeSharedKey(ClientPublicKey):
                self.Logger.error("Échec du calcul de la clé partagée")
                return False

            # Négociation de la compression
            ClientCompression = Request.GetSupportedCompression()
            ServerCompression = ClientInfo.EncryptionHandler.GetSupportedCompression()
            SelectedCompression = NegotiateCompression(ClientCompression, ServerCompression)

            # Configure la compression sur le handler
            ClientInfo.EncryptionHandler.SetCompression(SelectedCompression)
            self.Logger.info(f"Compression négociée: {SelectedCompression}")

            # Envoie la réponse
            Response = HandshakeResponse(
                PublicKey=ServerPublicKey,
                Success=True,
                Message="Handshake réussi",
                SelectedCompression=SelectedCompression
            )

            await self._SendMessage(ClientInfo, Response.ToJson())

            self.Logger.info(f"Handshake réussi avec le client {ClientInfo.ClientId}")
            return True

        except asyncio.TimeoutError:
            self.Logger.error("Timeout lors du handshake")
            return False
        except Exception as e:
            self.Logger.error(f"Erreur lors du handshake: {e}")
            return False

    async def Authenticate(self, ClientInfo: ClientInfo) -> bool:
        """
        Authentifie un client avec le mot de passe du serveur

        Args:
            ClientInfo: Information du client

        Returns:
            True si succès
        """
        try:
            # Attend la demande d'authentification
            RequestData = await asyncio.wait_for(
                self._ReceiveMessage(ClientInfo),
                timeout=NetworkConfig.CONNECTION_TIMEOUT
            )

            if not RequestData:
                return False

            # Déchiffre et parse la demande
            DecryptedData = ClientInfo.EncryptionHandler.DecryptMessage(RequestData)
            if not DecryptedData:
                self.Logger.error("Impossible de déchiffrer la demande d'authentification")
                return False

            Request = MessageFactory.CreateFromJson(DecryptedData)

            if not isinstance(Request, AuthRequest):
                self.Logger.error("Message d'authentification invalide")
                return False

            # Vérifie le mot de passe
            ClientPassword = Request.GetPassword()

            if ClientPassword != self.ServerPassword:
                self.Logger.warning(f"Mot de passe incorrect du client {ClientInfo.IpAddress}")

                # Envoie une réponse d'échec
                Response = AuthResponse(
                    Success=False,
                    Message="Mot de passe incorrect"
                )
                EncryptedResponse = ClientInfo.EncryptionHandler.EncryptMessage(Response.ToJson())
                await self._SendMessage(ClientInfo, EncryptedResponse)
                return False

            # Authentification réussie
            Response = AuthResponse(
                Success=True,
                ClientId=ClientInfo.ClientId,
                Message="Authentification réussie"
            )

            EncryptedResponse = ClientInfo.EncryptionHandler.EncryptMessage(Response.ToJson())
            await self._SendMessage(ClientInfo, EncryptedResponse)

            self.Logger.info(f"Client {ClientInfo.ClientId} authentifié")
            return True

        except asyncio.TimeoutError:
            self.Logger.error("Timeout lors de l'authentification")
            return False
        except Exception as e:
            self.Logger.error(f"Erreur lors de l'authentification: {e}")
            return False

    async def SendMessage(self, ClientId: str, Message: str, Encrypted: bool = True) -> bool:
        """
        Envoie un message à un client

        Args:
            ClientId: ID du client
            Message: Message à envoyer (JSON)
            Encrypted: Si True, chiffre le message

        Returns:
            True si succès
        """
        if ClientId not in self.Clients:
            self.Logger.error(f"Client {ClientId} non trouvé")
            return False

        ClientInfo = self.Clients[ClientId]

        try:
            MessageToSend = Message
            if Encrypted and ClientInfo.EncryptionHandler.IsReady():
                MessageToSend = ClientInfo.EncryptionHandler.EncryptMessage(Message)

            return await self._SendMessage(ClientInfo, MessageToSend)

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'envoi du message au client {ClientId}: {e}")
            return False

    async def ReceiveMessage(self, ClientId: str, Decrypt: bool = True) -> Optional[str]:
        """
        Reçoit un message d'un client

        Args:
            ClientId: ID du client
            Decrypt: Si True, déchiffre le message

        Returns:
            Message reçu (JSON) ou None
        """
        if ClientId not in self.Clients:
            self.Logger.error(f"Client {ClientId} non trouvé")
            return None

        ClientInfo = self.Clients[ClientId]

        try:
            ReceivedData = await self._ReceiveMessage(ClientInfo)

            if not ReceivedData:
                return None

            if Decrypt and ClientInfo.EncryptionHandler.IsReady():
                return ClientInfo.EncryptionHandler.DecryptMessage(ReceivedData)

            return ReceivedData

        except Exception as e:
            self.Logger.error(f"Erreur lors de la réception du message du client {ClientId}: {e}")
            return None

    async def _SendMessage(self, ClientInfo: ClientInfo, Message: str) -> bool:
        """Envoie un message (interne)"""
        try:
            # Format: taille (4 bytes) + message
            MessageBytes = Message.encode('utf-8')
            MessageSize = len(MessageBytes)
            SizeBytes = MessageSize.to_bytes(4, byteorder='big')

            ClientInfo.Writer.write(SizeBytes + MessageBytes)
            await ClientInfo.Writer.drain()

            return True

        except Exception as e:
            self.Logger.error(f"Erreur d'envoi: {e}")
            return False

    async def _ReceiveMessage(self, ClientInfo: ClientInfo) -> Optional[str]:
        """Reçoit un message (interne)"""
        try:
            # Lit la taille (4 bytes)
            SizeBytes = await ClientInfo.Reader.readexactly(4)
            MessageSize = int.from_bytes(SizeBytes, byteorder='big')

            # Limite de taille
            if MessageSize > NetworkConfig.MAX_MESSAGE_SIZE:
                self.Logger.error(f"Message trop grand: {MessageSize} bytes")
                return None

            # Lit le message
            MessageBytes = await ClientInfo.Reader.readexactly(MessageSize)
            return MessageBytes.decode('utf-8')

        except asyncio.IncompleteReadError:
            self.Logger.warning("Connexion fermée par le client")
            return None
        except Exception as e:
            self.Logger.error(f"Erreur de réception: {e}")
            return None

    async def RemoveClient(self, ClientId: str):
        """
        Retire un client et nettoie les ressources

        Args:
            ClientId: ID du client
        """
        if ClientId not in self.Clients:
            return

        ClientInfo = self.Clients[ClientId]

        # Appelle le callback de déconnexion AVANT de fermer
        # Permet de réallouer les batches assignés au client
        if self.OnClientDisconnected:
            try:
                await self.OnClientDisconnected(ClientId)
            except Exception as e:
                self.Logger.error(f"Erreur dans le callback de déconnexion: {e}")

        try:
            # Ferme la connexion
            ClientInfo.Writer.close()
            await ClientInfo.Writer.wait_closed()
        except Exception as e:
            self.Logger.error(f"Erreur lors de la fermeture de la connexion: {e}")

        # Met à jour l'historique
        History = self.Database.GetClientHistory(ClientId)
        if History:
            History.DisconnectedAt = datetime.now()
            History.LastSeen = datetime.now()
            self.Database.UpdateClientHistory(History)

        # Retire du dictionnaire
        del self.Clients[ClientId]

        self.Logger.info(f"Client {ClientId} retiré")

    def GetClientStatus(self, ClientId: str) -> Optional[str]:
        """Récupère le statut d'un client"""
        if ClientId in self.Clients:
            return self.Clients[ClientId].Status
        return None

    def UpdateClientStatus(self, ClientId: str, Status: str):
        """Met à jour le statut d'un client"""
        if ClientId in self.Clients:
            self.Clients[ClientId].Status = Status

    def GetConnectedClients(self) -> List[str]:
        """Récupère la liste des IDs des clients connectés"""
        return list(self.Clients.keys())

    def GetAllClients(self) -> Dict[str, ClientInfo]:
        """Récupère le dictionnaire complet des clients connectés"""
        return self.Clients.copy()

    def GetClientCount(self) -> int:
        """Récupère le nombre de clients connectés"""
        return len(self.Clients)

    async def DisconnectClient(self, ClientId: str):
        """
        Déconnecte un client (alias pour RemoveClient)

        Args:
            ClientId: ID du client
        """
        await self.RemoveClient(ClientId)

    async def StartHeartbeatMonitoring(self):
        """Démarre le monitoring des heartbeats"""
        self.Running = True
        self.HeartbeatTask = asyncio.create_task(self._HeartbeatLoop())
        self.Logger.info("Monitoring heartbeat démarré")

    async def StopHeartbeatMonitoring(self):
        """Arrête le monitoring des heartbeats"""
        self.Running = False
        if self.HeartbeatTask:
            self.HeartbeatTask.cancel()
            try:
                await self.HeartbeatTask
            except asyncio.CancelledError:
                pass
        self.Logger.info("Monitoring heartbeat arrêté")

    async def _HeartbeatLoop(self):
        """Boucle de monitoring des heartbeats"""
        while self.Running:
            try:
                await asyncio.sleep(NetworkConfig.HEARTBEAT_INTERVAL)

                # Vérifie tous les clients
                ClientsToRemove = []
                for ClientId, ClientInfo in list(self.Clients.items()):
                    if not ClientInfo.Authenticated:
                        continue

                    # Envoie un ping
                    Ping = HeartbeatPing()
                    Success = await self.SendMessage(ClientId, Ping.ToJson(), Encrypted=True)

                    if not Success:
                        self.Logger.warning(f"Impossible d'envoyer heartbeat au client {ClientId}")
                        ClientsToRemove.append(ClientId)
                        continue

                    # Vérifie le timeout - utilise BATCH_TIMEOUT si le client traite un batch
                    TimeSinceLastHeartbeat = time.time() - ClientInfo.LastHeartbeat

                    # Les clients en traitement ont un timeout plus long (BATCH_TIMEOUT)
                    # car Real-ESRGAN bloque l'envoi des heartbeats
                    if ClientInfo.Status == ClientStatus.PROCESSING:
                        TimeoutValue = NetworkConfig.BATCH_TIMEOUT
                    else:
                        TimeoutValue = NetworkConfig.HEARTBEAT_TIMEOUT

                    if TimeSinceLastHeartbeat > TimeoutValue:
                        self.Logger.warning(f"Client {ClientId} timeout (pas de heartbeat depuis {TimeSinceLastHeartbeat:.1f}s, statut: {ClientInfo.Status})")
                        ClientsToRemove.append(ClientId)

                # Retire les clients timeout
                for ClientId in ClientsToRemove:
                    await self.RemoveClient(ClientId)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.Logger.error(f"Erreur dans la boucle heartbeat: {e}")

    async def UpdateHeartbeat(self, ClientId: str):
        """Met à jour le timestamp du dernier heartbeat d'un client"""
        if ClientId in self.Clients:
            self.Clients[ClientId].LastHeartbeat = time.time()

            # Met à jour l'historique
            History = self.Database.GetClientHistory(ClientId)
            if History:
                History.LastSeen = datetime.now()
                self.Database.UpdateClientHistory(History)

    def UpdatePassword(self, NewPassword: str):
        """
        Met à jour le mot de passe du serveur dynamiquement.
        Les clients déjà connectés ne sont pas affectés (ils sont déjà authentifiés).
        Seules les nouvelles connexions devront utiliser le nouveau mot de passe.

        Args:
            NewPassword: Nouveau mot de passe (peut être vide pour désactiver)
        """
        self.ServerPassword = NewPassword
        self.Logger.info(f"Mot de passe serveur mis à jour (vide: {NewPassword == ''})")

    def SetDisconnectCallback(self, Callback):
        """
        Définit un callback à appeler lors de la déconnexion d'un client.
        Le callback sera appelé avant la fermeture de la connexion.

        Args:
            Callback: Fonction async prenant ClientId en paramètre
        """
        self.OnClientDisconnected = Callback
