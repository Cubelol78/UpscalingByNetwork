"""
Interface CLI pour le client d'upscaling vidéo
"""

import asyncio
import os
import sys
import click
from pathlib import Path

# Ajoute le répertoire parent au path pour les imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from client.core.client import UpscalingClient
from client.core.connection import SavedServersManager
from shared.utils.constants import ClientStatus


class ClientCLI:
    """Interface CLI du client"""

    def __init__(self):
        """Initialise l'interface CLI"""
        self.Client = None
        self.ServerManager = SavedServersManager()
        self.Running = False
        self.MonitoringTask = None

    async def Start(self):
        """Démarre l'interface CLI"""
        click.echo("="*60)
        click.echo("  CLIENT D'UPSCALING VIDÉO EN RÉSEAU")
        click.echo("  Real-ESRGAN Distributed Processing")
        click.echo("="*60)

        await self.MainMenu()

    async def MainMenu(self):
        """Menu principal"""
        while True:
            click.echo("\n" + "="*60)
            click.echo("MENU PRINCIPAL")
            click.echo("="*60)
            click.echo("1. Connecter à un serveur")
            click.echo("2. Serveurs sauvegardés")
            click.echo("3. Ajouter un serveur")
            click.echo("0. Quitter")
            click.echo("="*60)

            Choice = click.prompt("Votre choix", type=int, default=1)

            if Choice == 0:
                click.echo("Au revoir!")
                break
            elif Choice == 1:
                await self.ConnectToServer()
            elif Choice == 2:
                await self.ManageSavedServers()
            elif Choice == 3:
                self.AddServer()
            else:
                click.echo("✗ Choix invalide")

    async def ConnectToServer(self):
        """Menu de connexion à un serveur"""
        click.echo("\n" + "="*60)
        click.echo("CONNEXION AU SERVEUR")
        click.echo("="*60)

        # Affiche les serveurs sauvegardés
        SavedServers = self.ServerManager.ListServers()

        if SavedServers:
            click.echo("\nServeurs sauvegardés:")
            for Index, ServerName in enumerate(SavedServers, 1):
                ServerInfo = self.ServerManager.GetServer(ServerName)
                click.echo(f"{Index}. {ServerName} ({ServerInfo['host']}:{ServerInfo['port']})")
            click.echo(f"{len(SavedServers) + 1}. Autre serveur...")

            Choice = click.prompt("Choisir un serveur", type=int, default=1)

            if 1 <= Choice <= len(SavedServers):
                # Serveur sauvegardé
                ServerName = SavedServers[Choice - 1]
                ServerInfo = self.ServerManager.GetServer(ServerName)
                Host = ServerInfo['host']
                Port = ServerInfo['port']
                Password = ServerInfo.get('password', '')

                click.echo(f"\nConnexion à {ServerName} ({Host}:{Port})...")
            else:
                # Autre serveur
                Host, Port, Password = self._PromptServerDetails()
        else:
            # Pas de serveurs sauvegardés
            click.echo("\nAucun serveur sauvegardé")
            Host, Port, Password = self._PromptServerDetails()

        # Crée le client
        self.Client = UpscalingClient()

        # Lance la connexion dans une tâche
        try:
            # Démarre le monitoring du statut
            self.Running = True
            self.MonitoringTask = asyncio.create_task(self._MonitorStatus())

            # Connecte au serveur
            await self.Client.Start(Host, Port, Password)

        except KeyboardInterrupt:
            click.echo("\n\n✗ Interruption utilisateur")
        except Exception as e:
            click.echo(f"\n✗ Erreur: {e}")
        finally:
            self.Running = False
            if self.MonitoringTask:
                self.MonitoringTask.cancel()
                try:
                    await self.MonitoringTask
                except asyncio.CancelledError:
                    pass

            if self.Client:
                await self.Client.Stop()

    def _PromptServerDetails(self):
        """Demande les détails de connexion"""
        Host = click.prompt("Adresse du serveur", default="localhost")
        Port = click.prompt("Port", type=int, default=8765)
        Password = click.prompt("Mot de passe (laisser vide si aucun)", default="", show_default=False)

        return Host, Port, Password

    async def ManageSavedServers(self):
        """Gestion des serveurs sauvegardés"""
        while True:
            click.echo("\n" + "="*60)
            click.echo("SERVEURS SAUVEGARDÉS")
            click.echo("="*60)

            SavedServers = self.ServerManager.ListServers()

            if not SavedServers:
                click.echo("\nAucun serveur sauvegardé")
                click.echo("\n1. Ajouter un serveur")
                click.echo("0. Retour")

                Choice = click.prompt("Votre choix", type=int, default=0)

                if Choice == 1:
                    self.AddServer()
                else:
                    break
            else:
                click.echo(f"\nNombre de serveurs: {len(SavedServers)}\n")

                for Index, ServerName in enumerate(SavedServers, 1):
                    ServerInfo = self.ServerManager.GetServer(ServerName)
                    HasPassword = "Oui" if ServerInfo.get('password') else "Non"
                    click.echo(f"{Index}. {ServerName}")
                    click.echo(f"   Adresse: {ServerInfo['host']}:{ServerInfo['port']}")
                    click.echo(f"   Mot de passe: {HasPassword}")

                click.echo("\nActions:")
                click.echo("a. Ajouter un serveur")
                click.echo("r. Retirer un serveur")
                click.echo("0. Retour")

                Choice = click.prompt("Votre choix", default="0")

                if Choice == "0":
                    break
                elif Choice == "a":
                    self.AddServer()
                elif Choice == "r":
                    self.RemoveServer()
                else:
                    click.echo("✗ Choix invalide")

    def AddServer(self):
        """Ajoute un serveur aux favoris"""
        click.echo("\n" + "="*60)
        click.echo("AJOUTER UN SERVEUR")
        click.echo("="*60)

        Name = click.prompt("Nom du serveur")
        Host = click.prompt("Adresse", default="localhost")
        Port = click.prompt("Port", type=int, default=8765)

        SavePassword = click.confirm("Sauvegarder le mot de passe?", default=False)
        Password = ""
        if SavePassword:
            Password = click.prompt("Mot de passe", default="", show_default=False)

        # Ajoute le serveur
        self.ServerManager.AddServer(Name, Host, Port, Password)

        click.echo(f"\n✓ Serveur '{Name}' ajouté")

    def RemoveServer(self):
        """Retire un serveur des favoris"""
        SavedServers = self.ServerManager.ListServers()

        if not SavedServers:
            click.echo("✗ Aucun serveur à retirer")
            return

        click.echo("\nServeurs:")
        for Index, ServerName in enumerate(SavedServers, 1):
            click.echo(f"{Index}. {ServerName}")

        Choice = click.prompt("Numéro du serveur à retirer", type=int)

        if 1 <= Choice <= len(SavedServers):
            ServerName = SavedServers[Choice - 1]

            if click.confirm(f"Confirmer la suppression de '{ServerName}'?"):
                self.ServerManager.RemoveServer(ServerName)
                click.echo(f"✓ Serveur '{ServerName}' retiré")
        else:
            click.echo("✗ Numéro invalide")

    async def _MonitorStatus(self):
        """Monitore et affiche le statut du client"""
        try:
            LastStatus = None
            LastBatch = None

            while self.Running:
                await asyncio.sleep(2)

                if not self.Client:
                    continue

                Status = self.Client.GetStatus()

                # Affiche les changements de statut
                if Status['status'] != LastStatus:
                    click.echo(f"\n📊 Statut: {Status['status']}")
                    LastStatus = Status['status']

                # Affiche les batches en cours
                if Status['current_batch'] and Status['current_batch'] != LastBatch:
                    click.echo(f"🖼️  Traitement batch: {Status['current_batch'][:16]}...")
                    LastBatch = Status['current_batch']
                elif not Status['current_batch'] and LastBatch:
                    click.echo("✓ Batch terminé")
                    LastBatch = None

        except asyncio.CancelledError:
            pass
        except Exception as e:
            click.echo(f"\n✗ Erreur monitoring: {e}")


# ============================================================================
# FONCTION PRINCIPALE
# ============================================================================

def Main():
    """Fonction principale CLI"""
    Cli = ClientCLI()

    try:
        asyncio.run(Cli.Start())
    except KeyboardInterrupt:
        click.echo("\n\n✗ Interruption utilisateur")
    except Exception as e:
        click.echo(f"\n✗ Erreur: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    Main()
