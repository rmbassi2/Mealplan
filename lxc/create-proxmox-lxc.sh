#!/usr/bin/env bash
# ==============================================================================
# Dinner Decider — Proxmox VE LXC Creation & Provisioning Script
# Run this script directly on your Proxmox VE host (via Web Shell or SSH)
# ==============================================================================

set -euo pipefail

echo "=========================================================="
echo "  🍲 Dinner Decider — Proxmox VE LXC Provisioner          "
echo "=========================================================="

# 1. Ensure running on Proxmox VE
if ! command -v pveversion &>/dev/null; then
  echo "[-] Error: This script is intended to be run directly on a Proxmox VE host." >&2
  exit 1
fi

# 2. Defaults and Configuration
HOSTNAME="${HOSTNAME:-dinner-decider}"
MEMORY="${MEMORY:-512}"
SWAP="${SWAP:-256}"
CORES="${CORES:-1}"
DISK_SIZE="${DISK_SIZE:-4G}"
STORAGE="${STORAGE:-local-lvm}"
BRIDGE="${BRIDGE:-vmbr0}"
VZTMPL_STORAGE="${VZTMPL_STORAGE:-local}"

# Get next available CTID
NEXT_CTID=$(pvesh get /cluster/nextid)
read -r -p "Enter Container ID [${NEXT_CTID}]: " CTID_INPUT
CTID="${CTID_INPUT:-$NEXT_CTID}"

# Check Storage availability
if ! pvesm status -storage "$STORAGE" &>/dev/null; then
  echo "[!] Storage '${STORAGE}' not found. Falling back to default available storage..."
  STORAGE=$(pvesm status -content rootdir | awk 'NR>1 {print $1; exit}')
  echo "[+] Selected rootdir storage: ${STORAGE}"
fi

# 3. Locate or Download Debian 12 Template
echo "[+] Checking for Debian 12 LXC template..."
TEMPLATE_NAME=$(pveam available -section system | awk '{print $2}' | grep -E "debian-12-standard.*\.tar\.(zst|xz|gz)" | tail -n 1)

if [ -z "$TEMPLATE_NAME" ]; then
  echo "[-] Could not find Debian 12 standard template in pveam catalog. Using available local templates..."
  TEMPLATE=$(pveam list "$VZTMPL_STORAGE" | awk '$1 ~ /debian/ {print $1; exit}')
else
  # Check if template is already downloaded
  TEMPLATE="${VZTMPL_STORAGE}:vztmpl/${TEMPLATE_NAME}"
  if ! pveam list "$VZTMPL_STORAGE" | grep -q "$TEMPLATE_NAME"; then
    echo "[+] Downloading template ${TEMPLATE_NAME} to ${VZTMPL_STORAGE}..."
    pveam download "$VZTMPL_STORAGE" "$TEMPLATE_NAME"
  else
    echo "[+] Template already exists: ${TEMPLATE}"
  fi
fi

# 4. Create Container
echo "[+] Creating LXC container ${CTID} (${HOSTNAME})..."
pct create "$CTID" "$TEMPLATE" \
  --ostype debian \
  --hostname "$HOSTNAME" \
  --cores "$CORES" \
  --memory "$MEMORY" \
  --swap "$SWAP" \
  --rootfs "${STORAGE}:${DISK_SIZE}" \
  --net0 "name=eth0,bridge=${BRIDGE},ip=dhcp,type=veth" \
  --unprivileged 1 \
  --features nesting=1 \
  --onboot 1

# 5. Start Container
echo "[+] Starting container ${CTID}..."
pct start "$CTID"

echo "[+] Waiting for container network initialization (DHCP)..."
IP=""
for i in {1..30}; do
  IP=$(pct exec "$CTID" -- hostname -I 2>/dev/null | awk '{print $1}' || true)
  if [ -n "$IP" ] && [ "$IP" != "127.0.0.1" ]; then
    break
  fi
  sleep 1
done

if [ -z "$IP" ]; then
  echo "[!] Warning: Container did not obtain DHCP address yet. Checking later..."
fi

# 6. Copy or Clone project files into container
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"

echo "[+] Preparing container directories..."
pct exec "$CTID" -- mkdir -p /opt/dinner-decider

if [ -f "${PARENT_DIR}/main.py" ]; then
  echo "[+] Pushing project files from Proxmox host into container ${CTID}..."
  pct push "$CTID" "${PARENT_DIR}/main.py" /opt/dinner-decider/main.py
  pct push "$CTID" "${PARENT_DIR}/requirements.txt" /opt/dinner-decider/requirements.txt
  pct push "$CTID" "${PARENT_DIR}/.env.example" /opt/dinner-decider/.env.example
  [ -f "${PARENT_DIR}/.env" ] && pct push "$CTID" "${PARENT_DIR}/.env" /opt/dinner-decider/.env || true

  # Push directories (app, static, lxc)
  tar -C "${PARENT_DIR}" -czf /tmp/dinner-decider-app.tar.gz app static lxc
  pct push "$CTID" /tmp/dinner-decider-app.tar.gz /opt/dinner-decider/app.tar.gz
  pct exec "$CTID" -- tar -xzf /opt/dinner-decider/app.tar.gz -C /opt/dinner-decider/
  pct exec "$CTID" -- rm /opt/dinner-decider/app.tar.gz
  rm -f /tmp/dinner-decider-app.tar.gz
fi

# 7. Run the installer inside the container
echo "[+] Running installation script inside container..."
pct exec "$CTID" -- chmod +x /opt/dinner-decider/lxc/install.sh
pct exec "$CTID" -- /opt/dinner-decider/lxc/install.sh

IP=$(pct exec "$CTID" -- hostname -I 2>/dev/null | awk '{print $1}' || echo "UNKNOWN")

echo ""
echo "=========================================================="
echo "  🎉 LXC Container ${CTID} is Ready!"
echo "=========================================================="
echo "  • Web Interface: http://${IP}:8000"
echo "  • Container ID:  ${CTID}"
echo "  • To edit .env:  pct exec ${CTID} -- nano /opt/dinner-decider/.env"
echo "  • Restart app:   pct exec ${CTID} -- systemctl restart dinner-decider"
echo "  • View logs:     pct exec ${CTID} -- journalctl -u dinner-decider -f"
echo "=========================================================="
