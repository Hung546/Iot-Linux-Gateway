# ĐỒ ÁN 1 (CE201) – NHÓM N06
## Mạng Node Thu Thập Dữ Liệu Môi Trường Trên Nền Tảng Nhúng Linux i.MX6 (MYIR) Truyền Về Nền Tảng IoT

- **Thành viên thực hiện**:
  - **Mai Thế Hùng** (24520598) – *Phụ trách Gateway Linux i.MX6 (MYIR MYS-6ULX-IND)*
  - **Phan Xuân Hoàng** (24520566) – *Phụ trách Firmware ESP32 & Cảm biến*
- **Khoa**: Kỹ thuật Máy tính – Trường Đại học Công nghệ Thông tin (ĐHQG-HCM)
- **Hệ điều hành Gateway**: Embedded Linux trên vi xử lý NXP i.MX 6ULL ARM Cortex-A7
- **Phần cứng Gateway**: **MYIR MYS-6ULX-IND** (Industrial Grade)

---

## 1. Giới Thiệu Chung

Dự án hiện thực một trạm Gateway nhúng thông minh đóng vai trò trung gian thu thập dữ liệu quan trắc môi trường (Nhiệt độ, Độ ẩm từ SHT3x, Bụi mịn PM2.5 từ PMS5003, Khí CO2 từ SCD4x) từ $\ge 2$ Node ESP32 trong mạng cục bộ và đẩy lên nền tảng IoT Cloud (ThingsBoard).

Hệ thống được trang bị tính năng sống còn **Store-and-Forward (Lưu đệm và Gửi bù)**: Khi kết nối Internet bị mất, toàn bộ dữ liệu quan trắc được lưu trữ an toàn vào cơ sở dữ liệu SQLite nhúng trên Gateway; khi đường truyền mạng hồi phục, dữ liệu được gửi bù tuần tự lên máy chủ theo đúng thứ tự thời gian mà **không bị mất mát bất kỳ bản tin nào**.

---

## 2. Cấu Trúc Thư Mục

```
DO_AN_1/
├── gateway/                        # Dịch vụ hệ thống Gateway trên Linux i.MX6
│   ├── config.py                   # Bộ tải cấu hình (JSON / Môi trường / Mặc định)
│   ├── config.json                 # Tệp cấu hình chuẩn
│   ├── validator.py                # Kiểm tra tính hợp lệ của bản tin JSON M0/M1
│   ├── database.py                 # SQLite WAL engine, chống trùng lặp (Idempotency)
│   ├── ingestion_http.py           # REST API Server đa luồng đón bản tin (Port 8080)
│   ├── ingestion_mqtt.py           # Subscriber nhận bản tin từ MQTT Broker nội bộ
│   ├── forwarder.py                # Động cơ Store-and-Forward đẩy lên Cloud
│   ├── gateway_daemon.py           # Tiến trình nền chính quản lý hệ thống
│   └── gateway_cli.py              # Công cụ dòng lệnh kiểm tra cơ sở dữ liệu và node
├── scripts/                        # Kịch bản kiểm thử, mô phỏng và triển khai
│   ├── simulate_nodes.py           # Giả lập 2 Node ESP32 truyền dữ liệu
│   ├── run_demo_m2.sh              # Kịch bản chạy thực nghiệm tự động quay Video M2
│   ├── run_gateway.sh              # Chạy dịch vụ Gateway nhanh trên môi trường dev
│   └── deploy_board.sh             # Nạp code và cài systemd tự động lên board MYIR
├── systemd/                        # Cấu hình dịch vụ hệ thống cho Linux
│   ├── mys6ulx-gateway.service     # Unit file systemd tự chạy khi boot
│   └── install_service.sh          # Script cài đặt dịch vụ
├── tests/                          # Bộ kiểm thử tự động (Unit & Integration Tests)
│   ├── test_validator.py           # Kiểm thử chuẩn bản tin
│   ├── test_database.py            # Kiểm thử SQLite & chính sách lưu trữ
│   └── test_store_and_forward.py   # Kiểm thử cơ chế rớt mạng và gửi bù
├── docs/                           # Tài liệu báo cáo và triển khai
│   ├── BAO_CAO_TIEN_DO_M2.md       # Báo cáo tiến độ Mốc M2 chính thức
│   ├── DEPLOY_MYS6ULX.md           # Hướng dẫn đấu nối & nạp code lên board MYIR
│   └── ARCHITECTURE.md             # Tài liệu kiến trúc phần mềm chi tiết
├── requirements.txt                # Thư viện phụ thuộc
└── README.md
```

