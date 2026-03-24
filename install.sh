#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════
# DeepGuard – Installation Script
# Installs DeepGuard as a permanent systemd service on Linux.
# Usage: sudo bash install.sh
# ════════════════════════════════════════════════════════════════
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="deepguard"
INSTALL_DIR="/opt/deepguard"
VENV_DIR="${INSTALL_DIR}/venv"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
LOG_DIR="/var/log/deepguard"
APP_PORT="${DEEPGUARD_PORT:-8000}"
APP_USER="${DEEPGUARD_USER:-deepguard}"

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'
info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Pre-checks ────────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && err "Please run as root: sudo bash install.sh"
command -v python3 >/dev/null 2>&1 || err "python3 not found. Install Python 3.9+."
command -v pip3    >/dev/null 2>&1 || err "pip3 not found."

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
info "Python version: ${PYTHON_VERSION}"

echo -e "\n${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}   🛡️  DeepGuard Installer${NC}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

# ── Create system user ────────────────────────────────────────────────────────
if ! id "${APP_USER}" &>/dev/null; then
    info "Creating system user '${APP_USER}'…"
    useradd --system --no-create-home --shell /usr/sbin/nologin "${APP_USER}"
    ok "User '${APP_USER}' created"
else
    ok "User '${APP_USER}' already exists"
fi

# ── Copy application files ────────────────────────────────────────────────────
info "Installing application to ${INSTALL_DIR}…"
mkdir -p "${INSTALL_DIR}"
cp -r "${APP_DIR}/app"           "${INSTALL_DIR}/"
cp    "${APP_DIR}/requirements.txt" "${INSTALL_DIR}/"
chown -R "${APP_USER}:${APP_USER}" "${INSTALL_DIR}"
ok "Application files copied"

# ── Create log directory ──────────────────────────────────────────────────────
mkdir -p "${LOG_DIR}"
chown "${APP_USER}:${APP_USER}" "${LOG_DIR}"

# ── Create virtual environment ────────────────────────────────────────────────
info "Creating Python virtual environment at ${VENV_DIR}…"
python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/pip" install --upgrade pip -q
info "Installing Python dependencies (this may take a few minutes)…"
"${VENV_DIR}/bin/pip" install -r "${INSTALL_DIR}/requirements.txt" -q
ok "Dependencies installed"

# ── Write systemd unit file ───────────────────────────────────────────────────
info "Writing systemd service unit to ${SERVICE_FILE}…"
cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=DeepGuard – Multimodal Deepfake & Fake-News Detector
Documentation=https://github.com/Ansh200618/DEEPFAKE
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${VENV_DIR}/bin/uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT} --workers 2
Restart=always
RestartSec=5
StandardOutput=append:${LOG_DIR}/access.log
StandardError=append:${LOG_DIR}/error.log
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONPATH=${INSTALL_DIR}
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=${LOG_DIR}

[Install]
WantedBy=multi-user.target
EOF
ok "Service unit written"

# ── Enable and start ──────────────────────────────────────────────────────────
info "Enabling and starting DeepGuard service…"
systemctl daemon-reload
systemctl enable  "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

# ── Open firewall (optional) ──────────────────────────────────────────────────
if command -v ufw &>/dev/null; then
    info "Opening port ${APP_PORT} in ufw…"
    ufw allow "${APP_PORT}/tcp" >/dev/null 2>&1 && ok "ufw rule added"
fi

# ── Status check ─────────────────────────────────────────────────────────────
sleep 2
if systemctl is-active --quiet "${SERVICE_NAME}"; then
    ok "DeepGuard is running!"
else
    warn "Service may not have started. Check: journalctl -u ${SERVICE_NAME} -n 30"
fi

echo -e "\n${BOLD}${GREEN}✅  Installation complete!${NC}"
echo -e "   App URL : ${BOLD}http://localhost:${APP_PORT}${NC}"
echo -e "   Logs    : ${BOLD}${LOG_DIR}/${NC}"
echo -e "   Status  : ${BOLD}systemctl status ${SERVICE_NAME}${NC}"
echo -e "   Stop    : ${BOLD}systemctl stop ${SERVICE_NAME}${NC}"
echo -e "   Remove  : ${BOLD}sudo bash uninstall.sh${NC}\n"
