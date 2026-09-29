#!/usr/bin/env bash
# ==============================================================================
# Dinner Decider — Incus / Canonical LXD Container Launch Script
# Run on an Incus or LXD host to create and test Dinner Decider in an LXC container
# ==============================================================================

set -euo pipefail

# Detect whether using incus or lxc CLI
if command -v incus &>/dev/null; then
  CLI="incus"
elif command -v lxc &>/dev/null; then
  CLI="lxc"
else
  echo "[-] Error: Neither 'incus' nor 'lxc' command found on this host." >&2
  exit 1
fi

CONTAINER_NAME="dinner-decider"
IMAGE="images:debian/12"

echo "=========================================================="
echo "  🍲 Launching Dinner Decider LXC container with ${CLI}    "
echo "=========================================================="

# 1. Launch Container
if $CLI info "$CONTAINER_NAME" &>/dev/null; then
  echo "[!] Container '${CONTAINER_NAME}' already exists."
else
  echo "[+] Launching Debian 12 container '${CONTAINER_NAME}'..."
  $CLI launch "$IMAGE" "$CONTAINER_NAME"
fi

# Wait for IP
echo "[+] Waiting for container network..."
for i in {1..20}; do
  IP=$($CLI list -c 4 --format csv "$CONTAINER_NAME" | cut -d' ' -f1)
  if [ -n "$IP" ] && [ "$IP" != "" ]; then
    break
  fi
  sleep 1
done

# 2. Push application directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"

echo "[+] Pushing files to container..."
$CLI exec "$CONTAINER_NAME" -- mkdir -p /opt/dinner-decider
$CLI file push -r "${PARENT_DIR}/app" "${CONTAINER_NAME}/opt/dinner-decider/"
$CLI file push -r "${PARENT_DIR}/static" "${CONTAINER_NAME}/opt/dinner-decider/"
$CLI file push -r "${PARENT_DIR}/lxc" "${CONTAINER_NAME}/opt/dinner-decider/"
$CLI file push "${PARENT_DIR}/main.py" "${CONTAINER_NAME}/opt/dinner-decider/main.py"
$CLI file push "${PARENT_DIR}/requirements.txt" "${CONTAINER_NAME}/opt/dinner-decider/requirements.txt"
$CLI file push "${PARENT_DIR}/.env.example" "${CONTAINER_NAME}/opt/dinner-decider/.env.example"
[ -f "${PARENT_DIR}/.env" ] && $CLI file push "${PARENT_DIR}/.env" "${CONTAINER_NAME}/opt/dinner-decider/.env" || true

# 3. Execute installation script
echo "[+] Running installation inside container..."
$CLI exec "$CONTAINER_NAME" -- chmod +x /opt/dinner-decider/lxc/install.sh
$CLI exec "$CONTAINER_NAME" -- /opt/dinner-decider/lxc/install.sh

IP=$($CLI list -c 4 --format csv "$CONTAINER_NAME" | cut -d' ' -f1)

echo ""
echo "=========================================================="
echo "  🎉 Incus/LXD Container '${CONTAINER_NAME}' is Ready!"
echo "=========================================================="
echo "  • Access URL:    http://${IP}:8000"
echo "  • Bash Shell:    ${CLI} exec ${CONTAINER_NAME} -- bash"
echo "  • View logs:     ${CLI} exec ${CONTAINER_NAME} -- journalctl -u dinner-decider -f"
echo "=========================================================="
