# Guide d'utilisation des interfaces graphiques (GUI)

## 📋 Table des matières

1. [Installation](#installation)
2. [Lancement](#lancement)
3. [Interface Serveur](#interface-serveur)
4. [Interface Client](#interface-client)
5. [Résolution de problèmes](#résolution-de-problèmes)

---

## Installation

### Prérequis

Les interfaces graphiques utilisent **PyQt5**. Pour installer les dépendances GUI, exécutez:

```bash
# Dans l'environnement virtuel
pip install -r requirements.txt
```

### Vérification de l'installation

Pour vérifier que PyQt5 est correctement installé:

```bash
python3 -c "import PyQt5; print('PyQt5 version:', PyQt5.QtCore.PYQT_VERSION_STR)"
```

---

## Lancement

### Lancer l'interface serveur

**Option 1 - Via main.py:**
```bash
python3 main.py
# Choisir "1" pour Serveur
# L'interface graphique se lancera par défaut
```

**Option 2 - Directement:**
```bash
python3 -m server.gui.server_window
```

### Lancer l'interface client

**Option 1 - Via main.py:**
```bash
python3 main.py
# Choisir "2" pour Client
# L'interface graphique se lancera par défaut
```

**Option 2 - Directement:**
```bash
python3 -m client.gui.client_window
```

### Lancer en mode CLI (sans GUI)

Si vous préférez l'interface en ligne de commande:

```bash
python3 main.py --cli
```

---

## Interface Serveur

### 🖥️ Vue d'ensemble

L'interface serveur est composée de 4 onglets principaux:

#### 1. **Dashboard** 📊
- **Statistiques en temps réel:**
  - Nombre de clients connectés
  - Nombre de clients actifs
  - Vidéos en attente / en traitement
  - Batchs en attente / complétés

- **Activité récente:**
  - Liste des dernières vidéos traitées
  - Statut et progression en temps réel

#### 2. **Clients** 💻
- **Liste des clients connectés:**
  - ID du client (court)
  - Adresse IP:Port
  - Statut (Idle/Processing/Sending/Receiving)
  - Batch en cours de traitement
  - Dernier heartbeat reçu

- **Actions disponibles:**
  - Rafraîchir la liste
  - Déconnecter un client spécifique

#### 3. **Jobs** 🎬
- **File d'attente des vidéos:**
  - ID du job
  - Nom du fichier vidéo
  - Statut (Queued/Extracting/Processing/Reassembling/Completed/Failed)
  - Barre de progression
  - Ratio batchs complétés/total
  - Facteur d'upscaling
  - Modèle utilisé

- **Actions disponibles:**
  - Ajouter une nouvelle vidéo
  - Rafraîchir la liste

##### Ajouter une vidéo:
1. Cliquer sur **"➕ Ajouter une vidéo"**
2. Sélectionner le fichier vidéo (formats supportés: mp4, avi, mkv, mov, flv, wmv)
3. Choisir le facteur d'upscaling (x2, x3, x4)
4. Sélectionner le modèle Real-ESRGAN:
   - `realesr-animevideov3` - Optimisé pour l'animation (recommandé)
   - `realesrgan-x4plus-anime` - Alternative pour l'animation
   - `realesrgan-x4plus` - Généraliste (photos, vidéos réelles)
5. Valider

#### 4. **Configuration** ⚙️
- **Configuration réseau:**
  - Adresse IP d'écoute (0.0.0.0 = toutes les interfaces)
  - Port TCP (défaut: 8765)
  - Mot de passe du serveur (optionnel)

- **Configuration du traitement:**
  - Répertoire de travail (où stocker les fichiers temporaires)
  - Taille des batchs (nombre d'images par paquet)

- **Actions:**
  - Enregistrer la configuration (nécessite un redémarrage)
  - Annuler les modifications

### 🎯 Utilisation typique

1. **Configuration initiale:**
   - Aller dans l'onglet **Configuration**
   - Définir l'IP, le port, et optionnellement un mot de passe
   - Définir le répertoire de travail
   - Enregistrer

2. **Démarrage du serveur:**
   - Cliquer sur **"▶ Démarrer le serveur"**
   - Le statut passe à **"● En cours"** (vert)

3. **Ajouter des vidéos:**
   - Aller dans l'onglet **Jobs**
   - Ajouter une ou plusieurs vidéos

4. **Monitoring:**
   - Suivre la progression dans l'onglet **Dashboard**
   - Surveiller les clients dans l'onglet **Clients**
   - Vérifier l'état des jobs dans l'onglet **Jobs**

5. **Arrêt:**
   - Cliquer sur **"⏹ Arrêter le serveur"**

---

## Interface Client

### 🖥️ Vue d'ensemble

L'interface client est composée de 3 onglets:

#### 1. **Connexion** 🔌
- **Informations du serveur:**
  - Serveur sauvegardé (liste déroulante) ou saisie manuelle
  - Adresse (IP ou hostname)
  - Port (défaut: 8765)
  - Mot de passe (optionnel)

- **Statut de connexion:**
  - Indicateur visuel (● Déconnecté / ● Connecté)

- **Actions:**
  - Se connecter
  - Se déconnecter
  - Sauvegarder le serveur pour une connexion ultérieure

#### 2. **Monitoring** 📊
- **Statistiques:**
  - Batchs traités (compteur)
  - Images traitées (compteur)
  - Batch actuellement en cours
  - Statut du client (Inactif/En attente/Traitement en cours)

- **Activité en cours:**
  - Affiche le batch en traitement
  - Indication du statut

- **Logs récents:**
  - Historique des dernières actions

#### 3. **Serveurs** 💾
- **Liste des serveurs sauvegardés:**
  - Nom du serveur
  - Adresse IP
  - Port

- **Actions:**
  - Ajouter un nouveau serveur
  - Connecter à un serveur sauvegardé
  - Supprimer un serveur de la liste
  - Rafraîchir

### 🎯 Utilisation typique

1. **Première connexion:**
   - Aller dans l'onglet **Connexion**
   - Entrer l'adresse du serveur (IP ou hostname)
   - Entrer le port (défaut: 8765)
   - Entrer le mot de passe si le serveur en requiert un
   - Cliquer sur **"🔌 Se connecter"**
   - Le système demande si vous voulez sauvegarder le serveur

2. **Connexions ultérieures:**
   - Aller dans l'onglet **Connexion**
   - Sélectionner le serveur dans la liste déroulante
   - Cliquer sur **"🔌 Se connecter"**

   **Ou:**
   - Aller dans l'onglet **Serveurs**
   - Cliquer sur **"Connecter"** à côté du serveur souhaité

3. **Monitoring:**
   - Aller dans l'onglet **Monitoring**
   - Suivre l'activité en temps réel

4. **Déconnexion:**
   - Aller dans l'onglet **Connexion**
   - Cliquer sur **"✖ Se déconnecter"**

---

## Résolution de problèmes

### Erreur: ModuleNotFoundError: No module named 'PyQt5'

**Solution:**
```bash
pip install PyQt5
```

### L'interface ne se lance pas

**Vérifications:**
1. PyQt5 est-il installé?
   ```bash
   python3 -c "import PyQt5"
   ```

2. L'environnement virtuel est-il actif?
   ```bash
   which python3
   # Devrait pointer vers venv/bin/python3
   ```

3. Tous les modules sont-ils présents?
   ```bash
   pip install -r requirements.txt
   ```

### Le serveur GUI ne démarre pas

**Vérifications:**
1. Le port est-il déjà utilisé?
   ```bash
   # Linux
   sudo netstat -tulpn | grep 8765

   # macOS
   lsof -i :8765
   ```

2. Les permissions sont-elles correctes pour le répertoire de travail?

3. Les modèles Real-ESRGAN sont-ils présents?
   ```bash
   ls -la realesrgan-ncnn-vulkan-*/
   ```

### Le client ne peut pas se connecter

**Vérifications:**
1. Le serveur est-il démarré?

2. L'adresse IP et le port sont-ils corrects?

3. Un pare-feu bloque-t-il la connexion?
   ```bash
   # Test de connectivité
   telnet <IP_SERVEUR> 8765
   ```

4. Le mot de passe est-il correct?

### L'interface freeze ou ne répond plus

**Cause probable:** Opération bloquante dans le thread principal.

**Solution:**
- Fermer et relancer l'interface
- Vérifier les logs dans le dossier `logs/`:
  ```bash
  tail -f logs/server.log    # Pour le serveur
  tail -f logs/client.log    # Pour le client
  ```

### Les statistiques ne se mettent pas à jour

**Vérifications:**
1. Le serveur/client est-il bien démarré?
2. Y a-t-il des erreurs dans les logs?
3. Essayer de rafraîchir manuellement avec le bouton **"🔄 Rafraîchir"**

---

## 📚 Ressources supplémentaires

- [README.md](README.md) - Documentation générale du projet
- [TESTING.md](TESTING.md) - Guide de test complet
- [QUICKSTART.md](QUICKSTART.md) - Guide de démarrage rapide (CLI)
- [DEVELOPMENT_SUMMARY.md](DEVELOPMENT_SUMMARY.md) - Résumé du développement

---

## 🔧 Structure des fichiers GUI

### Serveur
```
server/gui/
├── __init__.py
├── server_window.py     # Fenêtre principale
├── dashboard_tab.py     # Onglet Dashboard
├── clients_tab.py       # Onglet Clients
├── jobs_tab.py          # Onglet Jobs
└── config_tab.py        # Onglet Configuration
```

### Client
```
client/gui/
├── __init__.py
├── client_window.py     # Fenêtre principale
├── connection_tab.py    # Onglet Connexion
├── monitoring_tab.py    # Onglet Monitoring
└── servers_tab.py       # Onglet Serveurs
```

---

## 💡 Conseils

### Performance

- **Taille des batchs:** Des batchs plus petits (50-100 images) permettent une meilleure distribution mais génèrent plus de trafic réseau.
- **Répertoire de travail:** Utilisez un disque rapide (SSD) pour de meilleures performances.

### Sécurité

- **Mot de passe:** Utilisez toujours un mot de passe fort pour protéger le serveur.
- **Réseau:** Ne pas exposer le serveur directement sur Internet sans VPN ou tunnel sécurisé.

### Stabilité

- **Heartbeat:** Les clients envoient un heartbeat toutes les 10 secondes. Un timeout de 30 secondes déclenche la déconnexion.
- **Reconnexion:** Les clients peuvent se reconnecter automatiquement en cas de déconnexion temporaire.

---

**Dernière mise à jour:** Sprint 10 - GUI Implementation
**Version:** 1.0
