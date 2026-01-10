#!/usr/bin/env python3
"""
Point d'entrée principal du système d'upscaling vidéo en réseau
Gère la création d'environnement virtuel et le lancement serveur/client
"""

import sys
import os
import subprocess
import argparse

# Import conditionnel pour le pare-feu Windows
try:
    from shared.utils.firewall import (
        IsWindows, RequestFirewallPermission, ShowFirewallDialog, RunAsAdmin
    )
    FIREWALL_AVAILABLE = True
except ImportError:
    from typing import Tuple
    FIREWALL_AVAILABLE = False

    def IsWindows() -> bool:
        return sys.platform == "win32"

    def RequestFirewallPermission(AppName: str) -> Tuple[bool, str]:
        return True, "Module pare-feu non disponible"

    def ShowFirewallDialog() -> bool:
        return False

    def RunAsAdmin() -> bool:
        return False


def CheckVirtualEnv():
    """Vérifie si un environnement virtuel Python est actif"""
    return hasattr(sys, 'real_prefix') or (
        hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix
    )


def CreateVirtualEnv(VenvPath):
    """Crée un environnement virtuel Python"""
    print(f"Création de l'environnement virtuel dans {VenvPath}...")
    try:
        subprocess.run([sys.executable, "-m", "venv", VenvPath], check=True)
        print(f"✓ Environnement virtuel créé avec succès")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Erreur lors de la création de l'environnement virtuel: {e}")
        return False


def InstallDependencies(VenvPath):
    """Installe les dépendances depuis requirements.txt"""
    print("Installation des dépendances...")

    # Détermine le chemin de pip dans le venv
    if sys.platform == "win32":
        PipPath = os.path.join(VenvPath, "Scripts", "pip.exe")
        PythonPath = os.path.join(VenvPath, "Scripts", "python.exe")
    else:
        PipPath = os.path.join(VenvPath, "bin", "pip")
        PythonPath = os.path.join(VenvPath, "bin", "python")

    RequirementsPath = os.path.join(os.path.dirname(__file__), "requirements.txt")

    try:
        # Mise à jour de pip
        subprocess.run([PythonPath, "-m", "pip", "install", "--upgrade", "pip"],
                      check=True, capture_output=True)

        # Installation des dépendances
        subprocess.run([PipPath, "install", "-r", RequirementsPath],
                      check=True)
        print("✓ Dépendances installées avec succès")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Erreur lors de l'installation des dépendances: {e}")
        return False


def UpdateDependencies():
    """Met à jour les dépendances dans l'environnement virtuel actif"""
    print("Vérification des dépendances...")

    RequirementsPath = os.path.join(os.path.dirname(__file__), "requirements.txt")

    try:
        # Mise à jour silencieuse des dépendances
        Result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", RequirementsPath, "--upgrade"],
            check=True,
            capture_output=True,
            text=True
        )

        # Vérifie si des paquets ont été mis à jour
        Output = Result.stdout
        if "Successfully installed" in Output or "Requirement already satisfied" in Output:
            print("✓ Dépendances à jour")
        else:
            print("✓ Dépendances vérifiées")

        return True

    except subprocess.CalledProcessError as e:
        print(f"⚠ Avertissement: Impossible de mettre à jour les dépendances: {e}")
        print("Vous pouvez continuer, mais certaines fonctionnalités peuvent ne pas fonctionner")
        return False


def AskYesNo(Question, AutoAccept=False):
    """
    Demande une réponse oui/non à l'utilisateur

    Args:
        Question: Question à poser
        AutoAccept: Si True, accepte automatiquement sans demander

    Returns:
        True pour oui, False pour non
    """
    if AutoAccept:
        print(f"{Question} (oui/non): oui [auto-accepté]")
        return True

    while True:
        Response = input(f"{Question} (oui/non): ").strip().lower()
        if Response in ["oui", "o", "yes", "y"]:
            return True
        elif Response in ["non", "n", "no"]:
            return False
        else:
            print("Réponse invalide. Veuillez répondre 'oui' ou 'non'")


def GetVenvPythonPath(VenvPath):
    """Retourne le chemin vers l'exécutable Python du venv"""
    if sys.platform == "win32":
        PythonPath = os.path.join(VenvPath, "Scripts", "python.exe")
    else:
        PythonPath = os.path.join(VenvPath, "bin", "python")
    return PythonPath


def VenvExists(VenvPath):
    """Vérifie si un environnement virtuel valide existe"""
    PythonPath = GetVenvPythonPath(VenvPath)
    return os.path.exists(PythonPath)