---

## 3. Hướng Dẫn Chạy Thử Nghiệm Trên Máy Tính Ubuntu (Không Cần Board)

Dịch vụ được thiết kế độc lập nền tảng, cho phép kiểm thử và chạy mô phỏng 100% chức năng trực tiếp trên Ubuntu trước khi nạp lên board nhúng.

### 3.1. Cài đặt môi trường
Dịch vụ chạy trực tiếp trên Python 3 chuẩn (không bắt buộc cài thêm thư viện phức tạp). Để sử dụng đầy đủ tính năng MQTT và kiểm thử:
```bash
pip install -r requirements.txt
```

### 3.2. Chạy bộ kiểm thử tự động (12 Tests)
```bash
python3 -m unittest discover -s tests
```
*Tất cả 12 ca kiểm thử sẽ vượt qua (OK) với thời gian thực thi ~2.5 giây.*

### 3.3. Chạy Kịch Bản Thực Nghiệm Cốt Lõi Mốc M2 (Dùng quay Video Demo)
Nhóm đã tích hợp toàn bộ kịch bản demo (Tiếp nhận $\ge 2$ node, kiểm thử chống lặp, giả lập mất mạng, lưu đệm `PENDING` và gửi bù `SENT`) vào một lệnh duy nhất:
```bash
./scripts/run_demo_m2.sh
```

---

## 4. Hướng Dẫn Sử Dụng Công Cụ CLI Giám Sát

Khi dịch vụ đang chạy, có thể kiểm tra trạng thái hoạt động bất cứ lúc nào qua công cụ `gateway_cli.py`:

- **Xem thông số tổng quan Gateway & Cơ sở dữ liệu**:
  ```bash
  python3 gateway/gateway_cli.py status
  ```
- **Xem danh sách các Node ESP32 đang kết nối**:
  ```bash
  python3 gateway/gateway_cli.py nodes
  ```
- **Xem bảng dữ liệu quan trắc gần nhất**:
  ```bash
  python3 gateway/gateway_cli.py recent --limit 10
  ```
- **Chuyển đổi trạng thái mạng giả lập (M2 Demo)**:
  ```bash
  python3 gateway/gateway_cli.py cloud --offline    # Giả lập rớt mạng (Lưu đệm vào SQLite)
  python3 gateway/gateway_cli.py cloud --online     # Giả lập có mạng lại (Tự động gửi bù)
  ```

---

## 5. Hướng Dẫn Triển Khai Lên Board MYIR MYS-6ULX-IND

Khi đã sẵn sàng thao tác trực tiếp trên phần cứng thật:
1. Kết nối cáp Ethernet giữa máy tính / mạng nội bộ và board `MYIR MYS-6ULX-IND`.
2. Chạy script triển khai tự động:
   ```bash
   ./scripts/deploy_board.sh <IP_CỦA_BOARD> root
   ```
3. Chi tiết các bước gạt switch boot, kết nối debug console UART (baud 115200) và kiểm tra Linux xem tại:
   [docs/DEPLOY_MYS6ULX.md](docs/DEPLOY_MYS6ULX.md)

---

## 6. Trạng Thái Hoàn Thành Đến Mốc M2

- [x] Thống nhất định dạng bản tin JSON M0/M1 và xử lý lỗi cảm biến `null`.
- [x] Hiện thực dịch vụ Linux đa luồng tiếp nhận bản tin qua REST API và MQTT.
- [x] Xây dựng cơ sở dữ liệu SQLite nhúng với chế độ WAL chống hỏng flash thẻ nhớ.
- [x] Hiện thực cơ chế chống lặp bản tin (Idempotency / Deduplication) qua `message_id`.
- [x] Hiện thực cơ chế Store-and-Forward (Lưu đệm khi rớt mạng, gửi bù khi có mạng).
- [x] Xây dựng bộ mô phỏng 2 Node ESP32 phát sinh dữ liệu cảm biến thực tế.
- [x] Hoàn thiện bộ kiểm thử tự động 12 test cases.
- [x] Hoàn thiện kịch bản demo và tài liệu báo cáo tiến độ Mốc M2.
