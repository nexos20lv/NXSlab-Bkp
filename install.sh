#!/bin/bash
# NXSlab Backup WebUI — Install script
# Usage: sudo bash install.sh
set -e

# ── Colors ──────────────────────────────────────────────────────────────────
R='\033[0;31m' G='\033[0;32m' C='\033[0;36m' Y='\033[1;33m'
B='\033[1m' D='\033[2m' NC='\033[0m'

INSTALL_DIR="/opt/nxslab-bkp"
CONFIG_DIR="/etc/nxslab-bkp"
SERVICE="nxslab-bkp"

# ── Banner ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${C}  ███╗   ██╗██╗  ██╗███████╗██╗      █████╗ ██████╗ ${NC}"
echo -e "${C}  ████╗  ██║╚██╗██╔╝██╔════╝██║     ██╔══██╗██╔══██╗${NC}"
echo -e "${C}  ██╔██╗ ██║ ╚███╔╝ ███████╗██║     ███████║██████╔╝${NC}"
echo -e "${C}  ██║╚██╗██║ ██╔██╗ ╚════██║██║     ██╔══██║██╔══██╗${NC}"
echo -e "${C}  ██║ ╚████║██╔╝ ██╗███████║███████╗██║  ██║██████╔╝${NC}"
echo -e "${C}  ╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝╚═════╝${NC}"
echo -e "${D}        Backup WebUI — Samba, FTP & Docker Backup${NC}"
echo ""

# ── Root check ───────────────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
  echo -e "${R}[✗] Ce script doit être exécuté en tant que root (sudo).${NC}"
  exit 1
fi

# ── Config interactif ────────────────────────────────────────────────────────
echo -e "${C}[?]${NC} Configuration de l'interface web"
echo ""

read -p "  Port web [5080]: " PORT
PORT=${PORT:-5080}

read -p "  Nom d'utilisateur admin [admin]: " ADMIN_USER
ADMIN_USER=${ADMIN_USER:-admin}

