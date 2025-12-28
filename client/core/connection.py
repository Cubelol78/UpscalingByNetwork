"""
Gestionnaire de connexion pour le client
Gère la connexion au serveur, le handshake et l'authentification
"""

import asyncio
import json
import os
from typing import Optional, Tuple
from pathlib import Path

from shared.protocol.messages import (
    HandshakeRequest, HandshakeResponse, AuthRequest, AuthResponse,
    MessageFactory
)
from shared.protocol.encryption import EncryptionHandler
from shared.utils.logger import GetClientLogger
from shared.utils.constants import NetworkConfig


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

    async def ConnectToServer(self, Host: str, Port: int, Password: str = "") -> bool:
        """
        Connecte au serveur et effectue le handshake + authentification

        Args:
            Host: Adresse du serveur
            Port: Port du serveur
            Password: Mot de passe (si requis)

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

            # Handshake
            if not await self._PerformHandshake():
                self.Logger.error("Échec du handshake")
                await self.Disconnect()
                return False

            # Authentification
            if not await self._Authenticate(Password):
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

            # Envoie la demande de handshake
            Request = HandshakeRequest(
                PublicKey=ClientPublicKey,
                ProtocolVersion="1.0"
            )

            await self._SendMessage(Request.ToJson())

            # Attend la réponse
            ResponseData = await asyncio.wait_for(
                self._ReceiveMessage(),
                timeout=NetworkConfig.CONNECTION_TIMEOUT
            )

            if not ResponseData:
                return False

            # Parse la réponse
            Response = MessageFactory.CreateFromJson(ResponseData)

            if not isinstance(Response, HandshakeResponse):
                self.Logger.error("Réponse de handshake invalide")
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

            self.Logger.info("✓ Handshake réussi, clé partagée établie")
            return True

        except asyncio.TimeoutError:
            self.Logger.error("Timeout lors du handshake")
            return False
        except Exception as e:
            self.Logger.error(f"Erreur lors du handshake: {e}")
            return False

    async def _Authenticate(self, Password: str) -> bool:
        """
        Authentification auprès du serveur

        Args:
            Password: Mot de passe du serveur

        Returns:
            True si succès
        """
        try:
            self.Logger.info("Authentification...")

            # Crée la demande d'authentification
            Request = AuthRequest(Password=Password)

            # Chiffre et envoie
            EncryptedRequest = self.EncryptionHandler.EncryptMessage(Request.ToJson())
            await self._SendMessage(EncryptedRequest)

            # Attend la réponse chiffrée
            EncryptedResponse = await asyncio.wait_for(
                self._ReceiveMessage(),
                timeout=NetworkConfig.CONNECTION_TIMEOUT
            )

            if not EncryptedResponse:
                return False

            # Déchiffre
            DecryptedResponse = self.EncryptionHandler.DecryptMessage(EncryptedResponse)
            if not DecryptedResponse:
                self.Logger.error("Impossible de déchiffrer la réponse d'authentification")
                return False

            # Parse
            Response = MessageFactory.CreateFromJson(DecryptedResponse)

            if not isinstance(Response, AuthResponse):
                self.Logger.error("Réponse d'authentification invalide")
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
            # Format: taille (4 bytes) + message
            MessageBytes = Message.encode('utf-8')
            MessageSize = len(MessageBytes)
            SizeBytes = MessageSize.to_bytes(4, byteorder='big')

            self.Writer.write(SizeBytes + MessageBytes)
            await self.Writer.drain()

            return True

        except Exception as e:
            self.Logger.error(f"Erreur d'envoi: {e}")
            return False

    async def _ReceiveMessage(self) -> Optional[str]:
        """Reçoit un message (interne)"""
        try:
            # Lit la taille (4 bytes)
            SizeBytes = await self.Reader.readexactly(4)
            MessageSize = int.from_bytes(SizeBytes, byteorder='big')

            # Limite de taille
            if MessageSize > NetworkConfig.MAX_MESSAGE_SIZE:
                self.Logger.error(f"Message trop grand: {MessageSize} bytes")
                return None

            # Lit le message
            MessageBytes = await self.Reader.readexactly(MessageSize)
            return MessageBytes.decode('utf-8')

        except asyncio.IncompleteReadError:
            self.Logger.warning("Connexion fermée par le serveur")
            self.Connected = False
            return None
        except Exception as e:
            self.Logger.error(f"Erreur de réception: {e}")
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