def RestartInVenv(VenvPath, Args):
    """Redémarre le script dans l'environnement virtuel"""
    PythonPath = GetVenvPythonPath(VenvPath)

    if not os.path.exists(PythonPath):
        print(f"✗ Python du venv non trouvé: {PythonPath}")
        return False

    # Relance le script avec le Python du venv
    ScriptPath = os.path.abspath(__file__)

    # Utilise subprocess au lieu de os.execv pour une meilleure compatibilité
    try:
        Result = subprocess.run(
            [PythonPath, ScriptPath] + Args,
            cwd=os.path.dirname(ScriptPath)
        )
        sys.exit(Result.returncode)
    except Exception as e:
        print(f"✗ Erreur lors du relancement dans le venv: {e}")
        # Fallback vers os.execv
        try:
            os.execv(PythonPath, [PythonPath, ScriptPath] + Args)
        except Exception as e2:
            print(f"✗ Erreur execv: {e2}")
            return False


def ChooseMode(CliMode, PresetMode=None):
    """
    Demande à l'utilisateur quel mode lancer (serveur ou client)

    Args:
        CliMode: True pour mode CLI, False pour GUI
        PresetMode: Mode prédéfini ("server" ou "client"), None pour demander

    Returns:
        "server" ou "client"
    """
    # Si un mode est déjà spécifié, le retourner directement
    if PresetMode:
        if PresetMode in ("server", "client"):
            ModeStr = "Serveur" if PresetMode == "server" else "Client"
            GuiCliStr = "CLI" if CliMode else "GUI"
            print(f"\nMode: {ModeStr} ({GuiCliStr})")
            return PresetMode
        else:
            print(f"⚠ Mode invalide spécifié: {PresetMode}")
            print("Modes valides: --server ou --client")
            # Continue pour demander interactivement

    if CliMode:
        print("\nMode CLI activé")
        print("Choisissez le mode:")
        print("1. Serveur")
        print("2. Client")

        while True:
            Choice = input("\nVotre choix (1 ou 2): ").strip()
            if Choice == "1":
                return "server"
            elif Choice == "2":
                return "client"
            else:
                print("Choix invalide. Veuillez choisir 1 ou 2")
    else:
        print("\nMode GUI")
        print("Choisissez le mode:")
        print("1. Serveur")
        print("2. Client")

        while True:
            Choice = input("\nVotre choix (1 ou 2): ").strip()
            if Choice == "1":
                return "server"
            elif Choice == "2":
                return "client"
            else:
                print("Choix invalide. Veuillez choisir 1 ou 2")


def CheckFirewallPermissions(AppName: str, AutoAccept: bool = False) -> bool:
    """
    Vérifie et configure les permissions pare-feu sur Windows

    Args:
        AppName: Nom de l'application pour les règles
        AutoAccept: Si True, configure automatiquement le pare-feu

    Returns:
        True si on peut continuer
    """
    if not IsWindows() or not FIREWALL_AVAILABLE:
        return True

    Success, Message = RequestFirewallPermission(AppName)
    if Success:
        print(f"✓ Pare-feu: {Message}")
        return True

    print(f"⚠ Pare-feu: {Message}")

    # Demande à l'utilisateur (ou auto-accepte)
    if AutoAccept:
        print("Voulez-vous configurer le pare-feu automatiquement ? (oui/non): oui [auto-accepté]")
        ShouldConfigure = True
    else:
        Response = input("\nVoulez-vous configurer le pare-feu automatiquement ? (oui/non): ").strip().lower()
        ShouldConfigure = Response in ("oui", "o", "yes", "y")

    if ShouldConfigure:
        if RunAsAdmin():
            print("Relancement en mode administrateur...")
            sys.exit(0)
        else:
            print("Impossible de relancer en mode administrateur")

    print("Continuation sans configuration du pare-feu...")
    return True


def LaunchServer(CliMode, AutoAccept=False):
    """
    Lance le serveur

    Args:
        CliMode: True pour mode CLI
        AutoAccept: Auto-accepte la configuration du pare-feu
    """
    print("\n" + "="*60)
    print("Lancement du serveur d'upscaling")
    print("="*60)

    # Vérification du pare-feu Windows
    CheckFirewallPermissions("UpscalingServer", AutoAccept)

    if CliMode:
        try:
            from server.cli.server_cli import Main as ServerCliMain
            ServerCliMain()
        except ImportError as e:
            print(f"✗ Erreur: Module serveur CLI non trouvé: {e}")
            print("Assurez-vous que toutes les dépendances sont installées")
            sys.exit(1)
    else:
        try:
            from server.gui.server_window import RunServerGUI
            RunServerGUI()
        except ImportError as e:
            print(f"✗ Erreur: Module serveur GUI non trouvé: {e}")
            print("Assurez-vous que PyQt5 est installé: pip install PyQt5")
            sys.exit(1)


def LaunchClient(CliMode, AutoAccept=False):
    """
    Lance le client

    Args:
        CliMode: True pour mode CLI
        AutoAccept: Auto-accepte la configuration du pare-feu
    """
    print("\n" + "="*60)
    print("Lancement du client d'upscaling")
    print("="*60)

    # Vérification du pare-feu Windows
    CheckFirewallPermissions("UpscalingClient", AutoAccept)

    if CliMode:
        try:
            from client.cli.client_cli import Main as ClientCliMain
            ClientCliMain()
        except ImportError as e:
            print(f"✗ Erreur: Module client CLI non trouvé: {e}")
            print("Assurez-vous que toutes les dépendances sont installées")
            sys.exit(1)
    else:
        try:
            from client.gui.client_window import RunClientGUI
            RunClientGUI()
        except ImportError as e:
            print(f"✗ Erreur: Module client GUI non trouvé: {e}")
            print("Assurez-vous que PyQt5 est installé: pip install PyQt5")
            sys.exit(1)


