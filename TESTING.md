# Guide de test - Système d'upscaling distribué

Ce guide permet de tester rapidement le système complet.

## ✅ Tests de base

### 1. Vérifier l'installation

```bash
# Tester les imports
python3 -c "
import sys
sys.path.insert(0, '.')

# Test serveur
from server.core.server import UpscalingServer
print('✓ Serveur OK')

# Test client
from client.core.client import UpscalingClient
print('✓ Client OK')

# Test shared
from shared.protocol.messages import MessageFactory
from shared.protocol.encryption import EncryptionHandler
print('✓ Protocole OK')
"
```

### 2. Tester le chiffrement

```bash
python3 shared/protocol/encryption.py
```

Résultat attendu:
```
=== Test du système de chiffrement ===
✓ Client handshake: ✓
✓ Server handshake: ✓
✓ Clés partagées identiques
✓ Chiffrement/déchiffrement réussi
✓ Vérification correct password: ✓
✓ Vérification wrong password: ✓
```

### 3. Tester le logging

```bash
python3 shared/utils/logger.py
```

Résultat attendu: Messages colorés dans la console et fichier `logs/Test.log` créé.

### 4. Tester Real-ESRGAN

```bash
python3 -c "
import sys
sys.path.insert(0, '.')
from server.utils.realesrgan_handler import RealESRGANHandler

handler = RealESRGANHandler()
print('Exécutable:', handler.ExecutablePath)
print('Modèles:', handler.GetAvailableModels())
"
```

Résultat attendu:
```
Exécutable: .../realesrgan-ncnn-vulkan
Modèles: ['realesr-animevideov3-x2', 'realesr-animevideov3-x3', ...]
```

## 🧪 Test du système complet

### Scénario 1: Serveur seul

```bash
# Terminal 1: Démarrer le serveur
python3 main.py --cli
> 1 (Serveur)

# Dans le menu serveur:
> 1 (Statut)
```

Vérifier:
- ✓ Serveur en ligne
- ✓ Port 8765 ouvert
- ✓ 0 clients connectés
- ✓ Base de données créée dans `work/`

### Scénario 2: Client seul (sans serveur)

```bash
# Terminal 1: Démarrer le client
python3 main.py --cli
> 2 (Client)
> 1 (Connecter)
> Adresse: localhost
> Port: 8765
> Mot de passe: (vide)
```

Résultat attendu:
```
✗ Impossible de se connecter au serveur
Connection refused
```

### Scénario 3: Serveur + Client local

#### Terminal 1 - Serveur:
```bash
python3 main.py --cli
> 1 (Serveur)

# Vérifier le statut
Menu > 1

# Le serveur attend des clients...
```

#### Terminal 2 - Client:
```bash
python3 main.py --cli
> 2 (Client)
> 1 (Connecter à un serveur)
> Autre serveur (dernier choix)
> Adresse: localhost
> Port: 8765
> Mot de passe: (vide)
```

Résultat attendu:
```
Connexion au serveur localhost:8765...
✓ Connexion TCP établie
Handshake avec le serveur...
✓ Handshake réussi, clé partagée établie
Authentification...
✓ Authentification réussie
✓ Client authentifié (ID: abc123...)

📊 Statut: idle
```

#### Vérification serveur (Terminal 1):
```
Menu > 2 (Clients connectés)

Clients connectés: 1
1. Client abc123...
   Adresse: 127.0.0.1
   Statut: idle
```

### Scénario 4: Ajout vidéo (simulation)

**Note**: Ce scénario nécessite une vraie vidéo et `imageio-ffmpeg` installé.

#### Installation FFmpeg:
```bash
pip install imageio-ffmpeg
```

#### Terminal 1 - Serveur:
```bash
# Dans le menu serveur
Menu > 3 (Ajouter une vidéo)

# Créer une petite vidéo de test si besoin:
ffmpeg -f lavfi -i testsrc=duration=5:size=320x240:rate=30 test_video.mp4

Chemin: test_video.mp4
Facteur: 2  # x2 pour tester rapidement
Modèle: 1 (realesr-animevideov3)

✓ Vidéo ajoutée (ID: ...)
```

#### Suivi du traitement:
```bash
Menu > 4 (File de jobs)

# Observer la progression:
📹 JOB EN COURS:
  Statut: extracting → distributing → processing → reassembling
  Progression: 0% → 100%
```

#### Terminal 2 - Client:
Le client traite automatiquement les batches:
```
📊 Statut: processing
🖼️  Traitement batch: abc123...
Progression: 1/5 (20.0%)
Progression: 2/5 (40.0%)
...
✓ Batch terminé
📊 Statut: idle
```

#### Récupération résultat:
```bash
ls work/output/

# Devrait contenir:
abc123_x2.mp4  # Vidéo upscalée
```

## 🔧 Tests avancés

### Test 1: Multiple clients

Démarrer plusieurs clients (3+) et ajouter une grande vidéo au serveur.

Observer:
- Distribution équitable des batches
- Progression parallèle
- Heartbeat de tous les clients

### Test 2: Déconnexion client

1. Démarrer serveur + 2 clients
2. Ajouter une vidéo
3. Arrêter brutalement un client (Ctrl+C)

Vérifier:
- Serveur détecte la déconnexion (timeout)
- Batch est réassigné à un autre client
- Traitement continue

### Test 3: Mot de passe serveur

