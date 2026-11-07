#!/bin/bash
# ==============================================================================
# Helper script to deploy Gateway code to physical MYIR MYS-6ULX-IND board via SSH/SCP
# Usage: ./scripts/deploy_board.sh [BOARD_IP] [BOARD_USER]
# Default: ./scripts/deploy_board.sh 192.168.1.150 root
# ==============================================================================

BOARD_IP="${1:-192.168.1.150}"
BOARD_USER="${2:-root}"
TARGET_DIR="/opt/gateway"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=================================================================="
echo " Deploying Gateway to MYIR MYS-6ULX-IND (${BOARD_USER}@${BOARD_IP})"
echo " Target Directory: ${TARGET_DIR}"
echo "=================================================================="

# Test ping
if ! ping -c 1 -W 2 "${BOARD_IP}" > /dev/null 2>&1; then
    echo "[WARNING] Cannot ping ${BOARD_IP}. Please check Ethernet/Wi-Fi connection."
fi

# Create remote directory
echo "[1/3] Creating directory on board..."
ssh "${BOARD_USER}@${BOARD_IP}" "mkdir -p ${TARGET_DIR}/data ${TARGET_DIR}/logs"

# Copy files
echo "[2/3] Transferring application files..."
rsync -avz --exclude "__pycache__" --exclude "*.db" --exclude "*.log" --exclude ".git" \
    "${ROOT_DIR}/gateway" \
    "${ROOT_DIR}/scripts" \
    "${ROOT_DIR}/systemd" \
    "${ROOT_DIR}/requirements.txt" \
    "${BOARD_USER}@${BOARD_IP}:${TARGET_DIR}/"

# Install systemd service
echo "[3/3] Setting up systemd service on board..."
ssh "${BOARD_USER}@${BOARD_IP}" "bash ${TARGET_DIR}/systemd/install_service.sh"

echo "[SUCCESS] Deployment completed!"
echo "To monitor logs: ssh ${BOARD_USER}@${BOARD_IP} 'journalctl -u mys6ulx-gateway -f'"