while true; do
  read -s -p "  Mot de passe admin: " ADMIN_PASS; echo ""
  if [ ${#ADMIN_PASS} -lt 8 ]; then
    echo -e "  ${Y}[!] Minimum 8 caractères.${NC}"
  else
    break
  fi
done

read -s -p "  Confirmer le mot de passe: " ADMIN_PASS2; echo ""
if [ "$ADMIN_PASS" != "$ADMIN_PASS2" ]; then
  echo -e "${R}[✗] Les mots de passe ne correspondent pas.${NC}"
  exit 1
fi

read -p "  Répertoire de données [/srv/nxslab-bkp]: " DATA_DIR
DATA_DIR=${DATA_DIR:-/srv/nxslab-bkp}

echo ""
echo -e "${C}[→]${NC} Démarrage de l'installation...\n"

# ── 1. Système ───────────────────────────────────────────────────────────────
echo -e "${C}[1/6]${NC} Mise à jour et installation des paquets..."
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  python3 python3-pip python3-venv samba vsftpd 2>/dev/null
echo -e "  ${G}✓${NC} python3, samba, vsftpd installés"

# ── 2. Répertoires ───────────────────────────────────────────────────────────
echo -e "${C}[2/6]${NC} Création des répertoires..."
mkdir -p "$INSTALL_DIR/templates"
mkdir -p "$CONFIG_DIR"
mkdir -p "$DATA_DIR"
chmod 775 "$DATA_DIR"
echo -e "  ${G}✓${NC} $INSTALL_DIR"
echo -e "  ${G}✓${NC} $DATA_DIR (données)"

# ── 3. Copie des fichiers ────────────────────────────────────────────────────
echo -e "${C}[3/6]${NC} Copie des fichiers..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -f "$SCRIPT_DIR/app.py" ]; then
  echo -e "${R}[✗] app.py introuvable dans $SCRIPT_DIR${NC}"
  exit 1
fi

cp "$SCRIPT_DIR/app.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/templates/login.html" "$INSTALL_DIR/templates/"
cp "$SCRIPT_DIR/templates/index.html" "$INSTALL_DIR/templates/"
chmod 750 "$INSTALL_DIR/app.py"
echo -e "  ${G}✓${NC} Fichiers copiés"

# ── 4. Python venv + Flask ───────────────────────────────────────────────────
echo -e "${C}[4/6]${NC} Création de l'environnement Python..."
python3 -m venv "$INSTALL_DIR/venv" --prompt nxslab-bkp
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet flask paramiko apscheduler flask-sock
echo -e "  ${G}✓${NC} Flask, paramiko, apscheduler installés"

# ── 5. Configuration ─────────────────────────────────────────────────────────
echo -e "${C}[5/6]${NC} Génération de la configuration..."

PASS_HASH=$(printf '%s' "$ADMIN_PASS" | \
  "$INSTALL_DIR/venv/bin/python3" -c \
  "import hashlib, sys; print(hashlib.sha256(sys.stdin.read().encode()).hexdigest())")

SECRET_KEY=$("$INSTALL_DIR/venv/bin/python3" -c \
  "import secrets; print(secrets.token_hex(32))")

cat > "$CONFIG_DIR/config.json" <<JSON
{
  "username": "${ADMIN_USER}",
  "password_hash": "${PASS_HASH}",
  "secret_key": "${SECRET_KEY}",
  "port": ${PORT},
  "data_dir": "${DATA_DIR}"
}
JSON

chmod 600 "$CONFIG_DIR/config.json"
echo -e "  ${G}✓${NC} $CONFIG_DIR/config.json"

# ── 5b. Configuration vsftpd ────────────────────────────────────────────────
VSFTPD_CONF="/etc/vsftpd.conf"
if ! grep -q "local_enable=YES" "$VSFTPD_CONF" 2>/dev/null; then
  echo -e "  ${Y}[i]${NC} Application de la config vsftpd..."
  cat >> "$VSFTPD_CONF" <<VSFTPD

# NXSlab — added by install.sh
local_enable=YES
write_enable=YES
local_umask=022
chroot_local_user=YES
allow_writeable_chroot=YES
local_root=${DATA_DIR}
VSFTPD
fi

# ── 5c. Partage Samba pour le répertoire de données ──────────────────────────
SMB_CONF="/etc/samba/smb.conf"
if [ -f "$SMB_CONF" ] && ! grep -q "\[nxslab-bkp\]" "$SMB_CONF"; then
  echo -e "  ${Y}[i]${NC} Ajout du partage Samba [nxslab-bkp]..."
  cat >> "$SMB_CONF" <<SAMBA

[nxslab-bkp]
   comment = NXSlab Backup Data
   path = ${DATA_DIR}
   browseable = yes
   read only = no
   guest ok = no
   create mask = 0664
   directory mask = 0775
SAMBA
  echo -e "  ${G}✓${NC} Partage Samba ajouté → $DATA_DIR"
fi

# ── 6. Service systemd ────────────────────────────────────────────────────────
echo -e "${C}[6/6]${NC} Création du service systemd..."

cat > "/etc/systemd/system/${SERVICE}.service" <<SERVICE
[Unit]
Description=NXSlab Backup WebUI
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
Environment=CONFIG_FILE=${CONFIG_DIR}/config.json
ExecStart=${INSTALL_DIR}/venv/bin/python3 ${INSTALL_DIR}/app.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable "$SERVICE" --quiet
systemctl restart "$SERVICE"
sleep 1

if systemctl is-active "$SERVICE" --quiet; then
  STATUS="${G}✓ actif${NC}"
else
  STATUS="${R}✗ erreur${NC}"
fi

# ── Résumé ────────────────────────────────────────────────────────────────────
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo ""
echo -e "${G}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${G}║       Installation terminée avec succès !            ║${NC}"
echo -e "${G}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${B}Interface web :${NC}  http://$IP:$PORT"
echo -e "  ${B}Utilisateur   :${NC}  $ADMIN_USER"
echo -e "  ${B}Service       :${NC}  $SERVICE (${STATUS})"
echo ""
echo -e "  Commandes utiles :"
echo -e "  ${D}systemctl status  $SERVICE${NC}"
echo -e "  ${D}systemctl restart $SERVICE${NC}"
echo -e "  ${D}journalctl -u $SERVICE -f${NC}"
echo ""
echo -e "${D}  NXSlab Backup WebUI — NeXoS_20${NC}"
echo ""
