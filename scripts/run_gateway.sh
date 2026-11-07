#!/bin/bash
# ==============================================================================
# Helper script to run Gateway locally on Ubuntu development machine
# ==============================================================================

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${ROOT_DIR}:${PYTHONPATH}"

echo "Starting MYIR MYS-6ULX Gateway Daemon locally..."
python3 "${ROOT_DIR}/gateway/gateway_daemon.py" "$@"
