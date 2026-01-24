"""
Gestionnaire de connexion pour le client
Gère la connexion au serveur, le handshake et l'authentification
"""

import asyncio
import json
import os
import socket
import platform
from typing import Optional, Tuple
from pathlib import Path

from shared.protocol.messages import (
    HandshakeRequest, HandshakeResponse, AuthRequest, AuthResponse,
    MessageFactory, DataChannelAuth, DataChannelAuthResponse
)
from shared.protocol.encryption import EncryptionHandler
from shared.utils.logger import GetClientLogger
from shared.utils.constants import NetworkConfig, CompressionConfig
from client.utils.performance_config import PerformanceConfigManager


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
            # Format: (onoff, keepalivetime_ms, keepaliveinterval_ms)
            # - Commence à envoyer des probes après 30s d'inactivité
            # - Envoie une probe toutes les 10s
            # Vérifie que le socket supporte ioctl (pas un TransportSocket)
            if hasattr(Sock, 'ioctl'):
                Sock.ioctl(
                    socket.SIO_KEEPALIVE_VALS,
                    (1, 30000, 10000)  # 30s idle, 10s interval
                )
                Logger.debug("✓ TCP Keepalive configuré (Windows)")
            else:
                Logger.debug("Socket wrapper détecté, configuration keepalive Windows ignorée")
        else:
            # Linux/Unix: utilise les options TCP standard
            if hasattr(socket, 'TCP_KEEPIDLE'):
                Sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)  # 30s
            if hasattr(socket, 'TCP_KEEPINTVL'):
                Sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)  # 10s
            if hasattr(socket, 'TCP_KEEPCNT'):
                Sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 6)  # 6 retries
            Logger.debug("✓ TCP Keepalive configuré (Linux/Unix)")

        # Désactive l'algorithme de Nagle pour réduire la latence
        Sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        # Augmente les buffers de réception/envoi pour les gros transferts (BatchResults avec images)
        Sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)  # 8MB (était 2MB)
        Sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8 * 1024 * 1024)  # 8MB (était 2MB)

    except Exception as e:
        Logger.warning(f"Impossible de configurer le socket: {e}")


class SavedServersWrapper:
    """Wrapper pour l'accès aux serveurs sauvegardés via attribut de classe"""

    def __init__(self):
        self._Manager = None

    def _GetManager(self):
        if self._Manager is None:
            self._Manager = SavedServersManager()
        return self._Manager

    def LoadServers(self) -> list:
        """Charge et retourne la liste des serveurs"""
        Manager = self._GetManager()
        Servers = Manager.GetAllServers()
        Result = []
        for Name, Info in Servers.items():
            Result.append({
                "name": Name,
                "host": Info.get("host", ""),
                "port": Info.get("port", 12345),
                "password": Info.get("password", "")
            })
        return Result

    def SaveServer(self, Name: str, Host: str, Port: int, Password: str = ""):
        """Sauvegarde un serveur"""
        self._GetManager().AddServer(Name, Host, Port, Password)

    def RemoveServer(self, Name: str):
        """Supprime un serveur"""
        self._GetManager().RemoveServer(Name)


