#!/bin/bash
# NXSlab Backup WebUI — Update script
# Usage: sudo bash update.sh
set -e

R='\033[0;31m' G='\033[0;32m' C='\033[0;36m' Y='\033[1;33m'
B='\033[1m' D='\033[2m' NC='\033[0m'

INSTALL_DIR="/opt/nxslab-bkp"
SERVICE="nxslab-bkp"
REPO_URL="https://git.nxslab.in/Pierre/NXSlab-Bkp"
TMP_DIR=$(mktemp -d)

echo ""
echo -e "${C}  ███╗   ██╗██╗  ██╗███████╗██╗      █████╗ ██████╗ ${NC}"
echo -e "${C}  ████╗  ██║╚██╗██╔╝██╔════╝██║     ██╔══██╗██╔══██╗${NC}"
echo -e "${C}  ██╔██╗ ██║ ╚███╔╝ ███████╗██║     ███████║██████╔╝${NC}"
echo -e "${C}  ██║╚██╗██║ ██╔██╗ ╚════██║██║     ██╔══██║██╔══██╗${NC}"
echo -e "${C}  ██║ ╚████║██╔╝ ██╗███████║███████╗██║  ██║██████╔╝${NC}"
echo -e "${C}  ╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝╚═════╝${NC}"
echo -e "${D}        Backup WebUI — Mise à jour${NC}"
echo ""

if [ "$EUID" -ne 0 ]; then
  echo -e "${R}[✗] Ce script doit être exécuté en tant que root (sudo).${NC}"
  exit 1
fi

if [ ! -d "$INSTALL_DIR" ]; then
  echo -e "${R}[✗] Installation introuvable dans $INSTALL_DIR${NC}"
  echo -e "    Lancez d'abord install.sh"
  exit 1
fi

trap 'rm -rf "$TMP_DIR"' EXIT

echo -e "${C}[1/5]${NC} Téléchargement depuis le dépôt..."
if command -v git &>/dev/null; then
  git clone --depth 1 "$REPO_URL" "$TMP_DIR/repo" 2>/dev/null || {
    echo -e "${R}[✗] Impossible de cloner le dépôt. Vérifiez la connectivité.${NC}"
    exit 1
  }
  SRC="$TMP_DIR/repo"
else
  echo -e "  ${Y}[!]${NC} git non trouvé, tentative avec curl..."
  ARCHIVE_URL="${REPO_URL}/archive/refs/heads/main.tar.gz"
  curl -fsSL "$ARCHIVE_URL" -o "$TMP_DIR/repo.tar.gz" || {
    echo -e "${R}[✗] Téléchargement échoué.${NC}"
    exit 1
  }
  mkdir -p "$TMP_DIR/repo"
  tar -xzf "$TMP_DIR/repo.tar.gz" -C "$TMP_DIR/repo" --strip-components=1
  SRC="$TMP_DIR/repo"
fi
echo -e "  ${G}✓${NC} Sources téléchargées"

echo -e "${C}[2/5]${NC} Arrêt du service..."
systemctl stop "$SERVICE" 2>/dev/null && echo -e "  ${G}✓${NC} Service arrêté" || echo -e "  ${Y}[!]${NC} Service déjà arrêté"

echo -e "${C}[3/5]${NC} Mise à jour des fichiers..."

# Ensure new directories exist
mkdir -p "$INSTALL_DIR/templates/partials"
mkdir -p "$INSTALL_DIR/static/css"
mkdir -p "$INSTALL_DIR/static/js"

# Python modules
for f in app.py config.py helpers.py auth.py system.py samba.py ftp.py files.py users.py backup_core.py remotes.py backup.py terminal.py; do
  if [ -f "$SRC/$f" ]; then
    cp "$SRC/$f" "$INSTALL_DIR/"
    echo -e "  ${G}✓${NC} $f"
  fi
done
chmod 750 "$INSTALL_DIR/app.py" 2>/dev/null || true

# Templates
if [ -d "$SRC/templates" ]; then
  cp "$SRC/templates/"*.html "$INSTALL_DIR/templates/" 2>/dev/null || true
  [ -d "$SRC/templates/partials" ] && cp "$SRC/templates/partials/"*.html "$INSTALL_DIR/templates/partials/" 2>/dev/null || true
  echo -e "  ${G}✓${NC} templates"
fi

# Static assets
[ -f "$SRC/static/css/app.css" ] && cp "$SRC/static/css/app.css" "$INSTALL_DIR/static/css/" && echo -e "  ${G}✓${NC} static/css/app.css"
[ -f "$SRC/static/js/app.js"  ] && cp "$SRC/static/js/app.js"  "$INSTALL_DIR/static/js/"  && echo -e "  ${G}✓${NC} static/js/app.js"

echo -e "${C}[4/5]${NC} Mise à jour des dépendances Python..."
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade flask paramiko apscheduler flask-sock
echo -e "  ${G}✓${NC} Paquets Python mis à jour"

echo -e "${C}[5/5]${NC} Redémarrage du service..."
systemctl start "$SERVICE"
sleep 1

if systemctl is-active "$SERVICE" --quiet; then
  STATUS="${G}✓ actif${NC}"
else
  STATUS="${R}✗ erreur${NC}"
fi

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
PORT=$(python3 -c "import json; c=json.load(open('/etc/nxslab-bkp/config.json')); print(c.get('port',5080))" 2>/dev/null || echo 5080)

echo ""
echo -e "${G}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${G}║         Mise à jour terminée avec succès !           ║${NC}"
echo -e "${G}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${B}Interface web :${NC}  http://$IP:$PORT"
echo -e "  ${B}Service       :${NC}  $SERVICE (${STATUS})"
echo ""
echo -e "  Commandes utiles :"
echo -e "  ${D}systemctl status  $SERVICE${NC}"
echo -e "  ${D}journalctl -u $SERVICE -f${NC}"
echo ""
echo -e "${D}  NXSlab Backup WebUI — NeXoS_20${NC}"
echo ""
