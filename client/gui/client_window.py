"""
Fenêtre principale de l'interface graphique du client
"""

import sys
import asyncio
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QStatusBar, QMessageBox, QApplication
)
from PyQt5.QtCore import QTimer, Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont

from .connection_tab import ConnectionTab
from .monitoring_tab import MonitoringTab
from .servers_tab import ServersTab
from .performance_tab import PerformanceTab
from .webhook_tab import WebhookTab

from client.core.client import UpscalingClient
from client.core.connection import ConnectionManager
from client.core.processor import LocalProcessor
from client.utils.hardware_detector import HardwareDetector
from shared.utils.logger import GetClientLogger
from shared.utils.firewall import (
    IsWindows, RequestFirewallPermission, ShowFirewallDialog, RunAsAdmin
)
from shared.gui.theme_manager import ThemeManager, ApplyTheme
from client.utils.performance_config import PerformanceConfigManager


class HardwareDetectionThread(QThread):
    """Thread de détection matériel au démarrage (non-bloquant)"""
    Finished = pyqtSignal(dict)

    def run(self):
        try:
            Detector = HardwareDetector()
            Hardware = Detector.DetectAll()
            self.Finished.emit(Hardware)
        except Exception:
            self.Finished.emit({})


class ClientWindow(QMainWindow):
    """Fenêtre principale du client avec interface graphique"""

    # Signal pour notifier la déconnexion demandée par le serveur (thread-safe)
    ServerDisconnectSignal = pyqtSignal(str)

    # Signal pour notifier une erreur critique nécessitant déconnexion (thread-safe)
    CriticalErrorSignal = pyqtSignal(dict)

    # Signal pour notifier les tentatives de reconnexion (thread-safe)
    ReconnectingSignal = pyqtSignal(int, float)  # (attempt, delay)

    def __init__(self):
        super().__init__()

        self.Logger = GetClientLogger()
        self.Logger.info("Initialisation de l'interface graphique du client")

        # Charge la configuration pour obtenir le work_directory
        self.ConfigManager = PerformanceConfigManager()
        Config = self.ConfigManager.Load()
        WorkDir = self.ConfigManager.GetWorkDirectory()

        # Composants client avec le répertoire de travail configuré
        self.Client = UpscalingClient(WorkDirectory=WorkDir)
        self.IsRunning = False
        self.BatchesProcessed = 0
        self.ImagesProcessed = 0

        # Cache matériel (pré-chargé au démarrage)
        self.CachedHardware = None
        self.HardwareDetectionThread = None

        # Configuration de l'interface
        self.SetupUI()

        # Lance la détection matériel en arrière-plan dès le démarrage
        self.StartHardwareDetection()

        # Timer pour rafraîchir l'interface
        self.RefreshTimer = QTimer()
        self.RefreshTimer.timeout.connect(self.RefreshInterface)
        self.RefreshTimer.start(1000)  # Rafraîchir chaque seconde

        # Connecte le signal de déconnexion serveur
        self.ServerDisconnectSignal.connect(self.OnServerDisconnect)

        # Connecte le signal d'erreur critique
        self.CriticalErrorSignal.connect(self.OnCriticalError)

        # Connecte le signal de reconnexion
        self.ReconnectingSignal.connect(self.OnReconnecting)

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
        self.PerformanceTab = PerformanceTab(self)
        self.WebhookTab = WebhookTab(self)

        self.Tabs.addTab(self.ConnectionTab, "🔌 Connexion")
        self.Tabs.addTab(self.MonitoringTab, "📊 Monitoring")
        self.Tabs.addTab(self.ServersTab, "💾 Serveurs")
        self.Tabs.addTab(self.PerformanceTab, "⚙️ Configuration")
        self.Tabs.addTab(self.WebhookTab, "🔔 Webhooks")

        MainLayout.addWidget(self.Tabs)

        # Barre de statut
        self.StatusBar = QStatusBar()
        self.setStatusBar(self.StatusBar)
        self.UpdateStatusBar("Déconnecté")

    def ConnectToServer(self, Host: str, Port: int, Password: str = ""):
        """Se connecte à un serveur"""
        try:
            self.Logger.info(f"Connexion au serveur {Host}:{Port}...")

            # Configure le callback de déconnexion serveur
            self.Client.OnServerDisconnect = lambda reason: self.ServerDisconnectSignal.emit(reason)

            # Configure le callback d'erreur critique
            self.Client.OnCriticalError = lambda errorInfo: self.CriticalErrorSignal.emit(errorInfo)

            # Configure le callback de reconnexion
            self.Client.OnReconnecting = lambda attempt, delay: self.ReconnectingSignal.emit(attempt, delay)

            # Démarrer le client dans un thread asyncio séparé
            import threading
            import concurrent.futures

            # Future pour récupérer le résultat de la connexion de manière thread-safe
            ConnectionResult = concurrent.futures.Future()

            def RunClientAsync():
                # Créer une nouvelle boucle pour ce thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                try:
                    # Démarrer le client (connecte et lance la boucle)
                    # Start() retourne True si connexion réussie, False sinon
                    Success = loop.run_until_complete(self.Client.Start(Host, Port, Password))
                    ConnectionResult.set_result(Success)

                    # CRITIQUE: Garde le loop actif pour que les tâches (MainLoop, DataReceiveLoop) s'exécutent
                    # Sans cela, le loop se ferme immédiatement et les tâches ne démarrent jamais
                    if Success and self.Client.MainLoopTask:
                        self.Logger.info("Event loop actif, les boucles de réception démarrent...")
                        # Attend que MainLoop se termine (déconnexion ou erreur)
                        loop.run_until_complete(self.Client.MainLoopTask)

                except asyncio.CancelledError:
                    # Arrêt normal du client (la tâche a été annulée)
                    self.Logger.info("Arrêt du client (tâche annulée)")
                except Exception as e:
                    self.Logger.error(f"Erreur dans la boucle client: {e}")
                    ConnectionResult.set_exception(e)
                finally:
                    self.IsRunning = False
                    loop.close()

            self.ClientThread = threading.Thread(target=RunClientAsync, daemon=True)
            self.ClientThread.start()

            # Attend le résultat réel de la connexion (timeout: 10 secondes)
            try:
                Success = ConnectionResult.result(timeout=10.0)
            except concurrent.futures.TimeoutError:
                self.Logger.error("Timeout lors de la tentative de connexion")
                QMessageBox.critical(self, "Erreur", "Timeout lors de la connexion au serveur.\nLe serveur ne répond pas.")
                return False
            except Exception as e:
                self.Logger.error(f"Exception lors de la connexion: {e}")
                QMessageBox.critical(self, "Erreur", f"Erreur lors de la connexion:\n{str(e)}")
                return False

            # Vérifie le résultat de la connexion
            if not Success:
                self.Logger.error("Échec de la connexion (handshake ou authentification)")
                QMessageBox.critical(
                    self,
                    "Erreur de connexion",
                    "Impossible de se connecter au serveur.\n\n"
                    "Vérifiez:\n"
                    "  - L'adresse et le port du serveur\n"
                    "  - Le mot de passe (si requis)\n"
                    "  - Que le serveur est bien démarré"
                )
                return False

            # Connexion réussie !
            self.IsRunning = True
            self.UpdateStatusBar(f"Connecté à {Host}:{Port}")
            self.Logger.info("Connexion établie avec succès")

            return True

        except Exception as e:
            self.Logger.error(f"Erreur lors de la connexion: {e}")
            QMessageBox.critical(self, "Erreur", f"Impossible de se connecter:\n{str(e)}")
            return False

    def DisconnectFromServer(self):
        """Se deconnecte du serveur"""
        try:
            self.Logger.info("Deconnexion du serveur...")

            if self.Client and self.IsRunning:
                # Demande l'arret thread-safe (planifie sur l'event loop du client)
                # Timeout augmente a 15s pour laisser le temps aux taches de s'arreter proprement
                StopSuccess = self.Client.RequestStop(Timeout=15.0)
                if not StopSuccess:
                    self.Logger.warning("L'arret du client a pris plus de temps que prevu (continue quand meme)")

            self.IsRunning = False
            self.UpdateStatusBar("Deconnecte")
            self.Logger.info("Deconnexion reussie")

        except Exception as e:
            self.Logger.error(f"Erreur lors de la deconnexion: {e}")
            QMessageBox.warning(self, "Avertissement", f"Erreur lors de la deconnexion:\n{str(e)}")

    def RefreshInterface(self):
        """Rafraichit toutes les donnees de l'interface"""
        try:
            # Rafraichir chaque onglet
            self.ConnectionTab.Refresh()
            self.MonitoringTab.Refresh()
            self.ServersTab.Refresh()
            self.PerformanceTab.Refresh()
        except Exception as e:
            self.Logger.error(f"Erreur lors du rafraichissement de l'interface: {e}")

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

    def OnServerDisconnect(self, Reason: str):
        """
        Appelé quand le serveur demande la déconnexion du client.
        Cette méthode est appelée via le signal Qt (thread-safe).

        Args:
            Reason: Raison de la déconnexion
        """
        self.Logger.warning(f"Déconnexion demandée par le serveur: {Reason}")
        self.IsRunning = False
        self.UpdateStatusBar("Déconnecté par le serveur")

        # Affiche un message à l'utilisateur
        QMessageBox.warning(
            self,
            "Déconnexion",
            f"Le serveur vous a déconnecté.\n\nRaison: {Reason}"
        )

        # Met à jour l'interface de connexion
        if hasattr(self, 'ConnectionTab') and self.ConnectionTab:
            self.ConnectionTab.Refresh()

    def OnCriticalError(self, ErrorInfo: dict):
        """
        Appelé quand une erreur critique est détectée (ex: mémoire GPU insuffisante).
        Le client se déconnecte automatiquement et affiche des suggestions.
        Cette méthode est appelée via le signal Qt (thread-safe).

        Args:
            ErrorInfo: Dictionnaire avec type, message, suggestions, raw_error
        """
        ErrorMessage = ErrorInfo.get("message", "Erreur inconnue")
        ErrorType = ErrorInfo.get("type", "unknown")
        Suggestions = ErrorInfo.get("suggestions", [])

        self.Logger.error(f"Erreur critique: {ErrorMessage} (type: {ErrorType})")
        self.IsRunning = False
        self.UpdateStatusBar("Erreur critique - Deconnecte")

        # Construit le message avec suggestions
        Message = f"{ErrorMessage}\n\n"

        if Suggestions:
            Message += "Suggestions pour corriger le probleme:\n\n"
            for Suggestion in Suggestions:
                Message += f"  - {Suggestion}\n"

            Message += "\nVeuillez ajuster les parametres dans l'onglet Configuration "
            Message += "puis vous reconnecter."

        # Affiche une boîte de dialogue critique
        QMessageBox.critical(
            self,
            "Erreur d'upscaling",
            Message
        )

        # Met à jour l'interface de connexion
        if hasattr(self, 'ConnectionTab') and self.ConnectionTab:
            self.ConnectionTab.Refresh()

    def OnReconnecting(self, Attempt: int, Delay: float):
        """
        Appelé lors de chaque tentative de reconnexion automatique.
        Cette méthode est appelée via le signal Qt (thread-safe).

        Args:
            Attempt: Numéro de la tentative
            Delay: Délai avant cette tentative (en secondes)
        """
        if Delay > 0:
            self.Logger.info(f"🔄 Reconnexion automatique - tentative #{Attempt} dans {Delay}s...")
            self.UpdateStatusBar(f"🔄 Reconnexion dans {Delay:.0f}s (tentative #{Attempt})...")
        else:
            self.Logger.info(f"🔄 Reconnexion automatique - tentative #{Attempt}...")
            self.UpdateStatusBar(f"🔄 Reconnexion en cours (tentative #{Attempt})...")

        # Met à jour l'interface de connexion pour refléter l'état de reconnexion
        if hasattr(self, 'ConnectionTab') and self.ConnectionTab:
            self.ConnectionTab.Refresh()

    def StartHardwareDetection(self):
        """Lance la détection matériel en arrière-plan"""
        self.Logger.info("Lancement de la détection matériel en arrière-plan...")
        self.HardwareDetectionThread = HardwareDetectionThread()
        self.HardwareDetectionThread.Finished.connect(self.OnHardwareDetected)
        self.HardwareDetectionThread.start()

    def OnHardwareDetected(self, Hardware: dict):
        """Appelé quand la détection matériel est terminée"""
        self.CachedHardware = Hardware
        self.Logger.info("Détection matériel terminée et mise en cache")

        # Notifie l'onglet Performance que le matériel est disponible
        if hasattr(self, 'PerformanceTab') and self.PerformanceTab:
            self.PerformanceTab.OnHardwareCacheReady(Hardware)

    def GetCachedHardware(self) -> dict:
        """Retourne le matériel détecté en cache (ou None si pas encore prêt)"""
        return self.CachedHardware

    def ReloadPerformanceConfig(self):
        """
        Recharge la configuration de performance et la propage au processeur actif.
        Appelé automatiquement quand les paramètres changent.
        """
        try:
            # Recharge la config dans le client/processeur s'il est actif
            if self.Client and hasattr(self.Client, 'Processor') and self.Client.Processor:
                self.Client.Processor.ReloadPerformanceConfig()
                self.Logger.info("Configuration de performance rechargée dans le processeur")

            return True
        except Exception as e:
            self.Logger.error(f"Erreur lors du rechargement de la configuration: {e}")
            return False

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

    # Charger la préférence de thème depuis la configuration
    try:
        ConfigMgr = PerformanceConfigManager()
        Config = ConfigMgr.Load()
        ThemePreference = Config.get("theme", ThemeManager.THEME_AUTO)
    except Exception:
        ThemePreference = ThemeManager.THEME_AUTO

    # Appliquer le thème adaptatif
    ThemeMgr = ApplyTheme(App, ThemePreference)

    Window = ClientWindow()
    Window.ThemeManager = ThemeMgr  # Stocker la référence pour l'onglet Performance
    Window.show()
    sys.exit(App.exec_())


if __name__ == "__main__":
    RunClientGUI()
