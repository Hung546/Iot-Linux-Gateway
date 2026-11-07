#!/bin/bash
# ==============================================================================
# Installation script for systemd service on MYIR MYS-6ULX-IND (Embedded Linux)
# ==============================================================================

set -e

SERVICE_NAME="mys6ulx-gateway"
SERVICE_SRC="$(dirname "$0")/mys6ulx-gateway.service"
SERVICE_DEST="/etc/systemd/system/${SERVICE_NAME}.service"
APP_DIR="/opt/gateway"

echo "[INFO] Installing Gateway Service for MYIR MYS-6ULX..."

# 1. Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "[ERROR] Please run as root (sudo ./install_service.sh)"
  exit 1
fi

# 2. Setup target application directory
echo "[INFO] Setting up ${APP_DIR}..."
mkdir -p "${APP_DIR}/data" "${APP_DIR}/logs"
cp -r "$(dirname "$0")/../gateway" "${APP_DIR}/"
cp -r "$(dirname "$0")/../scripts" "${APP_DIR}/"

# 3. Copy service unit
echo "[INFO] Copying systemd unit to ${SERVICE_DEST}..."
cp "${SERVICE_SRC}" "${SERVICE_DEST}"
chmod 644 "${SERVICE_DEST}"

# 4. Reload systemd daemon
echo "[INFO] Reloading systemd..."
systemctl daemon-reload

# 5. Enable and start service
echo "[INFO] Enabling ${SERVICE_NAME} to start on boot..."
systemctl enable "${SERVICE_NAME}"

echo "[INFO] Starting ${SERVICE_NAME}..."
systemctl restart "${SERVICE_NAME}"

echo "[SUCCESS] Service installed and running!"
echo "Check status with: systemctl status ${SERVICE_NAME}"
echo "View live logs with: journalctl -u ${SERVICE_NAME} -f"