def Main():
    """Fonction principale"""
    # Banner
    print("="*60)
    print("  Système d'upscaling vidéo en réseau - Real-ESRGAN")
    print("="*60)

    # Parse arguments
    Parser = argparse.ArgumentParser(
        description="Système d'upscaling vidéo distribué avec Real-ESRGAN",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples d'utilisation:
  python main.py                    Lancement interactif (GUI par défaut)
  python main.py --cli              Lancement interactif en mode CLI
  python main.py --server           Lancement direct du serveur (GUI)
  python main.py --server --cli     Lancement direct du serveur (CLI)
  python main.py --client           Lancement direct du client (GUI)
  python main.py --client --cli     Lancement direct du client (CLI)
  python main.py --server --yes     Serveur avec auto-acceptation (venv, pare-feu)
  python main.py --client -y        Client avec auto-acceptation (raccourci)
        """
    )
    Parser.add_argument(
        "--cli",
        action="store_true",
        help="Lance l'interface en ligne de commande au lieu de la GUI"
    )
    Parser.add_argument(
        "--server",
        action="store_true",
        help="Lance directement le serveur sans demander"
    )
    Parser.add_argument(
        "--client",
        action="store_true",
        help="Lance directement le client sans demander"
    )

    # Groupe d'arguments pour auto-acceptation (multiples variantes)
    AutoGroup = Parser.add_mutually_exclusive_group()
    AutoGroup.add_argument(
        "--yes", "-y",
        action="store_true",
        dest="auto_accept",
        help="Accepte automatiquement toutes les demandes (création venv, pare-feu)"
    )
    AutoGroup.add_argument(
        "--oui",
        action="store_true",
        dest="auto_accept",
        help="Alias pour --yes"
    )

    Args = Parser.parse_args()

    # Validation: ne peut pas spécifier à la fois --server et --client
    if Args.server and Args.client:
        Parser.error("Impossible de spécifier --server et --client en même temps")

    # Détermine le mode préselectionné
    PresetMode = None
    if Args.server:
        PresetMode = "server"
    elif Args.client:
        PresetMode = "client"

    # Vérification environnement virtuel
    VenvPath = os.path.join(os.path.dirname(__file__), "venv")

    if not CheckVirtualEnv():
        # Vérifie si un venv valide existe
        if VenvExists(VenvPath):
            # Relance automatiquement dans le venv existant sans demander
            print(f"\n→ Environnement virtuel détecté dans: {VenvPath}")
            print("  Relancement automatique dans l'environnement virtuel...")
            RestartInVenv(VenvPath, sys.argv[1:])
            # Si on arrive ici, le relancement a échoué
            print("\n⚠ Impossible de relancer dans le venv")
            if not AskYesNo("Voulez-vous continuer sans environnement virtuel?", Args.auto_accept):
                sys.exit(1)
        else:
            print("\n⚠ Aucun environnement virtuel Python détecté")
            if AskYesNo("Voulez-vous créer un environnement Python pour ce logiciel?", Args.auto_accept):
                if CreateVirtualEnv(VenvPath):
                    if InstallDependencies(VenvPath):
                        print("\n✓ Environnement prêt. Redémarrage dans le venv...")
                        # Redémarre dans le nouveau venv
                        RestartInVenv(VenvPath, sys.argv[1:])
                        # Si on arrive ici, le relancement a échoué
                        print("\n⚠ Impossible de relancer dans le venv")
                    else:
                        print("\n✗ Impossible d'installer les dépendances")
                        if not AskYesNo("Voulez-vous continuer quand même?", Args.auto_accept):
                            sys.exit(1)
                else:
                    print("\n✗ Impossible de créer l'environnement virtuel")
                    if not AskYesNo("Voulez-vous continuer quand même?", Args.auto_accept):
                        sys.exit(1)
            else:
                print("Tentative de lancement sans environnement virtuel...")
    else:
        print("✓ Environnement virtuel actif")

        # Mise à jour automatique des dépendances
        UpdateDependencies()

    # Choix du mode
    Mode = ChooseMode(Args.cli, PresetMode)

    # Lancement du module approprié
    if Mode == "server":
        LaunchServer(Args.cli, Args.auto_accept)
    elif Mode == "client":
        LaunchClient(Args.cli, Args.auto_accept)
    else:
        print(f"✗ Mode inconnu: {Mode}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        Main()
    except KeyboardInterrupt:
        print("\n\n✗ Interruption utilisateur")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Erreur fatale: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
