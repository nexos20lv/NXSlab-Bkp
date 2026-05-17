#!/bin/bash
# NXSlab Backup WebUI — Update script
# Usage: sudo bash update.sh
set -euo pipefail

R='\033[0;31m' G='\033[0;32m' C='\033[0;36m' Y='\033[1;33m'
B='\033[1m' D='\033[2m' NC='\033[0m'

INSTALL_DIR="/opt/nxslab-bkp"
CONFIG_DIR="/etc/nxslab-bkp"
SERVICE="nxslab-bkp"
REPO_URL="https://git.nxslab.in/Pierre/NXSlab-Bkp"
TMP_DIR=$(mktemp -d)
BACKUP_DIR=""

PY_MODULES="app.py config.py helpers.py auth.py system.py samba.py ftp.py files.py users.py backup_core.py remotes.py backup.py terminal.py"

echo ""
echo -e "${C}  ███╗   ██╗██╗  ██╗███████╗██╗      █████╗ ██████╗ ${NC}"
echo -e "${C}  ████╗  ██║╚██╗██╔╝██╔════╝██║     ██╔══██╗██╔══██╗${NC}"
echo -e "${C}  ██╔██╗ ██║ ╚███╔╝ ███████╗██║     ███████║██████╔╝${NC}"
echo -e "${C}  ██║╚██╗██║ ██╔██╗ ╚════██║██║     ██╔══██║██╔══██╗${NC}"
echo -e "${C}  ██║ ╚████║██╔╝ ██╗███████║███████╗██║  ██║██████╔╝${NC}"
echo -e "${C}  ╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝╚═════╝${NC}"
echo -e "${D}        Backup WebUI — Mise à jour${NC}"
echo ""

# ── Vérifications ─────────────────────────────────────────────────────────────

if [ "$EUID" -ne 0 ]; then
  echo -e "${R}[✗] Ce script doit être exécuté en tant que root (sudo).${NC}"
  exit 1
fi

if [ ! -d "$INSTALL_DIR" ]; then
  echo -e "${R}[✗] Installation introuvable dans $INSTALL_DIR${NC}"
  echo -e "    Lancez d'abord install.sh"
  exit 1
fi

# ── Rollback automatique en cas d'erreur ──────────────────────────────────────

rollback() {
  echo -e "\n${R}[✗] Erreur pendant la mise à jour — rollback...${NC}"
  if [ -n "$BACKUP_DIR" ] && [ -d "$BACKUP_DIR" ]; then
    cp "$BACKUP_DIR/"*.py "$INSTALL_DIR/" 2>/dev/null || true
    echo -e "  ${Y}[!]${NC} Fichiers Python restaurés depuis la sauvegarde"
  fi
  systemctl start "$SERVICE" 2>/dev/null || true
  rm -rf "$TMP_DIR"
  echo -e "  ${Y}[!]${NC} Vérifiez les logs : ${D}journalctl -u $SERVICE -n 30${NC}"
  exit 1
}
trap rollback ERR
trap 'rm -rf "$TMP_DIR"' EXIT

# ── 1. Téléchargement ─────────────────────────────────────────────────────────

echo -e "${C}[1/5]${NC} Téléchargement depuis le dépôt..."
SRC="$TMP_DIR/repo"

if command -v git &>/dev/null; then
  git clone --depth 1 --quiet "$REPO_URL" "$SRC" 2>/dev/null || {
    echo -e "${R}[✗] Impossible de cloner le dépôt. Vérifiez la connectivité.${NC}"
    exit 1
  }
else
  echo -e "  ${Y}[!]${NC} git non trouvé, téléchargement via curl..."
  curl -fsSL "${REPO_URL}/archive/refs/heads/master.tar.gz" -o "$TMP_DIR/repo.tar.gz" || {
    echo -e "${R}[✗] Téléchargement échoué.${NC}"
    exit 1
  }
  mkdir -p "$SRC"
  tar -xzf "$TMP_DIR/repo.tar.gz" -C "$SRC" --strip-components=1
fi

# Vérifier que les fichiers essentiels sont présents
if [ ! -f "$SRC/app.py" ] || [ ! -f "$SRC/config.py" ]; then
  echo -e "${R}[✗] Sources incomplètes (app.py ou config.py manquant).${NC}"
  exit 1
fi
echo -e "  ${G}✓${NC} Sources téléchargées"

# ── 2. Sauvegarde des fichiers actuels ────────────────────────────────────────

echo -e "${C}[2/5]${NC} Sauvegarde des fichiers actuels..."
BACKUP_DIR="$TMP_DIR/backup"
mkdir -p "$BACKUP_DIR"
for f in $PY_MODULES; do
  [ -f "$INSTALL_DIR/$f" ] && cp "$INSTALL_DIR/$f" "$BACKUP_DIR/"
