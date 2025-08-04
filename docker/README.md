# UpscalingByNetwork/docker/README.md

# UpscalingByNetwork Docker

## 🐳 Déploiement avec Docker

### Installation rapide

```bash
# Clone du repository
git clone https://github.com/votre-repo/UpscalingByNetwork.git
cd UpscalingByNetwork/docker

# Build et démarrage
docker-compose up -d
```

### Build manuel

```bash
# Build de l'image serveur
docker build -f Dockerfile.server -t upscaling-server ..

# Exécution
docker run -d \
  --name upscaling-server \
  -p 8888:8888 \
  -v $(pwd)/data:/home/upscaling/data \
  upscaling-server
```

### Configuration

Créez un fichier `docker-compose.override.yml` pour personnaliser :

```yaml
version: '3.8'

services:
  upscaling-server:
    environment:
      - SERVER_HOST=0.0.0.0
      - SERVER_PORT=8888
      - BATCH_SIZE=50
      - MAX_CLIENTS=20
    volumes:
      - /path/to/your/videos:/home/upscaling/data/input
      - /path/to/output:/home/upscaling/data/output
```

### Logs

```bash
# Voir les logs
docker-compose logs -f upscaling-server

# Logs en temps réel
docker logs -f upscaling-server
```

### Maintenance

```bash
# Arrêt
docker-compose down

# Mise à jour
docker-compose pull
docker-compose up -d

# Nettoyage
docker-compose down -v
docker system prune
```

## 🔧 Développement

### Build pour développement

```bash
# Build avec cache désactivé
docker build --no-cache -f Dockerfile.server -t upscaling-server-dev ..

# Mode développement avec bind mount
docker run -it \
  -p 8888:8888 \
  -v $(pwd)/..:/home/upscaling/UpscalingByNetwork \
  -v $(pwd)/data:/home/upscaling/data \
  upscaling-server-dev \
  ./start_server.sh --log-level DEBUG
```

### Debugging

```bash
# Shell dans le container
docker exec -it upscaling-server bash

# Tests
docker run --rm \
  -v $(pwd)/..:/home/upscaling/UpscalingByNetwork \
  upscaling-server-dev \
  python3 -m pytest tests/ -v
```

## 📝 Notes

- Le serveur fonctionne en mode console uniquement dans Docker
- PyQt5 nécessite X11 (fourni par Xvfb)
- Les clients se connectent depuis l'extérieur du container
- Vulkan n'est pas supporté dans cette version Docker (CPU seulement)

Pour un support GPU complet, utilisez les versions natives Windows/Linux.