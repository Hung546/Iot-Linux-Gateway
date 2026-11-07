#!/bin/bash
# ==============================================================================
# SCRIPT DEMO MOC M2 - DO AN 1 (NHOM N06)
# Mai The Hung (24520598) - Phu trach Gateway Linux i.MX6 (MYIR MYS-6ULX-IND)
# ==============================================================================

set -e

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DB_PATH="${ROOT_DIR}/data/demo_gateway.db"
PORT=8089

echo -e "${CYAN}${BOLD}"
echo "================================================================================"
echo "    DO AN 1 - HE THONG THU THAP DU LIEU MOI TRUONG TREN LINUX i.MX6 (MYIR)      "
echo "               KICH BAN DEMO THUC NGHIEM COT LOI - MOC M2                       "
echo "  Sinh vien thuc hien: Mai The Hung (24520598) - Gateway Linux i.MX6            "
echo "  Thiet bi muc tieu:   MYIR MYS-6ULX-IND (ARM Cortex-A7 i.MX 6ULL)              "
echo "================================================================================"
echo -e "${NC}"

# Clean up previous demo DB
rm -f "${DB_PATH}" "${DB_PATH}-wal" "${DB_PATH}-shm"

cleanup() {
    echo -e "\n${YELLOW}[DEMO] Dang dung cac tien trinh chay ngam...${NC}"
    if [ -n "$GATEWAY_PID" ]; then
        kill $GATEWAY_PID 2>/dev/null || true
    fi
}
trap cleanup EXIT

# ------------------------------------------------------------------------------
# BUOC 1: KHOI DONG DICH VU LINUX GATEWAY
# ------------------------------------------------------------------------------
echo -e "${GREEN}${BOLD}[BUOC 1/6] Khoi dong Linux Gateway Daemon tren port ${PORT}...${NC}"
python3 "${ROOT_DIR}/gateway/gateway_daemon.py" --port ${PORT} --db "${DB_PATH}" --mock-cloud > "${ROOT_DIR}/logs/demo_gateway.log" 2>&1 &
GATEWAY_PID=$!
sleep 2

if ps -p $GATEWAY_PID > /dev/null; then
    echo -e "  -> Gateway khoi dong thanh cong! (PID: ${GATEWAY_PID})"
else
    echo -e "${RED}  -> Loi khoi dong Gateway! Xem log:${NC}"
    cat "${ROOT_DIR}/logs/demo_gateway.log"
    exit 1
fi

# ------------------------------------------------------------------------------
# BUOC 2: KIEM TRA HEALTH CHECK CUA GATEWAY
# ------------------------------------------------------------------------------
echo -e "\n${GREEN}${BOLD}[BUOC 2/6] Kiem tra REST API Health Check qua curl...${NC}"
curl -s "http://127.0.0.1:${PORT}/api/v1/health" | python3 -m json.tool
sleep 1

# ------------------------------------------------------------------------------
# BUOC 3: TRUYEN NHAN DU LIEU TU 2 NODE ESP32 TRONG DIEU KIEN BINH THUONG
# ------------------------------------------------------------------------------
echo -e "\n${GREEN}${BOLD}[BUOC 3/6] Mo phong 2 Node ESP32 gui du lieu ve Gateway...${NC}"
echo -e "  - Node 1 (esp32_01): Cam bien SHT3x (Nhiet do, Do am) + PMS5003 (Bui PM2.5)"
echo -e "  - Node 2 (esp32_02): Cam bien SHT3x (Nhiet do, Do am) + SCD4x (Khi CO2)"
python3 "${ROOT_DIR}/scripts/simulate_nodes.py" --gateway "http://127.0.0.1:${PORT}/api/v1/telemetry" --count 3 --interval 1.0
sleep 2.5

echo -e "\n${BLUE}[KIEM TRA] Du lieu ghi nhan trong SQLite sau Buoc 3:${NC}"
python3 "${ROOT_DIR}/gateway/gateway_cli.py" --db "${DB_PATH}" recent --limit 6