class ConnectionManager:
    """Gestionnaire de connexion au serveur"""

    # Attribut de classe pour accès aux serveurs sauvegardés
    SavedServers = SavedServersWrapper()

    def __init__(self):
        """Initialise le gestionnaire de connexion"""
        self.Logger = GetClientLogger()
        self.Reader = None
        self.Writer = None
        self.EncryptionHandler = EncryptionHandler()
        self.Connected = False
        self.Authenticated = False
        self.ClientId = None
        self.ServerAddress = None
        self.ServerPort = None

    async def ConnectToServer(self, Host: str, Port: int, Password: str = "",
                              MaxConcurrentBatches: int = 2) -> bool:
        """
        Connecte au serveur et effectue le handshake + authentification

        Args:
            Host: Adresse du serveur
            Port: Port du serveur
            Password: Mot de passe (si requis)
            MaxConcurrentBatches: Capacité du pipeline client

        Returns:
            True si connexion réussie
        """
        try:
            self.Logger.info(f"Connexion au serveur {Host}:{Port}...")

            # Connexion TCP
            self.Reader, self.Writer = await asyncio.wait_for(
                asyncio.open_connection(Host, Port),
                timeout=NetworkConfig.CONNECTION_TIMEOUT
            )

            self.ServerAddress = Host
            self.ServerPort = Port
            self.Connected = True

            self.Logger.info("✓ Connexion TCP établie")

            # Configure le socket TCP pour éviter les timeouts
            ConfigureSocket(self.Writer, self.Logger)

            # Handshake
            if not await self._PerformHandshake():
                self.Logger.error("Échec du handshake")
                await self.Disconnect()
                return False

            # Authentification avec capacité du pipeline
            if not await self._Authenticate(Password, MaxConcurrentBatches):
                self.Logger.error("Échec de l'authentification")
                await self.Disconnect()
                return False

            self.Authenticated = True
            self.Logger.info(f"✓ Client authentifié (ID: {self.ClientId})")

            return True

        except asyncio.TimeoutError:
            self.Logger.error("Timeout lors de la connexion")
            return False
        except Exception as e:
            self.Logger.error(f"Erreur lors de la connexion: {e}")
            return False

    async def _PerformHandshake(self) -> bool:
        """
        Effectue le handshake avec le serveur

        Returns:
            True si succès
        """
        try:
            self.Logger.info("Handshake avec le serveur...")

            # Génère la clé publique du client
            ClientPublicKey = self.EncryptionHandler.GenerateKeyPair()

            # Récupère les algorithmes de compression supportés
            SupportedCompression = self.EncryptionHandler.GetSupportedCompression()

            # Envoie la demande de handshake avec les algos de compression
            Request = HandshakeRequest(
                PublicKey=ClientPublicKey,
                ProtocolVersion="1.0",
                SupportedCompression=SupportedCompression
            )

            await self._SendMessage(Request.ToJson())

            # Attend la réponse
            ResponseData = await asyncio.wait_for(
                self._ReceiveMessage(),
                timeout=NetworkConfig.CONNECTION_TIMEOUT
            )

            if not ResponseData:
                self.Logger.error("Aucune réponse reçue lors du handshake")
                return False

            # Parse la réponse
            try:
                Response = MessageFactory.CreateFromJson(ResponseData)
            except Exception as e:
                self.Logger.error(f"Impossible de parser la réponse du handshake: {e}")
                return False

            if not isinstance(Response, HandshakeResponse):
                self.Logger.error(f"Type de réponse inattendu: {type(Response).__name__} (attendu: HandshakeResponse)")
                return False

            if not Response.IsSuccess():
                self.Logger.error(f"Handshake refusé: {Response.Payload.get('message')}")
                return False

            # Récupère la clé publique du serveur
            ServerPublicKey = Response.GetPublicKey()

            # Calcule la clé partagée
            if not self.EncryptionHandler.ComputeSharedKey(ServerPublicKey):
                self.Logger.error("Échec du calcul de la clé partagée")
                return False

            # Configure la compression négociée
            SelectedCompression = Response.GetSelectedCompression()
            self.EncryptionHandler.SetCompression(SelectedCompression)

            # Applique le niveau de compression configuré
            PerformanceConfig = PerformanceConfigManager()
            Config = PerformanceConfig.Load()
            CompressionLevel = Config.get('compression_level', CompressionConfig.LEVEL_DEFAULT)
            self.EncryptionHandler.CompressionHandler.SetLevel(CompressionLevel)

            self.Logger.info(f"✓ Handshake réussi, compression: {SelectedCompression}, niveau: {CompressionLevel}/10")

            return True

        except asyncio.TimeoutError:
            self.Logger.error("Timeout lors du handshake")
            return False
        except Exception as e:
            self.Logger.error(f"Erreur lors du handshake: {e}")
            return False

    async def _Authenticate(self, Password: str, MaxConcurrentBatches: int = 2) -> bool:
        """
        Authentification auprès du serveur

        Args:
            Password: Mot de passe du serveur
            MaxConcurrentBatches: Capacité du pipeline client

        Returns:
            True si succès
        """
        try:
            self.Logger.info(f"Authentification (pipeline: {MaxConcurrentBatches} batches)...")

            # Crée la demande d'authentification avec la capacité du pipeline
            Request = AuthRequest(Password=Password, MaxConcurrentBatches=MaxConcurrentBatches)

            # Chiffre et envoie
            EncryptedRequest = self.EncryptionHandler.EncryptMessage(Request.ToJson())
            await self._SendMessage(EncryptedRequest)

            # Attend la réponse chiffrée
            EncryptedResponse = await asyncio.wait_for(
                self._ReceiveMessage(),
                timeout=NetworkConfig.CONNECTION_TIMEOUT
            )

            if not EncryptedResponse:
                self.Logger.error("Aucune réponse reçue lors de l'authentification")
                return False

            # Déchiffre
            DecryptedResponse = self.EncryptionHandler.DecryptMessage(EncryptedResponse)
            if not DecryptedResponse:
                self.Logger.error("Impossible de déchiffrer la réponse d'authentification")
                return False

            # Parse
            try:
                Response = MessageFactory.CreateFromJson(DecryptedResponse)
            except Exception as e:
                self.Logger.error(f"Impossible de parser la réponse d'authentification: {e}")
                return False

            if not isinstance(Response, AuthResponse):
                self.Logger.error(f"Type de réponse inattendu: {type(Response).__name__} (attendu: AuthResponse)")
                return False

            if not Response.IsSuccess():
                ErrorMsg = Response.Payload.get('message', 'Authentification refusée')
                self.Logger.error(ErrorMsg)
                return False

            # Récupère l'ID client
            self.ClientId = Response.GetClientId()

            self.Logger.info("✓ Authentification réussie")
            return True

        except asyncio.TimeoutError:
            self.Logger.error("Timeout lors de l'authentification")
            return False
        except Exception as e:
            self.Logger.error(f"Erreur lors de l'authentification: {e}")
            return False

    async def SendMessage(self, Message: str, Encrypted: bool = True) -> bool:
        """
        Envoie un message au serveur

        Args:
            Message: Message à envoyer (JSON)
            Encrypted: Si True, chiffre le message

        Returns:
            True si succès
        """
        if not self.Connected:
            self.Logger.error("Non connecté au serveur")
            return False

        try:
            MessageToSend = Message
            if Encrypted and self.EncryptionHandler.IsReady():
                MessageToSend = self.EncryptionHandler.EncryptMessage(Message)

            return await self._SendMessage(MessageToSend)

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'envoi du message: {e}")
            return False

    async def ReceiveMessage(self, Decrypt: bool = True) -> Optional[str]:
        """
        Reçoit un message du serveur

        Args:
            Decrypt: Si True, déchiffre le message

        Returns:
            Message reçu (JSON) ou None
        """
        if not self.Connected:
            self.Logger.error("Non connecté au serveur")
            return None

        try:
            ReceivedData = await self._ReceiveMessage()

            if not ReceivedData:
                return None

            if Decrypt and self.EncryptionHandler.IsReady():
                return self.EncryptionHandler.DecryptMessage(ReceivedData)

            return ReceivedData

        except Exception as e:
            self.Logger.error(f"Erreur lors de la réception du message: {e}")
            return None

    async def _SendMessage(self, Message: str) -> bool:
        """Envoie un message (interne)"""
        try:
            # Validation du message
            if not Message:
                self.Logger.error("Tentative d'envoi d'un message vide ou None")
                return False

            # Format: taille (4 bytes) + message
            MessageBytes = Message.encode('utf-8')
            MessageSize = len(MessageBytes)
            SizeBytes = MessageSize.to_bytes(4, byteorder='big')

            self.Writer.write(SizeBytes + MessageBytes)
            await self.Writer.drain()

            return True

        except (ConnectionResetError, BrokenPipeError) as e:
            self.Logger.error(f"Connexion perdue lors de l'envoi: {e}")
            self.Connected = False
            return False
        except Exception as e:
            self.Logger.error(f"Erreur d'envoi: {e}")
            return False

    async def _ReceiveMessage(self) -> Optional[str]:
        """Reçoit un message (interne)"""
        try:
            # Lit la taille (4 bytes)
            SizeBytes = await self.Reader.readexactly(4)
            MessageSize = int.from_bytes(SizeBytes, byteorder='big')

            # Validation de la taille
            if MessageSize <= 0:
                self.Logger.error(f"Taille de message invalide: {MessageSize}")
                self.Connected = False
                return None

            # Limite de taille maximale
            if MessageSize > NetworkConfig.MAX_MESSAGE_SIZE:
                self.Logger.error(f"Message trop grand: {MessageSize} bytes (max: {NetworkConfig.MAX_MESSAGE_SIZE})")
                self.Connected = False
                return None

            # Lit le message
            MessageBytes = await self.Reader.readexactly(MessageSize)
            return MessageBytes.decode('utf-8')

        except asyncio.IncompleteReadError:
            self.Logger.warning("Connexion fermée par le serveur (lecture incomplète)")
            self.Connected = False
            return None
        except (ConnectionResetError, BrokenPipeError) as e:
            self.Logger.error(f"Connexion perdue lors de la réception: {e}")
            self.Connected = False
            return None
        except UnicodeDecodeError as e:
            self.Logger.error(f"Données corrompues (encodage UTF-8 invalide): {e}")
            self.Connected = False
            return None
        except Exception as e:
            self.Logger.error(f"Erreur de réception: {e}")
            self.Connected = False
            return None

    async def Disconnect(self):
        """Déconnecte du serveur"""
        if self.Writer:
            try:
                self.Writer.close()
                await self.Writer.wait_closed()
            except Exception as e:
                self.Logger.error(f"Erreur lors de la déconnexion: {e}")

        self.Connected = False
        self.Authenticated = False
        self.ClientId = None
        self.Logger.info("Déconnecté du serveur")

    def IsConnected(self) -> bool:
        """Vérifie si connecté"""
        return self.Connected and self.Authenticated

    def GetServerInfo(self) -> Tuple[Optional[str], Optional[int]]:
        """Récupère les informations du serveur"""
        return (self.ServerAddress, self.ServerPort)


