"""
Gestionnaire de réseau pour le serveur
Permet le rebind dynamique du listener TCP sans perdre les clients connectés
"""

import asyncio
from typing import Callable, Optional
from shared.utils.logger import GetModuleLogger


class NetworkManager:
    """
    Gère le listener TCP du serveur.
    Permet de changer l'IP/Port à chaud sans déconnecter les clients existants.
    """

    def __init__(self, Host: str, Port: int):
        """
        Initialise le gestionnaire de réseau

        Args:
            Host: Adresse IP d'écoute
            Port: Port d'écoute
        """
        self.Host = Host
        self.Port = Port
        self.Server: Optional[asyncio.Server] = None
        self.ConnectionHandler: Optional[Callable] = None
        self.AcceptingConnections = True
        self.Logger = GetModuleLogger("NetworkManager")

    async def Start(self, ConnectionHandler: Callable) -> bool:
        """
        Démarre le listener TCP

        Args:
            ConnectionHandler: Fonction async appelée pour chaque nouvelle connexion
                              Signature: async def handler(reader, writer)

        Returns:
            True si succès
        """
        try:
            self.ConnectionHandler = ConnectionHandler

            self.Server = await asyncio.start_server(
                self._FilteredHandler,
                self.Host,
                self.Port
            )

            self.AcceptingConnections = True
            self.Logger.info(f"Listener TCP demarr sur {self.Host}:{self.Port}")
            return True

        except OSError as e:
            self.Logger.error(f"Impossible de bind sur {self.Host}:{self.Port}: {e}")
            return False
        except Exception as e:
            self.Logger.error(f"Erreur lors du demarrage du listener: {e}")
            return False

    async def _FilteredHandler(self, Reader: asyncio.StreamReader,
                                Writer: asyncio.StreamWriter):
        """
        Handler filtré qui refuse les connexions si AcceptingConnections est False

        Args:
            Reader: StreamReader asyncio
            Writer: StreamWriter asyncio
        """
        if not self.AcceptingConnections:
            # Refuse la connexion proprement
            PeerName = Writer.get_extra_info('peername')
            self.Logger.warning(f"Connexion refusee de {PeerName} (rebind en cours)")
            Writer.close()
            await Writer.wait_closed()
            return

        # Délègue au handler réel
        if self.ConnectionHandler:
            await self.ConnectionHandler(Reader, Writer)

    async def Rebind(self, NewHost: str, NewPort: int) -> bool:
        """
        Rebind le listener sur une nouvelle adresse sans perdre les clients connectés.

        Le processus:
        1. Refuse temporairement les nouvelles connexions
        2. Démarre un nouveau listener sur la nouvelle adresse
        3. Ferme l'ancien listener (les clients existants ne sont pas affectés)
        4. Active le nouveau listener

        Args:
            NewHost: Nouvelle adresse IP
            NewPort: Nouveau port

        Returns:
            True si succès, False sinon (ancien listener reste actif)
        """
        if not self.Server:
            self.Logger.error("Aucun listener actif pour rebind")
            return False

        self.Logger.info(f"Rebind du listener: {self.Host}:{self.Port} -> {NewHost}:{NewPort}")

        # Étape 1: Refuse temporairement les nouvelles connexions
        self.AcceptingConnections = False
        self.Logger.info("Nouvelles connexions temporairement refusees")

        try:
            # Étape 2: Démarre le nouveau listener
            NewServer = await asyncio.start_server(
                self._FilteredHandler,
                NewHost,
                NewPort
            )

            self.Logger.info(f"Nouveau listener demarre sur {NewHost}:{NewPort}")

            # Étape 3: Ferme l'ancien listener
            # Note: Cela ne ferme PAS les sockets des clients déjà connectés
            OldServer = self.Server
            OldServer.close()
            await OldServer.wait_closed()
            self.Logger.info(f"Ancien listener ferme ({self.Host}:{self.Port})")

            # Étape 4: Active le nouveau listener
            self.Server = NewServer
            self.Host = NewHost
            self.Port = NewPort
            self.AcceptingConnections = True

            self.Logger.info(f"Rebind reussi! Nouveau listener actif sur {NewHost}:{NewPort}")
            return True

        except OSError as e:
            # Échec du bind (port déjà utilisé, etc.)
            self.Logger.error(f"Echec du rebind sur {NewHost}:{NewPort}: {e}")
            # Réactive l'ancien listener
            self.AcceptingConnections = True
            self.Logger.info("Ancien listener reactiv")
            return False

        except Exception as e:
            self.Logger.error(f"Erreur lors du rebind: {e}")
            # Tente de réactiver l'ancien listener
            self.AcceptingConnections = True
            return False

    async def Stop(self):
        """Arrête le listener TCP"""
        if self.Server:
            self.AcceptingConnections = False
            self.Server.close()
            await self.Server.wait_closed()
            self.Logger.info("Listener TCP arret")
            self.Server = None

    def GetAddress(self) -> tuple:
        """
        Retourne l'adresse actuelle du listener

        Returns:
            Tuple (host, port)
        """
        return (self.Host, self.Port)

    def IsRunning(self) -> bool:
        """
        Vérifie si le listener est actif

        Returns:
            True si le listener est actif
        """
        return self.Server is not None and self.Server.is_serving()

    def IsAcceptingConnections(self) -> bool:
        """
        Vérifie si le listener accepte les nouvelles connexions

        Returns:
            True si les nouvelles connexions sont acceptées
        """
        return self.AcceptingConnections and self.IsRunning()


