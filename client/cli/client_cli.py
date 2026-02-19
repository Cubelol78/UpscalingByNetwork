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
from client.utils.hardware_detector import HardwareDetector
from client.utils.performance_config import PerformanceConfigManager, PerformancePresets
from client.web.client_web import ClientWebInterface
from shared.utils.constants import ClientStatus, CompressionConfig, NetworkConfig


class ClientCLI:
    """Interface CLI du client"""

    def __init__(self):
        """Initialise l'interface CLI"""
        self.Client = None
        self.ServerManager = SavedServersManager()
        self.PerformanceManager = PerformanceConfigManager()
        self.Running = False
        self.MonitoringTask = None
        self.WebInterface = None

    async def Start(self):
        """Démarre l'interface CLI"""
        click.echo("="*60)
        click.echo("  CLIENT D'UPSCALING VIDÉO EN RÉSEAU")
        click.echo("  Real-ESRGAN Distributed Processing")
        click.echo("="*60)

        # Démarrer la web UI
        try:
            self.WebInterface = ClientWebInterface()
            self.WebInterface.Start(Host="127.0.0.1", Port=NetworkConfig.CLIENT_WEB_PORT)
            click.echo(f"✓ Web UI client → http://localhost:{NetworkConfig.CLIENT_WEB_PORT}")
        except Exception as WebErr:
            click.echo(f"⚠ Web UI non disponible: {WebErr}")
            self.WebInterface = None

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
            click.echo("4. Configuration performances")
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
            elif Choice == 4:
                self.PerformanceMenu()
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

        # Connecter la web UI au client
        if self.WebInterface:
            self.WebInterface.SetClient(self.Client)

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

            # Déconnecter la web UI
            if self.WebInterface:
                self.WebInterface.ClearClient()

    def _PromptServerDetails(self):
        """Demande les détails de connexion"""
        Host = click.prompt("Adresse du serveur (IPv4 ou IPv6)", default="localhost")
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

    def PerformanceMenu(self):
        """Menu de configuration des performances"""
        while True:
            click.echo("\n" + "="*60)
            click.echo("CONFIGURATION DES PERFORMANCES")
            click.echo("="*60)

            # Charge la configuration actuelle
            Config = self.PerformanceManager.Load()

            # Affiche la configuration actuelle
            TileSize = Config.get('tile_size', 0)
            GpuIds = Config.get('gpu_ids', [])
            Threads = Config.get('threads', {})
            CompressionLevel = Config.get('compression_level', CompressionConfig.LEVEL_DEFAULT)

            click.echo("\nConfiguration actuelle:")
            click.echo(f"  Tile size: {TileSize if TileSize > 0 else 'Auto'}")
            click.echo(f"  GPU: {','.join(map(str, GpuIds)) if GpuIds else 'Auto'}")
            click.echo(f"  Threads: {Threads.get('load', 1)}:{Threads.get('process', 2)}:{Threads.get('save', 2)}")
            click.echo(f"  Compression reseau: {CompressionLevel}/10 (1=rapide, 10=max)")
            click.echo("  (Mode TTA: configuré côté serveur)")

            click.echo("\nActions:")
            click.echo("1. Détecter le matériel")
            click.echo("2. Configuration automatique")
            click.echo("3. Configuration manuelle")
            click.echo("4. Réinitialiser par défaut")
            click.echo("0. Retour")

            Choice = click.prompt("Votre choix", type=int, default=0)

            if Choice == 0:
                break
            elif Choice == 1:
                self._DetectHardware()
            elif Choice == 2:
                self._AutoConfigure()
            elif Choice == 3:
                self._ManualConfigure()
            elif Choice == 4:
                self._ResetPerformanceConfig()
            else:
                click.echo("✗ Choix invalide")

    def _DetectHardware(self):
        """Détecte et affiche le matériel"""
        click.echo("\n" + "="*60)
        click.echo("DÉTECTION DU MATÉRIEL")
        click.echo("="*60)

        click.echo("\nDétection en cours...")

        try:
            Detector = HardwareDetector()
            HardwareInfo = Detector.DetectAll()

            # CPU
            CpuInfo = HardwareInfo.get('cpu', {})
            click.echo(f"\n📦 CPU:")
            click.echo(f"   Nom: {CpuInfo.get('name', 'Inconnu')}")
            click.echo(f"   Coeurs physiques: {CpuInfo.get('physical_cores', '?')}")
            click.echo(f"   Coeurs logiques: {CpuInfo.get('logical_cores', '?')}")

            # RAM
            RamInfo = HardwareInfo.get('ram', {})
            click.echo(f"\n💾 RAM:")
            click.echo(f"   Total: {RamInfo.get('total_gb', '?')} GB")
            click.echo(f"   Disponible: {RamInfo.get('available_gb', '?')} GB")

            # GPU
            GpuList = HardwareInfo.get('gpu', [])
            click.echo(f"\n🎮 GPU ({len(GpuList)} détecté(s)):")

            if GpuList:
                for Gpu in GpuList:
                    GpuId = Gpu.get('id', -1)
                    Name = Gpu.get('name', 'Inconnu')
                    Vram = Gpu.get('vram_mb', 0)
                    VramStr = f"{Vram} MB" if Vram > 0 else "N/A"
                    click.echo(f"   [{GpuId}] {Name} - VRAM: {VramStr}")
            else:
                click.echo("   Aucun GPU Vulkan détecté")

            # Recommandations
            click.echo("\n📊 Recommandations:")
            TileSize = Detector.GetRecommendedTileSize()
            ThreadConfig = Detector.GetRecommendedThreads()
            click.echo(f"   Tile size recommandé: {TileSize}")
            click.echo(f"   Threads recommandés: {ThreadConfig.get('load', 1)}:{ThreadConfig.get('process', 2)}:{ThreadConfig.get('save', 2)}")

        except Exception as e:
            click.echo(f"\n✗ Erreur lors de la détection: {e}")

    def _AutoConfigure(self):
        """Configuration automatique basée sur le matériel (préfère les GPU dédiés)"""
        click.echo("\n" + "="*60)
        click.echo("CONFIGURATION AUTOMATIQUE")
        click.echo("="*60)

        click.echo("\nDétection du matériel...")

        try:
            Detector = HardwareDetector()
            HardwareInfo = Detector.DetectAll()

            # Affiche les GPU détectés
            Gpus = HardwareInfo.get('gpu', [])
            if Gpus:
                click.echo("\nGPU détectés:")
                for Gpu in Gpus:
                    VramMb = Gpu.get('vram_mb', 0)
                    VramStr = f"{VramMb} MB" if VramMb else "VRAM inconnue"
                    IsIntegrated = self.PerformanceManager._IsIntegratedGpu(Gpu.get('name', ''))
                    TypeStr = "(intégré)" if IsIntegrated else "(dédié)"
                    click.echo(f"  [{Gpu.get('id', '?')}] {Gpu.get('name', 'Inconnu')} - {VramStr} {TypeStr}")

            # Demande si multi-GPU souhaité
            UseMultiGpu = False
            DedicatedCount = sum(1 for g in Gpus if not self.PerformanceManager._IsIntegratedGpu(g.get('name', '')))
            if DedicatedCount > 1:
                UseMultiGpu = click.confirm(f"\nUtiliser les {DedicatedCount} GPU dédiés en parallèle?", default=False)

            # Génère la configuration optimale (préfère les GPU dédiés)
            click.echo("\nGénération de la configuration optimale...")
            click.echo("(Les GPU dédiés NVIDIA/AMD sont préférés aux GPU intégrés Intel)")
            Config = self.PerformanceManager.AutoConfigure(HardwareInfo, UseMultiGpu=UseMultiGpu)

            # Affiche les GPU sélectionnés
            SelectedIds = Config.get('gpu_ids', [])
            SelectedNames = []
            for Gpu in Gpus:
                if Gpu.get('id') in SelectedIds:
                    SelectedNames.append(Gpu.get('name', f"GPU {Gpu.get('id')}"))

            # Affiche la configuration proposée
            click.echo("\nConfiguration proposée:")
            click.echo(f"  GPU sélectionnés: {', '.join(SelectedNames) if SelectedNames else 'Aucun (mode CPU)'}")
            click.echo(f"  GPU IDs: {','.join(map(str, SelectedIds)) if SelectedIds else '-'}")
            click.echo(f"  Tile size: {Config.get('tile_size', 0)}")
            Threads = Config.get('threads', {})
            click.echo(f"  Threads: {Threads.get('load', 1)}:{Threads.get('process', 2)}:{Threads.get('save', 2)}")

            # Demande confirmation
            if click.confirm("\nAppliquer cette configuration?", default=True):
                self.PerformanceManager.Save(Config)
                click.echo("✓ Configuration sauvegardée")
            else:
                click.echo("Configuration non appliquée")

        except Exception as e:
            click.echo(f"\n✗ Erreur: {e}")

    def _ManualConfigure(self):
        """Configuration manuelle des performances"""
        click.echo("\n" + "="*60)
        click.echo("CONFIGURATION MANUELLE")
        click.echo("="*60)

        Config = self.PerformanceManager.Load()

        # Tile size
        CurrentTile = Config.get('tile_size', 0)
        click.echo(f"\nTile size (0=auto, min={PerformancePresets.MIN_TILE_SIZE}, max={PerformancePresets.MAX_TILE_SIZE})")
        TileSize = click.prompt("Tile size", type=int, default=CurrentTile)

        if TileSize < 0:
            TileSize = 0
        elif TileSize > 0 and TileSize < PerformancePresets.MIN_TILE_SIZE:
            TileSize = PerformancePresets.MIN_TILE_SIZE
        elif TileSize > PerformancePresets.MAX_TILE_SIZE:
            TileSize = PerformancePresets.MAX_TILE_SIZE

        Config['tile_size'] = TileSize

        # GPU selection
        click.echo("\nSélection GPU (vide=auto, ex: 0 ou 0,1 pour multi-GPU)")
        CurrentGpu = ','.join(map(str, Config.get('gpu_ids', [])))
        GpuInput = click.prompt("GPU IDs", default=CurrentGpu, show_default=True)

        if GpuInput.strip():
            try:
                GpuIds = [int(x.strip()) for x in GpuInput.split(',') if x.strip()]
                Config['gpu_ids'] = GpuIds
            except ValueError:
                click.echo("✗ Format invalide, GPU non modifié")
        else:
            Config['gpu_ids'] = []

        # Threads
        Threads = Config.get('threads', {})
        click.echo(f"\nConfiguration threads (min={PerformancePresets.MIN_THREADS}, max={PerformancePresets.MAX_THREADS})")

        LoadThreads = click.prompt("Threads de chargement", type=int, default=Threads.get('load', 1))
        ProcessThreads = click.prompt("Threads de traitement", type=int, default=Threads.get('process', 2))
        SaveThreads = click.prompt("Threads de sauvegarde", type=int, default=Threads.get('save', 2))

        Config['threads'] = {
            'load': max(PerformancePresets.MIN_THREADS, min(PerformancePresets.MAX_THREADS, LoadThreads)),
            'process': max(PerformancePresets.MIN_THREADS, min(PerformancePresets.MAX_THREADS, ProcessThreads)),
            'save': max(PerformancePresets.MIN_THREADS, min(PerformancePresets.MAX_THREADS, SaveThreads))
        }

        # Compression level
        CurrentCompression = Config.get('compression_level', CompressionConfig.LEVEL_DEFAULT)
        click.echo(f"\nCompression reseau ({CompressionConfig.LEVEL_MIN}-{CompressionConfig.LEVEL_MAX}, 1=rapide, 10=max)")
        CompressionLevel = click.prompt("Niveau de compression", type=int, default=CurrentCompression)
        CompressionLevel = max(CompressionConfig.LEVEL_MIN, min(CompressionConfig.LEVEL_MAX, CompressionLevel))
        Config['compression_level'] = CompressionLevel

        # Note: Le mode TTA est configuré côté serveur
        click.echo("\n(Note: Le mode TTA est configuré côté serveur)")

        # Sauvegarde
        if click.confirm("\nSauvegarder cette configuration?", default=True):
            self.PerformanceManager.Save(Config)
            click.echo("✓ Configuration sauvegardée")
        else:
            click.echo("Configuration non sauvegardée")

    def _ResetPerformanceConfig(self):
        """Réinitialise la configuration des performances"""
        if click.confirm("Réinitialiser aux valeurs par défaut?", default=False):
            self.PerformanceManager.Reset()
            click.echo("✓ Configuration réinitialisée")

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
