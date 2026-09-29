#!/usr/bin/env bash
# ==============================================================================
# Dinner Decider — LXC Container Update Script
# Run this on your Proxmox host from ~/Mealplan
# Usage: ./lxc/update.sh [CTID] (defaults to 123)
# ==============================================================================

set -euo pipefail

CTID="${1:-123}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=========================================================="
echo "  🍲 Updating Dinner Decider on Proxmox CT ${CTID}        "
echo "=========================================================="

echo "[+] Pulling latest changes from git repository..."
cd "$REPO_DIR"
git pull origin master

echo "[+] Syncing updated files into container ${CTID}..."
pct push "$CTID" "${REPO_DIR}/main.py" /opt/dinner-decider/main.py
pct push "$CTID" "${REPO_DIR}/requirements.txt" /opt/dinner-decider/requirements.txt

tar -C "${REPO_DIR}" -czf /tmp/dinner-decider-update.tar.gz app static
pct push "$CTID" /tmp/dinner-decider-update.tar.gz /opt/dinner-decider/update.tar.gz
pct exec "$CTID" -- tar -xzf /opt/dinner-decider/update.tar.gz -C /opt/dinner-decider/
pct exec "$CTID" -- chown -R dinnerdecider:dinnerdecider /opt/dinner-decider/app /opt/dinner-decider/static /opt/dinner-decider/main.py
pct exec "$CTID" -- rm -f /opt/dinner-decider/update.tar.gz
rm -f /tmp/dinner-decider-update.tar.gz

echo "[+] Restarting dinner-decider service..."
pct exec "$CTID" -- systemctl restart dinner-decider

echo ""
echo "=========================================================="
echo "  🎉 Dinner Decider updated and running on CT ${CTID}!"
echo "=========================================================="
