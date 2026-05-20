#!/bin/bash
# NXSlab Backup WebUI â€” Install script
# Usage: sudo bash install.sh
set -euo pipefail

R='\033[0;31m' G='\033[0;32m' C='\033[0;36m' Y='\033[1;33m'
B='\033[1m' D='\033[2m' NC='\033[0m'

INSTALL_DIR="/opt/nxslab-bkp"
CONFIG_DIR="/etc/nxslab-bkp"
SERVICE="nxslab-bkp"
REPO_URL="https://github.com/nexos20lv/NXSlab-Bkp.git"

APP_FILES=(app.py)
APP_DIRS=(core blueprints templates static)

echo ""
echo -e "${C}  â–ˆâ–ˆâ–ˆâ•—   â–ˆâ–ˆâ•—â–ˆâ–ˆâ•—  â–ˆâ–ˆâ•—â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•—â–ˆâ–ˆâ•—      â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•— â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•— ${NC}"
echo -e "${C}  â–ˆâ–ˆâ–ˆâ–ˆâ•—  â–ˆâ–ˆâ•‘â•šâ–ˆâ–ˆâ•—â–ˆâ–ˆâ•”â•â–ˆâ–ˆâ•”â•â•â•â•â•â–ˆâ–ˆâ•‘     â–ˆâ–ˆâ•”â•â•â–ˆâ–ˆâ•—â–ˆâ–ˆâ•”â•â•â–ˆâ–ˆâ•—${NC}"
echo -e "${C}  â–ˆâ–ˆâ•”â–ˆâ–ˆâ•— â–ˆâ–ˆâ•‘ â•šâ–ˆâ–ˆâ–ˆâ•”â• â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•—â–ˆâ–ˆâ•‘     â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•‘â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•”â•${NC}"
echo -e "${C}  â–ˆâ–ˆâ•‘â•šâ–ˆâ–ˆâ•—â–ˆâ–ˆâ•‘ â–ˆâ–ˆâ•”â–ˆâ–ˆâ•— â•šâ•â•â•â•â–ˆâ–ˆâ•‘â–ˆâ–ˆâ•‘     â–ˆâ–ˆâ•”â•â•â–ˆâ–ˆâ•‘â–ˆâ–ˆâ•”â•â•â–ˆâ–ˆâ•—${NC}"
echo -e "${C}  â–ˆâ–ˆâ•‘ â•šâ–ˆâ–ˆâ–ˆâ–ˆâ•‘â–ˆâ–ˆâ•”â• â–ˆâ–ˆâ•—â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•‘â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•—â–ˆâ–ˆâ•‘  â–ˆâ–ˆâ•‘â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•”â•${NC}"
echo -e "${C}  â•šâ•â•  â•šâ•â•â•â•â•šâ•â•  â•šâ•â•â•šâ•â•â•â•â•â•â•â•šâ•â•â•â•â•â•â•â•šâ•â•  â•šâ•â•â•šâ•â•â•â•â•â•${NC}"
echo -e "${D}        Backup WebUI â€” Samba, FTP & Docker Backup${NC}"
echo ""

# â”€â”€ VÃ©rifications prÃ©alables â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

if [ "$EUID" -ne 0 ]; then
  echo -e "${R}[âœ—] Ce script doit Ãªtre exÃ©cutÃ© en tant que root (sudo).${NC}"
  exit 1
fi

if ! command -v systemctl &>/dev/null; then
  echo -e "${R}[âœ—] systemd requis (systemctl non trouvÃ©).${NC}"
  exit 1
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
PY_MAJ=$(echo "$PY_VER" | cut -d. -f1)
PY_MIN=$(echo "$PY_VER" | cut -d. -f2)
if [ "$PY_MAJ" -lt 3 ] || { [ "$PY_MAJ" -eq 3 ] && [ "$PY_MIN" -lt 8 ]; }; then
  echo -e "${R}[âœ—] Python 3.8+ requis (dÃ©tectÃ© : $PY_VER).${NC}"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ ! -f "$SCRIPT_DIR/app.py" ] || [ ! -f "$SCRIPT_DIR/core/config.py" ] || [ ! -f "$SCRIPT_DIR/blueprints/auth.py" ]; then
  echo -e "${R}[âœ—] Sources incomplÃ¨tes dans $SCRIPT_DIR (app.py, core/config.py ou blueprints/auth.py manquant).${NC}"
  echo -e "    Ce script doit Ãªtre lancÃ© depuis le rÃ©pertoire du projet."
  exit 1