class DualNetworkManager:
    """
    Gère deux listeners TCP: Control (handshake/heartbeat) et Data (transferts de batches).
    Permet de changer l'IP/Ports à chaud sans déconnecter les clients existants.
    """

    def __init__(self, Host: str, ControlPort: int, DataPort: int):
        """
        Initialise le gestionnaire de réseau dual-port

        Args:
            Host: Adresse IP d'écoute
            ControlPort: Port de contrôle (handshake, heartbeat, status)
            DataPort: Port de données (transferts de batches)
        """
        self.Host = Host
        self.ControlPort = ControlPort
        self.DataPort = DataPort

        self.ControlServer: Optional[asyncio.Server] = None
        self.DataServer: Optional[asyncio.Server] = None

        self.ControlHandler: Optional[Callable] = None
        self.DataHandler: Optional[Callable] = None

        self.AcceptingConnections = True
        self.Logger = GetModuleLogger("DualNetworkManager")

    async def Start(self, ControlHandler: Callable, DataHandler: Callable) -> bool:
        """
        Démarre les deux listeners TCP

        Args:
            ControlHandler: Handler pour le port de contrôle
                           Signature: async def handler(reader, writer)
            DataHandler: Handler pour le port de données
                        Signature: async def handler(reader, writer)

        Returns:
            True si les deux listeners démarrent avec succès
        """
        try:
            self.ControlHandler = ControlHandler
            self.DataHandler = DataHandler

            # Démarre le listener Control
            self.ControlServer = await asyncio.start_server(
                self._FilteredControlHandler,
                self.Host,
                self.ControlPort
            )
            self.Logger.info(f"Control listener démarré sur {self.Host}:{self.ControlPort}")

            # Démarre le listener Data
            self.DataServer = await asyncio.start_server(
                self._FilteredDataHandler,
                self.Host,
                self.DataPort
            )
            self.Logger.info(f"Data listener démarré sur {self.Host}:{self.DataPort}")

            self.AcceptingConnections = True
            return True

        except OSError as e:
            self.Logger.error(f"Impossible de bind: {e}")
            # Nettoie si un des deux a démarré
            await self._Cleanup()
            return False
        except Exception as e:
            self.Logger.error(f"Erreur lors du démarrage des listeners: {e}")
            await self._Cleanup()
            return False

    async def _Cleanup(self):
        """Nettoie les serveurs partiellement démarrés"""
        if self.ControlServer:
            self.ControlServer.close()
            await self.ControlServer.wait_closed()
            self.ControlServer = None
        if self.DataServer:
            self.DataServer.close()
            await self.DataServer.wait_closed()
            self.DataServer = None

    async def _FilteredControlHandler(self, Reader: asyncio.StreamReader,
                                       Writer: asyncio.StreamWriter):
        """Handler filtré pour le port Control"""
        if not self.AcceptingConnections:
            PeerName = Writer.get_extra_info('peername')
            self.Logger.warning(f"Connexion Control refusée de {PeerName} (rebind en cours)")
            Writer.close()
            await Writer.wait_closed()
            return

        if self.ControlHandler:
            await self.ControlHandler(Reader, Writer)

    async def _FilteredDataHandler(self, Reader: asyncio.StreamReader,
                                    Writer: asyncio.StreamWriter):
        """Handler filtré pour le port Data"""
        if not self.AcceptingConnections:
            PeerName = Writer.get_extra_info('peername')
            self.Logger.warning(f"Connexion Data refusée de {PeerName} (rebind en cours)")
            Writer.close()
            await Writer.wait_closed()
            return

        if self.DataHandler:
            await self.DataHandler(Reader, Writer)

    async def Rebind(self, NewHost: str, NewControlPort: int, NewDataPort: int) -> bool:
        """
        Rebind les deux listeners sur de nouvelles adresses.

        Args:
            NewHost: Nouvelle adresse IP
            NewControlPort: Nouveau port de contrôle
            NewDataPort: Nouveau port de données

        Returns:
            True si succès, False sinon (anciens listeners restent actifs)
        """
        if not self.ControlServer or not self.DataServer:
            self.Logger.error("Aucun listener actif pour rebind")
            return False

        self.Logger.info(f"Rebind: {self.Host}:{self.ControlPort}/{self.DataPort} -> {NewHost}:{NewControlPort}/{NewDataPort}")

        # Refuse temporairement les nouvelles connexions
        self.AcceptingConnections = False
        self.Logger.info("Nouvelles connexions temporairement refusées")

        try:
            # Démarre les nouveaux listeners
            NewControlServer = await asyncio.start_server(
                self._FilteredControlHandler,
                NewHost,
                NewControlPort
            )
            self.Logger.info(f"Nouveau Control listener démarré sur {NewHost}:{NewControlPort}")

            NewDataServer = await asyncio.start_server(
                self._FilteredDataHandler,
                NewHost,
                NewDataPort
            )
            self.Logger.info(f"Nouveau Data listener démarré sur {NewHost}:{NewDataPort}")

            # Ferme les anciens listeners
            OldControlServer = self.ControlServer
            OldDataServer = self.DataServer

            OldControlServer.close()
            await OldControlServer.wait_closed()
            OldDataServer.close()
            await OldDataServer.wait_closed()
            self.Logger.info(f"Anciens listeners fermés")

            # Active les nouveaux listeners
            self.ControlServer = NewControlServer
            self.DataServer = NewDataServer
            self.Host = NewHost
            self.ControlPort = NewControlPort
            self.DataPort = NewDataPort
            self.AcceptingConnections = True

            self.Logger.info(f"Rebind réussi! Control: {NewHost}:{NewControlPort}, Data: {NewHost}:{NewDataPort}")
            return True

        except OSError as e:
            self.Logger.error(f"Échec du rebind: {e}")
            self.AcceptingConnections = True
            return False
        except Exception as e:
            self.Logger.error(f"Erreur lors du rebind: {e}")
            self.AcceptingConnections = True
            return False

    async def Stop(self):
        """Arrête les deux listeners TCP"""
        self.AcceptingConnections = False

        if self.ControlServer:
            self.ControlServer.close()
            await self.ControlServer.wait_closed()
            self.Logger.info("Control listener arrêté")
            self.ControlServer = None

        if self.DataServer:
            self.DataServer.close()
            await self.DataServer.wait_closed()
            self.Logger.info("Data listener arrêté")
            self.DataServer = None

    def GetControlAddress(self) -> tuple:
        """Retourne l'adresse du port Control"""
        return (self.Host, self.ControlPort)

    def GetDataAddress(self) -> tuple:
        """Retourne l'adresse du port Data"""
        return (self.Host, self.DataPort)

    def IsRunning(self) -> bool:
        """Vérifie si les deux listeners sont actifs"""
        ControlRunning = self.ControlServer is not None and self.ControlServer.is_serving()
        DataRunning = self.DataServer is not None and self.DataServer.is_serving()
        return ControlRunning and DataRunning

    def IsAcceptingConnections(self) -> bool:
        """Vérifie si les listeners acceptent les nouvelles connexions"""
        return self.AcceptingConnections and self.IsRunning()
