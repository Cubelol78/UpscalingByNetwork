"""
Fenêtre principale de l'interface graphique du serveur
"""

import os
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
from server.database.db_manager import DatabaseManager
from shared.utils.logger import GetServerLogger
from shared.utils.constants import PathConfig


class ServerWindow(QMainWindow):
    """Fenêtre principale du serveur avec interface graphique"""

    # Signal pour mettre à jour l'interface depuis le thread asyncio
    UpdateSignal = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.Logger = GetServerLogger()
        self.Logger.info("Initialisation de l'interface graphique du serveur")

        # Composants serveur
        DbPath = os.path.join(PathConfig.WORK_DIR, PathConfig.DATABASE_NAME)
        self.Database = DatabaseManager(DbPath)
        self.Server = None
        self.JobManager = None
        self.IsRunning = False

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
        self.StatusLabel.setStyleSheet("color: red; font-weight: bold; font-size: 14px;")
        ControlLayout.addWidget(self.StatusLabel)

        ControlLayout.addStretch()

        # Bouton Start
        self.StartButton = QPushButton("▶ Démarrer le serveur")
        self.StartButton.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.StartButton.clicked.connect(self.StartServer)
        ControlLayout.addWidget(self.StartButton)

        # Bouton Stop
        self.StopButton = QPushButton("⏹ Arrêter le serveur")
        self.StopButton.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
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

            # Créer les instances
            self.Server = UpscalingServer(ServerConfig)

            self.JobManager = JobManager(
                Server=self.Server,
                Database=self.Database,
                WorkDirectory=GuiConfig['work_directory']
            )

            # Initialiser et démarrer dans un thread asyncio séparé
            import threading

            def RunServerAsync():
                # Créer une nouvelle boucle pour ce thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                # Initialiser et démarrer
                loop.run_until_complete(self.Server.Initialize())
                loop.run_until_complete(self.Server.Start())

                # Garder la boucle active
                loop.run_forever()

            self.ServerThread = threading.Thread(target=RunServerAsync, daemon=True)
            self.ServerThread.start()

            self.IsRunning = True

            # Mettre à jour l'interface
            self.StatusLabel.setText("● En cours")
            self.StatusLabel.setStyleSheet("color: green; font-weight: bold; font-size: 14px;")
            self.StartButton.setEnabled(False)
            self.StopButton.setEnabled(True)
            self.UpdateStatusBar(f"Serveur démarré sur {Config['ip']}:{Config['port']}")

            self.Logger.info("Serveur démarré avec succès")

        except Exception as e:
            self.Logger.error(f"Erreur lors du démarrage du serveur: {e}")
            QMessageBox.critical(self, "Erreur", f"Impossible de démarrer le serveur:\n{str(e)}")

    def StopServer(self):
        """Arrête le serveur"""
        try:
            self.Logger.info("Arrêt du serveur...")

            if self.Server:
                # Arrêter le serveur dans son propre thread
                import threading

                def StopServerAsync():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self.Server.Stop())
                    loop.close()

                StopThread = threading.Thread(target=StopServerAsync)
                StopThread.start()
                StopThread.join(timeout=5)

            self.IsRunning = False

            # Mettre à jour l'interface
            self.StatusLabel.setText("● Arrêté")
            self.StatusLabel.setStyleSheet("color: red; font-weight: bold; font-size: 14px;")
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
    App = QApplication(sys.argv)
    Window = ServerWindow()
    Window.show()
    sys.exit(App.exec_())


if __name__ == "__main__":
    RunServerGUI()
