#!/bin/bash
# NXSlab Backup WebUI â€” Update script
# Usage: sudo bash update.sh
set -euo pipefail

R='\033[0;31m' G='\033[0;32m' C='\033[0;36m' Y='\033[1;33m'
B='\033[1m' D='\033[2m' NC='\033[0m'

INSTALL_DIR="/opt/nxslab-bkp"
CONFIG_DIR="/etc/nxslab-bkp"
SERVICE="nxslab-bkp"
REPO_URL="https://github.com/nexos20lv/NXSlab-Bkp.git"
REPO_HTTP_URL="${REPO_URL%.git}"
TMP_DIR=$(mktemp -d)
BACKUP_DIR=""

APP_FILES=(app.py)
APP_DIRS=(core blueprints)
ASSET_DIRS=(templates static)
LEGACY_MODULES=(config.py helpers.py auth.py system.py samba.py ftp.py files.py users.py backup_core.py remotes.py backup.py terminal.py)

echo ""
echo -e "${C}  â–ˆâ–ˆâ–ˆâ•—   â–ˆâ–ˆâ•—â–ˆâ–ˆâ•—  â–ˆâ–ˆâ•—â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•—â–ˆâ–ˆâ•—      â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•— â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•— ${NC}"
echo -e "${C}  â–ˆâ–ˆâ–ˆâ–ˆâ•—  â–ˆâ–ˆâ•‘â•šâ–ˆâ–ˆâ•—â–ˆâ–ˆâ•”â•â–ˆâ–ˆâ•”â•â•â•â•â•â–ˆâ–ˆâ•‘     â–ˆâ–ˆâ•”â•â•â–ˆâ–ˆâ•—â–ˆâ–ˆâ•”â•â•â–ˆâ–ˆâ•—${NC}"
echo -e "${C}  â–ˆâ–ˆâ•”â–ˆâ–ˆâ•— â–ˆâ–ˆâ•‘ â•šâ–ˆâ–ˆâ–ˆâ•”â• â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•—â–ˆâ–ˆâ•‘     â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•‘â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•”â•${NC}"
echo -e "${C}  â–ˆâ–ˆâ•‘â•šâ–ˆâ–ˆâ•—â–ˆâ–ˆâ•‘ â–ˆâ–ˆâ•”â–ˆâ–ˆâ•— â•šâ•â•â•â•â–ˆâ–ˆâ•‘â–ˆâ–ˆâ•‘     â–ˆâ–ˆâ•”â•â•â–ˆâ–ˆâ•‘â–ˆâ–ˆâ•”â•â•â–ˆâ–ˆâ•—${NC}"
echo -e "${C}  â–ˆâ–ˆâ•‘ â•šâ–ˆâ–ˆâ–ˆâ–ˆâ•‘â–ˆâ–ˆâ•”â• â–ˆâ–ˆâ•—â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•‘â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•—â–ˆâ–ˆâ•‘  â–ˆâ–ˆâ•‘â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•”â•${NC}"
echo -e "${C}  â•šâ•â•  â•šâ•â•â•â•â•šâ•â•  â•šâ•â•â•šâ•â•â•â•â•â•â•â•šâ•â•â•â•â•â•â•â•šâ•â•  â•šâ•â•â•šâ•â•â•â•â•â•${NC}"
echo -e "${D}        Backup WebUI â€” Mise Ã  jour${NC}"
echo ""

# â”€â”€ VÃ©rifications â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

if [ "$EUID" -ne 0 ]; then
  echo -e "${R}[âœ—] Ce script doit Ãªtre exÃ©cutÃ© en tant que root (sudo).${NC}"
  exit 1
fi

if [ ! -d "$INSTALL_DIR" ]; then
  echo -e "${R}[âœ—] Installation introuvable dans $INSTALL_DIR${NC}"
  echo -e "    Lancez d'abord install.sh"
  exit 1
fi

# â”€â”€ Rollback automatique en cas d'erreur â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