# ============================================================================
# GESTION DES SERVEURS SAUVEGARDÉS
# ============================================================================

class SavedServersManager:
    """Gestionnaire des serveurs sauvegardés"""

    def __init__(self, ConfigPath: str = None):
        """
        Initialise le gestionnaire

        Args:
            ConfigPath: Chemin du fichier de configuration
        """
        if ConfigPath:
            self.ConfigPath = ConfigPath
        else:
            # Utilise le répertoire utilisateur
            ConfigDir = os.path.join(Path.home(), '.upscaling_client')
            os.makedirs(ConfigDir, exist_ok=True)
            self.ConfigPath = os.path.join(ConfigDir, 'servers.json')

        self.Servers = self._LoadServers()

    def _LoadServers(self) -> dict:
        """Charge les serveurs sauvegardés"""
        if os.path.exists(self.ConfigPath):
            try:
                with open(self.ConfigPath, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Erreur lors du chargement des serveurs: {e}")
                return {}
        return {}

    def _SaveServers(self):
        """Sauvegarde les serveurs"""
        try:
            with open(self.ConfigPath, 'w') as f:
                json.dump(self.Servers, f, indent=2)
        except Exception as e:
            print(f"Erreur lors de la sauvegarde des serveurs: {e}")

    def AddServer(self, Name: str, Host: str, Port: int, Password: str = ""):
        """
        Ajoute un serveur

        Args:
            Name: Nom du serveur
            Host: Adresse
            Port: Port
            Password: Mot de passe (optionnel)
        """
        self.Servers[Name] = {
            "host": Host,
            "port": Port,
            "password": Password
        }
        self._SaveServers()

    def GetServer(self, Name: str) -> Optional[dict]:
        """
        Récupère un serveur

        Args:
            Name: Nom du serveur

        Returns:
            Dictionnaire serveur ou None
        """
        return self.Servers.get(Name)

    def RemoveServer(self, Name: str):
        """
        Retire un serveur

        Args:
            Name: Nom du serveur
        """
        if Name in self.Servers:
            del self.Servers[Name]
            self._SaveServers()

    def ListServers(self) -> list:
        """
        Liste tous les serveurs

        Returns:
            Liste des noms de serveurs
        """
        return list(self.Servers.keys())

    def GetAllServers(self) -> dict:
        """Récupère tous les serveurs"""
        return self.Servers.copy()


# ============================================================================
# DUAL CONNECTION MANAGER (Architecture dual-port)
# ============================================================================

class DualConnectionManager:
    """
    Gestionnaire de connexion dual-port (Control + Data).
    Le canal Control gère handshake/heartbeat/status.
    Le canal Data gère les transferts de batches.
    """

    # Attribut de classe pour accès aux serveurs sauvegardés (compatibilité)
    SavedServers = SavedServersWrapper()

    def __init__(self):
        """Initialise le gestionnaire de connexion dual-port"""
        self.Logger = GetClientLogger()

        # Connexion Control (handshake, heartbeat, status)
        self.ControlReader = None
        self.ControlWriter = None
        self.ControlEncryption = EncryptionHandler()
        self.ControlConnected = False

        # Connexion Data (transferts de batches)
        self.DataReader = None
        self.DataWriter = None
        self.DataEncryption = EncryptionHandler()
        self.DataConnected = False

        # État global
        self.Authenticated = False
        self.ClientId = None
        self.ServerAddress = None
        self.ControlPort = None
        self.DataPort = None
        self.Password = None  # Stockage du mot de passe pour la reconnexion
        self.MaxConcurrentBatches = 2  # Capacité du pipeline (stocké pour reconnexion)

    async def ConnectToDualPorts(self, Host: str, ControlPort: int, DataPort: int,
                                  Password: str = "", MaxConcurrentBatches: int = 2) -> bool:
        """
        Connecte aux deux ports du serveur (Control + Data)

        Args:
            Host: Adresse du serveur
            ControlPort: Port de contrôle (handshake, heartbeat)
            DataPort: Port de données (batches)
            Password: Mot de passe (si requis)
            MaxConcurrentBatches: Capacité du pipeline client

        Returns:
            True si les deux connexions sont établies
        """
        try:
            self.ServerAddress = Host
            self.ControlPort = ControlPort
            self.DataPort = DataPort
            self.Password = Password  # Stocke le mot de passe pour la reconnexion
            self.MaxConcurrentBatches = MaxConcurrentBatches  # Stocke pour la reconnexion

            # 1. Connexion au port Control avec handshake complet
            self.Logger.info(f"Connexion au port Control {Host}:{ControlPort}...")
            if not await self._ConnectControl(Host, ControlPort, Password, MaxConcurrentBatches):
                return False

            # 2. Connexion au port Data et authentification
            self.Logger.info(f"Connexion au port Data {Host}:{DataPort}...")
            if not await self._ConnectData(Host, DataPort):
                # Ferme la connexion Control si Data échoue
                await self._DisconnectControl()
                return False

            self.Logger.info(f"✓ Connexion dual-port établie (Control: {ControlPort}, Data: {DataPort})")
            return True

        except Exception as e:
            self.Logger.error(f"Erreur lors de la connexion dual-port: {e}")
            await self.Disconnect()
            return False

    async def _ConnectControl(self, Host: str, Port: int, Password: str,
                               MaxConcurrentBatches: int = 2) -> bool:
        """Établit la connexion Control avec handshake et authentification"""
        try:
            # Connexion TCP Control
            self.ControlReader, self.ControlWriter = await asyncio.wait_for(
                asyncio.open_connection(Host, Port),
                timeout=NetworkConfig.CONNECTION_TIMEOUT
            )
            self.ControlConnected = True
            self.Logger.info("✓ Connexion TCP Control établie")

            # Configure le socket TCP pour éviter les timeouts
            ConfigureSocket(self.ControlWriter, self.Logger)

            # Handshake
            if not await self._PerformHandshake():
                self.Logger.error("Échec du handshake Control")
                return False

            # Authentification (inclut la capacité du pipeline)
            if not await self._Authenticate(Password, MaxConcurrentBatches):
                self.Logger.error("Échec de l'authentification")
                return False

            self.Authenticated = True
            self.Logger.info(f"✓ Client authentifié (ID: {self.ClientId})")

            return True

        except asyncio.TimeoutError:
            self.Logger.error("Timeout connexion Control")
            return False
        except Exception as e:
            self.Logger.error(f"Erreur connexion Control: {e}")
            return False

    async def _ConnectData(self, Host: str, Port: int) -> bool:
        """Établit la connexion Data et s'authentifie avec DataChannelAuth"""
        try:
            # Connexion TCP Data
            self.DataReader, self.DataWriter = await asyncio.wait_for(
                asyncio.open_connection(Host, Port),
                timeout=NetworkConfig.CONNECTION_TIMEOUT
            )
            self.Logger.info("✓ Connexion TCP Data établie")

            # Configure le socket TCP pour éviter les timeouts
            ConfigureSocket(self.DataWriter, self.Logger)

            # Importe le contexte de chiffrement depuis Control
            Context = self.ControlEncryption.ExportEncryptionContext()
            self.DataEncryption.ImportEncryptionContext(Context)
            self.Logger.info("✓ Contexte de chiffrement importé sur Data")

            # Envoie DataChannelAuth pour s'identifier
            AuthMessage = DataChannelAuth(self.ClientId)
            EncryptedAuth = self.DataEncryption.EncryptMessage(AuthMessage.ToJson())

            # Envoie avec préfixe de taille
            MessageBytes = EncryptedAuth.encode('utf-8')
            MessageSize = len(MessageBytes)
            SizeBytes = MessageSize.to_bytes(4, byteorder='big')

            self.DataWriter.write(SizeBytes + MessageBytes)
            await self.DataWriter.drain()
            self.Logger.info("✓ Authentification Data envoyée")

            # Attend la confirmation du serveur
            # NOTE: On ne peut pas utiliser ReceiveDataMessage() ici car DataConnected n'est pas encore True
            # Il faut lire directement depuis le DataReader
            try:
                SizeBytes = await asyncio.wait_for(
                    self.DataReader.readexactly(4),
                    timeout=10
                )
                ResponseSize = int.from_bytes(SizeBytes, byteorder='big')

                if ResponseSize <= 0 or ResponseSize > NetworkConfig.MAX_MESSAGE_SIZE:
                    self.Logger.error("Taille de réponse Data invalide")
                    return False

                ResponseBytes = await self.DataReader.readexactly(ResponseSize)
                EncryptedResponse = ResponseBytes.decode('utf-8')
                ResponseData = self.DataEncryption.DecryptMessage(EncryptedResponse)

            except asyncio.TimeoutError:
                self.Logger.error("Timeout en attente de confirmation Data")
                return False
            except Exception as e:
                self.Logger.error(f"Erreur lors de la réception de confirmation Data: {e}")
                return False

            if not ResponseData:
                self.Logger.error("Pas de réponse du serveur pour Data association")
                return False

            Response = MessageFactory.CreateFromJson(ResponseData)
            if not isinstance(Response, DataChannelAuthResponse) or not Response.IsSuccess():
                ErrorMsg = Response.GetErrorMessage() if isinstance(Response, DataChannelAuthResponse) else "Type de réponse invalide"
                self.Logger.error(f"Data association échouée: {ErrorMsg}")
                return False

            self.DataConnected = True
            self.Logger.info("✓ Canal Data confirmé par le serveur")

            return True

        except asyncio.TimeoutError:
            self.Logger.error("Timeout connexion Data")
            return False
        except Exception as e:
            self.Logger.error(f"Erreur connexion Data: {e}")
            return False

    async def _PerformHandshake(self) -> bool:
        """Effectue le handshake sur le canal Control"""
        try:
            self.Logger.info("Handshake avec le serveur...")

            # Génère la clé publique
            ClientPublicKey = self.ControlEncryption.GenerateKeyPair()
            SupportedCompression = self.ControlEncryption.GetSupportedCompression()

            Request = HandshakeRequest(
                PublicKey=ClientPublicKey,
                ProtocolVersion="1.0",
                SupportedCompression=SupportedCompression
            )

            await self._SendControlMessage(Request.ToJson(), Encrypted=False)

            # Attend la réponse
            ResponseData = await asyncio.wait_for(
                self._ReceiveControlMessage(Decrypt=False),
                timeout=NetworkConfig.CONNECTION_TIMEOUT
            )

            if not ResponseData:
                return False

            Response = MessageFactory.CreateFromJson(ResponseData)
            if not isinstance(Response, HandshakeResponse) or not Response.IsSuccess():
                self.Logger.error(f"Handshake refusé: {Response.Payload.get('message', '')}")
                return False

            # Configure la clé partagée
            ServerPublicKey = Response.GetPublicKey()
            if not self.ControlEncryption.ComputeSharedKey(ServerPublicKey):
                return False

            # Configure la compression
            SelectedCompression = Response.GetSelectedCompression()
            self.ControlEncryption.SetCompression(SelectedCompression)

            # Applique le niveau de compression
            PerformanceConfig = PerformanceConfigManager()
            Config = PerformanceConfig.Load()
            CompressionLevel = Config.get('compression_level', CompressionConfig.LEVEL_DEFAULT)
            self.ControlEncryption.CompressionHandler.SetLevel(CompressionLevel)

            self.Logger.info(f"✓ Handshake réussi, compression: {SelectedCompression}")
            return True

        except Exception as e:
            self.Logger.error(f"Erreur handshake: {e}")
            return False

    async def _Authenticate(self, Password: str, MaxConcurrentBatches: int = 2) -> bool:
        """Authentification sur le canal Control"""
        try:
            self.Logger.info(f"Authentification (pipeline: {MaxConcurrentBatches} batches)...")

            Request = AuthRequest(Password=Password, MaxConcurrentBatches=MaxConcurrentBatches)
            await self._SendControlMessage(Request.ToJson(), Encrypted=True)

            EncryptedResponse = await asyncio.wait_for(
                self._ReceiveControlMessage(Decrypt=False),
                timeout=NetworkConfig.CONNECTION_TIMEOUT
            )

            if not EncryptedResponse:
                return False

            DecryptedResponse = self.ControlEncryption.DecryptMessage(EncryptedResponse)
            Response = MessageFactory.CreateFromJson(DecryptedResponse)

            if not isinstance(Response, AuthResponse) or not Response.IsSuccess():
                self.Logger.error(Response.Payload.get('message', 'Authentification refusée'))
                return False

            self.ClientId = Response.GetClientId()
            self.Logger.info("✓ Authentification réussie")
            return True

        except Exception as e:
            self.Logger.error(f"Erreur authentification: {e}")
            return False

    async def SendControlMessage(self, Message: str, Encrypted: bool = True) -> bool:
        """Envoie un message via le canal Control"""
        return await self._SendControlMessage(Message, Encrypted)

    async def _SendControlMessage(self, Message: str, Encrypted: bool = True) -> bool:
        """Envoie un message via Control (interne)"""
        if not self.ControlConnected:
            return False

        try:
            MessageToSend = Message
            if Encrypted and self.ControlEncryption.IsReady():
                MessageToSend = self.ControlEncryption.EncryptMessage(Message)

            MessageBytes = MessageToSend.encode('utf-8')
            MessageSize = len(MessageBytes)
            SizeBytes = MessageSize.to_bytes(4, byteorder='big')

            self.ControlWriter.write(SizeBytes + MessageBytes)
            await self.ControlWriter.drain()
            return True

        except Exception as e:
            self.Logger.error(f"Erreur envoi Control: {e}")
            self.ControlConnected = False
            return False

    async def ReceiveControlMessage(self, Decrypt: bool = True) -> Optional[str]:
        """Reçoit un message via le canal Control"""
        return await self._ReceiveControlMessage(Decrypt)

    async def _ReceiveControlMessage(self, Decrypt: bool = True) -> Optional[str]:
        """Reçoit un message via Control (interne)"""
        if not self.ControlConnected:
            return None

        try:
            SizeBytes = await self.ControlReader.readexactly(4)
            MessageSize = int.from_bytes(SizeBytes, byteorder='big')

            if MessageSize <= 0 or MessageSize > NetworkConfig.MAX_MESSAGE_SIZE:
                return None

            MessageBytes = await self.ControlReader.readexactly(MessageSize)
            ReceivedData = MessageBytes.decode('utf-8')

            if Decrypt and self.ControlEncryption.IsReady():
                return self.ControlEncryption.DecryptMessage(ReceivedData)

            return ReceivedData

        except Exception as e:
            self.Logger.error(f"Erreur réception Control: {e}")
            self.ControlConnected = False
            return None

    async def SendDataMessage(self, Message: str, Encrypted: bool = True) -> bool:
        """Envoie un message via le canal Data"""
        if not self.DataConnected:
            self.Logger.error("Canal Data non connecté")
            return False

        try:
            MessageToSend = Message
            if Encrypted and self.DataEncryption.IsReady():
                MessageToSend = self.DataEncryption.EncryptMessage(Message)

            MessageBytes = MessageToSend.encode('utf-8')
            MessageSize = len(MessageBytes)
            SizeBytes = MessageSize.to_bytes(4, byteorder='big')

            self.DataWriter.write(SizeBytes + MessageBytes)
            await self.DataWriter.drain()
            return True

        except Exception as e:
            self.Logger.error(f"Erreur envoi Data: {e}")
            self.DataConnected = False
            return False

    async def ReceiveDataMessage(self, Decrypt: bool = True, Timeout: float = None) -> Optional[str]:
        """Recoit un message via le canal Data"""
        if not self.DataConnected:
            self.Logger.warning("ReceiveDataMessage: canal Data non connecte")
            return None

        try:
            if Timeout:
                SizeBytes = await asyncio.wait_for(
                    self.DataReader.readexactly(4),
                    timeout=Timeout
                )
            else:
                SizeBytes = await self.DataReader.readexactly(4)

            MessageSize = int.from_bytes(SizeBytes, byteorder='big')
            self.Logger.debug(f"ReceiveDataMessage: taille annoncee = {MessageSize} bytes")

            if MessageSize <= 0 or MessageSize > NetworkConfig.MAX_MESSAGE_SIZE:
                self.Logger.error(f"ReceiveDataMessage: taille invalide ({MessageSize}), max={NetworkConfig.MAX_MESSAGE_SIZE}")
                return None

            self.Logger.debug(f"ReceiveDataMessage: lecture de {MessageSize} bytes...")
            MessageBytes = await self.DataReader.readexactly(MessageSize)
            self.Logger.debug(f"ReceiveDataMessage: {len(MessageBytes)} bytes recus")

            ReceivedData = MessageBytes.decode('utf-8')

            if Decrypt and self.DataEncryption.IsReady():
                DecryptedData = self.DataEncryption.DecryptMessage(ReceivedData)
                if DecryptedData:
                    self.Logger.debug(f"ReceiveDataMessage: message dechiffre ({len(DecryptedData)} chars)")
                else:
                    self.Logger.error("ReceiveDataMessage: echec du dechiffrement")
                return DecryptedData

            return ReceivedData

        except asyncio.TimeoutError:
            return None
        except asyncio.IncompleteReadError as e:
            self.Logger.error(f"ReceiveDataMessage: lecture incomplete - attendu {e.expected} bytes, recu {len(e.partial)} bytes")
            self.DataConnected = False
            return None
        except Exception as e:
            self.Logger.error(f"Erreur reception Data: {e}")
            self.DataConnected = False
            return None

    async def _DisconnectControl(self):
        """Ferme la connexion Control"""
        if self.ControlWriter:
            try:
                self.ControlWriter.close()
                await self.ControlWriter.wait_closed()
            except Exception:
                pass  # Ignorer les erreurs de fermeture lors de la déconnexion
        self.ControlConnected = False

    async def _DisconnectData(self):
        """Ferme la connexion Data"""
        if self.DataWriter:
            try:
                self.DataWriter.close()
                await self.DataWriter.wait_closed()
            except Exception:
                pass  # Ignorer les erreurs de fermeture lors de la déconnexion
        self.DataConnected = False

    async def Disconnect(self):
        """Déconnecte les deux canaux"""
        await self._DisconnectControl()
        await self._DisconnectData()
        self.Authenticated = False
        self.ClientId = None
        self.Logger.info("Déconnecté du serveur (dual-port)")

    def IsConnected(self) -> bool:
        """Vérifie si connecté (les deux canaux)"""
        return self.ControlConnected and self.DataConnected and self.Authenticated

    def IsControlConnected(self) -> bool:
        """Vérifie si le canal Control est connecté"""
        return self.ControlConnected and self.Authenticated

    def IsDataConnected(self) -> bool:
        """Vérifie si le canal Data est connecté"""
        return self.DataConnected

    def GetServerInfo(self):
        """Récupère les informations du serveur"""
        return (self.ServerAddress, self.ControlPort, self.DataPort)

    async def ReconnectWithRetry(self, MaxAttempts: int = NetworkConfig.RECONNECT_INFINITE,
                                  OnAttempt=None) -> bool:
        """
        Tente de se reconnecter avec backoff exponentiel

        Args:
            MaxAttempts: Nombre maximum de tentatives (-1 = infini)
            OnAttempt: Callback appelé avant chaque tentative (attempt_number, delay)

        Returns:
            True si reconnexion réussie
        """
        if not self.ServerAddress or not self.ControlPort or not self.Password:
            self.Logger.error("Informations de connexion manquantes pour la reconnexion")
            return False

        Attempt = 0
        while True:
            Attempt += 1

            # Vérifie si on a atteint le maximum de tentatives
            if MaxAttempts != NetworkConfig.RECONNECT_INFINITE and Attempt > MaxAttempts:
                self.Logger.error(f"Échec de la reconnexion après {MaxAttempts} tentatives")
                return False

            # Calcule le délai avec backoff exponentiel
            if Attempt == 1:
                Delay = 0  # Première tentative immédiate
            else:
                Delay = min(
                    NetworkConfig.RECONNECT_BASE_DELAY * (2 ** (Attempt - 2)),
                    NetworkConfig.RECONNECT_MAX_DELAY
                )

            # Notifie via callback
            if OnAttempt:
                try:
                    OnAttempt(Attempt, Delay)
                except Exception as e:
                    self.Logger.error(f"Erreur dans callback OnAttempt: {e}")

            # Attend avant de réessayer (sauf première tentative)
            if Delay > 0:
                self.Logger.info(f"Tentative de reconnexion #{Attempt} dans {Delay}s...")
                await asyncio.sleep(Delay)
            else:
                self.Logger.info(f"Tentative de reconnexion #{Attempt}...")

            # Ferme les connexions existantes
            await self.Disconnect()

            # Tente la reconnexion
            try:
                Success = await self.ConnectToDualPorts(
                    self.ServerAddress,
                    self.ControlPort,
                    self.DataPort,
                    self.Password,
                    self.MaxConcurrentBatches
                )

                if Success:
                    self.Logger.info(f"✓ Reconnexion réussie après {Attempt} tentative(s)")
                    return True
                else:
                    self.Logger.warning(f"✗ Tentative #{Attempt} échouée")

            except Exception as e:
                self.Logger.warning(f"✗ Tentative #{Attempt} échouée: {e}")

            # Continue la boucle pour réessayer
