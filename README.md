# NXSlab Backup WebUI

Interface web d'administration pour serveur de sauvegarde — gestion Samba, FTP, sauvegardes SSH distantes et terminal web interactif.

```
  ███╗   ██╗██╗  ██╗███████╗██╗      █████╗ ██████╗
  ████╗  ██║╚██╗██╔╝██╔════╝██║     ██╔══██╗██╔══██╗
  ██╔██╗ ██║ ╚███╔╝ ███████╗██║     ███████║██████╔╝
  ██║╚██╗██║ ██╔██╗ ╚════██║██║     ██╔══██║██╔══██╗
  ██║ ╚████║██╔╝ ██╗███████║███████╗██║  ██║██████╔╝
  ╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝╚═════╝
```

Une solution **complète** et **centralisée** pour gérer les sauvegardes de multiples serveurs distants, partager des données via Samba/FTP et accéder directement aux serveurs via un terminal web.

---

## 📋 Table des matières

- [Fonctionnalités](#fonctionnalités)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Premier démarrage](#premier-démarrage)
- [Configuration](#configuration)
- [Guide des modules](#guide-des-modules)
- [Sauvegardes](#sauvegardes)
- [Accès utilisateurs](#accès-utilisateurs)
- [Sécurité](#sécurité)
- [Troubleshooting](#troubleshooting)
- [Architecture](#architecture)
- [API](#api)
- [Maintenance](#maintenance)
- [FAQ](#faq)

---

## 🎯 Fonctionnalités

| Module | Description |
|--------|-------------|
| **Dashboard** | Métriques système temps réel (CPU, RAM, disques), statut des services, résumé des backups |
| **Backup** | Sauvegardes SSH vers VPS distants, planification cron, compression tar/gzip/bzip2, restore, Docker volumes & bind mounts, MySQL/PostgreSQL, sites web, configs |
| **Samba** | Gestion des partages et utilisateurs Samba, config live, accès fichiers centralisé |
| **FTP** | Gestion des utilisateurs vsftpd, chroot sur DATA_DIR, débit temps réel, statistiques |
| **Fichiers** | Explorateur de fichiers web (upload, download, mkdir, rename, delete, compression) |
| **Terminal** | Terminal SSH web vers les VPS distants via WebSocket, redimensionnement PTY live |
| **Logs** | Journaux centralisés temps réel : Samba, FTP, NXSlab, Auth/SSH, Kernel, Docker, Système |
| **Paramètres** | Gestion des comptes panel, changement de mot de passe, infos capacités système |

---

## 📦 Prérequis

- **Système** : Debian 11+ / Ubuntu 20.04+ (systemd requis)
- **Python** : 3.8+
- **Paquets** : `samba`, `vsftpd`, `curl` (installés automatiquement)
- **Réseau** : SSH sortant vers VPS distants (port 22 ou custom)
- **Accès** : Root pour l'installation
- **Espace** : Suffisant pour les sauvegardes (calculé à l'installation)

### Vérification rapide

```bash
# Vérifier les prérequis
python3 --version     # >= 3.8
systemctl --version  # systemd
ssh -V              # OpenSSH
docker --version    # optionnel, pour sauvegardes Docker
```

---

## 🚀 Installation

### Installation standard

```bash
# Cloner le dépôt
git clone https://git.nxslab.in/Pierre/NXSlab-Bkp
cd NXSlab-Bkp

# Lancer l'installation
sudo bash install.sh
```

**Pendant l'installation, vous serez invité à configurer :**

```
Port web [5080]:                          # Port d'écoute de l'interface
Nom d'utilisateur admin [admin]:          # Compte administrateur
Mot de passe admin:                       # Minimum 8 caractères
Répertoire de données [/srv/nxslab-bkp]: # Où stocker données et backups
nginx détecté — configurer reverse proxy: # Optionnel (oui/non)
Nom de domaine (ex: bkp.example.com):     # Si nginx
```

### Installation avancée (personnalisée)

```bash
# Personnaliser les chemins avant installation
export INSTALL_DIR="/custom/path"
export CONFIG_DIR="/etc/custom"
export DATA_DIR="/mnt/backups"
sudo bash install.sh
```

### Installation sur système sans accès root

```bash
# Installation locale (utilisateur courant)
bash install.sh --local
# Les services seront gérés manuellement, pas de systemd
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python3 app.py  # Lancer directement
```

---

## ⚙️ Premier démarrage

Après l'installation, accédez à l'interface :

```
URL : http://<ip-serveur>:5080
Utilisateur : admin
Mot de passe : (celui configuré à l'installation)
```

### Checklist premier démarrage

- [ ] Vérifier que le service est actif : `systemctl status nxslab-bkp`
- [ ] Se connecter avec le compte admin
- [ ] Configurer au moins un serveur distant (VPS) → menu **Paramètres** → **Serveurs distants**
- [ ] Tester la connexion SSH au VPS
- [ ] Configurer les utilisateurs Samba/FTP si nécessaire
- [ ] Planifier une première sauvegarde test

---

## ⚙️ Configuration

### Configuration initiale (`/etc/nxslab-bkp/config.json`)

Le fichier de configuration contient :

```json
{
  "users": [
    {"username": "admin", "password_hash": "sha256...", "role": "admin"},
    {"username": "viewer", "password_hash": "sha256...", "role": "readonly"}
  ],
  "secret_key": "hex_token_aleatoire",
  "port": 5080,
  "data_dir": "/srv/nxslab-bkp",
  "remotes": [
    {
      "id": "vps01",
      "name": "VPS Principal",
      "host": "vps.example.com",
      "port": 22,
      "user": "root",
      "auth_type": "key",
      "key_path": "/root/.ssh/id_rsa",
      "key_passphrase": null,
      "backup": {...}
    }
  ]
}
```

**Modification du mot de passe admin :**

```bash
# Via l'interface web → Paramètres → Compte
# OU via CLI
sudo python3 -c "
import hashlib, json
with open('/etc/nxslab-bkp/config.json') as f:
    c = json.load(f)
c['users'][0]['password_hash'] = hashlib.sha256(b'nouveau_mot_de_passe').hexdigest()
with open('/etc/nxslab-bkp/config.json', 'w') as f:
    json.dump(c, f)
"
```

### Structure du répertoire de données

```
/srv/nxslab-bkp/
├── backups/                    # Sauvegardes organisées par VPS
│   ├── vps01/                  # ID du VPS
│   │   ├── 2026-05-18_12-00-00/
│   │   │   ├── docker/         # Sauvegardes des conteneurs
│   │   │   │   ├── nextcloud/
│   │   │   │   │   ├── data.tar.gz        # Volume nommé
│   │   │   │   │   ├── config.tar.gz      # Volume nommé
│   │   │   │   │   ├── bind_etc.tar.gz    # Bind mount
│   │   │   │   │   └── inspect.json       # Metadata Docker
│   │   │   ├── databases/      # MySQL, PostgreSQL dumps
│   │   │   │   ├── mysql_wordpress.sql.gz
│   │   │   │   └── pgsql_api.sql.gz
│   │   │   ├── websites/       # Répertoires web
│   │   │   │   ├── var_www_html.tar.gz
│   │   │   ├── configs/        # Configurations système
│   │   │   │   ├── etc_nginx.tar.gz
│   │   │   │   └── etc_docker.tar.gz
│   │   │   └── manifest.json   # Métadonnées et statut
│   │   ├── 2026-05-17_12-00-00/
│   │   └── ...
│   └── vps02/
├── data/                       # Données partagées (Samba/FTP)
│   ├── utilisateur1/
│   ├── utilisateur2/
│   └── shared/
└── temp/                       # Fichiers temporaires
```

---

## 📖 Guide des modules

### 🏠 Dashboard

Vue d'ensemble du système :

- **Métriques système** : CPU, mémoire, disques (actualisé toutes les 30s)
- **État des services** : NXSlab, Samba, FTP (ping toutes les 10s)
- **Résumé des backups** : Dernière sauvegarde, taille totale, prochaine planifiée
- **Connexions actives** : Utilisateurs FTP/Samba connectés

**API :**
```bash
curl http://localhost:5080/api/status
curl http://localhost:5080/api/system
```

---

### 💾 Backup (le cœur du système)

#### Types de sauvegarde supportés

1. **Docker** (conteneurs + volumes + bind mounts)
   - Tous les conteneurs ou liste spécifique
   - Volumes nommés (via `docker run -v`)
   - Bind mounts (montages hôte direct)
   - Sauvegarde du `docker inspect` pour metadata
   - Option : arrêt conteneur avant/après backup

2. **Bases de données**
   - MySQL : dumps avec `mysqldump` (routines, triggers inclus)
   - PostgreSQL : dumps avec `pg_dump`
   - Support des conteneurs Docker ou hôte

3. **Sites web**
   - Répertoires personnalisés (défaut : `/var/www/html`)
   - Support exclusions (`.git`, `node_modules`, etc.)

4. **Configurations système**
   - `/etc/nginx`, `/etc/docker`, `/etc/mysql`, etc.
   - Chemins personnalisables

#### Configuration d'une sauvegarde

1. Aller dans **Backup** → Sélectionner un VPS → **Paramètres**

2. **Paramètres généraux**
   ```json
   {
     "schedule_enabled": true,
     "schedule": "0 2 * * *",          // Cron : 02:00 chaque jour
     "compression": "gz",               // gz, bz2, none
     "verify": true,                    // Vérifier archives après
     "max_count": 7,                    // Garder 7 derniers
     "max_days": 30,                    // Garder 30 jours max
     "targets": ["docker", "databases", "websites", "configs"]
   }
   ```

3. **Docker**
   ```json
   {
     "docker_all": true,              // Tous les conteneurs
     "docker_names": ["nextcloud", "postgres"],  // Ou sélection
     "docker_stop": false,            // Arrêter avant backup
     "excludes": []
   }
   ```

4. **Bases de données**
   ```json
   {
     "databases": {
       "mysql": [
         {"name": "wordpress", "host": "127.0.0.1", "user": "root", 
          "password": "***", "docker_container": "mysql"}
       ],
       "postgres": [
         {"name": "api", "host": "127.0.0.1", "user": "postgres",
          "password": "***", "docker_container": "postgres"}
       ]
     }
   }
   ```

5. **Web & Config**
   ```json
   {
     "web_paths": ["/var/www/html", "/home/user/app"],
     "config_paths": ["/etc/nginx", "/etc/docker"],
     "excludes": [".git", "node_modules", "*.log", "__pycache__"]
   }
   ```

6. **Hooks (pre/post backup)**
   ```json
   {
     "pre_hook": "systemctl stop myservice",
     "post_hook": "systemctl start myservice"
   }
   ```

7. **Webhook notifications**
   ```json
   {
     "webhook_url": "https://example.com/webhooks/backup",
     "events": ["success", "error"]
   }
   ```

#### Exécuter une sauvegarde

**Manuel :**
- Aller dans **Backup** → **Exécuter maintenant**
- Suivre la progression en temps réel
- Voir les logs détaillés

**Automatisé :**
- Configurer le cron (ex: `0 2 * * *` pour 2h du matin)
- Les sauvegardes se lancent automatiquement

**API :**
```bash
# Lancer un backup
curl -X POST http://localhost:5080/api/backup/run/vps01

# Voir le statut
curl http://localhost:5080/api/backup/status/vps01

# Voir l'historique
curl http://localhost:5080/api/backup/list/vps01
```

#### Restauration

1. **Via l'interface web**
   - **Backup** → Historique → Sélectionner un backup → **Voir archives**
   - Cliquer sur l'archive → **Restaurer dans** `/tmp/restore` (custom path possible)
   - Archive décompressée sur le VPS

2. **Manuellement**
   ```bash
   # Sur le serveur NXSlab
   cd /srv/nxslab-bkp/backups/vps01/2026-05-18_12-00-00/
   
   # Voir le manifeste
   cat manifest.json
   
   # Restaurer un volume Docker
   tar xzf docker/nextcloud/data.tar.gz -C /tmp/restore/
   
   # Restaurer une base de données
   gzip -dc databases/mysql_wordpress.sql.gz | mysql wordpress
   ```

3. **API**
   ```bash
   curl -X POST http://localhost:5080/api/backup/restore/vps01 \
     -H 'Content-Type: application/json' \
     -d '{
       "backup_id": "2026-05-18_12-00-00",
       "archive": "docker/nextcloud/data.tar.gz",
       "dest": "/tmp/restore"
     }'
   ```

---

### 🌐 Samba (partage de fichiers Windows/Mac/Linux)

#### Configuration

1. **Interface web** → **Samba** → **Paramètres**
   - Activer/désactiver le service
   - Paramètres de partage (vitesse réseau, cache)

2. **Ajouter un utilisateur Samba**
   - Interface web → **Samba** → **Ajouter utilisateur**
   - Utilisateur créé automatiquement sur le système Linux
   - Ajouté au groupe `nxslab-data`
   - Peut accéder à `/srv/nxslab-bkp/data`

#### Connexion depuis le client

**Windows :**
```
\\<ip-serveur>\nxslab-bkp
Utilisateur: samba_user
Mot de passe: (défini à la création)
```

**macOS :**
```
cmd+k
smb://samba_user@<ip-serveur>/nxslab-bkp
```

**Linux :**
```bash
mount -t cifs //<ip-serveur>/nxslab-bkp /mnt/backup \
  -o username=samba_user,password=***
```

#### Sécurité Samba

- Utilisateurs limités à `/srv/nxslab-bkp/data` (chroot virtuel)
- Permissions groupe `nxslab-data` (0775, sticky bit)
- Fichiers créés hérités du groupe
- Pas d'accès shell (nologin)

---

### 📤 FTP (File Transfer Protocol)

#### Configuration

1. **Interface web** → **FTP** → **Paramètres**
   - Port FTP (défaut 21)
   - Timeout connexion
   - Bande passante max

2. **Ajouter un utilisateur FTP**
   - Interface web → **FTP** → **Ajouter utilisateur**
   - Utilisateur confiné à `/srv/nxslab-bkp/data` (chroot)
   - Pas d'accès shell

#### Connexion

```bash
ftp <ip-serveur>
> user ftp_user
> pass ***

# Ou via CLI
ftp -in <<EOF
open <ip-serveur>
user ftp_user ***
ls
bye
EOF

# Ou via lftp
lftp ftp_user@<ip-serveur>
lftp> mirror /data/ /local/
lftp> quit
```

#### Statistiques

- Connexions actives en temps réel
- Uploads/downloads totaux
- Débit par session

---

### 📁 Fichiers (gestionnaire web)

#### Navigation

- **Interface web** → **Fichiers**
- Naviguer dans `/srv/nxslab-bkp/data/`
- Support des sous-répertoires

#### Opérations supportées

| Opération | Description |
|-----------|-------------|
| Upload | Fichiers individuels ou batch |
| Download | Télécharger fichiers/dossiers (ZIP automatique pour dossiers) |
| Créer dossier | Mkdir avec permissions 0775 |
| Renommer | Fichiers et dossiers |
| Supprimer | Avec confirmation |
| Extraire | ZIP, TAR, TAR.GZ |
| Compression | Créer ZIP à la volée |

#### Limitations

- Taille max upload : définie par nginx (défaut 0 = illimité)
- Timeout : 120s pour downloads
- Concurrent uploads : limité par système de fichiers

---

### 🖥️ Terminal (SSH Web)

Accès SSH interactif aux VPS distants via navigateur, **sans client SSH nécessaire**.

#### Utilisation

1. **Interface web** → **Terminal**
2. Sélectionner un VPS → **Connexion**
3. Utiliser comme terminal SSH normal

#### Fonctionnalités

- ✅ Redimensionnement PTY live
- ✅ Copier-coller (Ctrl+C/V ou Cmd+C/V)
- ✅ Historique des sessions
- ✅ Support couleurs ANSI
- ✅ UTF-8 complète

#### Limitations & Troubleshooting

**Problème : "Invalid frame header"**

**Cause** : Proxy nginx mal configuré ou WebSocket non supporté

**Solution 1 : Nginx Proxy Manager**
```
Proxy host → Details → ☑ WebSocket Support
Proxy host → Advanced → ajouter :
```

```nginx
proxy_read_timeout 86400s;
proxy_send_timeout 86400s;
proxy_buffering off;
```

**Solution 2 : nginx manuel**
```nginx
location /ws/ {
    proxy_pass http://127.0.0.1:5080;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_read_timeout 86400s;
    proxy_send_timeout 86400s;
    proxy_buffering off;
}
```

**Problème : Déconnexion après SSH prompt**

**Cause** : Socket timeout trop court ou exception SSH non capturée

**Solution** : Mise à jour terminal.py (v2.0+) qui gère les timeouts correctement

---

### 📋 Logs (journalisation centralisée)

Sources de logs disponibles :

| Source | Description |
|--------|-------------|
| **NXSlab** | Logs de l'application (backup, users, config changes) |
| **Auth/SSH** | Authentifications système, tentatives SSH |
| **Kernel** | Logs kernel (montages, permissions, etc.) |
| **Docker** | Logs des conteneurs et daemon Docker |
| **Samba** | Accès partages, erreurs authentification |
| **FTP** | Connexions, uploads/downloads, erreurs vsftpd |
| **Système** | Logs système généraux (systemd journal) |

#### Consultation

- **Interface web** → **Logs** → Sélectionner source
- Affichage temps réel (auto-scroll)
- 30 dernières lignes par défaut
- Filtrage par mot-clé possible

#### API

```bash
# Logs NXSlab (50 dernières lignes)
curl http://localhost:5080/api/logs/nxslab?lines=50

# Logs Samba filtrés
curl http://localhost:5080/api/logs/samba?filter=auth

# Logs temps réel via EventSource
curl http://localhost:5080/api/logs/stream/docker
```

---

### ⚙️ Paramètres

#### Gestion des comptes

- **Ajouter utilisateur** : Créer compte admin ou readonly
- **Changer mot de passe** : Pour l'utilisateur courant
- **Supprimer utilisateur** : Avec confirmation (irréversible)
- **Rôles** :
  - `admin` : Accès complet (sauvegardes, users, config)
  - `readonly` : Lecture seule (logs, status, dashboards)

#### Serveurs distants

Configurer les VPS à sauvegarder :

```json
{
  "id": "vps01",                           // Identifiant unique
  "name": "VPS Principal",                 // Nom d'affichage
  "host": "vps.example.com",               // Hostname ou IP
  "port": 22,                              // Port SSH (défaut 22)
  "user": "root",                          // Utilisateur SSH
  "auth_type": "key",                      // "key" ou "password"
  "key_path": "/root/.ssh/id_rsa",         // Chemin clé privée
  "key_passphrase": "***",                 // Passphrase si protégée
  "password": "***"                        // Alternative à clé
}
```

**Test de connexion :**
- Interface web → **Paramètres** → **Serveurs distants** → **Test**
- Affiche hostname, OS, version Docker

#### Informations système

- **Version** : NXSlab Backup WebUI
- **Uptime** : Temps de fonctionnement du serveur
- **Répertoire données** : Chemin DATA_DIR
- **Espace disponible** : Disque total/utilisé/libre
- **Capacités** : Docker, MySQL, PostgreSQL installés/OK
- **Python** : Version utilisée
- **Hostname** : Nom du serveur

---

## 🔐 Accès utilisateurs

### Rôles et permissions

```
┌─────────────────────────────────────────────┐
│ ADMIN                  READONLY             │
├──────────────────────────────────────────┤
│ Lancer backup       │ Voir backups       │
│ Config backup       │ Voir historique    │
│ Ajouter users       │ Voir logs          │
│ Config Samba/FTP    │ Voir status        │
│ Voir/télécharger    │ Accès terminal     │
│ Upload fichiers     │ (pas écriture)     │
│ Modifier config     │                    │
│ Accès terminal SSH  │                    │
└─────────────────────────────────────────────┘
```

### Partages multi-utilisateur

**Samba/FTP** : Chaque utilisateur a son dossier personnel

```
/srv/nxslab-bkp/data/
├── admin/           # Admin peut accéder tous les dossiers
├── user1/           # User1 accède seulement à son dossier
├── user2/           # User2 accède seulement à son dossier
└── shared/          # Dossier partagé (config via Samba)
```

Pour modifier accès, éditer `/etc/samba/smb.conf` après création utilisateur.

---

## 🔒 Sécurité

### Authentification

- **Stockage** : Mots de passe hashés SHA-256 (jamais en clair)
- **Session** : Token Flask signé cryptographiquement
- **Expiration** : Session 24h par défaut (configurable)
- **HTTPS** : Recommandé en production (reverse proxy nginx + certbot)

### Contrôle d'accès

```
Session Flask → Rôle utilisateur → Permissions endpoint
```

- Décorateurs `@login_required` et `@admin_required` sur toutes les routes sensibles
- Vérifications au niveau endpoint (validation double)

### Isolation utilisateurs

**Filesystem :**
- Utilisateurs FTP : chroot enforced à `/srv/nxslab-bkp/data`
- Utilisateurs Samba : permissions groupe `nxslab-data` (0775)
- Fichiers temp : permissions restrictives (0600)

**Base de données :**
- Config stockée `/etc/nxslab-bkp/config.json` (chmod 600, root only)
- Mots de passe VPS stockés en clair (⚠️ protection filesystem uniquement)

### SSH vers VPS distants

**Options supportées :**

```json
{
  "auth_type": "key",
  "key_path": "/root/.ssh/id_rsa",         // Doit être chmod 600
  "key_passphrase": "***",                 // Optionnel
  "password": "***"                        // Alternative (moins sûr)
}
```

**Bonnes pratiques :**
- Utiliser clés SSH plutôt que mots de passe
- Clés : 4096 bits minimum RSA (ou Ed25519)
- SSH_CONFIG : Autoriser connexions root ou user específique sur VPS
- Fail2ban : Activer sur VPS pour limiter tentatives

### Mise à jour de sécurité

```bash
cd /opt/nxslab-bkp
git fetch origin
git log --oneline master...origin/master  # Voir les changements
sudo bash update.sh
```

---

## 🔧 Troubleshooting

### Service ne démarre pas

```bash
systemctl status nxslab-bkp
journalctl -u nxslab-bkp -n 50 --no-pager
```

**Causes courantes :**

| Erreur | Solution |
|--------|----------|
| `Port already in use` | Changer port : éditer `/etc/nxslab-bkp/config.json` → `port` |
| `Permission denied` | Vérifier permissions `/etc/nxslab-bkp/` : `sudo chmod 600 config.json` |
| `Module not found` | Réinstaller dependencies : `pip install -r requirements.txt` |
| `Docker socket: permission denied` | Ajouter user à groupe docker : `usermod -aG docker nxslab` |

### Connexion SSH au VPS échoue

```bash
# Test SSH manuel
ssh -i /root/.ssh/id_rsa root@vps.example.com "hostname"

# Via l'interface
Paramètres → Serveurs distants → Test
```

**Causes :**

- ❌ Clé privée introuvable ou permissions incorrectes (doit être 600)
- ❌ Passphrase non fournie si clé protégée
- ❌ Authentification host key refusée (ajouter à known_hosts)
- ❌ Firewall bloque port SSH

**Fix :**
```bash
# S'assurer que clé est accessible
ls -la /root/.ssh/id_rsa   # doit être 600
chmod 600 /root/.ssh/id_rsa

# Accepter host key
ssh -i /root/.ssh/id_rsa root@vps.example.com "exit"

# Configurer via interface web ensuite
```

### Terminal WebSocket déconnecte immédiatement

**Solution rapide :** Vérifier nginx WebSocket support (voir section Terminal)

### Backup échoue avec "docker: command not found"

**Problème :** Docker n'installé sur le VPS

**Options :**
1. Installer Docker : `apt install docker.io`
2. Retirer `docker` des targets backup dans config
3. Ajouter seulement les conteneurs en fonctionnement : décocher "Tous les conteneurs"

### FTP/Samba lent

**Diagnostique :**
```bash
# Voir taille répertoire données
du -sh /srv/nxslab-bkp/data

# Voir nombre fichiers
find /srv/nxslab-bkp/data -type f | wc -l

# Tester débit Samba
iozone -a -n 1000 -g 1000  # Installer: apt install iozone3
```

**Optimisations :**
```bash
# Augmenter buffers Samba : éditer /etc/samba/smb.conf
[nxslab-bkp]
   socket options = TCP_NODELAY IPTOS_LOWDELAY SO_RCVBUF=131072 SO_SNDBUF=131072
```

### Espace disque saturé

```bash
# Voir utilisation
df -h /srv/nxslab-bkp/

# Trouver gros fichiers
find /srv/nxslab-bkp/backups -type f -size +1G

# Purger backups anciens
rm -rf /srv/nxslab-bkp/backups/vps01/2026-01-*   # Janvier 2026

# Voir la config de rotation
curl http://localhost:5080/api/backup/settings/vps01 | grep max_
```

---

## 🏗️ Architecture

### Stack technique

```
┌─ CLIENT ────────────────────────────────────────────┐
│  Navigateur (HTML5 + WebSocket)                     │
│  Chrome, Firefox, Safari, Edge                      │
└──────────────────────────────────────────────────────┘
            ↓ HTTPS/WSS (optionnel: Nginx)
┌─ SERVEUR NXSlab ────────────────────────────────────┐
│                                                     │
│  ┌─ Flask (Python 3.8+) ──────────────────────┐   │
│  │ • Authentication (auth.py)                 │   │
│  │ • REST API routes (*.py)                   │   │
│  │ • Static files (CSS, JS)                   │   │
│  │ • WebSocket terminal (terminal.py)         │   │
│  │ • Templating (Jinja2)                      │   │
│  └────────────────────────────────────────────┘   │
│                   ↓                                 │
│  ┌─ Services système ──────────────────────────┐   │
│  │ • Samba (smbd, nmbd)                        │   │
│  │ • FTP (vsftpd)                              │   │
│  │ • Scheduler (APScheduler)                   │   │
│  │ • Terminal (Paramiko SSH)                   │   │
│  └────────────────────────────────────────────┘   │
│                   ↓                                 │
│  ┌─ Filesystem ────────────────────────────────┐   │
│  │ /srv/nxslab-bkp/                            │   │
│  │ ├── backups/          (sauvegardes)         │   │
│  │ ├── data/             (partages Samba/FTP) │   │
│  │ └── temp/             (fichiers temp)       │   │
│  └────────────────────────────────────────────┘   │
│                   ↓                                 │
│  /etc/nxslab-bkp/config.json (config + users)    │
│                                                     │
└──────────────────────────────────────────────────────┘
            ↓ SSH                                   ↓ HTTP/HTTPS
      ┌─────────────────┐              ┌────────────────────┐
      │  VPS Distants   │              │  Nginx Proxy       │
      │  (Backup source)│              │  (optionnel)       │
      └─────────────────┘              └────────────────────┘
```

### Flux d'une sauvegarde

```
1. Interface web / Cron trigger
    ↓
2. run_backup(remote_id)  [backup_core.py]
    ├─ SSH connect to VPS
    ├─ Docker inspect + tar volumes
    ├─ MySQL/PostgreSQL dump
    ├─ TAR websites/configs
    └─ Generate manifest.json
    ↓
3. Stream remote via Paramiko
    ├─ tar c... | gzip | stream
    └─ Save to local /backups/
    ↓
4. Verify + Rotate
    ├─ Vérifier archives (tar -tzf)
    ├─ Keep max N backups (par count)
    ├─ Keep max X days (par âge)
    └─ Delete old
    ↓
5. Notification (webhook)
    └─ POST {event: success/error, ...}
```

### Performance

**Métriques typiques :**

| Opération | Temps (exemple) | Facteurs |
|-----------|-----------------|----------|
| Backup Docker (1GB volume) | 2-5 min | Réseau, compression |
| PostgreSQL dump (5GB) | 10-20 min | CPU, RAM, taille DB |
| Samba upload file (100MB) | 30-60s | Vitesse réseau, HDD |
| Terminal connexion | <1s | Latence SSH, firewall |
| Dashboard refresh | <200ms | System load, cache |

---

## 📡 API

Base URL : `http://localhost:5080`

### Authentification

```bash
# Login
curl -X POST http://localhost:5080/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"***"}'

# Réponse
{"ok":true,"user":"admin","role":"admin"}

# Les headers Set-Cookie contiennent la session
# À inclure dans les requêtes suivantes (auto-géré par navigateur)
```

### Endpoints Backup

```bash
# Lancer un backup
curl -X POST http://localhost:5080/api/backup/run/vps01

# Statut en temps réel
curl http://localhost:5080/api/backup/status/vps01

# Historique
curl http://localhost:5080/api/backup/list/vps01

# Détails d'un backup
curl http://localhost:5080/api/backup/manifest/vps01/2026-05-18_12-00-00

# Restaurer une archive
curl -X POST http://localhost:5080/api/backup/restore/vps01 \
  -d '{"backup_id":"2026-05-18_12-00-00","archive":"docker/app.tar.gz","dest":"/tmp"}'
```

### Endpoints Samba/FTP

```bash
# Lister utilisateurs FTP
curl http://localhost:5080/api/ftp/users

# Créer utilisateur FTP
curl -X POST http://localhost:5080/api/ftp/users/add \
  -d '{"username":"newuser","password":"***"}'

# Même pour Samba
curl http://localhost:5080/api/samba/users
curl -X POST http://localhost:5080/api/samba/users/add \
  -d '{"username":"newuser","password":"***"}'
```

### Endpoints Files

```bash
# Lister fichiers
curl 'http://localhost:5080/api/files/?path=/data'

# Upload
curl -F 'file=@document.pdf' http://localhost:5080/api/files/upload

# Download
curl http://localhost:5080/api/files/download?path=/data/document.pdf

# Créer dossier
curl -X POST http://localhost:5080/api/files/mkdir \
  -d '{"path":"/data/newfolder"}'

# Renommer
curl -X POST http://localhost:5080/api/files/rename \
  -d '{"path":"/data/old","new":"new"}'

# Supprimer
curl -X POST http://localhost:5080/api/files/delete \
  -d '{"path":"/data/file"}'
```

### Endpoints System

```bash
# Statut global
curl http://localhost:5080/api/status

# Métriques système
curl http://localhost:5080/api/system

# Logs
curl http://localhost:5080/api/logs/nxslab?lines=50
curl http://localhost:5080/api/logs/samba
curl http://localhost:5080/api/logs/ftp
curl http://localhost:5080/api/logs/docker
```

**Documentation OpenAPI complète :** (TODO: générer Swagger)

---

## 📚 Maintenance

### Mise à jour

```bash
# Vérifier les mises à jour disponibles
cd /opt/nxslab-bkp
git fetch origin

# Lire les changements
git log --oneline master...origin/master

# Mettre à jour (avec backup automatique)
sudo bash update.sh

# Voir le statut
systemctl status nxslab-bkp
journalctl -u nxslab-bkp -n 20 --no-pager
```

### Backup du serveur NXSlab lui-même

```bash
# Sauvegarder la configuration
sudo tar czf nxslab-bkp_config_$(date +%Y%m%d).tar.gz \
  /etc/nxslab-bkp/ \
  /opt/nxslab-bkp/

# Sauvegarder les données
sudo tar czf nxslab-bkp_data_$(date +%Y%m%d).tar.gz \
  /srv/nxslab-bkp/

# Tous les 2 jours
0 3 */2 * * /opt/nxslab-bkp/backup-self.sh
```

### Monitoring

**Recommandé :**

```bash
# Vérifier que le service est actif
watch -n 10 'systemctl status nxslab-bkp | tail -5'

# Surveiller les disques
watch -n 60 'df -h /srv/nxslab-bkp/'

# Voir les backups en cours
watch -n 5 'curl -s http://localhost:5080/api/backup/status/vps01 | grep percent'

# Alertes via cron
# 0 6 * * * curl -f http://localhost:5080/api/status > /dev/null || send_alert
```

### Restauration complète (disaster recovery)

```bash
# Si le serveur NXSlab a besoin d'être restauré

# 1. Réinstaller OS (Debian 11+)
# 2. Restaurer les données
tar xzf nxslab-bkp_data_*.tar.gz -C /
tar xzf nxslab-bkp_config_*.tar.gz -C /

# 3. Réinstaller l'application
cd /opt/nxslab-bkp
sudo bash install.sh

# 4. Les config/backups sont intacts
# 5. Vérifier statut
systemctl status nxslab-bkp
```

---

## ❓ FAQ

### Q: Puis-je utiliser un autre répertoire pour les backups?

**A:** Oui, lors de l'installation spécifier `DATA_DIR` personnalisé ou éditer `/etc/nxslab-bkp/config.json` → `data_dir`. Redémarrer le service ensuite.

### Q: Est-ce que les mots de passe FTP/Samba sont stockés en clair?

**A:** Les mots de passe FTP/Samba sont stockés par le système Linux (PAM), pas dans la config NXSlab. Configuration sensible (`/etc/nxslab-bkp/config.json`) est protégée chmod 600.

### Q: Comment restaurer depuis une vieille sauvegarde?

**A:** Aller dans **Backup** → historique → cliquer une date → **Voir archives** → sélectionner archive → **Restaurer**. Les archives sont décompressées directement sur le VPS.

### Q: Y a-t-il une limite de taille de sauvegarde?

**A:** Non de limite fixe. Limité par:
- Espace disque NXSlab
- Temps réseau (peut être très long)
- Memoria VPS/NXSlab lors streaming

Pour grosses BD (>100GB), faire des exports sélectifs plutôt qu'entier.

### Q: Puis-je utiliser HTTP au lieu de HTTPS?

**A:** Oui en local. En réseau, **très fortement recommandé** d'utiliser HTTPS via nginx reverse proxy + certificat SSL (Let's Encrypt gratuit).

### Q: Comment automatiser les backups?

**A:** Configurer le cron dans l'interface web (**Backup** → **Paramètres** → `schedule`). Format cron standard : `minute hour day month day_of_week`.

Exemples :
- `0 2 * * *` = 02:00 chaque jour
- `0 2 * * 0` = 02:00 chaque dimanche (hebdo)
- `0 2 1 * *` = 02:00 le 1er de chaque mois

### Q: Puis-je exécuter plusieurs backups en parallèle?

**A:** Non, NXSlab exécute un backup à la fois par VPS (pour éviter charge excessive). Planifier les backups à des heures différentes si plusieurs VPS.

### Q: Comment monitorer les backups depuis l'extérieur?

**A:** Via webhooks. Configurer URL dans **Backup** → **Paramètres** → `webhook_url`. NXSlab POST les événements success/error.

### Q: Est-ce que Docker bind mount est sauvegardé?

**A:** Oui depuis v2.0! Les bind mounts sont détectés et archivés comme volumes nommés. Voir manifest.json pour les identifier (`"bind:"` prefix).

### Q: Puis-je supprimer les données partagées (Samba/FTP) sans affecter les backups?

**A:** Oui, `/srv/nxslab-bkp/data/` est séparé de `/srv/nxslab-bkp/backups/`. Supprimer le contenu de `data/` ne touche pas aux backups.

### Q: Comment changer le port web après installation?

**A:** Éditer `/etc/nxslab-bkp/config.json` → `port`, puis redémarrer : `sudo systemctl restart nxslab-bkp`

### Q: Puis-je merger plusieurs serveurs de backup?

**A:** Non de merge dans l'interface. Mais possible manuellement :
```bash
cp -r /mnt/backup1/backups/vps01/* /srv/nxslab-bkp/backups/vps01/
# Mettre à jour manifest.json si nécessaire
```

### Q: Peut-on configurer une notification par email?

**A:** Non de support mail built-in. Utiliser webhook + service comme Zapier, IFTTT ou script webhook perso pour envoyer email.

---

## 📝 Licence

NXSlab Backup WebUI — © 2025 NeXoS_20

---

## 🤝 Support

- **Issues & Bugs** : https://git.nxslab.in/Pierre/NXSlab-Bkp/issues
- **Documentation** : Ce README
- **Logs** : `journalctl -u nxslab-bkp -f`

---

*Dernière mise à jour : 2026-05-18*
*Version : 2.0+ avec support Docker bind mounts*