fi

# â”€â”€ DÃ©tection d'une installation existante â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

if [ -d "$INSTALL_DIR" ] && [ -f "$CONFIG_DIR/config.json" ]; then
  echo -e "${Y}[!]${NC} Une installation existante a Ã©tÃ© dÃ©tectÃ©e dans $INSTALL_DIR"
  echo -e "    Pour mettre Ã  jour, utilisez plutÃ´t ${B}update.sh${NC}"
  echo ""
  read -p "  Ã‰craser l'installation existante ? Les donnÃ©es sont conservÃ©es. [o/N] : " CONFIRM
  CONFIRM=${CONFIRM:-N}
  if [[ ! "$CONFIRM" =~ ^[oOyY]$ ]]; then
    echo -e "  AnnulÃ©."
    exit 0
  fi
  echo ""
fi

# â”€â”€ Configuration interactive â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

echo -e "${C}[?]${NC} Configuration de l'interface web"
echo ""

read -p "  Port web [5080]: " PORT
PORT=${PORT:-5080}

# VÃ©rifier si le port est disponible
if ss -tlnp "sport = :$PORT" 2>/dev/null | grep -q LISTEN; then
  echo -e "  ${Y}[!]${NC} Le port $PORT est dÃ©jÃ  utilisÃ© â€” le service dÃ©marrera quand mÃªme"
fi

read -p "  Nom d'utilisateur admin [admin]: " ADMIN_USER
ADMIN_USER=${ADMIN_USER:-admin}