done
echo -e "  ${G}✓${NC} Sauvegarde dans $BACKUP_DIR"

# ── 3. Arrêt du service ───────────────────────────────────────────────────────

echo -e "${C}[3/5]${NC} Arrêt du service..."
if systemctl is-active "$SERVICE" --quiet 2>/dev/null; then
  systemctl stop "$SERVICE"
  echo -e "  ${G}✓${NC} Service arrêté"
else
  echo -e "  ${D}(service déjà arrêté)${NC}"
fi

# ── 4. Mise à jour des fichiers ───────────────────────────────────────────────

echo -e "${C}[4/5]${NC} Mise à jour des fichiers..."

# Créer les nouveaux répertoires si nécessaire
mkdir -p "$INSTALL_DIR/templates/partials"
mkdir -p "$INSTALL_DIR/static/css"
mkdir -p "$INSTALL_DIR/static/js"

# Modules Python
UPDATED=0
for f in $PY_MODULES; do
  if [ -f "$SRC/$f" ]; then
    cp "$SRC/$f" "$INSTALL_DIR/"
    UPDATED=$((UPDATED + 1))
  fi
done
chmod 750 "$INSTALL_DIR/app.py"
echo -e "  ${G}✓${NC} $UPDATED modules Python"

# Templates
TPL_COUNT=0
if [ -d "$SRC/templates" ]; then
  for f in "$SRC/templates/"*.html; do
    [ -f "$f" ] && cp "$f" "$INSTALL_DIR/templates/" && TPL_COUNT=$((TPL_COUNT + 1))
  done
  if [ -d "$SRC/templates/partials" ]; then
    for f in "$SRC/templates/partials/"*.html; do
      [ -f "$f" ] && cp "$f" "$INSTALL_DIR/templates/partials/" && TPL_COUNT=$((TPL_COUNT + 1))
    done
  fi
fi
echo -e "  ${G}✓${NC} $TPL_COUNT templates"

# Assets statiques
STATIC_COUNT=0
[ -f "$SRC/static/css/app.css" ] && cp "$SRC/static/css/app.css" "$INSTALL_DIR/static/css/" && STATIC_COUNT=$((STATIC_COUNT + 1))
[ -f "$SRC/static/js/app.js"  ] && cp "$SRC/static/js/app.js"  "$INSTALL_DIR/static/js/"  && STATIC_COUNT=$((STATIC_COUNT + 1))
[ "$STATIC_COUNT" -gt 0 ] && echo -e "  ${G}✓${NC} $STATIC_COUNT fichiers statiques"

# Dépendances Python
echo -e "${C}[4/5]${NC} Mise à jour des dépendances Python..."
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade flask paramiko apscheduler flask-sock
echo -e "  ${G}✓${NC} Dépendances à jour"

# ── 5. Redémarrage et vérification ────────────────────────────────────────────

echo -e "${C}[5/5]${NC} Redémarrage du service..."
systemctl start "$SERVICE"

# Attendre jusqu'à 8 secondes que le service soit actif
for i in 1 2 3 4; do
  sleep 2
  if systemctl is-active "$SERVICE" --quiet; then
    break
  fi
done

if systemctl is-active "$SERVICE" --quiet; then
  STATUS="${G}✓ actif${NC}"
  FAILED=0
else
  STATUS="${R}✗ erreur${NC}"
  FAILED=1
fi

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
PORT=$("$INSTALL_DIR/venv/bin/python3" -c \
  "import json; c=json.load(open('$CONFIG_DIR/config.json')); print(c.get('port',5080))" 2>/dev/null || echo 5080)

echo ""
if [ "$FAILED" -eq 0 ]; then
  echo -e "${G}╔══════════════════════════════════════════════════════╗${NC}"
  echo -e "${G}║         Mise à jour terminée avec succès !           ║${NC}"
  echo -e "${G}╚══════════════════════════════════════════════════════╝${NC}"
else
  echo -e "${R}╔══════════════════════════════════════════════════════╗${NC}"
  echo -e "${R}║      Mise à jour terminée — service en erreur !      ║${NC}"
  echo -e "${R}╚══════════════════════════════════════════════════════╝${NC}"
fi
echo ""
echo -e "  ${B}Interface web :${NC}  http://$IP:$PORT"
echo -e "  ${B}Service       :${NC}  $SERVICE (${STATUS})"
echo ""
if [ "$FAILED" -eq 1 ]; then
  echo -e "  ${Y}Dernières lignes du journal :${NC}"
  journalctl -u "$SERVICE" -n 8 --no-pager 2>/dev/null | sed 's/^/    /'
  echo ""
fi
echo -e "  ${D}systemctl status  $SERVICE${NC}"
echo -e "  ${D}journalctl -u $SERVICE -f${NC}"
echo ""
echo -e "${D}  NXSlab Backup WebUI — NeXoS_20${NC}"
echo ""
