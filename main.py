#!/usr/bin/env python3
"""
Point d'entrée principal du système d'upscaling vidéo en réseau
Gère la création d'environnement virtuel et le lancement serveur/client
"""

import sys
import os
import subprocess
import argparse


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


def AskYesNo(Question):
    """Demande une réponse oui/non à l'utilisateur"""
    while True:
        Response = input(f"{Question} (oui/non): ").strip().lower()
        if Response in ["oui", "o", "yes", "y"]:
            return True
        elif Response in ["non", "n", "no"]:
            return False
        else:
            print("Réponse invalide. Veuillez répondre 'oui' ou 'non'")


def RestartInVenv(VenvPath, Args):
    """Redémarre le script dans l'environnement virtuel"""
    if sys.platform == "win32":
        PythonPath = os.path.join(VenvPath, "Scripts", "python.exe")
    else:
        PythonPath = os.path.join(VenvPath, "bin", "python")

    # Relance le script avec le Python du venv
    ScriptPath = os.path.abspath(__file__)
    os.execv(PythonPath, [PythonPath, ScriptPath] + Args)


def ChooseMode(CliMode):
    """Demande à l'utilisateur quel mode lancer (serveur ou client)"""
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


def LaunchServer(CliMode):
    """Lance le serveur"""
    print("\n" + "="*60)
    print("Lancement du serveur d'upscaling")
    print("="*60)

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


def LaunchClient(CliMode):
    """Lance le client"""
    print("\n" + "="*60)
    print("Lancement du client d'upscaling")
    print("="*60)

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
        description="Système d'upscaling vidéo distribué avec Real-ESRGAN"
    )
    Parser.add_argument(
        "--cli",
        action="store_true",
        help="Lance l'interface en ligne de commande au lieu de la GUI"
    )
    Args = Parser.parse_args()

    # Vérification environnement virtuel
    VenvPath = os.path.join(os.path.dirname(__file__), "venv")

    if not CheckVirtualEnv():
        print("\n⚠ Aucun environnement virtuel Python détecté")

        if os.path.exists(VenvPath):
            print(f"Un environnement virtuel existe déjà dans: {VenvPath}")
            if AskYesNo("Voulez-vous l'utiliser?"):
                # Redémarre dans le venv existant
                RestartInVenv(VenvPath, sys.argv[1:])
            else:
                print("Tentative de lancement sans environnement virtuel...")
        else:
            if AskYesNo("Voulez-vous créer un environnement Python pour ce logiciel?"):
                if CreateVirtualEnv(VenvPath):
                    if InstallDependencies(VenvPath):
                        print("\n✓ Environnement prêt. Redémarrage dans le venv...")
                        # Redémarre dans le nouveau venv
                        RestartInVenv(VenvPath, sys.argv[1:])
                    else:
                        print("\n✗ Impossible d'installer les dépendances")
                        if not AskYesNo("Voulez-vous continuer quand même?"):
                            sys.exit(1)
                else:
                    print("\n✗ Impossible de créer l'environnement virtuel")
                    if not AskYesNo("Voulez-vous continuer quand même?"):
                        sys.exit(1)
            else:
                print("Tentative de lancement sans environnement virtuel...")
    else:
        print("✓ Environnement virtuel actif")

        # Mise à jour automatique des dépendances
        UpdateDependencies()

    # Choix du mode
    Mode = ChooseMode(Args.cli)

    # Lancement du module approprié
    if Mode == "server":
        LaunchServer(Args.cli)
    elif Mode == "client":
        LaunchClient(Args.cli)
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
