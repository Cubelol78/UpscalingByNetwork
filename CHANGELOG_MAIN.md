# Changelog - main.py

## Modifications récentes

### Mise à jour automatique des dépendances (2025)

**Problème résolu:**
Lorsque l'utilisateur lançait le projet avec un environnement virtuel déjà actif, les dépendances n'étaient pas vérifiées ni mises à jour automatiquement. Cela pouvait causer des erreurs si de nouvelles dépendances étaient ajoutées (comme PyQt5 pour les GUI).

**Solution implémentée:**

#### 1. Nouvelle fonction `UpdateDependencies()`
```python
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
```

**Fonctionnement:**
- Vérifie et installe automatiquement les dépendances manquantes
- Met à jour les dépendances existantes si nécessaire
- Affiche un message clair selon le résultat
- N'échoue pas si la mise à jour échoue (affiche juste un avertissement)

#### 2. Appel automatique au démarrage

La fonction est appelée automatiquement lorsqu'un environnement virtuel est détecté:

```python
else:
    print("✓ Environnement virtuel actif")

    # Mise à jour automatique des dépendances
    UpdateDependencies()
```

#### 3. Corrections Pylance

- Retiré l'import `Path` qui n'était pas utilisé
- Changé `parse_known_args()` en `parse_args()` car `RemainingArgs` n'était pas utilisé

**Avantages:**
- ✅ Les utilisateurs n'ont plus à se soucier de mettre à jour manuellement les dépendances
- ✅ Évite les erreurs "ModuleNotFoundError" quand de nouvelles dépendances sont ajoutées
- ✅ Particulièrement utile après l'ajout de PyQt5 pour les GUI
- ✅ Installation rapide et silencieuse (capture_output=True)
- ✅ Ne bloque pas le lancement si la mise à jour échoue

**Exemple de sortie:**
```
============================================================
  Système d'upscaling vidéo en réseau - Real-ESRGAN
============================================================

✓ Environnement virtuel actif
Vérification des dépendances...
✓ Dépendances à jour

Mode GUI
Choisissez le mode:
1. Serveur
2. Client
```

**Test:**
```bash
# Test manuel
python3 main.py

# Test de la fonction
python3 -c "from main import UpdateDependencies; UpdateDependencies()"
```

---

**Date:** 2025
**Fichier modifié:** main.py
**Lignes ajoutées:** ~30
**Impact:** Amélioration de l'expérience utilisateur