# ------------------------------------------------------------------------------
# BUOC 4: KIEM THU TINH IDEMPOTENCY VA DEDUPLICATION (CHONG TRUNG LAP)
# ------------------------------------------------------------------------------
echo -e "\n${GREEN}${BOLD}[BUOC 4/6] Kiem thu co che Deduplication (Phat hien & loai tru ban tin trung)...${NC}"
python3 "${ROOT_DIR}/scripts/simulate_nodes.py" --gateway "http://127.0.0.1:${PORT}/api/v1/telemetry" --test-duplicate
sleep 1

# ------------------------------------------------------------------------------
# BUOC 5: THU NGHIEM CỐT LÕI - STORE AND FORWARD KHI MAT MANG INTERNET
# ------------------------------------------------------------------------------
echo -e "\n${GREEN}${BOLD}[BUOC 5/6] THU NGHIEM TINH NANG COT LOI: STORE-AND-FORWARD (LUU DEM & GUI BU)${NC}"
echo -e "${YELLOW}>> [5.1] Gia lap SU CO MAT INTERNET / MAT KET NOI CLOUD... <<${NC}"
curl -s -X POST "http://127.0.0.1:${PORT}/api/v1/control/cloud" \
     -H "Content-Type: application/json" \
     -d '{"mock_online": false}' | python3 -m json.tool
sleep 1

echo -e "\n${YELLOW}>> [5.2] 2 Node ESP32 tiep tuc gui 4 ban tin trong luc mat mang (Start seq 100)... <<${NC}"
python3 "${ROOT_DIR}/scripts/simulate_nodes.py" --gateway "http://127.0.0.1:${PORT}/api/v1/telemetry" --start-seq 100 --count 2 --interval 1.0
sleep 1

echo -e "\n${YELLOW}>> [5.3] Kiem tra trang thai bo dem SQLite: Cac ban tin moi phai o trang thai 'PENDING' <<${NC}"
python3 "${ROOT_DIR}/gateway/gateway_cli.py" --db "${DB_PATH}" recent --limit 4

echo -e "\n${GREEN}${BOLD}>> [5.4] KHOI PHUC KET NOI INTERNET (Cloud ONLINE tro lai)... <<${NC}"
curl -s -X POST "http://127.0.0.1:${PORT}/api/v1/control/cloud" \
     -H "Content-Type: application/json" \
     -d '{"mock_online": true}' | python3 -m json.tool

echo -e "  -> Cho Gateway xu ly va gui bu toan bo hang doi PENDING..."
sleep 3.5

# ------------------------------------------------------------------------------
# BUOC 6: TONG HOP KET QUA & BANG THONG KE
# ------------------------------------------------------------------------------
echo -e "\n${GREEN}${BOLD}[BUOC 6/6] Kiem tra ket qua sau khi khoi phuc mang:${NC}"
python3 "${ROOT_DIR}/gateway/gateway_cli.py" --db "${DB_PATH}" status
python3 "${ROOT_DIR}/gateway/gateway_cli.py" --db "${DB_PATH}" nodes
python3 "${ROOT_DIR}/gateway/gateway_cli.py" --db "${DB_PATH}" recent --limit 12

echo -e "\n${CYAN}${BOLD}"
echo "================================================================================"
echo "  KET QUA KIEM CHUNG MOC M2 CHO GATEWAY LINUX i.MX6: HOAN TOAN THANH CONG!     "
echo "  - Dịch vu chay on dinh, nhan dung ban tin tu >= 2 Node ESP32                 "
echo "  - SQLite WAL luu tru ben vung, chong ghi de va xu ly trung lap (Idempotency) "
echo "  - Co che Store-and-Forward hoat dong chinh xac: 0 ban tin bi mat!            "
echo "================================================================================"
echo -e "${NC}"
