# NXSlab Backup WebUI

Interface web d'administration pour serveur de sauvegarde — gestion Samba, FTP, sauvegardes SSH distantes et terminal web.

```
  ███╗   ██╗██╗  ██╗███████╗██╗      █████╗ ██████╗
  ████╗  ██║╚██╗██╔╝██╔════╝██║     ██╔══██╗██╔══██╗
  ██╔██╗ ██║ ╚███╔╝ ███████╗██║     ███████║██████╔╝
  ██║╚██╗██║ ██╔██╗ ╚════██║██║     ██╔══██║██╔══██╗
  ██║ ╚████║██╔╝ ██╗███████║███████╗██║  ██║██████╔╝
  ╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝╚═════╝
```

---

## Fonctionnalités

| Module | Description |
|--------|-------------|
| **Dashboard** | Métriques système temps réel (CPU, RAM, disques), statut des services, résumé des backups |
| **Backup** | Sauvegardes SSH vers VPS distants, planification cron, transferts rsync/tar, restore |
| **Samba** | Gestion des partages et utilisateurs Samba, config live |
| **FTP** | Gestion des utilisateurs vsftpd, chroot sur le répertoire de données |
| **Fichiers** | Explorateur de fichiers web (upload, download, mkdir, rename, delete) |
| **Terminal** | Terminal SSH web vers les VPS distants (WebSocket) |
| **Logs** | Journaux en temps réel : Samba, FTP, NXSlab, Auth/SSH, Kernel, Docker, Système |
| **Paramètres** | Gestion des comptes panel, changement de mot de passe, infos capacités |

---

## Prérequis

- Debian / Ubuntu (systemd)
- Python 3.8+
- `samba`, `vsftpd` (installés automatiquement)
- Accès root pour l'installation

---

## Installation

```bash
git clone https://git.nxslab.in/Pierre/NXSlab-Bkp
cd NXSlab-Bkp
sudo bash install.sh
```

L'installeur configure :
- L'environnement Python (venv + dépendances)
- Le service systemd `nxslab-bkp`
- La configuration vsftpd (chroot sur DATA_DIR)
- Le partage Samba `[nxslab-bkp]`
- Le site nginx (optionnel, si nginx est détecté)

---

## Mise à jour

```bash
sudo bash update.sh
```

Le script télécharge la dernière version depuis le dépôt, sauvegarde les fichiers actuels, applique la mise à jour et relance le service. En cas d'erreur, un rollback automatique restaure l'état précédent.

---

## Configuration nginx (reverse proxy)

Si tu passes par un reverse proxy nginx, le bloc `/ws/` nécessite une config spécifique pour les WebSocket du terminal SSH. Voir [`nginx.conf.example`](nginx.conf.example).

**Avec Nginx Proxy Manager** :
1. Proxy host → onglet **Details** → activer **WebSocket Support**
2. Onglet **Advanced** → ajouter :

```nginx
proxy_read_timeout 86400s;
proxy_send_timeout 86400s;
proxy_buffering off;
```

---

## Sécurité

- Authentification par session Flask (SHA-256)
- Rôles `admin` / `readonly`
- Utilisateurs FTP chroot sur `DATA_DIR` uniquement
- Utilisateurs FTP/Samba dans le groupe `nxslab-data` (chmod 2775 sur DATA_DIR)
- Config stockée dans `/etc/nxslab-bkp/config.json` (chmod 600)
- Clés SSH ou mot de passe pour les connexions VPS distants

---

## Structure

```
NXSlab-Bkp/
├── app.py              # Point d'entrée Flask
├── auth.py             # Authentification, décorateurs login_required/admin_required
├── backup.py           # Routes /api/backup/*
├── backup_core.py      # Moteur SSH rsync/tar, APScheduler
├── config.py           # Chargement/sauvegarde config.json, migration
├── files.py            # Routes /api/files/* (explorateur)
├── ftp.py              # Routes /api/ftp/*
├── helpers.py          # Utilitaires partagés (run, shell, setup_data_access)
├── remotes.py          # Routes /api/remotes/*
├── samba.py            # Routes /api/samba/*
├── system.py           # Routes /health /api/status /api/system /api/logs/*
├── terminal.py         # WebSocket SSH /ws/terminal/<id>
├── users.py            # Routes /api/users/* /api/settings/*
├── install.sh          # Script d'installation
├── update.sh           # Script de mise à jour avec rollback
├── nginx.conf.example  # Config nginx avec WebSocket
├── static/
│   ├── css/app.css
│   └── js/app.js
└── templates/
    ├── login.html
    ├── index.html
    └── partials/       # nav, dashboard, samba, ftp, files, logs,
                        # backup, terminal, settings, modals
```

---

## Services gérés

| Service | Commande systemd |
|---------|-----------------|
| NXSlab WebUI | `systemctl status nxslab-bkp` |
| Samba | `systemctl status smbd nmbd` |
| FTP | `systemctl status vsftpd` |

```bash
journalctl -u nxslab-bkp -f   # logs temps réel
systemctl restart nxslab-bkp  # redémarrer
```

---

## Dépendances Python

| Package | Usage |
|---------|-------|
| `flask` | Framework web |
| `flask-sock` | WebSocket terminal |
| `paramiko` | Connexions SSH (backup + terminal) |
| `apscheduler` | Planification des sauvegardes |

```bash
pip install flask paramiko apscheduler flask-sock
```

---

*NXSlab Backup WebUI — NeXoS_20*
