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
    HeartbeatPing, HeartbeatPong, MessageFactory, ErrorMessage, DataChannelAuth,
    DataChannelAuthResponse
)
from shared.protocol.encryption import EncryptionHandler, PasswordHasher
from shared.protocol.compression import NegotiateCompression
from shared.utils.logger import GetModuleLogger
from shared.utils.constants import ClientStatus, ErrorCode, NetworkConfig, CompressionConfig
from shared.utils.error_events import EmitError, ErrorCategory, ErrorSeverity
from shared.utils.webhook_manager import TriggerServerWebhook
from server.database.db_manager import DatabaseManager
from server.database.models import ClientHistory


class ClientInfo:
    """Information sur un client connecté (architecture dual-port)"""

    def __init__(self, ClientId: str, Reader: asyncio.StreamReader,
                 Writer: asyncio.StreamWriter, IpAddress: str):
        """
        Initialise les informations client

        Args:
            ClientId: ID unique du client
            Reader: StreamReader asyncio (canal Control)
            Writer: StreamWriter asyncio (canal Control)
            IpAddress: Adresse IP du client
        """
        self.ClientId = ClientId

        # Connexion Control (handshake, heartbeat, status)
        self.ControlReader = Reader
        self.ControlWriter = Writer

        # Connexion Data (transferts de batches) - configurée après DataChannelAuth
        self.DataReader: asyncio.StreamReader = None
        self.DataWriter: asyncio.StreamWriter = None
        self.DataConnected = False

        # Alias pour compatibilité descendante (utilise Control par défaut)
        self.Reader = self.ControlReader
        self.Writer = self.ControlWriter

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
        self.HeartbeatEnabled = False  # Active seulement après connexion Data

        # Pipeline multi-batch : capacité du client
        self.MaxConcurrentBatches = 2  # Valeur par défaut, peut être mise à jour par le client

    def SetDataConnection(self, Reader: asyncio.StreamReader, Writer: asyncio.StreamWriter):
        """
        Configure la connexion Data pour ce client

        Args:
            Reader: StreamReader pour le canal Data
            Writer: StreamWriter pour le canal Data
        """
        self.DataReader = Reader
        self.DataWriter = Writer
        self.DataConnected = True
        self.HeartbeatEnabled = True  # Active le heartbeat maintenant que Data est connecté

    def IsDataConnected(self) -> bool:
        """Vérifie si la connexion Data est établie"""
        return self.DataConnected and self.DataWriter is not None