#### Configuration:
Éditer `config/default_config.json`:
```json
{
  "server": {
    "password": "test123"
  }
}
```

#### Test avec bon mot de passe:
```bash
# Client
> Mot de passe: test123
✓ Authentification réussie
```

#### Test avec mauvais mot de passe:
```bash
# Client
> Mot de passe: wrong
✗ Mot de passe incorrect
✗ Authentification échouée
```

### Test 4: Serveurs sauvegardés

```bash
# Client
Menu > 3 (Ajouter un serveur)
Nom: MonServeur
Adresse: 192.168.1.100
Port: 8765
Sauvegarder mot de passe: Oui
Mot de passe: secret123

✓ Serveur 'MonServeur' ajouté

# Vérifier
Menu > 2 (Serveurs sauvegardés)

1. MonServeur
   Adresse: 192.168.1.100:8765
   Mot de passe: Oui

# Connexion rapide
Menu > 1 (Connecter)
> 1 (MonServeur)
```

## 🐛 Tests de robustesse

### Test timeout batch

1. Modifier le timeout dans `shared/utils/constants.py`:
```python
BATCH_TIMEOUT = 10  # 10 secondes au lieu de 300
```

2. Démarrer serveur + client
3. Ajouter une vidéo
4. Arrêter le client au milieu d'un batch

Vérifier:
- Serveur détecte le timeout après 10s
- Batch est marqué en timeout
- Retry automatique si < 3 tentatives

### Test crash serveur

1. Démarrer serveur + clients
2. Arrêter brutalement le serveur (Ctrl+C)

Vérifier:
- Clients détectent la déconnexion
- Messages d'erreur clairs
- Pas de corruption BDD

### Test grosse vidéo

Tester avec une vidéo HD (1080p, 1+ minute):

```bash
# Ajuster batch_size selon RAM
config/default_config.json:
{
  "server": {
    "batch_size": 50  # Pour 1080p
  }
}
```

Observer:
- Utilisation mémoire stable
- Pas de timeout
- Vidéo finale complète

## 📊 Vérification des logs

### Logs serveur:
```bash
tail -f logs/Server.log

# Devrait montrer:
- Connexions clients
- Attribution batches
- Réception résultats
- Progression jobs
```

### Logs client:
```bash
tail -f logs/Client.log

# Devrait montrer:
- Connexion serveur
- Handshake
- Réception batches
- Upscaling progression
- Envoi résultats
```

## ✅ Checklist de validation

### Infrastructure
- [ ] main.py démarre sans erreur
- [ ] Environnement virtuel créé automatiquement
- [ ] Dépendances installées
- [ ] Configuration chargée

### Serveur
- [ ] Démarre sur port 8765
- [ ] Accepte connexions
- [ ] Handshake fonctionne
- [ ] Authentification fonctionne
- [ ] Heartbeat actif
- [ ] Base de données créée
- [ ] Logs écrits

### Client
- [ ] Connecte au serveur
- [ ] Handshake fonctionne
- [ ] Authentification fonctionne
- [ ] Heartbeat envoyé
- [ ] Serveurs favoris sauvegardés
- [ ] Logs écrits

### Traitement
- [ ] Extraction vidéo fonctionne
- [ ] Découpage en images OK
- [ ] Batches créés
- [ ] Distribution aux clients
- [ ] Upscaling fonctionne
- [ ] Résultats reçus
- [ ] Réassemblage OK
- [ ] Audio/sous-titres préservés

### Réseau
- [ ] Messages chiffrés
- [ ] Timeouts respectés
- [ ] Retry fonctionnel
- [ ] Déconnexions gérées
- [ ] Pas de corruption données

## 🎯 Résultats attendus

Après un test complet réussi:

```
work/
├── upscaling_server.db   # Base de données
├── input/                # Vide (vidéos sources externes)
├── frames/               # Vide (nettoyé)
├── audio/                # Vide (nettoyé)
├── subtitles/            # Vide (nettoyé)
├── upscaled/             # Vide (nettoyé)
├── output/               # ✓ Vidéos finales
│   └── abc123_x4.mp4    # Vidéo upscalée
└── temp/                 # Vide

logs/
├── Server.log           # Logs serveur
├── Client.log           # Logs client
└── ...

~/.upscaling_client/
├── servers.json         # Serveurs favoris client
└── temp/                # Fichiers temporaires client
```

## 🔍 Debugging

### Problème: Client ne se connecte pas

```bash
# Vérifier que le serveur écoute
netstat -an | grep 8765
# ou
lsof -i :8765

# Tester la connexion
telnet localhost 8765
# ou
nc -zv localhost 8765
```

### Problème: Erreur FFmpeg

```bash
# Vérifier FFmpeg
python3 -c "
from imageio_ffmpeg import get_ffmpeg_exe
print(get_ffmpeg_exe())
"

# Réinstaller si nécessaire
pip install --upgrade imageio-ffmpeg
```

### Problème: Erreur Real-ESRGAN

```bash
# Vérifier l'exécutable
ls -la realesrgan-ncnn-vulkan-20220424-ubuntu/realesrgan-ncnn-vulkan

# Rendre exécutable (Linux)
chmod +x realesrgan-ncnn-vulkan-20220424-ubuntu/realesrgan-ncnn-vulkan

# Tester directement
./realesrgan-ncnn-vulkan-20220424-ubuntu/realesrgan-ncnn-vulkan -h
```

---

**Tous les tests passent = Système opérationnel! 🎉**
