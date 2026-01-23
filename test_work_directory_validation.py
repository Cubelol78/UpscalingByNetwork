#!/usr/bin/env python3
"""
Script de test pour la validation du répertoire de travail.
Démontre les différents scénarios de validation et gestion d'erreurs.
"""

import os
import tempfile
from pathlib import Path
from shared.utils.path_validator import ValidateWorkDirectory, NormalizePath, GetDefaultWorkDirectory


def print_result(test_name: str, result):
    """Affiche le résultat d'un test de validation"""
    print(f"\n{'='*60}")
    print(f"Test: {test_name}")
    print(f"{'='*60}")
    print(f"Valide: {result.is_valid}")
    if not result.is_valid:
        print(f"Code d'erreur: {result.error_code}")
        print(f"Message: {result.error_message}")
        if result.suggested_fix:
            print(f"Solution suggérée: {result.suggested_fix}")


def run_tests():
    """Exécute une série de tests de validation"""

    print("\n" + "="*60)
    print("Tests de validation du répertoire de travail")
    print("="*60)

    # Test 1: Chemin vide
    print_result(
        "Chemin vide",
        ValidateWorkDirectory("")
    )

    # Test 2: Chemin valide qui existe (/tmp)
    print_result(
        "Chemin valide existant (/tmp)",
        ValidateWorkDirectory("/tmp")
    )

    # Test 3: Chemin trop long
    long_path = "/tmp/" + "a" * 5000
    print_result(
        "Chemin trop long",
        ValidateWorkDirectory(long_path)
    )

    # Test 4: Chemin avec caractères invalides (Windows)
    if os.name == 'nt':
        print_result(
            "Chemin avec caractères invalides",
            ValidateWorkDirectory("/tmp/test<>:file")
        )

    # Test 5: Chemin non absolu
    print_result(
        "Chemin relatif",
        ValidateWorkDirectory("relative/path")
    )

    # Test 6: Chemin pointe vers un fichier
    test_file = "/tmp/test_file_not_dir.txt"
    try:
        with open(test_file, 'w') as f:
            f.write("test")
        print_result(
            "Chemin pointe vers un fichier",
            ValidateWorkDirectory(test_file)
        )
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)

    # Test 7: Permissions insuffisantes (tentative d'accès à /root si pas root)
    if os.getuid() != 0:  # Pas root
        print_result(
            "Permissions insuffisantes (/root)",
            ValidateWorkDirectory("/root/test_no_permission")
        )

    # Test 8: Répertoire parent n'existe pas
    print_result(
        "Parent inexistant",
        ValidateWorkDirectory("/nonexistent/parent/child")
    )

    # Test 9: Création d'un nouveau répertoire
    test_new_dir = "/tmp/test_new_work_dir_12345"
    if os.path.exists(test_new_dir):
        os.rmdir(test_new_dir)

    result = ValidateWorkDirectory(test_new_dir, create_if_missing=True)
    print_result(
        "Création nouveau répertoire",
        result
    )

    # Vérifie que le répertoire a été créé
    if result.is_valid:
        print(f"Répertoire créé: {os.path.exists(test_new_dir)}")
        if os.path.exists(test_new_dir):
            os.rmdir(test_new_dir)

    # Test 10: Normalisation de chemin
    print(f"\n{'='*60}")
    print("Test: Normalisation de chemins")
    print(f"{'='*60}")

    test_paths = [
        "~/Documents/work",
        "/tmp/../tmp/work",
        "/tmp/./work",
        "/tmp/work/",
    ]

    for path in test_paths:
        normalized = NormalizePath(path)
        print(f"{path:30} -> {normalized}")

    # Test 11: Répertoire par défaut
    print(f"\n{'='*60}")
    print("Répertoire par défaut")
    print(f"{'='*60}")
    default_dir = GetDefaultWorkDirectory()
    print(f"Répertoire par défaut: {default_dir}")
    result = ValidateWorkDirectory(default_dir, create_if_missing=True)
    print(f"Valide: {result.is_valid}")

    print(f"\n{'='*60}")
    print("Tests terminés")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    run_tests()
