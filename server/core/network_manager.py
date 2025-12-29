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