class ClientManager:
    """Gestionnaire de clients connectés"""

    def __init__(self, ServerPassword: str, Database: DatabaseManager, CompressionLevel: int = None):
        """
        Initialise le gestionnaire de clients

        Args:
            ServerPassword: Mot de passe du serveur
            Database: Gestionnaire de base de données
            CompressionLevel: Niveau de compression réseau (1-10)
        """
        self.ServerPassword = ServerPassword
        self.Database = Database
        self.Clients: Dict[str, ClientInfo] = {}
        self.PendingDataConnections: Dict[str, ClientInfo] = {}  # Clients en attente de connexion Data
        self.Logger = GetModuleLogger("ClientManager")
        self.HeartbeatTask = None
        self.Running = False
        self.OnClientDisconnected = None  # Callback async appelé lors d'une déconnexion

        # Niveau de compression (1-10)
        if CompressionLevel is None:
            CompressionLevel = Database.GetParameterInt('compression_level', CompressionConfig.LEVEL_DEFAULT)
        self.CompressionLevel = CompressionLevel

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

            # Webhook: client connecté
            TriggerServerWebhook("client_connected", client_id=ClientId, ip=IpAddress)

            # Ajoute à l'historique
            History = ClientHistory(
                ClientId=ClientId,
                IpAddress=IpAddress,
                ConnectedAt=ClientInfo_obj.ConnectedAt
            )
            self.Database.AddClientHistory(History)

            # Enregistre pour la future connexion Data (recherche O(1))
            self.PendingDataConnections[ClientId] = ClientInfo_obj
            self.Logger.debug(f"Client {ClientId} enregistré en attente de connexion Data")

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
                self.Logger.error("Aucune donnée reçue lors du handshake")
                return False

            # Parse la demande
            try:
                Request = MessageFactory.CreateFromJson(RequestData)
            except Exception as e:
                self.Logger.error(f"Impossible de parser la demande de handshake: {e}")
                return False

            if not isinstance(Request, HandshakeRequest):
                self.Logger.error(f"Type de message inattendu: {type(Request).__name__} (attendu: HandshakeRequest)")
                return False

            # Récupère la clé publique du client
            ClientPublicKey = Request.GetPublicKey()

            # Génère la clé publique du serveur
            ServerPublicKey = ClientInfo.EncryptionHandler.GenerateKeyPair()

            # Calcule la clé partagée
            if not ClientInfo.EncryptionHandler.ComputeSharedKey(ClientPublicKey):
                self.Logger.error("Échec du calcul de la clé partagée")
                # Envoie un message d'erreur au client avant de fermer
                ErrorResponse = HandshakeResponse(
                    Success=False,
                    Message="Échec du calcul de la clé partagée - clé publique invalide"
                )
                await self._SendMessage(ClientInfo, ErrorResponse.ToJson())
                return False

            # Négociation de la compression
            ClientCompression = Request.GetSupportedCompression()
            ServerCompression = ClientInfo.EncryptionHandler.GetSupportedCompression()
            SelectedCompression = NegotiateCompression(ClientCompression, ServerCompression)

            # Configure la compression sur le handler
            ClientInfo.EncryptionHandler.SetCompression(SelectedCompression)

            # Applique le niveau de compression configuré
            ClientInfo.EncryptionHandler.CompressionHandler.SetLevel(self.CompressionLevel)
            self.Logger.info(f"Compression négociée: {SelectedCompression}, niveau: {self.CompressionLevel}/10")

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
                self.Logger.error("Aucune donnée reçue lors de l'authentification")
                return False

            # Déchiffre et parse la demande
            DecryptedData = ClientInfo.EncryptionHandler.DecryptMessage(RequestData)
            if not DecryptedData:
                self.Logger.error("Impossible de déchiffrer la demande d'authentification")
                return False

            try:
                Request = MessageFactory.CreateFromJson(DecryptedData)
            except Exception as e:
                self.Logger.error(f"Impossible de parser la demande d'authentification: {e}")
                return False

            if not isinstance(Request, AuthRequest):
                self.Logger.error(f"Type de message inattendu: {type(Request).__name__} (attendu: AuthRequest)")
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

            # Authentification réussie - récupère la capacité du pipeline client
            ClientInfo.MaxConcurrentBatches = Request.GetMaxConcurrentBatches()
            self.Logger.info(f"Client {ClientInfo.ClientId} pipeline: {ClientInfo.MaxConcurrentBatches} batches max")

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
        Envoie un message à un client via le canal Control

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

    async def SendDataMessage(self, ClientId: str, Message: str, Encrypted: bool = True) -> bool:
        """
        Envoie un message à un client via le canal Data (pour les gros transferts)

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

        if not ClientInfo.IsDataConnected():
            self.Logger.error(f"Canal Data non connecté pour le client {ClientId}")
            return False

        try:
            MessageToSend = Message
            if Encrypted and ClientInfo.EncryptionHandler.IsReady():
                MessageToSend = ClientInfo.EncryptionHandler.EncryptMessage(Message)

            return await self._SendDataMessage(ClientInfo, MessageToSend)

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'envoi Data au client {ClientId}: {e}")
            return False

    async def _SendDataMessage(self, ClientInfo: 'ClientInfo', Message: str) -> bool:
        """Envoie un message via le canal Data (interne)"""
        try:
            if not ClientInfo.DataWriter:
                self.Logger.error(f"DataWriter non disponible pour {ClientInfo.ClientId}")
                return False

            # Format: taille (4 bytes) + message
            MessageBytes = Message.encode('utf-8')
            MessageSize = len(MessageBytes)
            SizeBytes = MessageSize.to_bytes(4, byteorder='big')

            self.Logger.debug(f"SendDataMessage: envoi de {MessageSize} bytes au client {ClientInfo.ClientId[:8]}...")

            ClientInfo.DataWriter.write(SizeBytes + MessageBytes)
            await ClientInfo.DataWriter.drain()

            self.Logger.debug(f"SendDataMessage: {MessageSize} bytes envoyes avec succes")
            return True

        except (ConnectionResetError, BrokenPipeError) as e:
            self.Logger.error(f"Connexion Data perdue avec {ClientInfo.ClientId}: {e}")
            return False
        except Exception as e:
            self.Logger.error(f"Erreur d'envoi Data au client {ClientInfo.ClientId}: {e}")
            return False

    async def ReceiveDataMessage(self, ClientId: str, Decrypt: bool = True, Timeout: float = None) -> Optional[str]:
        """
        Reçoit un message d'un client via le canal Data

        Args:
            ClientId: ID du client
            Decrypt: Si True, déchiffre le message
            Timeout: Timeout optionnel en secondes

        Returns:
            Message reçu (JSON) ou None
        """
        if ClientId not in self.Clients:
            self.Logger.error(f"Client {ClientId} non trouvé")
            return None

        ClientInfo = self.Clients[ClientId]

        if not ClientInfo.IsDataConnected():
            self.Logger.error(f"Canal Data non connecté pour le client {ClientId}")
            return None

        try:
            if Timeout:
                ReceivedData = await asyncio.wait_for(
                    self._ReceiveDataMessage(ClientInfo),
                    timeout=Timeout
                )
            else:
                ReceivedData = await self._ReceiveDataMessage(ClientInfo)

            if not ReceivedData:
                return None

            if Decrypt and ClientInfo.EncryptionHandler.IsReady():
                return ClientInfo.EncryptionHandler.DecryptMessage(ReceivedData)

            return ReceivedData

        except asyncio.TimeoutError:
            self.Logger.warning(f"Timeout de réception Data du client {ClientId}")
            return None
        except Exception as e:
            self.Logger.error(f"Erreur de réception Data du client {ClientId}: {e}")
            return None

    async def _ReceiveDataMessage(self, ClientInfo: 'ClientInfo') -> Optional[str]:
        """Reçoit un message via le canal Data (interne)"""
        try:
            if not ClientInfo.DataReader:
                self.Logger.error(f"DataReader non disponible pour {ClientInfo.ClientId}")
                return None

            # Lit la taille (4 bytes)
            SizeBytes = await ClientInfo.DataReader.readexactly(4)
            MessageSize = int.from_bytes(SizeBytes, byteorder='big')

            # Validation de la taille
            if MessageSize <= 0:
                self.Logger.error(f"Taille de message Data invalide: {MessageSize}")
                return None

            if MessageSize > NetworkConfig.MAX_MESSAGE_SIZE:
                self.Logger.error(f"Message Data trop grand: {MessageSize} bytes")
                return None

            # Lit le message
            MessageBytes = await ClientInfo.DataReader.readexactly(MessageSize)
            return MessageBytes.decode('utf-8')

        except asyncio.IncompleteReadError:
            self.Logger.warning(f"Connexion Data fermée par le client {ClientInfo.ClientId}")
            return None
        except (ConnectionResetError, BrokenPipeError) as e:
            self.Logger.error(f"Connexion Data perdue avec {ClientInfo.ClientId}: {e}")
            return None
        except Exception as e:
            self.Logger.error(f"Erreur de réception Data: {e}")
            return None

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
            # Validation du message
            if not Message:
                self.Logger.error(f"Tentative d'envoi d'un message vide au client {ClientInfo.ClientId}")
                return False

            # Format: taille (4 bytes) + message
            MessageBytes = Message.encode('utf-8')
            MessageSize = len(MessageBytes)
            SizeBytes = MessageSize.to_bytes(4, byteorder='big')

            ClientInfo.Writer.write(SizeBytes + MessageBytes)
            await ClientInfo.Writer.drain()

            return True

        except (ConnectionResetError, BrokenPipeError) as e:
            self.Logger.error(f"Connexion perdue avec {ClientInfo.ClientId} lors de l'envoi: {e}")
            return False
        except Exception as e:
            self.Logger.error(f"Erreur d'envoi au client {ClientInfo.ClientId}: {e}")
            return False

    async def _ReceiveMessage(self, ClientInfo: ClientInfo) -> Optional[str]:
        """Reçoit un message (interne)"""
        try:
            # Lit la taille (4 bytes)
            SizeBytes = await ClientInfo.Reader.readexactly(4)
            MessageSize = int.from_bytes(SizeBytes, byteorder='big')

            # Validation de la taille
            if MessageSize <= 0:
                self.Logger.error(f"Taille de message invalide du client {ClientInfo.ClientId}: {MessageSize}")
                return None

            # Limite de taille maximale
            if MessageSize > NetworkConfig.MAX_MESSAGE_SIZE:
                self.Logger.error(f"Message trop grand du client {ClientInfo.ClientId}: {MessageSize} bytes (max: {NetworkConfig.MAX_MESSAGE_SIZE})")
                return None

            # Lit le message
            MessageBytes = await ClientInfo.Reader.readexactly(MessageSize)
            return MessageBytes.decode('utf-8')

        except asyncio.IncompleteReadError:
            self.Logger.warning(f"Connexion fermée par le client {ClientInfo.ClientId} (lecture incomplète)")
            return None
        except (ConnectionResetError, BrokenPipeError) as e:
            self.Logger.error(f"Connexion perdue avec {ClientInfo.ClientId} lors de la réception: {e}")
            return None
        except UnicodeDecodeError as e:
            self.Logger.error(f"Données corrompues du client {ClientInfo.ClientId} (encodage UTF-8 invalide): {e}")
            return None
        except Exception as e:
            self.Logger.error(f"Erreur de réception du client {ClientInfo.ClientId}: {e}")
            return None

    async def HandleDataConnection(self, Reader: asyncio.StreamReader,
                                    Writer: asyncio.StreamWriter) -> bool:
        """
        Gère une connexion entrante sur le port Data.
        Le client doit s'identifier avec un DataChannelAuth contenant son ClientId.

        Args:
            Reader: StreamReader asyncio
            Writer: StreamWriter asyncio

        Returns:
            True si l'association a réussi
        """
        PeerName = Writer.get_extra_info('peername')
        IpAddress = PeerName[0] if PeerName else "unknown"

        self.Logger.info(f"Connexion Data entrante depuis {IpAddress}")

        try:
            # Attend le message DataChannelAuth (chiffré)
            # Le client utilise le même contexte de chiffrement que le canal Control
            SizeBytes = await asyncio.wait_for(
                Reader.readexactly(4),
                timeout=NetworkConfig.CONNECTION_TIMEOUT
            )
            MessageSize = int.from_bytes(SizeBytes, byteorder='big')

            if MessageSize <= 0 or MessageSize > NetworkConfig.MAX_MESSAGE_SIZE:
                self.Logger.error(f"Taille de message Data invalide: {MessageSize}")
                Writer.close()
                await Writer.wait_closed()
                return False

            MessageBytes = await Reader.readexactly(MessageSize)
            EncryptedData = MessageBytes.decode('utf-8')

            # Optimisation: essaie d'abord avec les clients en attente de connexion Data
            # Cela réduit la complexité de O(n) à O(p) où p << n
            ClientFound = None
            DecryptedData = None

            # Essaie d'abord avec les clients dans PendingDataConnections (O(p))
            for ClientId, ClientInfo in self.PendingDataConnections.items():
                if ClientInfo.IpAddress == IpAddress:
                    try:
                        DecryptedData = ClientInfo.EncryptionHandler.DecryptMessage(EncryptedData)
                        if DecryptedData:
                            ClientFound = ClientInfo
                            break
                    except Exception as e:
                        self.Logger.debug(f"Échec déchiffrement pour client {ClientId}: {e}")
                        continue

            # Si pas trouvé, essaie avec tous les clients (fallback pour reconnexions)
            if not ClientFound:
                for ClientId, ClientInfo in self.Clients.items():
                    if ClientInfo.IpAddress == IpAddress and ClientInfo.Authenticated:
                        try:
                            DecryptedData = ClientInfo.EncryptionHandler.DecryptMessage(EncryptedData)
                            if DecryptedData:
                                ClientFound = ClientInfo
                                break
                        except Exception as e:
                            self.Logger.debug(f"Échec déchiffrement pour client {ClientId}: {e}")
                            continue

            if not DecryptedData or not ClientFound:
                self.Logger.error(f"Impossible de déchiffrer le DataChannelAuth depuis {IpAddress}")
                Writer.close()
                await Writer.wait_closed()
                return False

            # Parse le message
            Message = MessageFactory.CreateFromJson(DecryptedData)
            if not isinstance(Message, DataChannelAuth):
                self.Logger.error(f"Message inattendu sur port Data: {type(Message).__name__}")
                Writer.close()
                await Writer.wait_closed()
                return False

            # Vérifie que le ClientId correspond
            ClaimedClientId = Message.GetClientId()
            if ClaimedClientId != ClientFound.ClientId:
                self.Logger.error(f"ClientId mismatch: {ClaimedClientId} vs {ClientFound.ClientId}")
                Writer.close()
                await Writer.wait_closed()
                return False

            # Vérifie que le client est toujours dans self.Clients
            # (Il pourrait être dans PendingDataConnections pendant le délai de grâce mais déjà déconnecté)
            if ClaimedClientId not in self.Clients:
                self.Logger.warning(f"Client {ClaimedClientId} n'est plus connecté (Control fermé pendant délai de grâce)")
                # Nettoie PendingDataConnections immédiatement
                if ClaimedClientId in self.PendingDataConnections:
                    del self.PendingDataConnections[ClaimedClientId]
                Writer.close()
                await Writer.wait_closed()
                return False

            # Retire des PendingDataConnections (connexion Data établie)
            if ClaimedClientId in self.PendingDataConnections:
                del self.PendingDataConnections[ClaimedClientId]
                self.Logger.debug(f"Client {ClaimedClientId} retiré de PendingDataConnections")

            # Association réussie
            ClientFound.SetDataConnection(Reader, Writer)
            self.Logger.info(f"Canal Data associé au client {ClientFound.ClientId}")

            # Envoie une confirmation au client
            AckMessage = DataChannelAuthResponse(Success=True)
            EncryptedAck = ClientFound.EncryptionHandler.EncryptMessage(AckMessage.ToJson())
            await self._SendDataMessage(ClientFound, EncryptedAck)
            self.Logger.debug(f"Confirmation Data envoyée au client {ClientFound.ClientId}")

            return True

        except asyncio.TimeoutError:
            self.Logger.error(f"Timeout lors de l'authentification Data depuis {IpAddress}")
            Writer.close()
            await Writer.wait_closed()
            return False
        except Exception as e:
            self.Logger.error(f"Erreur lors de la gestion de connexion Data: {e}")
            try:
                Writer.close()
                await Writer.wait_closed()
            except Exception:
                pass  # Ignorer les erreurs de fermeture lors du cleanup
            return False

    async def RemoveClient(self, ClientId: str):
        """
        Retire un client et nettoie les ressources

        Args:
            ClientId: ID du client
        """
        if ClientId not in self.Clients:
            return

        ClientInfo = self.Clients.get(ClientId)
        if not ClientInfo:
            return

        # Ne nettoie PAS immédiatement PendingDataConnections
        # Si Data n'est pas connecté, la connexion pourrait être en cours
        # Laisse un délai de grâce de 5s pour permettre à Data de se connecter
        if ClientId in self.PendingDataConnections and not ClientInfo.DataConnected:
            async def DelayedCleanup():
                await asyncio.sleep(5)
                if ClientId in self.PendingDataConnections:
                    del self.PendingDataConnections[ClientId]
                    self.Logger.debug(f"Client {ClientId} retiré de PendingDataConnections après délai")

            asyncio.create_task(DelayedCleanup())
            self.Logger.debug(f"Délai de grâce de 5s pour Data du client {ClientId}")
        elif ClientId in self.PendingDataConnections:
            # Data déjà connecté, on peut supprimer immédiatement
            del self.PendingDataConnections[ClientId]
            self.Logger.debug(f"Client {ClientId} retiré de PendingDataConnections (Data connecté)")

        # Appelle le callback de déconnexion AVANT de fermer
        # Permet de réallouer les batches assignés au client
        if self.OnClientDisconnected:
            try:
                await self.OnClientDisconnected(ClientId)
            except Exception as e:
                self.Logger.error(f"Erreur dans le callback de déconnexion: {e}")

        # Ferme la connexion Control
        try:
            ClientInfo.ControlWriter.close()
            await ClientInfo.ControlWriter.wait_closed()
        except Exception as e:
            self.Logger.error(f"Erreur lors de la fermeture de la connexion Control: {e}")

        # Ferme la connexion Data si elle existe
        if ClientInfo.DataConnected and ClientInfo.DataWriter:
            try:
                ClientInfo.DataWriter.close()
                await ClientInfo.DataWriter.wait_closed()
            except Exception as e:
                self.Logger.error(f"Erreur lors de la fermeture de la connexion Data: {e}")

        # Met à jour l'historique
        History = self.Database.GetClientHistory(ClientId)
        if History:
            History.DisconnectedAt = datetime.now()
            History.LastSeen = datetime.now()
            self.Database.UpdateClientHistory(History)

        # Retire du dictionnaire (avec vérification pour éviter KeyError)
        if ClientId in self.Clients:
            del self.Clients[ClientId]
            self.Logger.info(f"Client {ClientId} retiré")

            # Webhook: client déconnecté
            TriggerServerWebhook(
                "client_disconnected",
                client_id=ClientId,
                ip=ClientInfo.IpAddress if ClientInfo else "unknown"
            )

            # Émet un événement de déconnexion
            EmitError(
                Exception(f"Client {ClientId} déconnecté"),
                ErrorCategory.CLIENT,
                ErrorSeverity.INFO,
                "ClientManager",
                context={"client_id": ClientId, "ip_address": ClientInfo.IpAddress if ClientInfo else None},
                recoverable=True,
                suggested_action="ignore"
            )

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

    async def DisconnectClient(self, ClientId: str, Reason: str = "Déconnecté par le serveur"):
        """
        Déconnecte un client volontairement depuis le serveur.
        Envoie d'abord un message au client pour l'informer.

        Args:
            ClientId: ID du client
            Reason: Raison de la déconnexion
        """
        if ClientId not in self.Clients:
            self.Logger.warning(f"Tentative de déconnexion d'un client inexistant: {ClientId}")
            return

        try:
            # Informe le client de la déconnexion
            from shared.protocol.messages import DisconnectMessage
            DisconnectMsg = DisconnectMessage(Reason=Reason)
            await self.SendMessage(ClientId, DisconnectMsg.ToJson(), Encrypted=True)
            self.Logger.info(f"Message de déconnexion envoyé au client {ClientId}: {Reason}")
        except Exception as e:
            self.Logger.warning(f"Impossible d'envoyer le message de déconnexion au client {ClientId}: {e}")

        # Retire le client
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

                    # Skip si le heartbeat n'est pas encore activé (en attente de connexion Data)
                    if not ClientInfo.HeartbeatEnabled:
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

    def UpdateCompressionLevel(self, NewLevel: int):
        """
        Met à jour le niveau de compression pour tous les clients connectés.
        Le nouveau niveau sera utilisé pour les prochains messages envoyés.

        Args:
            NewLevel: Nouveau niveau de compression (1-10)
        """
        # Valide le niveau
        NewLevel = max(CompressionConfig.LEVEL_MIN, min(NewLevel, CompressionConfig.LEVEL_MAX))
        self.CompressionLevel = NewLevel

        # Applique à tous les clients connectés
        for ClientId, ClientInfo in self.Clients.items():
            if ClientInfo.EncryptionHandler and ClientInfo.EncryptionHandler.CompressionHandler:
                ClientInfo.EncryptionHandler.CompressionHandler.SetLevel(NewLevel)

        self.Logger.info(f"Niveau de compression mis à jour: {NewLevel}/10 (appliqué à {len(self.Clients)} clients)")
