#!/usr/bin/env bash
# ==============================================================================
# Dinner Decider — LXC Installation & Provisioning Script
# Suitable for Debian 11/12, Ubuntu 22.04/24.04 LXC containers
# ==============================================================================

set -euo pipefail

APP_NAME="dinner-decider"
APP_DIR="/opt/dinner-decider"
APP_USER="dinnerdecider"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"

echo "=========================================================="
echo "  🍲 Installing Dinner Decider in LXC Container           "
echo "=========================================================="

# 1. Check Root Privileges
if [ "$(id -u)" -ne 0 ]; then
  echo "[-] Error: This script must be run as root inside the LXC container." >&2
  exit 1
fi

# 2. Update package lists and install runtime dependencies
echo "[+] Updating system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
  python3 \
  python3-venv \
  python3-pip \
  curl \
  ca-certificates \
  git

# 3. Create unprivileged service user if not exists
if ! id -u "$APP_USER" &>/dev/null; then
  echo "[+] Creating dedicated service user '${APP_USER}'..."
  useradd -r -m -d "$APP_DIR" -s /bin/false "$APP_USER"
else
  echo "[+] User '${APP_USER}' already exists."
fi

# 4. Prepare application directory
echo "[+] Deploying application files to ${APP_DIR}..."
mkdir -p "$APP_DIR"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"

# If run from within the source repo clone
if [ -f "${PARENT_DIR}/main.py" ]; then
  echo "[+] Copying files from local repository (${PARENT_DIR})..."
  cp -r "${PARENT_DIR}/app" "$APP_DIR/"
  cp -r "${PARENT_DIR}/static" "$APP_DIR/"
  cp "${PARENT_DIR}/main.py" "$APP_DIR/"
  cp "${PARENT_DIR}/requirements.txt" "$APP_DIR/"
  cp "${PARENT_DIR}/.env.example" "$APP_DIR/"
  if [ -f "${PARENT_DIR}/.env" ] && [ ! -f "${APP_DIR}/.env" ]; then
    cp "${PARENT_DIR}/.env" "$APP_DIR/"
  fi
else
  echo "[!] Local repository files not found in parent directory."
  if [ ! -f "${APP_DIR}/main.py" ]; then
    echo "[-] Error: ${APP_DIR}/main.py is missing. Please ensure project files are in ${APP_DIR} or run this script from the project directory." >&2
    exit 1
  fi
fi

# 5. Create .env if not exists
if [ ! -f "${APP_DIR}/.env" ]; then
  echo "[+] Creating initial .env configuration from template..."
  cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
fi

# 6. Set up Python virtual environment
echo "[+] Setting up Python virtual environment in ${APP_DIR}/.venv..."
python3 -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/pip" install --no-cache-dir --upgrade pip
"${APP_DIR}/.venv/bin/pip" install --no-cache-dir -r "${APP_DIR}/requirements.txt"

# 7. Configure permissions
echo "[+] Setting ownership to '${APP_USER}'..."
chown -R "${APP_USER}:${APP_USER}" "$APP_DIR"
chmod 600 "${APP_DIR}/.env" || true

# 8. Install Systemd Service
echo "[+] Installing systemd service '${APP_NAME}.service'..."
if [ -f "${SCRIPT_DIR}/dinner-decider.service" ]; then
  cp "${SCRIPT_DIR}/dinner-decider.service" "$SERVICE_FILE"
else
  cat <<'EOF' > "$SERVICE_FILE"
[Unit]
Description=Dinner Decider - Mealie Dinner Voting Web App
After=network.target

[Service]
Type=simple
User=dinnerdecider
Group=dinnerdecider
WorkingDirectory=/opt/dinner-decider
EnvironmentFile=/opt/dinner-decider/.env
ExecStart=/opt/dinner-decider/.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true

[Install]
WantedBy=multi-user.target
EOF
fi

chmod 644 "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable "$APP_NAME"
systemctl restart "$APP_NAME"

# 9. Verify service health
echo "[+] Waiting for service startup..."
sleep 2

LXC_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")

if systemctl is-active --quiet "$APP_NAME"; then
  echo ""
  echo "=========================================================="
  echo "  ✅ Dinner Decider is successfully installed and running!"
  echo "=========================================================="
  echo "  • Access URL:    http://${LXC_IP}:8000"
  echo "  • Config File:   ${APP_DIR}/.env"
  echo "  • Service Logs:  journalctl -u ${APP_NAME} -f"
  echo "  • Status Check:  systemctl status ${APP_NAME}"
  echo ""
  echo "  Next Step: Update ${APP_DIR}/.env with your live Mealie URL"
  echo "  and API token, then run: systemctl restart ${APP_NAME}"
  echo "=========================================================="
else
  echo "[-] Warning: Service failed to start automatically. Check logs:"
  journalctl -u "$APP_NAME" -n 25 --no-pager
  exit 1
fi
