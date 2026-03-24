#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════
# DeepGuard – Uninstall Script
# Usage: sudo bash uninstall.sh
# ════════════════════════════════════════════════════════════════
set -euo pipefail

SERVICE_NAME="deepguard"
INSTALL_DIR="/opt/deepguard"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
LOG_DIR="/var/log/deepguard"
APP_USER="deepguard"

GREEN='\033[0;32m'; BLUE='\033[0;34m'; NC='\033[0m'; BOLD='\033[1m'
info() { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()   { echo -e "${GREEN}[OK]${NC}    $*"; }

[[ $EUID -ne 0 ]] && { echo "Please run as root: sudo bash uninstall.sh"; exit 1; }

echo -e "\n${BOLD}🗑️  DeepGuard Uninstaller${NC}\n"

info "Stopping and disabling service…"
systemctl stop    "${SERVICE_NAME}" 2>/dev/null || true
systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
ok "Service stopped"

info "Removing systemd unit…"
rm -f "${SERVICE_FILE}"
systemctl daemon-reload
ok "Unit file removed"

info "Removing application files from ${INSTALL_DIR}…"
rm -rf "${INSTALL_DIR}"
ok "Application files removed"

info "Removing log directory…"
rm -rf "${LOG_DIR}"
ok "Logs removed"

info "Removing system user '${APP_USER}'…"
userdel "${APP_USER}" 2>/dev/null || true
ok "User removed"

echo -e "\n${BOLD}${GREEN}✅  DeepGuard uninstalled successfully.${NC}\n"
