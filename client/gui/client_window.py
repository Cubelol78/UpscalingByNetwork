"""
Fenêtre principale de l'interface graphique du client
"""

import sys
import asyncio
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QStatusBar, QMessageBox, QApplication
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont

from .connection_tab import ConnectionTab
from .monitoring_tab import MonitoringTab
from .servers_tab import ServersTab

from client.core.client import UpscalingClient
from client.core.connection import ConnectionManager
from client.core.processor import LocalProcessor
from shared.utils.logger import GetClientLogger
from shared.utils.firewall import (
    IsWindows, RequestFirewallPermission, ShowFirewallDialog, RunAsAdmin
)


class ClientWindow(QMainWindow):
    """Fenêtre principale du client avec interface graphique"""

    def __init__(self):
        super().__init__()

        self.Logger = GetClientLogger()
        self.Logger.info("Initialisation de l'interface graphique du client")

        # Composants client
        self.Client = UpscalingClient()
        self.IsRunning = False
        self.BatchesProcessed = 0
        self.ImagesProcessed = 0

        # Configuration de l'interface
        self.SetupUI()

        # Timer pour rafraîchir l'interface
        self.RefreshTimer = QTimer()
        self.RefreshTimer.timeout.connect(self.RefreshInterface)
        self.RefreshTimer.start(1000)  # Rafraîchir chaque seconde

    def SetupUI(self):
        """Configure l'interface utilisateur"""
        self.setWindowTitle("Client d'Upscaling")
        self.setMinimumSize(800, 600)

        # Widget central
        CentralWidget = QWidget()
        self.setCentralWidget(CentralWidget)

        # Layout principal
        MainLayout = QVBoxLayout(CentralWidget)

        # Onglets
        self.Tabs = QTabWidget()

        # Création des onglets
        self.ConnectionTab = ConnectionTab(self)
        self.MonitoringTab = MonitoringTab(self)
        self.ServersTab = ServersTab(self)

        self.Tabs.addTab(self.ConnectionTab, "🔌 Connexion")
        self.Tabs.addTab(self.MonitoringTab, "📊 Monitoring")
        self.Tabs.addTab(self.ServersTab, "💾 Serveurs")

        MainLayout.addWidget(self.Tabs)

        # Barre de statut
        self.StatusBar = QStatusBar()
        self.setStatusBar(self.StatusBar)
        self.UpdateStatusBar("Déconnecté")

    def ConnectToServer(self, Host: str, Port: int, Password: str = ""):
        """Se connecte à un serveur"""
        try:
            self.Logger.info(f"Connexion au serveur {Host}:{Port}...")

            # Démarrer le client dans un thread asyncio séparé
            import threading

            def RunClientAsync():
                # Créer une nouvelle boucle pour ce thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                try:
                    # Démarrer le client (connecte et lance la boucle)
                    loop.run_until_complete(self.Client.Start(Host, Port, Password))
                except Exception as e:
                    self.Logger.error(f"Erreur dans la boucle client: {e}")
                finally:
                    self.IsRunning = False
                    loop.close()

            self.ClientThread = threading.Thread(target=RunClientAsync, daemon=True)
            self.ClientThread.start()

            # Attendre un peu pour vérifier que la connexion est établie
            import time
            time.sleep(0.5)

            self.IsRunning = True
            self.UpdateStatusBar(f"Connecté à {Host}:{Port}")
            self.Logger.info("Connexion établie")

            return True

        except Exception as e:
            self.Logger.error(f"Erreur lors de la connexion: {e}")
            QMessageBox.critical(self, "Erreur", f"Impossible de se connecter:\n{str(e)}")
            return False

    def DisconnectFromServer(self):
        """Se déconnecte du serveur"""
        try:
            self.Logger.info("Déconnexion du serveur...")

            if self.Client and self.IsRunning:
                # Arrêter le client dans son propre thread
                import threading

                def StopClientAsync():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self.Client.Stop())
                    loop.close()

                StopThread = threading.Thread(target=StopClientAsync)
                StopThread.start()
                StopThread.join(timeout=5)

            self.IsRunning = False
            self.UpdateStatusBar("Déconnecté")
            self.Logger.info("Déconnexion réussie")

        except Exception as e:
            self.Logger.error(f"Erreur lors de la déconnexion: {e}")
            QMessageBox.warning(self, "Avertissement", f"Erreur lors de la déconnexion:\n{str(e)}")

    def RefreshInterface(self):
        """Rafraîchit toutes les données de l'interface"""
        try:
            # Rafraîchir chaque onglet
            self.ConnectionTab.Refresh()
            self.MonitoringTab.Refresh()
            self.ServersTab.Refresh()
        except Exception as e:
            self.Logger.error(f"Erreur lors du rafraîchissement de l'interface: {e}")

    def UpdateStatusBar(self, Message: str):
        """Met à jour la barre de statut"""
        self.StatusBar.showMessage(Message)

    def GetClient(self):
        """Retourne l'instance du client"""
        return self.Client

    def GetConnectionManager(self):
        """Retourne l'instance du gestionnaire de connexion"""
        return self.Client.ConnectionManager

    def IsClientRunning(self) -> bool:
        """Retourne True si le client est connecté"""
        return self.IsRunning

    def closeEvent(self, event):
        """Gère la fermeture de la fenêtre"""
        if self.IsRunning:
            Reply = QMessageBox.question(
                self,
                'Confirmation',
                'Le client est connecté. Voulez-vous vraiment quitter?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if Reply == QMessageBox.Yes:
                self.DisconnectFromServer()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def RunClientGUI():
    """Lance l'interface graphique du client"""
    # Vérification du pare-feu Windows
    if IsWindows():
        Success, Message = RequestFirewallPermission("UpscalingClient")
        if not Success:
            # Demande à l'utilisateur s'il veut configurer le pare-feu
            if ShowFirewallDialog():
                # Relance en mode administrateur
                if RunAsAdmin():
                    sys.exit(0)  # Ferme cette instance, la nouvelle s'ouvre en admin
            # Continue quand même, l'utilisateur a refusé ou ça a échoué
            print(f"Avertissement pare-feu: {Message}")

    App = QApplication(sys.argv)
    Window = ClientWindow()
    Window.show()
    sys.exit(App.exec_())


if __name__ == "__main__":
    RunClientGUI()
