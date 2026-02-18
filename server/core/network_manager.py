"""
Gestionnaire de réseau pour le serveur
Permet le rebind dynamique du listener TCP sans perdre les clients connectés
"""

import asyncio
from typing import Callable, List, Optional
from shared.utils.logger import GetModuleLogger


def _GetListenHosts(Host: str) -> List[str]:
    """
    Retourne la liste des adresses d'écoute pour asyncio.start_server (NetworkManager simple).

    - "" ou None → IPv4 uniquement par défaut
    - adresse spécifique → cette adresse
    """
    return [Host] if Host else ["0.0.0.0"]


def BuildListenHosts(HostV4: str, HostV6: str) -> List[str]:
    """
    Construit la liste des adresses d'écoute à partir des deux champs IPv4 et IPv6.

    - Les deux remplis → dual-stack [IPv4, IPv6]
    - IPv4 uniquement → [IPv4]
    - IPv6 uniquement → [IPv6]
    - Les deux vides → fallback [0.0.0.0]
    """
    Hosts = []
    if HostV4:
        Hosts.append(HostV4)
    if HostV6:
        Hosts.append(HostV6)
    return Hosts if Hosts else ["0.0.0.0"]


def _FormatAddress(PeerName) -> str:
    """
    Formate un tuple peername en chaîne lisible.
    IPv6 retourne un tuple à 4 éléments (host, port, flowinfo, scope_id).
    IPv4 retourne un tuple à 2 éléments (host, port).
    """
    if PeerName and len(PeerName) == 4:
        return f"[{PeerName[0]}]:{PeerName[1]}"
    elif PeerName and len(PeerName) >= 2:
        return f"{PeerName[0]}:{PeerName[1]}"
    return str(PeerName)


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

            Hosts = _GetListenHosts(self.Host)
            try:
                self.Server = await asyncio.start_server(
                    self._FilteredHandler,
                    Hosts,
                    self.Port
                )
            except OSError:
                if len(Hosts) > 1:
                    # Fallback : IPv6 indisponible, écoute uniquement IPv4
                    self.Logger.warning("IPv6 indisponible, demarrage en IPv4 uniquement")
                    self.Server = await asyncio.start_server(
                        self._FilteredHandler,
                        Hosts[0],
                        self.Port
                    )
                else:
                    raise

            self.AcceptingConnections = True
            self.Logger.info(f"Listener TCP demarre sur {Hosts}:{self.Port}")
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
            self.Logger.warning(f"Connexion refusee de {_FormatAddress(PeerName)} (rebind en cours)")
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
            NewHosts = _GetListenHosts(NewHost)
            try:
                NewServer = await asyncio.start_server(
                    self._FilteredHandler,
                    NewHosts,
                    NewPort
                )
            except OSError:
                if len(NewHosts) > 1:
                    self.Logger.warning("IPv6 indisponible lors du rebind, fallback IPv4")
                    NewServer = await asyncio.start_server(
                        self._FilteredHandler,
                        NewHosts[0],
                        NewPort
                    )
                else:
                    raise

            self.Logger.info(f"Nouveau listener demarre sur {NewHosts}:{NewPort}")

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
    Supporte IPv4 seul, IPv6 seul, ou dual-stack selon les adresses configurées.
    """

    def __init__(self, HostV4: str, ControlPort: int, DataPort: int, HostV6: str = ""):
        """
        Initialise le gestionnaire de réseau dual-port

        Args:
            HostV4: Adresse IPv4 d'écoute (ex: "0.0.0.0"), vide pour désactiver
            ControlPort: Port de contrôle (handshake, heartbeat, status)
            DataPort: Port de données (transferts de batches)
            HostV6: Adresse IPv6 d'écoute (ex: "::"), vide pour désactiver
        """
        self.HostV4 = HostV4
        self.HostV6 = HostV6
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

            Hosts = BuildListenHosts(self.HostV4, self.HostV6)

            # Démarre le listener Control
            try:
                self.ControlServer = await asyncio.start_server(
                    self._FilteredControlHandler,
                    Hosts,
                    self.ControlPort,
                    backlog=128
                )
            except OSError:
                if len(Hosts) > 1:
                    self.Logger.warning("IPv6 indisponible pour Control, fallback IPv4 uniquement")
                    self.ControlServer = await asyncio.start_server(
                        self._FilteredControlHandler,
                        [self.HostV4],
                        self.ControlPort,
                        backlog=128
                    )
                else:
                    raise
            self.Logger.info(f"Control listener démarré sur {Hosts}:{self.ControlPort}")

            # Démarre le listener Data
            try:
                self.DataServer = await asyncio.start_server(
                    self._FilteredDataHandler,
                    Hosts,
                    self.DataPort,
                    backlog=128
                )
            except OSError:
                if len(Hosts) > 1:
                    self.Logger.warning("IPv6 indisponible pour Data, fallback IPv4 uniquement")
                    self.DataServer = await asyncio.start_server(
                        self._FilteredDataHandler,
                        [self.HostV4],
                        self.DataPort,
                        backlog=128
                    )
                else:
                    raise
            self.Logger.info(f"Data listener démarré sur {Hosts}:{self.DataPort}")

            self.AcceptingConnections = True
            return True

        except OSError as e:
            self.Logger.error(f"Impossible de bind: {e}")
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
            self.Logger.warning(f"Connexion Control refusée de {_FormatAddress(PeerName)} (rebind en cours)")
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
            self.Logger.warning(f"Connexion Data refusée de {_FormatAddress(PeerName)} (rebind en cours)")
            Writer.close()
            await Writer.wait_closed()
            return

        if self.DataHandler:
            await self.DataHandler(Reader, Writer)

    async def Rebind(self, NewHostV4: str, NewControlPort: int, NewDataPort: int, NewHostV6: str = None) -> bool:
        """
        Rebind les deux listeners sur de nouvelles adresses.

        Args:
            NewHostV4: Nouvelle adresse IPv4 (vide pour désactiver)
            NewControlPort: Nouveau port de contrôle
            NewDataPort: Nouveau port de données
            NewHostV6: Nouvelle adresse IPv6 (None = inchangée, "" = désactiver)

        Returns:
            True si succès, False sinon (anciens listeners restent actifs)
        """
        if not self.ControlServer or not self.DataServer:
            self.Logger.error("Aucun listener actif pour rebind")
            return False

        if NewHostV6 is None:
            NewHostV6 = self.HostV6

        self.Logger.info(
            f"Rebind: v4={self.HostV4} v6={self.HostV6} ports={self.ControlPort}/{self.DataPort}"
            f" -> v4={NewHostV4} v6={NewHostV6} ports={NewControlPort}/{NewDataPort}"
        )

        # Refuse temporairement les nouvelles connexions
        self.AcceptingConnections = False
        self.Logger.info("Nouvelles connexions temporairement refusées")

        try:
            NewHosts = BuildListenHosts(NewHostV4, NewHostV6)

            # Démarre les nouveaux listeners
            try:
                NewControlServer = await asyncio.start_server(
                    self._FilteredControlHandler,
                    NewHosts,
                    NewControlPort
                )
            except OSError:
                if len(NewHosts) > 1:
                    self.Logger.warning("IPv6 indisponible lors du rebind Control, fallback IPv4")
                    NewControlServer = await asyncio.start_server(
                        self._FilteredControlHandler,
                        [NewHostV4],
                        NewControlPort
                    )
                else:
                    raise
            self.Logger.info(f"Nouveau Control listener démarré sur {NewHosts}:{NewControlPort}")

            try:
                NewDataServer = await asyncio.start_server(
                    self._FilteredDataHandler,
                    NewHosts,
                    NewDataPort
                )
            except OSError:
                if len(NewHosts) > 1:
                    self.Logger.warning("IPv6 indisponible lors du rebind Data, fallback IPv4")
                    NewDataServer = await asyncio.start_server(
                        self._FilteredDataHandler,
                        [NewHostV4],
                        NewDataPort
                    )
                else:
                    raise
            self.Logger.info(f"Nouveau Data listener démarré sur {NewHosts}:{NewDataPort}")

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
            self.HostV4 = NewHostV4
            self.HostV6 = NewHostV6
            self.ControlPort = NewControlPort
            self.DataPort = NewDataPort
            self.AcceptingConnections = True

            self.Logger.info(
                f"Rebind réussi! Control: {NewHosts}:{NewControlPort}, Data: {NewHosts}:{NewDataPort}"
            )
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
        """Retourne (HostV4, HostV6, ControlPort)"""
        return (self.HostV4, self.HostV6, self.ControlPort)

    def GetDataAddress(self) -> tuple:
        """Retourne (HostV4, HostV6, DataPort)"""
        return (self.HostV4, self.HostV6, self.DataPort)

    def IsRunning(self) -> bool:
        """Vérifie si les deux listeners sont actifs"""
        ControlRunning = self.ControlServer is not None and self.ControlServer.is_serving()
        DataRunning = self.DataServer is not None and self.DataServer.is_serving()
        return ControlRunning and DataRunning

    def IsAcceptingConnections(self) -> bool:
        """Vérifie si les listeners acceptent les nouvelles connexions"""
        return self.AcceptingConnections and self.IsRunning()
