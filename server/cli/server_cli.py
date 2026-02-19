"""
Interface CLI pour le serveur d'upscaling vidéo
Configuration stockée dans la base de données SQLite
"""

import asyncio
import os
import sys
import click
from pathlib import Path

# Ajoute le répertoire parent au path pour les imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from server.core.server import UpscalingServer
from server.core.batch_distributor import BatchDistributor
from server.core.job_manager import JobManager
from server.core.video_processor import VideoProcessor
from server.database.db_manager import DatabaseManager
from server.web.server_web import ServerWebInterface
from shared.utils.constants import NetworkConfig


class ServerCLI:
    """Interface CLI du serveur"""

    def __init__(self):
        """
        Initialise l'interface CLI
        Charge la configuration depuis la base de données
        """
        # Initialise la base de données pour charger la configuration
        self.Database = DatabaseManager()  # Utilise le chemin par défaut
        self.Database.Connect()
        self.Database.InitializeDefaultParameters()

        # Charge la configuration depuis la DB
        DbConfig = self.Database.GetServerConfig()
        self.Config = {
            "server": {
                "ipv4": DbConfig['ipv4'],
                "ipv6": DbConfig['ipv6'],
                "port": DbConfig['port'],
                "password": DbConfig['password'],
                "work_directory": DbConfig['work_directory'],
                "batch_size": DbConfig['batch_size'],
                "compression_level": DbConfig.get('compression_level', 5)
            },
            "processing": {
                "upscale_factor": 4,
                "model": "realesr-animevideov3"
            }
        }

        self.Server = None
        self.JobManager = None
        self.Running = False
        self.WebInterface = None

    async def StartServer(self):
        """Démarre le serveur"""
        if self.Running:
            click.echo("✗ Le serveur est déjà en cours d'exécution")
            return

        # Démarrer la web UI avant le serveur upscaling
        try:
            WebPort = self.Database.GetParameterInt("web_port", NetworkConfig.SERVER_WEB_PORT)
            self.WebInterface = ServerWebInterface(self.Database)
            self.WebInterface.Start(Host="0.0.0.0", Port=WebPort)
            click.echo(f"✓ Web UI démarrée → http://localhost:{WebPort}")
        except Exception as WebErr:
            click.echo(f"⚠ Web UI non disponible: {WebErr}")
            self.WebInterface = None

        click.echo("Démarrage du serveur...")

        # Crée le serveur
        self.Server = UpscalingServer(self.Config)

        # Initialise
        if not self.Server.Initialize():
            click.echo("✗ Échec de l'initialisation du serveur")
            return

        # Démarre le serveur
        if not await self.Server.Start():
            click.echo("✗ Échec du démarrage du serveur")
            return

        # Crée le JobManager
        BatchDistributor_obj = BatchDistributor(
            self.Server.ClientManager,
            VideoProcessor(
                self.Config["server"]["work_directory"],
                self.Server.Database
            ),
            self.Server.Database
        )

        # Connecter le distributeur au serveur pour recevoir les résultats
        self.Server.SetBatchDistributor(BatchDistributor_obj)

        self.JobManager = JobManager(
            VideoProcessor(
                self.Config["server"]["work_directory"],
                self.Server.Database
            ),
            BatchDistributor_obj,
            self.Server.Database,
            self.Config["server"]["batch_size"]
        )

        # Démarre le JobManager
        await self.JobManager.Start()

        self.Running = True
        click.echo("✓ Serveur démarré avec succès")

        # Connecter la web UI aux composants upscaling (boucle asyncio courante)
        if self.WebInterface:
            self.WebInterface.SetServerComponents(
                self.Server, self.JobManager, BatchDistributor_obj,
                ServerLoop=asyncio.get_event_loop()
            )

        # Menu interactif
        await self.InteractiveMenu()

    async def StopServer(self):
        """Arrête le serveur"""
        if not self.Running:
            click.echo("✗ Le serveur n'est pas en cours d'exécution")
            return

        click.echo("Arrêt du serveur...")

        if self.JobManager:
            await self.JobManager.Stop()

        if self.Server:
            await self.Server.Stop()

        self.Running = False
        if self.WebInterface:
            self.WebInterface.ClearServerComponents()
            self.WebInterface.Stop()
            self.WebInterface = None
        click.echo("✓ Serveur arrêté")

    async def InteractiveMenu(self):
        """Menu interactif principal"""
        while self.Running:
            click.echo("\n" + "="*60)
            click.echo("SERVEUR D'UPSCALING VIDÉO - MENU PRINCIPAL")
            click.echo("="*60)
            click.echo("1. Statut du serveur")
            click.echo("2. Clients connectés")
            click.echo("3. Ajouter une vidéo")
            click.echo("4. File de jobs")
            click.echo("5. Statistiques")
            click.echo("6. Configuration")
            click.echo("0. Arrêter le serveur")
            click.echo("="*60)

            Choice = click.prompt("Votre choix", type=int, default=1)

            if Choice == 0:
                await self.StopServer()
                break
            elif Choice == 1:
                self.ShowServerStatus()
            elif Choice == 2:
                self.ShowConnectedClients()
            elif Choice == 3:
                await self.AddVideo()
            elif Choice == 4:
                self.ShowJobsQueue()
            elif Choice == 5:
                self.ShowStatistics()
            elif Choice == 6:
                self.ShowConfiguration()
            else:
                click.echo("✗ Choix invalide")

            await asyncio.sleep(0.1)

    def ShowServerStatus(self):
        """Affiche le statut du serveur"""
        click.echo("\n" + "="*60)
        click.echo("STATUT DU SERVEUR")
        click.echo("="*60)

        if not self.Server:
            click.echo("✗ Serveur non initialisé")
            return

        Status = self.Server.GetStatus()

        click.echo(f"État: {'✓ En ligne' if Status['running'] else '✗ Hors ligne'}")
        click.echo(f"Adresse: {Status['host']}:{Status['port']}")
        click.echo(f"Clients connectés: {Status['connected_clients']}")
        click.echo(f"Répertoire de travail: {Status['work_directory']}")
        click.echo(f"Base de données: {Status['database']}")

        # Job en cours
        if self.JobManager:
            CurrentJob = self.JobManager.GetCurrentJob()
            if CurrentJob:
                click.echo(f"\nJob en cours: {CurrentJob.VideoId}")
                click.echo(f"  Statut: {CurrentJob.Status}")
                click.echo(f"  Progression: {CurrentJob.Progress*100:.1f}%")
                click.echo(f"  Batches: {CurrentJob.CompletedBatches}/{CurrentJob.TotalBatches}")

    def ShowConnectedClients(self):
        """Affiche les clients connectés"""
        click.echo("\n" + "="*60)
        click.echo("CLIENTS CONNECTÉS")
        click.echo("="*60)

        if not self.Server or not self.Server.ClientManager:
            click.echo("✗ Serveur non démarré")
            return

        ClientIds = self.Server.ClientManager.GetConnectedClients()

        if not ClientIds:
            click.echo("Aucun client connecté")
            return

        click.echo(f"Nombre de clients: {len(ClientIds)}\n")

        for Index, ClientId in enumerate(ClientIds, 1):
            Status = self.Server.ClientManager.GetClientStatus(ClientId)
            ClientInfo = self.Server.ClientManager.Clients.get(ClientId)

            click.echo(f"{Index}. Client {ClientId[:8]}...")
            if ClientInfo:
                click.echo(f"   Adresse: {ClientInfo.IpAddress}")
                click.echo(f"   Statut: {Status}")
                click.echo(f"   Connecté depuis: {ClientInfo.ConnectedAt.strftime('%H:%M:%S')}")

    async def AddVideo(self):
        """Ajoute une vidéo à la file d'attente"""
        click.echo("\n" + "="*60)
        click.echo("AJOUTER UNE VIDÉO")
        click.echo("="*60)

        if not self.JobManager:
            click.echo("✗ JobManager non démarré")
            return

        # Demande le chemin de la vidéo
        VideoPath = click.prompt("Chemin de la vidéo")

        # Vérifie que le fichier existe
        if not os.path.exists(VideoPath):
            click.echo(f"✗ Fichier non trouvé: {VideoPath}")
            return

        # Demande le facteur d'upscaling
        UpscaleFactor = click.prompt(
            "Facteur d'upscaling",
            type=click.Choice(['2', '3', '4']),
            default='4'
        )

        # Demande le modèle
        Models = [
            "realesr-animevideov3",
            "realesrgan-x4plus-anime",
            "realesrgan-x4plus"
        ]
        click.echo("\nModèles disponibles:")
        for i, Model in enumerate(Models, 1):
            click.echo(f"{i}. {Model}")

        ModelChoice = click.prompt("Choisir le modèle", type=int, default=1)
        Model = Models[ModelChoice - 1]

        # Demande le mode TTA
        TtaMode = click.confirm(
            "Activer le mode TTA? (meilleure qualité, plus lent)",
            default=False
        )

        # Ajoute la vidéo
        VideoId = self.JobManager.AddVideo(
            VideoPath,
            int(UpscaleFactor),
            Model,
            TtaMode
        )

        if VideoId:
            click.echo(f"\n✓ Vidéo ajoutée à la file d'attente")
            click.echo(f"ID: {VideoId}")
        else:
            click.echo("✗ Échec de l'ajout de la vidéo")

    def ShowJobsQueue(self):
        """Affiche la file de jobs"""
        click.echo("\n" + "="*60)
        click.echo("FILE DE JOBS")
        click.echo("="*60)

        if not self.JobManager:
            click.echo("✗ JobManager non démarré")
            return

        QueueStatus = self.JobManager.GetQueueStatus()

        # Job en cours
        if QueueStatus['current_job']:
            click.echo(f"\n📹 JOB EN COURS:")
            Progress = self.JobManager.GetJobProgress(QueueStatus['current_job'])
            click.echo(f"  ID: {Progress['video_id']}")
            click.echo(f"  Statut: {Progress['status']}")
            click.echo(f"  Progression: {Progress['progress']:.1f}%")
            click.echo(f"  Batches: {Progress['completed_batches']}/{Progress['total_batches']}")

        # Jobs en attente
        QueuedCount = QueueStatus['queued_count']
        click.echo(f"\n📋 JOBS EN ATTENTE: {QueuedCount}")

        if QueuedCount > 0:
            for Index, Video in enumerate(QueueStatus['queued_videos'], 1):
                click.echo(f"\n{Index}. {os.path.basename(Video['video_path'])}")
                click.echo(f"   ID: {Video['video_id']}")
                click.echo(f"   Ajouté: {Video['created_at']}")

    def ShowStatistics(self):
        """Affiche les statistiques"""
        click.echo("\n" + "="*60)
        click.echo("STATISTIQUES")
        click.echo("="*60)

        if not self.Server or not self.Server.Database:
            click.echo("✗ Serveur non démarré")
            return

        Stats = self.Server.Database.GetStatistics()

        click.echo(f"\n📊 VIDÉOS:")
        click.echo(f"  Total: {Stats.get('total_videos', 0)}")
        VideosByStatus = Stats.get('videos_by_status', {})
        for Status, Count in VideosByStatus.items():
            click.echo(f"  {Status}: {Count}")

        click.echo(f"\n📦 BATCHES:")
        click.echo(f"  Total: {Stats.get('total_batches', 0)}")
        BatchesByStatus = Stats.get('batches_by_status', {})
        for Status, Count in BatchesByStatus.items():
            click.echo(f"  {Status}: {Count}")

        click.echo(f"\n👥 CLIENTS:")
        click.echo(f"  Total historique: {Stats.get('total_clients', 0)}")
        click.echo(f"  Connectés actuellement: {self.Server.ClientManager.GetClientCount()}")

    def ShowConfiguration(self):
        """Affiche la configuration (depuis la base de données)"""
        click.echo("\n" + "="*60)
        click.echo("CONFIGURATION (stockee dans la base de donnees)")
        click.echo("="*60)

        # Relit la config depuis la DB pour avoir les valeurs actuelles
        DbConfig = self.Database.GetServerConfig()

        click.echo("\n📡 SERVEUR:")
        click.echo(f"  IPv4: {DbConfig.get('ipv4', 'N/A') or '(désactivé)'}")
        click.echo(f"  IPv6: {DbConfig.get('ipv6', '') or '(désactivé)'}")
        click.echo(f"  Port: {DbConfig.get('port', 'N/A')}")
        click.echo(f"  Mot de passe: {'Defini' if DbConfig.get('password') else 'Non defini'}")
        click.echo(f"  Repertoire de travail: {DbConfig.get('work_directory', 'N/A')}")
        click.echo(f"  Taille batch: {DbConfig.get('batch_size', 'N/A')}")
        click.echo(f"  Compression reseau: {DbConfig.get('compression_level', 5)}/10")
        click.echo(f"  Envois concurrents: {DbConfig.get('max_concurrent_batches', 3)}")
        click.echo(f"\n  Base de donnees: {self.Database.DbPath}")


# ============================================================================
# FONCTION PRINCIPALE
# ============================================================================

def Main():
    """Fonction principale CLI"""
    click.echo("="*60)
    click.echo("  SERVEUR D'UPSCALING VIDÉO EN RÉSEAU")
    click.echo("  Real-ESRGAN Distributed Processing")
    click.echo("="*60)

    # Crée l'interface CLI
    Cli = ServerCLI()

    # Démarre le serveur de manière asynchrone
    try:
        asyncio.run(Cli.StartServer())
    except KeyboardInterrupt:
        click.echo("\n\n✗ Interruption utilisateur")
        if Cli.Running:
            asyncio.run(Cli.StopServer())
    except Exception as e:
        click.echo(f"\n✗ Erreur: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    Main()
