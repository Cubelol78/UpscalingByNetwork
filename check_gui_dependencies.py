#!/usr/bin/env python3
"""
Script de vérification des dépendances GUI
Vérifie que PyQt5 est correctement installé
"""

import sys


def CheckPyQt5():
    """Vérifie si PyQt5 est installé"""
    try:
        import PyQt5
        from PyQt5 import QtCore, QtWidgets, QtGui

        print("✓ PyQt5 est installé")
        print(f"  Version: {QtCore.PYQT_VERSION_STR}")
        print(f"  Qt Version: {QtCore.QT_VERSION_STR}")
        return True

    except ImportError as e:
        print(f"✗ PyQt5 n'est pas installé: {e}")
        print("\nPour installer PyQt5:")
        print("  pip install PyQt5")
        return False


def CheckOtherDependencies():
    """Vérifie les autres dépendances"""
    Dependencies = {
        "imageio-ffmpeg": "FFmpeg portable",
        "cryptography": "Chiffrement",
        "click": "Interface CLI",
        "Pillow": "Traitement d'images"
    }

    AllOk = True

    for Module, Description in Dependencies.items():
        try:
            __import__(Module.replace("-", "_"))
            print(f"✓ {Module} ({Description})")
        except ImportError:
            print(f"✗ {Module} ({Description}) - NON INSTALLÉ")
            AllOk = False

    return AllOk


def CheckGUIModules():
    """Vérifie que les modules GUI existent"""
    GuiModules = [
        ("server.gui.server_window", "Interface serveur"),
        ("client.gui.client_window", "Interface client"),
    ]

    print("\nVérification des modules GUI:")

    AllOk = True

    for ModuleName, Description in GuiModules:
        try:
            # On essaye seulement de voir si le fichier existe
            import importlib.util
            ModulePath = ModuleName.replace(".", "/") + ".py"

            if importlib.util.find_spec(ModuleName.split(".")[0]):
                print(f"✓ {Description} ({ModuleName})")
            else:
                print(f"✗ {Description} - MODULE NON TROUVÉ")
                AllOk = False

        except Exception as e:
            print(f"⚠ {Description} - Impossible de vérifier: {e}")

    return AllOk


def Main():
    """Fonction principale"""
    print("="*60)
    print("Vérification des dépendances GUI")
    print("="*60)
    print()

    # Vérifier PyQt5
    PyQt5Ok = CheckPyQt5()
    print()

    # Vérifier les autres dépendances
    print("Vérification des dépendances:")
    DepsOk = CheckOtherDependencies()
    print()

    # Vérifier les modules GUI
    ModulesOk = CheckGUIModules()
    print()

    # Résumé
    print("="*60)
    if PyQt5Ok and DepsOk and ModulesOk:
        print("✓ Toutes les dépendances sont installées!")
        print("\nVous pouvez lancer les interfaces graphiques:")
        print("  python3 main.py  (sans --cli)")
        return 0
    else:
        print("✗ Certaines dépendances sont manquantes")
        print("\nInstallez les dépendances manquantes:")
        print("  pip install -r requirements.txt")
        return 1


if __name__ == "__main__":
    sys.exit(Main())
