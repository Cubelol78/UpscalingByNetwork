"""
Gestion des règles de pare-feu Windows
Permet d'ajouter automatiquement les règles nécessaires pour la communication réseau
"""

import os
import sys
import subprocess
import ctypes
from typing import Tuple


def IsWindows() -> bool:
    """Vérifie si on est sur Windows"""
    return sys.platform == "win32"


def IsAdmin() -> bool:
    """Vérifie si le processus a les droits administrateur"""
    if not IsWindows():
        return True  # Sur Linux/Mac, pas besoin de vérification spéciale

    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def FirewallRuleExists(RuleName: str) -> bool:
    """
    Vérifie si une règle de pare-feu existe déjà

    Args:
        RuleName: Nom de la règle

    Returns:
        True si la règle existe
    """
    if not IsWindows():
        return True

    try:
        Result = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule", f"name={RuleName}"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if IsWindows() else 0
        )
        return Result.returncode == 0 and RuleName in Result.stdout
    except Exception:
        return False


def AddFirewallRule(RuleName: str, ProgramPath: str, Direction: str = "in") -> Tuple[bool, str]:
    """
    Ajoute une règle de pare-feu Windows

    Args:
        RuleName: Nom de la règle
        ProgramPath: Chemin vers l'exécutable
        Direction: "in" pour entrant, "out" pour sortant

    Returns:
        Tuple (succès, message)
    """
    if not IsWindows():
        return True, "Non-Windows: pas de règle nécessaire"

    if not IsAdmin():
        return False, "Droits administrateur requis"

    try:
        # Ajoute la règle
        Cmd = [
            "netsh", "advfirewall", "firewall", "add", "rule",
            f"name={RuleName}",
            f"dir={Direction}",
            "action=allow",
            f"program={ProgramPath}",
            "enable=yes",
            "profile=any"
        ]

        Result = subprocess.run(
            Cmd,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        if Result.returncode == 0:
            return True, f"Règle '{RuleName}' ajoutée avec succès"
        else:
            return False, f"Erreur: {Result.stderr}"

    except Exception as e:
        return False, f"Exception: {str(e)}"


def EnsureFirewallRules(AppName: str = "UpscalingNetwork") -> Tuple[bool, str]:
    """
    S'assure que les règles de pare-feu sont configurées pour l'application

    Args:
        AppName: Nom de l'application pour les règles

    Returns:
        Tuple (succès, message)
    """
    if not IsWindows():
        return True, "Non-Windows: pas de configuration nécessaire"

    PythonExe = sys.executable
    RuleNameIn = f"{AppName} - Python (Entrant)"
    RuleNameOut = f"{AppName} - Python (Sortant)"

    Messages = []
    AllSuccess = True

    # Vérifie et ajoute la règle entrante
    if not FirewallRuleExists(RuleNameIn):
        if IsAdmin():
            Success, Msg = AddFirewallRule(RuleNameIn, PythonExe, "in")
            Messages.append(Msg)
            AllSuccess = AllSuccess and Success
        else:
            Messages.append(f"Règle entrante manquante: {RuleNameIn}")
            AllSuccess = False
    else:
        Messages.append(f"Règle entrante OK: {RuleNameIn}")

    # Vérifie et ajoute la règle sortante
    if not FirewallRuleExists(RuleNameOut):
        if IsAdmin():
            Success, Msg = AddFirewallRule(RuleNameOut, PythonExe, "out")
            Messages.append(Msg)
            AllSuccess = AllSuccess and Success
        else:
            Messages.append(f"Règle sortante manquante: {RuleNameOut}")
            AllSuccess = False
    else:
        Messages.append(f"Règle sortante OK: {RuleNameOut}")

    return AllSuccess, "\n".join(Messages)


def RequestFirewallPermission(AppName: str = "UpscalingNetwork") -> Tuple[bool, str]:
    """
    Demande les permissions de pare-feu si nécessaire
    Relance le script en mode administrateur si besoin

    Args:
        AppName: Nom de l'application

    Returns:
        Tuple (succès, message)
    """
    if not IsWindows():
        return True, "Non-Windows"

    RuleNameIn = f"{AppName} - Python (Entrant)"
    RuleNameOut = f"{AppName} - Python (Sortant)"

    # Vérifie si les règles existent déjà
    InExists = FirewallRuleExists(RuleNameIn)
    OutExists = FirewallRuleExists(RuleNameOut)

    if InExists and OutExists:
        return True, "Règles de pare-feu déjà configurées"

    # Si pas admin, on ne peut pas ajouter les règles
    if not IsAdmin():
        return False, (
            "Règles de pare-feu manquantes.\n"
            "Veuillez exécuter l'application en tant qu'administrateur\n"
            "pour configurer automatiquement le pare-feu Windows,\n"
            "ou ajouter manuellement une règle pour Python."
        )

    # On est admin, on ajoute les règles
    return EnsureFirewallRules(AppName)


def ShowFirewallDialog() -> bool:
    """
    Affiche une boîte de dialogue pour configurer le pare-feu (Windows uniquement)

    Returns:
        True si l'utilisateur accepte
    """
    if not IsWindows():
        return True

    try:
        import ctypes
        MessageBox = ctypes.windll.user32.MessageBoxW

        Result = MessageBox(
            None,
            "L'application a besoin d'accéder au réseau.\n\n"
            "Voulez-vous configurer automatiquement le pare-feu Windows ?\n"
            "(Nécessite les droits administrateur)",
            "Configuration du pare-feu",
            0x04 | 0x20  # MB_YESNO | MB_ICONQUESTION
        )

        return Result == 6  # IDYES

    except Exception:
        return False


def RunAsAdmin() -> bool:
    """
    Relance le script actuel en mode administrateur

    Returns:
        True si le relancement a réussi
    """
    if not IsWindows():
        return False

    try:
        Script = sys.argv[0]
        Params = " ".join(sys.argv[1:])

        # Utilise ShellExecuteW pour demander l'élévation
        ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            f'"{Script}" {Params}',
            None,
            1  # SW_SHOWNORMAL
        )

        return True

    except Exception:
        return False
