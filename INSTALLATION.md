# Installation et Démarrage - UpscalingByNetwork

## 🔍 Diagnostic du Problème

### Symptôme
Lorsque vous lancez `server/main.py`, un terminal apparaît brièvement puis disparaît immédiatement sans lancer l'application.

### Cause Identifiée
Le serveur se fermait immédiatement en raison de **dépendances Python manquantes** :
- `psutil` - Surveillance système
- `PyQt5` - Framework GUI
- `qasync` - Async pour Qt
- `cryptography` - Sécurité
- Et autres...

Le code détecte les dépendances manquantes, affiche un message d'erreur, puis se ferme. Comme la fenêtre se ferme trop vite, vous ne voyez pas l'erreur.

---

## ✅ Solution : Utiliser un Environnement Virtuel

Python sur Linux moderne utilise des "environnements gérés" qui empêchent l'installation globale de packages pour éviter de casser le système. La solution est d'utiliser un **environnement virtuel**.

### Option 1 : Scripts de Lancement Automatiques (RECOMMANDÉ)

Nous avons créé des scripts qui gèrent tout automatiquement :

#### Démarrer avec GUI (Interface Graphique)
```bash
./start_server.sh
```

#### Démarrer en mode CLI (Sans interface graphique)
```bash
./start_server_cli.sh
```

**Ces scripts font automatiquement :**
1. Créent l'environnement virtuel si nécessaire
2. Installent toutes les dépendances
3. Lancent le serveur

---

### Option 2 : Installation Manuelle

Si vous préférez installer manuellement :

#### 1. Créer l'environnement virtuel
```bash
cd /DATA-2T/UpscalingByNetwork
python3 -m venv venv
```

#### 2. Activer l'environnement virtuel
```bash
source venv/bin/activate
```

#### 3. Installer les dépendances
```bash
pip install -r server/requirements.txt
```

#### 4. Lancer le serveur
```bash
# Mode GUI (auto-détection de l'affichage)
python server/main.py

# Mode CLI
python server/main.py --no-gui

# Mode headless (sans interface)
python server/main.py --no-gui --non-interactive

# Mode daemon (service en arrière-plan)
python server/main.py --daemon
```

---

## 🖥️ Modes de Démarrage Disponibles

### 1. Mode GUI (Interface Graphique)
```bash
./venv/bin/python server/main.py
```
- Détecte automatiquement si un affichage X11/Wayland est disponible
- Lance l'interface PyQt5 si possible
- Sinon, bascule automatiquement en mode CLI

**Prérequis :**
- Variable `$DISPLAY` ou `$WAYLAND_DISPLAY` définie
- Serveur X11 ou Wayland en cours d'exécution
- Dépendances GUI installées (PyQt5, qasync)

### 2. Mode CLI (Interface en ligne de commande)
```bash
./venv/bin/python server/main.py --no-gui
```
- Interface Rich en ligne de commande
- Affichage en temps réel des statistiques
- Fonctionne sans affichage graphique

### 3. Mode Headless (Minimal)
```bash
./venv/bin/python server/main.py --no-gui --non-interactive
```
- Sortie minimale (logs seulement)
- Parfait pour serveurs sans interface
- Idéal pour Docker/conteneurs

### 4. Mode Daemon (Service)
```bash
./venv/bin/python server/main.py --daemon
```
- Exécution en arrière-plan
- Compatible systemd
- Gestion PID file

---

## 🔧 Options de Configuration

### Port et Adresse
```bash
./venv/bin/python server/main.py --host 0.0.0.0 --port 9000
```

### Niveau de Log
```bash
./venv/bin/python server/main.py --log-level DEBUG
```

### Fichier de Configuration
```bash
./venv/bin/python server/main.py --config server_config.json
```

---

## 📝 Vérification de l'Installation

### Tester que les dépendances sont installées
```bash
./venv/bin/python -c "import PyQt5; import qasync; import psutil; print('✅ Toutes les dépendances sont installées')"
```

### Afficher l'aide du serveur
```bash
./venv/bin/python server/main.py --help
```

### Vérifier l'affichage disponible
```bash
echo $DISPLAY          # Devrait afficher :0, :1, etc.
echo $WAYLAND_DISPLAY  # Ou wayland-0
```

---

## 🐛 Dépannage

### Problème : "No module named 'PyQt5'"
**Solution :** L'environnement virtuel n'est pas activé ou les dépendances ne sont pas installées
```bash
source venv/bin/activate
pip install -r server/requirements.txt
```

### Problème : Terminal se ferme immédiatement
**Solution :** Utilisez les scripts de lancement ou lancez avec des logs :
```bash
./venv/bin/python server/main.py --log-level DEBUG 2>&1 | tee server_log.txt
```

### Problème : "Display not available"
**Solution :** Utilisez le mode CLI ou headless :
```bash
./start_server_cli.sh
```

### Problème : Permission refusée
**Solution :** Rendez les scripts exécutables :
```bash
chmod +x start_server.sh start_server_cli.sh
```

---

## 📦 Dépendances Installées

### Core
- `websockets` - Communication WebSocket
- `cryptography` - Chiffrement
- `psutil` - Surveillance système
- `requests` - Requêtes HTTP

### GUI
- `PyQt5` - Framework interface graphique
- `qasync` - Intégration asyncio/Qt
- `qdarkstyle` - Thème sombre
- `pyqtgraph` - Graphiques

### CLI
- `rich` - Interface CLI enrichie
- `click` - Parser de commandes
- `colorlog` - Logs colorés

### Traitement
- `Pillow` - Traitement d'images
- `aiohttp` - HTTP asynchrone
- `pycryptodome` - Cryptographie avancée

### Optionnel
- `pynvml` - Détection GPU NVIDIA
- `pywin32` - Support Windows Service (Windows uniquement)

---

## 🚀 Démarrage Rapide

**Pour la plupart des utilisateurs :**
```bash
cd /DATA-2T/UpscalingByNetwork
./start_server.sh
```

**Pour les serveurs sans interface graphique :**
```bash
cd /DATA-2T/UpscalingByNetwork
./start_server_cli.sh
```

**C'est tout ! Le serveur devrait démarrer correctement.**

---

## 📚 Ressources Supplémentaires

- **README.md** - Documentation complète du projet
- **server/requirements.txt** - Liste des dépendances serveur
- **requirements-base.txt** - Dépendances partagées
- **server/config/settings.py** - Configuration serveur

Pour plus d'informations, consultez les logs dans `server/logs/server.log`.