while true; do
  read -s -p "  Mot de passe admin: " ADMIN_PASS; echo ""
  if [ ${#ADMIN_PASS} -lt 8 ]; then
    echo -e "  ${Y}[!]${NC} Minimum 8 caractÃ¨res."
  else
    break
  fi
done

read -s -p "  Confirmer le mot de passe: " ADMIN_PASS2; echo ""
if [ "$ADMIN_PASS" != "$ADMIN_PASS2" ]; then
  echo -e "${R}[âœ—] Les mots de passe ne correspondent pas.${NC}"
  exit 1
fi

read -p "  RÃ©pertoire de donnÃ©es [/srv/nxslab-bkp]: " DATA_DIR
DATA_DIR=${DATA_DIR:-/srv/nxslab-bkp}

echo ""
echo -e "${C}[â†’]${NC} DÃ©marrage de l'installation...\n"

# â”€â”€ 1. SystÃ¨me â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

echo -e "${C}[1/6]${NC} Installation des paquets systÃ¨me..."
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  python3 python3-pip python3-venv samba vsftpd curl 2>/dev/null
echo -e "  ${G}âœ“${NC} python3 $(python3 --version 2>&1 | cut -d' ' -f2), samba, vsftpd installÃ©s"

# â”€â”€ 2. RÃ©pertoires â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

echo -e "${C}[2/6]${NC} CrÃ©ation des rÃ©pertoires..."
mkdir -p "$INSTALL_DIR/core"
mkdir -p "$INSTALL_DIR/blueprints"
mkdir -p "$INSTALL_DIR/templates/partials"
mkdir -p "$INSTALL_DIR/static/css"
mkdir -p "$INSTALL_DIR/static/js"
mkdir -p "$CONFIG_DIR"
mkdir -p "$DATA_DIR"
chmod 775 "$DATA_DIR"
echo -e "  ${G}âœ“${NC} $INSTALL_DIR"
echo -e "  ${G}âœ“${NC} $DATA_DIR (donnÃ©es)"

# â”€â”€ 3. Copie des fichiers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

echo -e "${C}[3/6]${NC} Copie des fichiers..."

# Code applicatif
for f in "${APP_FILES[@]}"; do
  [ -f "$SCRIPT_DIR/$f" ] && cp "$SCRIPT_DIR/$f" "$INSTALL_DIR/"
done
for d in "${APP_DIRS[@]}"; do
  [ -d "$SCRIPT_DIR/$d" ] && rm -rf "$INSTALL_DIR/$d" && cp -a "$SCRIPT_DIR/$d" "$INSTALL_DIR/"
done
chmod 750 "$INSTALL_DIR/app.py"

# Templates
cp "$SCRIPT_DIR/templates/login.html" "$INSTALL_DIR/templates/"
cp "$SCRIPT_DIR/templates/index.html" "$INSTALL_DIR/templates/"
cp "$SCRIPT_DIR/templates/partials/"*.html "$INSTALL_DIR/templates/partials/"

# Fichiers statiques
[ -f "$SCRIPT_DIR/static/css/app.css" ] && cp "$SCRIPT_DIR/static/css/app.css" "$INSTALL_DIR/static/css/"
[ -f "$SCRIPT_DIR/static/js/app.js"  ] && cp "$SCRIPT_DIR/static/js/app.js"  "$INSTALL_DIR/static/js/"

echo -e "  ${G}âœ“${NC} code applicatif, templates, assets statiques"

# â”€â”€ 4. Environnement Python â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

echo -e "${C}[4/6]${NC} CrÃ©ation de l'environnement Python..."
python3 -m venv "$INSTALL_DIR/venv" --prompt nxslab-bkp
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet flask paramiko apscheduler flask-sock
echo -e "  ${G}âœ“${NC} Flask, paramiko, apscheduler, flask-sock installÃ©s"

# â”€â”€ 5. Configuration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

echo -e "${C}[5/6]${NC} GÃ©nÃ©ration de la configuration..."

PASS_HASH=$(printf '%s' "$ADMIN_PASS" | \
  "$INSTALL_DIR/venv/bin/python3" -c \
  "import hashlib, sys; print(hashlib.sha256(sys.stdin.read().encode()).hexdigest())")

SECRET_KEY=$("$INSTALL_DIR/venv/bin/python3" -c \
  "import secrets; print(secrets.token_hex(32))")

# Ne pas Ã©craser le config si l'utilisateur a confirmÃ© la rÃ©install mais il y a dÃ©jÃ  un config
if [ ! -f "$CONFIG_DIR/config.json" ]; then
  cat > "$CONFIG_DIR/config.json" <<JSON
{
  "users": [{"username": "${ADMIN_USER}", "password_hash": "${PASS_HASH}", "role": "admin"}],
  "secret_key": "${SECRET_KEY}",
  "port": ${PORT},
  "data_dir": "${DATA_DIR}",
  "remotes": []
}
JSON
  chmod 600 "$CONFIG_DIR/config.json"
  echo -e "  ${G}âœ“${NC} $CONFIG_DIR/config.json crÃ©Ã©"
else
  echo -e "  ${Y}[!]${NC} config.json existant conservÃ© (utilisateurs et remotes prÃ©servÃ©s)"
fi

# vsftpd
VSFTPD_CONF="/etc/vsftpd.conf"
if ! grep -q "local_enable=YES" "$VSFTPD_CONF" 2>/dev/null; then
  echo -e "  ${Y}[i]${NC} Application de la config vsftpd..."
  cat >> "$VSFTPD_CONF" <<VSFTPD

# NXSlab â€” added by install.sh
local_enable=YES
write_enable=YES
local_umask=022
chroot_local_user=YES
allow_writeable_chroot=YES
local_root=${DATA_DIR}
VSFTPD
  echo -e "  ${G}âœ“${NC} vsftpd configurÃ©"
fi

# Partage Samba
SMB_CONF="/etc/samba/smb.conf"
if [ -f "$SMB_CONF" ] && ! grep -q "\[nxslab-bkp\]" "$SMB_CONF"; then
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
  echo -e "  ${G}âœ“${NC} Partage Samba [nxslab-bkp] â†’ $DATA_DIR"
fi

# â”€â”€ 6. Service systemd â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

echo -e "${C}[6/6]${NC} Configuration du service systemd..."

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

# Attendre jusqu'Ã  8 secondes que le service soit actif
for i in 1 2 3 4; do
  sleep 2
  if systemctl is-active "$SERVICE" --quiet; then
    break
  fi
done

if systemctl is-active "$SERVICE" --quiet; then
  STATUS="${G}âœ“ actif${NC}"
  FAILED=0
else
  STATUS="${R}âœ— erreur${NC}"
  FAILED=1
fi

# â”€â”€ 6b. nginx (optionnel) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

NGINX_SITE=""
if command -v nginx &>/dev/null && [ -d "/etc/nginx/sites-available" ]; then
  echo ""
  read -p "  nginx dÃ©tectÃ© â€” configurer un site reverse proxy ? [o/N] : " NGINX_CONFIRM
  NGINX_CONFIRM=${NGINX_CONFIRM:-N}
  if [[ "$NGINX_CONFIRM" =~ ^[oOyY]$ ]]; then
    read -p "  Nom de domaine (ex: bkp.example.com) [laisser vide = IP seule] : " NGINX_DOMAIN
    NGINX_DOMAIN=${NGINX_DOMAIN:-_}
    NGINX_SITE="/etc/nginx/sites-available/nxslab-bkp"
    cat > "$NGINX_SITE" <<NGINX
server {
    listen 80;
    server_name ${NGINX_DOMAIN};

    location /ws/ {
        proxy_pass         http://127.0.0.1:${PORT};
        proxy_http_version 1.1;
        proxy_set_header   Upgrade    \$http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host       \$host;
        proxy_set_header   X-Real-IP  \$remote_addr;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
        proxy_buffering    off;
    }

    location / {
        proxy_pass         http://127.0.0.1:${PORT};
        proxy_http_version 1.1;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
        client_max_body_size 0;
    }
}
NGINX
    ln -sf "$NGINX_SITE" "/etc/nginx/sites-enabled/nxslab-bkp" 2>/dev/null || true
    if nginx -t &>/dev/null; then
      systemctl reload nginx
      echo -e "  ${G}âœ“${NC} nginx configurÃ© â†’ ${NGINX_DOMAIN}"
    else
      echo -e "  ${Y}[!]${NC} nginx -t a Ã©chouÃ© â€” vÃ©rifier manuellement $NGINX_SITE"
    fi
  fi
fi

# â”€â”€ RÃ©sumÃ© â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo ""
if [ "$FAILED" -eq 0 ]; then
  echo -e "${G}â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—${NC}"
  echo -e "${G}â•‘       Installation terminÃ©e avec succÃ¨s !            â•‘${NC}"
  echo -e "${G}â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•${NC}"
else
  echo -e "${R}â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—${NC}"
  echo -e "${R}â•‘     Installation terminÃ©e â€” service en erreur !      â•‘${NC}"
  echo -e "${R}â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•${NC}"
fi
echo ""
echo -e "  ${B}Interface web :${NC}  http://$IP:$PORT"
echo -e "  ${B}Utilisateur   :${NC}  $ADMIN_USER"
echo -e "  ${B}DonnÃ©es       :${NC}  $DATA_DIR"
echo -e "  ${B}Service       :${NC}  $SERVICE (${STATUS})"
echo ""
if [ "$FAILED" -eq 1 ]; then
  echo -e "  ${Y}DerniÃ¨res lignes du journal :${NC}"
  journalctl -u "$SERVICE" -n 8 --no-pager 2>/dev/null | sed 's/^/    /'
  echo ""
fi
echo -e "  Commandes utiles :"
echo -e "  ${D}systemctl status  $SERVICE${NC}"
echo -e "  ${D}systemctl restart $SERVICE${NC}"
echo -e "  ${D}journalctl -u $SERVICE -f${NC}"
echo ""
echo -e "${D}  NXSlab Backup WebUI â€” NeXoS_20${NC}"
echo ""
