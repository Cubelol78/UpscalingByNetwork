# Système d'Upscaling Vidéo en Réseau

Système distribué d'upscaling vidéo utilisant Real-ESRGAN pour traiter des vidéos en parallèle sur plusieurs ordinateurs.

## 📋 Table des matières

- [Caractéristiques](#caractéristiques)
- [Architecture](#architecture)
- [Installation](#installation)
- [Utilisation](#utilisation)
- [Configuration](#configuration)
- [Documentation](#documentation)
- [Sécurité](#sécurité)

## ✨ Caractéristiques

### Serveur
- ✅ Gestion de file d'attente FIFO pour vidéos
- ✅ Extraction automatique audio multi-pistes et sous-titres
- ✅ Distribution intelligente des batches aux clients
- ✅ Monitoring en temps réel de la progression
- ✅ Réassemblage automatique avec audio et sous-titres
- ✅ Support encodage AV1 (optionnel)
- ✅ Interface CLI interactive
- ✅ **Interface graphique (GUI) PyQt5**
- ✅ **Interface Web (FastAPI + Vanilla JS) - Port 8780**
- ✅ Base de données SQLite pour tracking
- ✅ Gestion des timeouts et retry automatique
- ✅ WebSocket temps réel pour monitoring
- ✅ Upload vidéo via web UI

### Client
- ✅ Connexion sécurisée au serveur
- ✅ Upscaling local avec Real-ESRGAN
- ✅ Gestion des serveurs favoris
- ✅ Interface CLI simple
- ✅ **Interface graphique (GUI) PyQt5**
- ✅ **Interface Web (FastAPI + Vanilla JS) - Port 8781**
- ✅ Heartbeat automatique
- ✅ Nettoyage automatique des fichiers temporaires
- ✅ WebSocket temps réel pour monitoring
- ✅ Configuration de performance web

### Sécurité
- 🔒 Handshake Diffie-Hellman (2048 bits)
- 🔒 Chiffrement AES-256-GCM
- 🔒 Authentification par mot de passe
- 🔒 Communication end-to-end chiffrée

## 🏗️ Architecture

```
┌─────────────────────┐
│   Main.py (CLI)     │
│  Point d'entrée     │
└──────────┬──────────┘
           │
     ┌─────┴─────┐
     │           │
     ▼           ▼
┌─────────┐  ┌─────────┐
│ Serveur │  │ Client  │
└────┬────┘  └────┬────┘
     │            │
     │  Réseau    │
     │  Chiffré   │
     └────────────┘
```

### Pipeline de traitement

```
1. SERVEUR: Réception vidéo
   └─→ Extraction (audio, sous-titres, métadonnées)
   └─→ Découpage en images (frames)
   └─→ Création de batches (100 images/batch)

2. DISTRIBUTION
   ├─→ Client 1: Batch 1 → Upscaling → Retour
   ├─→ Client 2: Batch 2 → Upscaling → Retour
   └─→ Client N: Batch N → Upscaling → Retour

3. SERVEUR: Réassemblage
   └─→ Images upscalées → Vidéo
   └─→ Réintégration audio + sous-titres
   └─→ Encodage AV1 (optionnel)
   └─→ Vidéo finale ✓
```

## 📦 Installation

### Prérequis

- Python 3.8+
- Linux (Ubuntu 24.04) ou Windows

### Installation rapide

```bash
# Cloner le repository
git clone <repository_url>
cd UpscalingByNetwork

# Créer l'environnement virtuel (recommandé)
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows

# Installer les dépendances
pip install -r requirements.txt
```

### Vérification

```bash
# Tester l'installation
python3 main.py --cli
```

## 🚀 Utilisation

### Mode Web UI (Interface web) - Nouveau! 🎨

**Serveur Web:**
- Adresse: `http://localhost:8780`
- Interface moderne avec design Glassmorphism
- Dashboard temps réel via WebSocket
- Gestion complète des jobs, clients, configuration
- Upload vidéo direct
- Authentication par mot de passe (optionnel)

**Client Web:**
- Adresse: `http://localhost:8781`
- Monitoring temps réel des batches
- Gestion des serveurs sauvegardés
- Configuration de performance
- Logs streaming

**Accès direct:**
```bash
# Les interfaces web démarrent automatiquement avec le serveur/client
# Serveur: http://localhost:8780
# Client: http://localhost:8781
```

---

### Mode GUI (Interface graphique PyQt5)

**Démarrer le serveur avec GUI:**
```bash
python3 main.py
> Choisir: 1 (Serveur)
# L'interface graphique s'ouvre automatiquement
```

**Démarrer le client avec GUI:**
```bash
python3 main.py
> Choisir: 2 (Client)
# L'interface graphique s'ouvre automatiquement
```

**Fonctionnalités GUI:**
- 📊 Monitoring en temps réel
- 🎨 Interface intuitive et moderne
- 📈 Graphiques de progression
- 🔧 Configuration visuelle
- 💾 Gestion des serveurs favoris

**Documentation complète:** Voir [GUI_GUIDE.md](GUI_GUIDE.md)

---

### Mode CLI (Ligne de commande)

**Démarrer le serveur en CLI:**

```bash
python3 main.py --cli
> Choisir: 1 (Serveur)
```

Menu serveur:
- `1` - Statut du serveur
- `2` - Clients connectés
- `3` - Ajouter une vidéo
- `4` - File de jobs
- `5` - Statistiques
- `6` - Configuration
- `0` - Arrêter

### Démarrer un client

```bash
python3 main.py --cli
> Choisir: 2 (Client)
> Connecter à un serveur
```

Menu client:
- `1` - Connecter à un serveur
- `2` - Serveurs sauvegardés
- `3` - Ajouter un serveur
- `0` - Quitter

### Exemple complet

#### Sur la machine serveur:

```bash
# 1. Démarrer le serveur
python3 main.py --cli
> 1 (Serveur)

# 2. Ajouter une vidéo
Menu > 3
Chemin: /home/user/video.mp4
Facteur: 4
Modèle: 1 (realesr-animevideov3)

# 3. Vérifier le statut
Menu > 1
État: ✓ En ligne
Clients connectés: 0  # En attente de clients
```

#### Sur les machines clientes:

```bash
# Se connecter au serveur
python3 main.py --cli
> 2 (Client)
> 1 (Connecter)
> Adresse: 192.168.1.100
> Port: 8765
> Mot de passe: (vide)

# Le client traite automatiquement les batches
📊 Statut: processing
🖼️  Traitement batch: abc123...
✓ Batch terminé
```

## ⚙️ Configuration

Fichier: `config/default_config.json`

```json
{
  "server": {
    "ip": "0.0.0.0",           // Toutes interfaces
    "port": 8765,              // Port d'écoute
    "password": "",            // Mot de passe (vide = aucun)
    "work_directory": "./work",
    "batch_size": 100          // Images par batch
  },
  "processing": {
    "upscale_factor": 4,       // 2, 3, ou 4
    "model": "realesr-animevideov3"
  }
}
```

### Configuration réseau

Pour permettre des clients distants:

1. **Serveur**:
   - Configurer `"ip": "0.0.0.0"` (écoute sur toutes interfaces)
   - Ouvrir le port 8765 dans le pare-feu
   - Optionnel: Définir un mot de passe

2. **Client**:
   - Utiliser l'IP publique/locale du serveur
   - Même port (défaut: 8765)

### Modèles disponibles

| Modèle | Usage | Facteurs | Performance |
|--------|-------|----------|-------------|
| `realesr-animevideov3` | Vidéos anime | x2, x3, x4 | Rapide |
| `realesrgan-x4plus-anime` | Anime optimisé | x4 | Moyenne |
| `realesrgan-x4plus` | Vidéos générales | x4 | Moyenne |

### Optimisation batch_size

Ajuster selon la RAM disponible:

- **720p**: 100-200 images/batch
- **1080p**: 50-100 images/batch
- **4K**: 20-50 images/batch

## 📁 Structure du projet

```
UpscalingByNetwork/
├── main.py                    # Point d'entrée unique
├── requirements.txt           # Dépendances Python
├── QUICKSTART.md             # Guide de démarrage rapide
├── README.md                 # Ce fichier
│
├── config/
│   └── default_config.json   # Configuration par défaut
│
├── shared/                   # Code partagé serveur/client
│   ├── protocol/
│   │   ├── messages.py      # Protocole de messages
│   │   └── encryption.py    # Chiffrement E2E
│   └── utils/
│       ├── logger.py        # Système de logging
│       └── constants.py     # Constantes
│
├── server/                   # Serveur
│   ├── core/
│   │   ├── server.py        # Serveur TCP asyncio
│   │   ├── client_manager.py
│   │   ├── video_processor.py
│   │   ├── batch_distributor.py
│   │   └── job_manager.py
│   ├── database/
│   │   ├── db_manager.py    # SQLite
│   │   └── models.py
│   ├── utils/
│   │   ├── ffmpeg_handler.py
│   │   └── realesrgan_handler.py
│   ├── gui/
│   │   └── server_window.py # Interface PyQt5
│   ├── cli/
│   │   └── server_cli.py    # Interface CLI
│   └── web/                 # Interface Web (NOUVEAU)
│       ├── server_web.py    # FastAPI backend (port 8780)
│       └── static/
│           ├── index.html   # UI HTML5 glassmorphism
│           ├── style.css    # Design moderne
│           └── app.js       # Logic vanilla JS + WebSocket
│
├── client/                   # Client
│   ├── core/
│   │   ├── client.py        # Client principal
│   │   ├── connection.py    # Connexion serveur
│   │   └── processor.py     # Traitement local
│   ├── utils/
│   │   └── realesrgan_handler.py
│   ├── gui/
│   │   └── client_window.py # Interface PyQt5
│   ├── cli/
│   │   └── client_cli.py    # Interface CLI
│   └── web/                 # Interface Web (NOUVEAU)
│       ├── client_web.py    # FastAPI backend (port 8781)
│       └── static/
│           ├── index.html   # UI HTML5 glassmorphism
│           ├── style.css    # Design moderne
│           └── app.js       # Logic vanilla JS + WebSocket
│
└── realesrgan-ncnn-vulkan-*/  # Exécutables Real-ESRGAN
    ├── models/               # Modèles AI
    └── realesrgan-ncnn-vulkan
```

## 📚 Documentation

- **[GUI_GUIDE.md](GUI_GUIDE.md)** - Guide complet des interfaces graphiques (PyQt5)
- **[QUICKSTART.md](QUICKSTART.md)** - Guide de démarrage rapide (CLI)
- **[TESTING.md](TESTING.md)** - Guide de test complet
- **[DEVELOPMENT_SUMMARY.md](DEVELOPMENT_SUMMARY.md)** - Résumé du développement
- **[CLAUDE.md](CLAUDE.md)** - Spécifications détaillées du projet
- **Logs** - Consultez `logs/server.log` et `logs/client.log`

## 🎨 Interface Web (Nouveau!)

Les interfaces web offrent une alternative moderne aux CLI et GUI:

### Caractéristiques
- **Design Glassmorphism** - Interface moderne avec backdrop-filter blur, gradients et glow effects
- **Temps réel** - WebSocket pour monitoring en direct (rafraîchissement 1s)
- **Responsive** - Compatible mobile et desktop
- **Sans dépendances externes** - HTML5 vanilla JS, CSS pur, FastAPI backend
- **Dark/Light mode** - Adaptation automatique aux préférences système

### Serveur Web (Port 8780)
- Dashboard avec statistiques (clients, vidéos, batches)
- Liste des clients connectés avec statut détaillé
- Gestion des jobs (création, annulation, suppression)
- Configuration serveur (réseau, sécurité, traitement)
- Upload vidéo direct avec progress bar
- Webhooks Discord intégrés
- Authentication par mot de passe (optionnel)

### Client Web (Port 8781)
- État de connexion au serveur
- Monitoring temps réel des batches en cours
- Logs streaming (50 derniers logs)
- Gestion des serveurs sauvegardés
- Configuration de performance (tile size, threads)
- Webhooks Discord intégrés

### Architecture Web
```
Frontend (Vanilla JS):
├── index.html      (370 lignes) - Markup HTML5
├── style.css       (500 lignes) - Glassmorphism design
└── app.js          (560 lignes) - WebSocket + API fetch + rendu DOM

Backend (FastAPI):
├── server_web.py   (665 lignes) - Routes REST + WebSocket
└── client_web.py   (400 lignes) - Routes REST + WebSocket
```

### SVG Icons
- Remplacement de tous les emojis par SVG inline
- Style Feather/Lucide (stroke-based)
- Héritent la couleur du texte (`currentColor`)

## 🔒 Sécurité

### Handshake

1. Client génère une clé DH publique/privée
2. Client envoie sa clé publique au serveur
3. Serveur génère sa propre paire de clés
4. Serveur envoie sa clé publique au client
5. Les deux calculent la clé partagée (identique)
6. Toutes les communications ultérieures utilisent AES-256-GCM

### Authentification

- Mot de passe hashé avec PBKDF2-SHA256 (100k itérations)
- Transmission chiffrée avec la clé partagée
- Rejet immédiat en cas d'échec

### Communication

- Tous les messages après handshake sont chiffrés
- AES-256-GCM avec authentification
- Protection contre replay attacks et tampering

## 🐛 Résolution de problèmes

### Le serveur ne démarre pas

```bash
# Vérifier le port
lsof -i :8765  # Linux
netstat -an | grep 8765  # Windows

# Changer le port dans config/default_config.json
{
  "server": {
    "port": 9876
  }
}
```

### Clients ne peuvent pas se connecter

1. Vérifier le pare-feu:
   ```bash
   # Linux
   sudo ufw allow 8765/tcp

   # Windows
   # Panneau de configuration > Pare-feu > Autoriser une app
   ```

2. Vérifier l'IP du serveur:
   ```bash
   # Linux/Mac
   ip addr show
   ifconfig

   # Windows
   ipconfig
   ```

3. Tester la connexion:
   ```bash
   telnet <server_ip> 8765
   # ou
   nc -zv <server_ip> 8765
   ```

### Erreur FFmpeg

```bash
# Installer/Réinstaller
pip install --upgrade imageio-ffmpeg
```

### Erreur Real-ESRGAN

Vérifier que les exécutables sont présents:
```bash
ls -la realesrgan-ncnn-vulkan-20220424-ubuntu/realesrgan-ncnn-vulkan
ls -la realesrgan-ncnn-vulkan-20220424-windows/realesrgan-ncnn-vulkan.exe
```

## 🚧 Limitations connues

- Une seule vidéo traitée à la fois (FIFO)
- Nécessite Vulkan pour GPU (sinon CPU, plus lent)
- Encodage AV1 très lent (désactivé par défaut)
- Taille max message: 100 MB

## 🎯 Roadmap

- [x] GUI (PyQt5) ✅
- [x] Interface Web temps réel ✅
- [ ] Support multi-vidéos simultanées
- [ ] Compression réseau optimisée
- [ ] Mode cluster (multi-serveurs)
- [ ] Support Docker
- [ ] API REST avancée
- [ ] Authentification multi-utilisateur
- [ ] Téléchargement vidéo final depuis web UI

## 📝 License

Ce projet est développé pour un usage personnel/éducatif.

## 🙏 Remerciements

- **Real-ESRGAN** - xinntao et al.
- **FFmpeg** - Équipe FFmpeg
- **imageio-ffmpeg** - almarklein

## 📧 Contact

Pour questions ou bugs, ouvrir une issue sur GitHub.

---

**Développé avec ❤️ et Claude Code**
