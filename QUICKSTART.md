# Guide de démarrage rapide - Upscaling vidéo en réseau

## Installation

### 1. Créer l'environnement virtuel (recommandé)

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows
```

### 2. Installer les dépendances

```bash
pip install -r requirements.txt
```

## Utilisation

### Démarrer le serveur (mode CLI)

```bash
python3 main.py --cli
```

Lors du premier lancement:
1. Choisir "Serveur" (option 1)
2. Le serveur démarre automatiquement
3. Un menu interactif s'affiche

### Menu serveur

```
SERVEUR D'UPSCALING VIDÉO - MENU PRINCIPAL
==========================================================
1. Statut du serveur
2. Clients connectés
3. Ajouter une vidéo
4. File de jobs
5. Statistiques
6. Configuration
0. Arrêter le serveur
==========================================================
```

### Ajouter une vidéo pour upscaling

1. Depuis le menu principal, choisir option **3**
2. Entrer le chemin de la vidéo (ex: `/path/to/video.mp4`)
3. Choisir le facteur d'upscaling (2, 3, ou 4)
4. Choisir le modèle:
   - `realesr-animevideov3` - Pour vidéos anime
   - `realesrgan-x4plus-anime` - Pour anime (optimisé)
   - `realesrgan-x4plus` - Pour vidéos générales

### Surveiller la progression

- **Option 1**: Statut du serveur - Vue d'ensemble
- **Option 4**: File de jobs - Détails de chaque job
- **Option 5**: Statistiques - Statistiques globales

## Architecture du système

```
Serveur                          Client(s)
   |                                |
   |--- Accepte connexions -------->|
   |<-- Handshake + Auth -----------|
   |                                |
   |--- Envoie batch (images) ----->|
   |                                |
   |                            [Upscaling]
   |                                |
   |<-- Résultats (upscalées) ------|
   |                                |
   [Réassemble vidéo]
   |
   └--> Vidéo finale (work/output/)
```

## Structure des dossiers de travail

```
work/
├── input/          # Vidéos à traiter (optionnel)
├── frames/         # Images extraites (temporaire)
│   └── <video_id>/
├── audio/          # Pistes audio extraites
│   └── <video_id>/
├── subtitles/      # Sous-titres extraits
│   └── <video_id>/
├── upscaled/       # Images upscalées (temporaire)
│   └── <video_id>/
├── output/         # Vidéos finales ✓
└── temp/           # Fichiers temporaires
```

## Configuration

Fichier: `config/default_config.json`

```json
{
  "server": {
    "ip": "0.0.0.0",
    "port": 8765,
    "password": "",
    "work_directory": "./work",
    "batch_size": 100
  },
  "processing": {
    "upscale_factor": 4,
    "model": "realesr-animevideov3"
  }
}
```

### Paramètres importants

- **ip**: Adresse d'écoute (`0.0.0.0` = toutes interfaces)
- **port**: Port du serveur (défaut: 8765)
- **password**: Mot de passe pour les clients (vide = pas de mot de passe)
- **batch_size**: Nombre d'images par paquet (ajuster selon RAM)
- **upscale_factor**: Facteur d'upscaling par défaut (2, 3, ou 4)

## Modèles disponibles

Le projet inclut les modèles Real-ESRGAN suivants:

| Modèle | Usage | Facteurs |
|--------|-------|----------|
| `realesr-animevideov3` | Vidéos anime | x2, x3, x4 |
| `realesrgan-x4plus-anime` | Anime optimisé | x4 |
| `realesrgan-x4plus` | Vidéos générales | x4 |

## Exemple complet

### 1. Démarrer le serveur

```bash
python3 main.py --cli
> Choisissez le mode: 1 (Serveur)
```

### 2. Vérifier le statut

```
Menu > 1 (Statut)

État: ✓ En ligne
Adresse: 0.0.0.0:8765
Clients connectés: 0
Répertoire de travail: ./work
```

### 3. Ajouter une vidéo

```
Menu > 3 (Ajouter une vidéo)

Chemin de la vidéo: /home/user/video.mp4
Facteur d'upscaling: 4
Modèle: 1 (realesr-animevideov3)

✓ Vidéo ajoutée à la file d'attente
ID: abc123...
```

### 4. Connecter des clients

Sur d'autres machines (ou la même):
```bash
python3 main.py --cli
> Choisissez le mode: 2 (Client)
> Connexion au serveur: <IP_SERVEUR>:8765
```

### 5. Suivre la progression

```
Menu > 4 (File de jobs)

📹 JOB EN COURS:
  ID: abc123...
  Statut: processing
  Progression: 45.2%
  Batches: 45/100
```

### 6. Récupérer la vidéo

Une fois terminée:
```
Sortie: work/output/abc123_x4.mp4
```

## Résolution de problèmes

### Le serveur ne démarre pas

- Vérifier que le port 8765 n'est pas déjà utilisé
- Vérifier les permissions sur le répertoire de travail
- Consulter les logs: `logs/Server.log`

### Pas de clients connectés

- Vérifier le pare-feu (autoriser port 8765)
- Vérifier que le client utilise la bonne IP
- Vérifier le mot de passe (si configuré)

### Erreur "FFmpeg non trouvé"

```bash
pip install imageio-ffmpeg
```

### Erreur Real-ESRGAN

- Vérifier que les exécutables sont présents:
  - Linux: `realesrgan-ncnn-vulkan-20220424-ubuntu/`
  - Windows: `realesrgan-ncnn-vulkan-20220424-windows/`

## Performance

### Optimisation batch_size

- **Petites vidéos (720p)**: 100-200 images/batch
- **HD (1080p)**: 50-100 images/batch
- **4K**: 20-50 images/batch

Plus le batch est petit, plus la distribution est rapide mais plus il y a d'overhead réseau.

### Facteurs d'upscaling

- **x2**: Rapide, bon pour preview
- **x3**: Compromis qualité/vitesse
- **x4**: Meilleure qualité, plus lent

## Sécurité

### Configuration du mot de passe

Éditer `config/default_config.json`:

```json
{
  "server": {
    "password": "MonMotDePasseSecret123"
  }
}
```

### Chiffrement

Toutes les communications sont automatiquement chiffrées avec:
- **Handshake**: Diffie-Hellman (2048 bits)
- **Messages**: AES-256-GCM

## Support

Pour plus d'informations, consulter:
- `CLAUDE.md` - Spécifications du projet
- `logs/` - Fichiers de logs
- GitHub Issues