rollback() {
  echo -e "\n${R}[âœ—] Erreur pendant la mise Ã  jour â€” rollback...${NC}"
  if [ -n "$BACKUP_DIR" ] && [ -d "$BACKUP_DIR" ]; then
    cp -a "$BACKUP_DIR/." "$INSTALL_DIR/" 2>/dev/null || true
    echo -e "  ${Y}[!]${NC} Code restaurÃ© depuis la sauvegarde"
  fi
  systemctl start "$SERVICE" 2>/dev/null || true
  rm -rf "$TMP_DIR"
  echo -e "  ${Y}[!]${NC} VÃ©rifiez les logs : ${D}journalctl -u $SERVICE -n 30${NC}"
  exit 1
}
trap rollback ERR
trap 'rm -rf "$TMP_DIR"' EXIT

# â”€â”€ 1. TÃ©lÃ©chargement â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

echo -e "${C}[1/5]${NC} TÃ©lÃ©chargement depuis le dÃ©pÃ´t..."
SRC="$TMP_DIR/repo"

if command -v git &>/dev/null; then
  git clone --depth 1 --quiet "$REPO_URL" "$SRC" 2>/dev/null || {
    echo -e "${R}[âœ—] Impossible de cloner le dÃ©pÃ´t. VÃ©rifiez la connectivitÃ©.${NC}"
    exit 1
  }
else
  echo -e "  ${Y}[!]${NC} git non trouvÃ©, tÃ©lÃ©chargement via curl..."
  curl -fsSL "${REPO_HTTP_URL}/archive/refs/heads/master.tar.gz" -o "$TMP_DIR/repo.tar.gz" || {
    echo -e "${R}[âœ—] TÃ©lÃ©chargement Ã©chouÃ©.${NC}"
    exit 1
  }
  mkdir -p "$SRC"
  tar -xzf "$TMP_DIR/repo.tar.gz" -C "$SRC" --strip-components=1
fi

# VÃ©rifier que les fichiers essentiels sont prÃ©sents
if [ ! -f "$SRC/app.py" ] || [ ! -f "$SRC/core/config.py" ] || [ ! -f "$SRC/blueprints/auth.py" ]; then
  echo -e "${R}[âœ—] Sources incomplÃ¨tes (app.py, core/config.py ou blueprints/auth.py manquant).${NC}"
  exit 1
fi
echo -e "  ${G}âœ“${NC} Sources tÃ©lÃ©chargÃ©es"

# â”€â”€ 2. Sauvegarde des fichiers actuels â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

echo -e "${C}[2/5]${NC} Sauvegarde des fichiers actuels..."
BACKUP_DIR="$TMP_DIR/backup"
mkdir -p "$BACKUP_DIR"
for f in "${APP_FILES[@]}"; do
  [ -f "$INSTALL_DIR/$f" ] && cp -a "$INSTALL_DIR/$f" "$BACKUP_DIR/"
done
for d in "${APP_DIRS[@]}" "${ASSET_DIRS[@]}"; do
  [ -d "$INSTALL_DIR/$d" ] && cp -a "$INSTALL_DIR/$d" "$BACKUP_DIR/"
done
echo -e "  ${G}âœ“${NC} Sauvegarde dans $BACKUP_DIR"

# â”€â”€ 3. ArrÃªt du service â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

echo -e "${C}[3/5]${NC} ArrÃªt du service..."
if systemctl is-active "$SERVICE" --quiet 2>/dev/null; then
  systemctl stop "$SERVICE"
  echo -e "  ${G}âœ“${NC} Service arrÃªtÃ©"
else
  echo -e "  ${D}(service dÃ©jÃ  arrÃªtÃ©)${NC}"
fi

# â”€â”€ 4. Mise Ã  jour des fichiers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

echo -e "${C}[4/5]${NC} Mise Ã  jour des fichiers..."

