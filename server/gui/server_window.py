"""
Fenêtre principale de l'interface graphique du serveur
"""

import sys
import asyncio
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTabWidget, QStatusBar, QMessageBox,
    QLabel, QApplication
)
from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QIcon

from .dashboard_tab import DashboardTab
from .clients_tab import ClientsTab
from .jobs_tab import JobsTab
from .config_tab import ConfigTab

from server.core.server import UpscalingServer
from server.core.job_manager import JobManager
from server.core.video_processor import VideoProcessor
from server.core.batch_distributor import BatchDistributor
from server.database.db_manager import DatabaseManager
from shared.utils.logger import GetServerLogger
from shared.utils.firewall import (
    IsWindows, RequestFirewallPermission, ShowFirewallDialog, RunAsAdmin
)
from shared.gui.theme_manager import ThemeManager, ApplyTheme


class ServerWindow(QMainWindow):
    """Fenêtre principale du serveur avec interface graphique"""

    # Signal pour mettre à jour l'interface depuis le thread asyncio
    UpdateSignal = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.Logger = GetServerLogger()
        self.Logger.info("Initialisation de l'interface graphique du serveur")

        # Composants serveur
        # Utilise le chemin par défaut de la DB (indépendant du work_directory)
        self.Database = DatabaseManager()  # Utilise GetDefaultDbPath()
        self.Database.Connect()
        self.Database.InitializeDefaultParameters()  # Initialise les paramètres par défaut

        self.Server = None
        self.JobManager = None
        self.IsRunning = False
        self.ServerLoop = None  # Référence à la boucle asyncio du serveur

        # Configuration de l'interface
        self.SetupUI()

        # Timer pour rafraîchir l'interface
        self.RefreshTimer = QTimer()
        self.RefreshTimer.timeout.connect(self.RefreshInterface)
        self.RefreshTimer.start(1000)  # Rafraîchir chaque seconde

    def SetupUI(self):
        """Configure l'interface utilisateur"""
        self.setWindowTitle("Serveur d'Upscaling - Contrôle")
        self.setMinimumSize(1000, 700)

        # Widget central
        CentralWidget = QWidget()
        self.setCentralWidget(CentralWidget)

        # Layout principal
        MainLayout = QVBoxLayout(CentralWidget)

        # Barre de contrôle
        ControlBar = self.CreateControlBar()
        MainLayout.addWidget(ControlBar)

        # Onglets
        self.Tabs = QTabWidget()

        # Création des onglets
        self.DashboardTab = DashboardTab(self)
        self.ClientsTab = ClientsTab(self)
        self.JobsTab = JobsTab(self)
        self.ConfigTab = ConfigTab(self)

        self.Tabs.addTab(self.DashboardTab, "📊 Dashboard")
        self.Tabs.addTab(self.ClientsTab, "💻 Clients")
        self.Tabs.addTab(self.JobsTab, "🎬 Jobs")
        self.Tabs.addTab(self.ConfigTab, "⚙️ Configuration")

        MainLayout.addWidget(self.Tabs)

        # Barre de statut
        self.StatusBar = QStatusBar()
        self.setStatusBar(self.StatusBar)
        self.UpdateStatusBar("Serveur arrêté")

    def CreateControlBar(self) -> QWidget:
        """Crée la barre de contrôle avec les boutons Start/Stop"""
        ControlWidget = QWidget()
        ControlLayout = QHBoxLayout(ControlWidget)

        # Label statut
        self.StatusLabel = QLabel("● Arrêté")
        self.StatusLabel.setObjectName("StatusLabel")
        self.StatusLabel.setProperty("status", "stopped")
        ControlLayout.addWidget(self.StatusLabel)

        ControlLayout.addStretch()

        # Bouton Start
        self.StartButton = QPushButton("▶ Démarrer le serveur")
        self.StartButton.setObjectName("StartButton")
        self.StartButton.setProperty("class", "primary")
        self.StartButton.clicked.connect(self.StartServer)
        ControlLayout.addWidget(self.StartButton)

        # Bouton Stop
        self.StopButton = QPushButton("⏹ Arrêter le serveur")
        self.StopButton.setObjectName("StopButton")
        self.StopButton.setProperty("class", "danger")
        self.StopButton.clicked.connect(self.StopServer)
        self.StopButton.setEnabled(False)
        ControlLayout.addWidget(self.StopButton)

        return ControlWidget

    def StartServer(self):
        """Démarre le serveur"""
        try:
            # Récupérer la configuration
            GuiConfig = self.ConfigTab.GetConfiguration()

            self.Logger.info(f"Démarrage du serveur sur {GuiConfig['ip']}:{GuiConfig['port']}")

            # Formater la configuration pour UpscalingServer
            ServerConfig = {
                "server": {
                    "ip": GuiConfig['ip'],
                    "port": GuiConfig['port'],
                    "password": GuiConfig['password'],
                    "work_directory": GuiConfig['work_directory']
                }
            }

            # Créer le serveur
            self.Server = UpscalingServer(ServerConfig)

            # Configuration pour le thread
            WorkDir = GuiConfig['work_directory']
            BatchSize = GuiConfig.get('batch_size', 100)

            # Initialiser et démarrer dans un thread asyncio séparé
            import threading

            def RunServerAsync():
                # Créer une nouvelle boucle pour ce thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self.ServerLoop = loop  # Stocker la référence

                # Initialiser le serveur (crée ClientManager) - fonction synchrone
                if not self.Server.Initialize():
                    self.Logger.error("Échec de l'initialisation du serveur")
                    return

                # Créer le VideoProcessor et BatchDistributor après Initialize
                Processor = VideoProcessor(WorkDir, self.Server.Database)
                Distributor = BatchDistributor(
                    self.Server.ClientManager,
                    Processor,
                    self.Server.Database
                )

                # Connecter le distributeur au serveur pour recevoir les résultats
                self.Server.SetBatchDistributor(Distributor)

                self.JobManager = JobManager(
                    Processor,
                    Distributor,
                    self.Server.Database,
                    BatchSize
                )

                # Démarrer le JobManager et le serveur (fonctions async)
                loop.run_until_complete(self.JobManager.Start())
                loop.run_until_complete(self.Server.Start())

                # Garder la boucle active
                loop.run_forever()

                # Nettoyage après arrêt de la boucle
                loop.close()
                self.ServerLoop = None

            self.ServerThread = threading.Thread(target=RunServerAsync, daemon=True)
            self.ServerThread.start()

            self.IsRunning = True

            # Mettre à jour l'interface
            self.StatusLabel.setText("● En cours")
            self.StatusLabel.setProperty("status", "running")
            self.StatusLabel.style().unpolish(self.StatusLabel)
            self.StatusLabel.style().polish(self.StatusLabel)
            self.StartButton.setEnabled(False)
            self.StopButton.setEnabled(True)
            self.UpdateStatusBar(f"Serveur démarré sur {GuiConfig['ip']}:{GuiConfig['port']}")

            self.Logger.info("Serveur démarré avec succès")

        except Exception as e:
            self.Logger.error(f"Erreur lors du démarrage du serveur: {e}")
            QMessageBox.critical(self, "Erreur", f"Impossible de démarrer le serveur:\n{str(e)}")

    def StopServer(self):
        """Arrête le serveur"""
        try:
            self.Logger.info("Arrêt du serveur...")

            if self.Server and self.ServerLoop:
                # Utilise la boucle asyncio du serveur pour l'arrêter proprement
                import concurrent.futures

                # Créer un Future pour attendre la fin
                StopComplete = concurrent.futures.Future()

                async def DoStop():
                    try:
                        await self.Server.Stop()
                        StopComplete.set_result(True)
                    except Exception as e:
                        StopComplete.set_exception(e)
                    finally:
                        # Arrêter la boucle après l'arrêt du serveur
                        self.ServerLoop.stop()

                # Planifier l'arrêt dans la boucle du serveur
                self.ServerLoop.call_soon_threadsafe(
                    lambda: asyncio.ensure_future(DoStop(), loop=self.ServerLoop)
                )

                # Attendre que l'arrêt soit terminé (timeout 5s)
                try:
                    StopComplete.result(timeout=5)
                except concurrent.futures.TimeoutError:
                    self.Logger.warning("Timeout lors de l'arrêt du serveur")
                except Exception as e:
                    self.Logger.error(f"Erreur lors de l'arrêt: {e}")

            self.IsRunning = False

            # Mettre à jour l'interface
            self.StatusLabel.setText("● Arrêté")
            self.StatusLabel.setProperty("status", "stopped")
            self.StatusLabel.style().unpolish(self.StatusLabel)
            self.StatusLabel.style().polish(self.StatusLabel)
            self.StartButton.setEnabled(True)
            self.StopButton.setEnabled(False)
            self.UpdateStatusBar("Serveur arrêté")

            self.Logger.info("Serveur arrêté avec succès")

        except Exception as e:
            self.Logger.error(f"Erreur lors de l'arrêt du serveur: {e}")
            QMessageBox.warning(self, "Avertissement", f"Erreur lors de l'arrêt:\n{str(e)}")

    def RefreshInterface(self):
        """Rafraîchit toutes les données de l'interface"""
        if self.IsRunning and self.Server:
            try:
                # Rafraîchir chaque onglet
                self.DashboardTab.Refresh()
                self.ClientsTab.Refresh()
                self.JobsTab.Refresh()
            except Exception as e:
                self.Logger.error(f"Erreur lors du rafraîchissement de l'interface: {e}")

    def UpdateStatusBar(self, Message: str):
        """Met à jour la barre de statut"""
        self.StatusBar.showMessage(Message)

    def GetServer(self):
        """Retourne l'instance du serveur"""
        return self.Server

    def GetJobManager(self):
        """Retourne l'instance du gestionnaire de jobs"""
        return self.JobManager

    def GetDatabase(self):
        """Retourne l'instance de la base de données"""
        return self.Database

    def closeEvent(self, event):
        """Gère la fermeture de la fenêtre"""
        if self.IsRunning:
            Reply = QMessageBox.question(
                self,
                'Confirmation',
                'Le serveur est en cours d\'exécution. Voulez-vous vraiment quitter?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if Reply == QMessageBox.Yes:
                self.StopServer()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def RunServerGUI():
    """Lance l'interface graphique du serveur"""
    # Vérification du pare-feu Windows
    if IsWindows():
        Success, Message = RequestFirewallPermission("UpscalingServer")
        if not Success:
            # Demande à l'utilisateur s'il veut configurer le pare-feu
            if ShowFirewallDialog():
                # Relance en mode administrateur
                if RunAsAdmin():
                    sys.exit(0)  # Ferme cette instance, la nouvelle s'ouvre en admin
            # Continue quand même, l'utilisateur a refusé ou ça a échoué
            print(f"Avertissement pare-feu: {Message}")

    App = QApplication(sys.argv)

    # Charger la préférence de thème depuis la base de données
    try:
        TempDb = DatabaseManager()
        ThemePreference = TempDb.GetParameter("theme", ThemeManager.THEME_AUTO)
    except Exception:
        ThemePreference = ThemeManager.THEME_AUTO

    # Appliquer le thème adaptatif
    ThemeMgr = ApplyTheme(App, ThemePreference)

    Window = ServerWindow()
    Window.ThemeManager = ThemeMgr  # Stocker la référence pour l'onglet Config
    Window.show()
    sys.exit(App.exec_())


if __name__ == "__main__":
    RunServerGUI()
