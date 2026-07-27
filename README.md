<div align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=0:7b2cbf,100:c77dff&height=200&section=header&text=NXSlab%20Backup&fontSize=55&fontAlignY=40&animation=twinkling&desc=Outil%20Python%20de%20Sauvegarde%20Automatis%C3%A9e&descAlignY=60&descAlign=50" alt="NXSlab Backup Banner" />

  <p align="center">
    <img src="https://img.shields.io/badge/Language-Python_3.x-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
    <img src="https://img.shields.io/badge/Type-CLI_Utility-4A5568?style=for-the-badge" alt="CLI Tool">
    <img src="https://img.shields.io/badge/Feature-Automated_Cron-2ECC71?style=for-the-badge" alt="Cron Backup">
    <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" alt="License">
  </p>

  <p align="center">
    <b>Un script Python robuste et léger pour planifier, exécuter et nettoyer automatiquement les sauvegardes de vos serveurs.</b>
  </p>
</div>

---

## 📖 Présentation

**NXSlab-Bkp** est un outil de sauvegarde automatisée écrit en Python, conçu spécifiquement pour les environnements de serveurs Linux et Windows. Il permet de compresser des dossiers critiques, d'effectuer des dumps de bases de données et d'appliquer une politique de rétention automatique des archives.

---

## ✨ Fonctionnalités Clés

- 📦 **Compression d'Archives :** Création d'archives ZIP / TAR.GZ horodatées.
- 🗄️ **Sauvegarde de Bases de Données :** Support automatique des dumps MySQL / MariaDB et PostgreSQL.
- 🧹 **Politique de Rétention (Rotation) :** Suppression automatique des sauvegardes datant de plus de X jours pour économiser l'espace disque.
- 🔔 **Notifications Discord / Email :** Envoi d'un rapport de statut (Succès / Échec) par Webhook Discord à la fin de chaque exécution.
- ⏱️ **Prêt pour Cron & Systemd :** Exécution planifiée sans intervention humaine.

---

## 🚀 Utilisation Rapide

```bash
# Cloner le dépôt
git clone https://github.com/nexos20lv/NXSlab-Bkp.git
cd NXSlab-Bkp

# Exécuter la sauvegarde manuelle
python3 backup.py --config config.json
```

### Exemple de configuration (`config.json`)
```json
{
  "backup_paths": ["/var/www", "/etc/nginx"],
  "destination": "/backups/nxslab",
  "retention_days": 14,
  "discord_webhook": "https://discord.com/api/webhooks/..."
}
```

---

## 📄 Licence

Distribué sous licence **MIT**. Voir [LICENSE](LICENSE).