# CrÃ©er les nouveaux rÃ©pertoires si nÃ©cessaire
mkdir -p "$INSTALL_DIR/core"
mkdir -p "$INSTALL_DIR/blueprints"
mkdir -p "$INSTALL_DIR/templates/partials"
mkdir -p "$INSTALL_DIR/static/css"
mkdir -p "$INSTALL_DIR/static/js"

# Code applicatif
UPDATED=0
for f in "${APP_FILES[@]}"; do
  if [ -f "$SRC/$f" ]; then
    cp "$SRC/$f" "$INSTALL_DIR/"
    UPDATED=$((UPDATED + 1))
  fi
done
for d in "${APP_DIRS[@]}"; do
  if [ -d "$SRC/$d" ]; then
    rm -rf "$INSTALL_DIR/$d"
    cp -a "$SRC/$d" "$INSTALL_DIR/"
    UPDATED=$((UPDATED + 1))
  fi
done

for f in "${LEGACY_MODULES[@]}"; do
  [ -f "$INSTALL_DIR/$f" ] && rm -f "$INSTALL_DIR/$f"
done

chmod 750 "$INSTALL_DIR/app.py"
echo -e "  ${G}âœ“${NC} $UPDATED Ã©lÃ©ments applicatifs"

# Templates
TPL_COUNT=0
if [ -d "$SRC/templates" ]; then
  rm -rf "$INSTALL_DIR/templates"
  cp -a "$SRC/templates" "$INSTALL_DIR/"
  TPL_COUNT=$(find "$SRC/templates" -type f -name '*.html' | wc -l)
fi
echo -e "  ${G}âœ“${NC} $TPL_COUNT templates"

# Assets statiques
STATIC_COUNT=0
[ -d "$SRC/static" ] && rm -rf "$INSTALL_DIR/static" && cp -a "$SRC/static" "$INSTALL_DIR/" && STATIC_COUNT=$(find "$SRC/static" -type f | wc -l)
[ "$STATIC_COUNT" -gt 0 ] && echo -e "  ${G}âœ“${NC} $STATIC_COUNT fichiers statiques"

# DÃ©pendances Python
echo -e "${C}[4/5]${NC} Mise Ã  jour des dÃ©pendances Python..."
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade flask paramiko apscheduler flask-sock
echo -e "  ${G}âœ“${NC} DÃ©pendances Ã  jour"

# â”€â”€ 5. RedÃ©marrage et vÃ©rification â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

echo -e "${C}[5/5]${NC} RedÃ©marrage du service..."
systemctl start "$SERVICE"

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

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
PORT=$("$INSTALL_DIR/venv/bin/python3" -c \
  "import json; c=json.load(open('$CONFIG_DIR/config.json')); print(c.get('port',5080))" 2>/dev/null || echo 5080)

echo ""
if [ "$FAILED" -eq 0 ]; then
  echo -e "${G}â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—${NC}"
  echo -e "${G}â•‘         Mise Ã  jour terminÃ©e avec succÃ¨s !           â•‘${NC}"
  echo -e "${G}â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•${NC}"
else
  echo -e "${R}â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—${NC}"
  echo -e "${R}â•‘      Mise Ã  jour terminÃ©e â€” service en erreur !      â•‘${NC}"
  echo -e "${R}â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•${NC}"
fi
echo ""
echo -e "  ${B}Interface web :${NC}  http://$IP:$PORT"
echo -e "  ${B}Service       :${NC}  $SERVICE (${STATUS})"
echo ""
if [ "$FAILED" -eq 1 ]; then
  echo -e "  ${Y}DerniÃ¨res lignes du journal :${NC}"
  journalctl -u "$SERVICE" -n 8 --no-pager 2>/dev/null | sed 's/^/    /'
  echo ""
fi
echo -e "  ${D}systemctl status  $SERVICE${NC}"
echo -e "  ${D}journalctl -u $SERVICE -f${NC}"
echo ""
echo -e "${D}  NXSlab Backup WebUI â€” NeXoS_20${NC}"
echo ""
