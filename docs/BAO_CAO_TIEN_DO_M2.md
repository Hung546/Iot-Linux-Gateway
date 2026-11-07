# BÁO CÁO TIẾN ĐỘ THỰC HIỆN ĐỀ TÀI – MỐC M2
**Đề tài**: Xây dựng mạng node thu thập dữ liệu môi trường trên nền tảng nhúng Linux i.MX6 (MYIR) truyền về nền tảng IoT  
**Mã nhóm**: N06 – Đồ án 1 (CE201)  
**Thời gian thực hiện**: Tuần 4 – Tuần 6 (19/10/2026 – 08/11/2026) | **Hạn nộp**: 09/11/2026  

---

### THÀNH VIÊN VÀ PHÂN CÔNG THỰC HIỆN
| Họ và tên | MSSV | Nhiệm vụ chính trong dự án | Nội dung hoàn thành đến Mốc M2 |
| :--- | :---: | :--- | :--- |
| **Mai Thế Hùng** *(Trưởng nhóm)* | **24520598** | Quản lý & phát triển Gateway Linux i.MX6 (MYIR MYS-6ULX-IND), dịch vụ hệ thống systemd, lưu trữ SQLite, cơ chế Store-and-Forward | Hoàn thành toàn bộ kiến trúc phần mềm Gateway Linux, bộ mô phỏng Node, kiểm thử tự động, kịch bản demo M2 và tài liệu triển khai phần cứng. |
| **Phan Xuân Hoàng** | **24520566** | Phát triển Firmware ESP32 (Node 1 & Node 2), giao tiếp cảm biến SHT3x, PMS5003, SCD4x, định dạng bản tin JSON M0/M1 | Phối hợp thống nhất định dạng bản tin; hoàn thiện logic đọc cảm biến và chuẩn bị tích hợp phần cứng nội bộ. |

---

## 1. MỤC TIÊU VÀ YÊU CẦU CỐT LÕI CỦA MỐC M2

Căn cứ theo bản đặc tả đề tài và kế hoạch 13 tuần đã nộp ở Mốc M0/M1:
1. **Tuần 4**: Thiết lập dịch vụ Linux (`systemd`) chạy nền trên vi xử lý i.MX6 sẵn sàng tiếp nhận dữ liệu quan trắc từ các node.
2. **Tuần 5**: Hiện thực giao tiếp thực tế giữa $\ge 2$ node ESP32 và gateway i.MX6 theo chuẩn định dạng JSON đã thống nhất tại M0. Dữ liệu truyền nhận thành công trong mạng nội bộ.
3. **Tuần 6 (Mốc M2 - hạn 09/11/2026)**:
   - Đưa toàn bộ mã nguồn lên Git với cấu trúc module rõ ràng, chuẩn hóa.
   - Hoàn thiện module thử nghiệm cốt lõi (Core Prototype): Dịch vụ Gateway tiếp nhận bản tin, kiểm tra tính hợp lệ của schema, lưu đệm cơ sở dữ liệu SQLite chống mất mát dữ liệu và xử lý chống trùng lặp.
   - Thực nghiệm tính năng cốt lõi **Store-and-Forward (Lưu đệm & Gửi bù)** khi xảy ra sự cố mất kết nối mạng Internet.
   - Xây dựng kịch bản và quay video demo (thời lượng 1–3 phút) chứng minh hoạt động thực tế của hệ thống.

> **Chiến lược kiểm thử an toàn phần cứng**: Nhóm hiện đã có board phần cứng `MYIR MYS-6ULX-IND` (NXP i.MX 6ULL ARM Cortex-A7). Tuy nhiên, nhằm hạn chế rủi ro hỏng hóc hoặc sai lệch logic trong giai đoạn đầu (như đã phân tích tại mục 9 - Rủi ro & Dự phòng của Bản đặc tả M0), sinh viên Mai Thế Hùng đã triển khai kiến trúc phần mềm theo hướng độc lập nền tảng, hoàn thiện môi trường kiểm thử giả lập end-to-end trên Ubuntu trước. Kiến trúc này đảm bảo 100% tính tương thích khi nạp lên board nhúng i.MX6 thông qua cấu hình `systemd` và toolchain ARM có sẵn.

---

## 2. KIẾN TRÚC PHẦN MỀM GATEWAY LINUX i.MX6

Toàn bộ mã nguồn dịch vụ Gateway được đặt trong thư mục `UIT/DO_AN_1/gateway`, thiết kế theo mô hình đa luồng (multi-threaded), hướng module, đáp ứng yêu cầu tài nguyên nhúng của dòng vi xử lý ARM Cortex-A7:

```
UIT/DO_AN_1/
├── gateway/                        # Module dịch vụ Gateway trên Linux i.MX6
│   ├── __init__.py
│   ├── config.py                   # Cấu hình hệ thống (Port, DB, Cloud, Lưu trữ)
│   ├── config.json                 # File cấu hình mặc định dạng JSON
│   ├── validator.py                # Kiểm tra tính toàn vẹn và phạm vi dữ liệu cảm biến
│   ├── database.py                 # Động cơ lưu trữ SQLite (Chế độ WAL, chống trùng bản tin)
│   ├── ingestion_http.py           # Máy chủ REST API đa luồng tiếp nhận bản tin từ ESP32
│   ├── ingestion_mqtt.py           # Module đón nhận bản tin qua MQTT Broker nội bộ
│   ├── forwarder.py                # Động cơ Store-and-Forward đẩy dữ liệu lên ThingsBoard/IoT Cloud
│   ├── gateway_daemon.py           # Tiến trình nền chính quản lý vòng đời hệ thống
│   └── gateway_cli.py              # Công cụ dòng lệnh giám sát cơ sở dữ liệu và nút cảm biến
├── scripts/                        # Kịch bản kiểm thử, mô phỏng và triển khai
│   ├── simulate_nodes.py           # Bộ mô phỏng 2 Node ESP32 truyền dữ liệu theo chuẩn M0
│   ├── run_demo_m2.sh              # Kịch bản chạy thực nghiệm tự động phục vụ quay Video Demo M2
│   ├── run_gateway.sh              # Kịch bản khởi chạy gateway nhanh trên môi trường dev
│   └── deploy_board.sh             # Kịch bản sao chép & cài đặt tự động lên board MYIR qua mạng
├── systemd/                        # Cấu hình dịch vụ hệ thống cho hệ điều hành Linux
│   ├── mys6ulx-gateway.service     # Unit file systemd tự khởi động cùng hệ điều hành
│   └── install_service.sh          # Script cài đặt dịch vụ tự động vào /etc/systemd/system/
├── tests/                          # Bộ kiểm thử tự động (Unit & Integration Tests)
│   ├── test_validator.py           # Kiểm tra định dạng bản tin JSON M0/M1
│   ├── test_database.py            # Kiểm tra đọc/ghi SQLite, chống trùng lặp, ring-buffer
│   └── test_store_and_forward.py   # Kiểm tra cơ chế lưu đệm khi mất mạng và gửi bù
├── docs/                           # Tài liệu kỹ thuật
│   ├── BAO_CAO_TIEN_DO_M2.md       # Báo cáo tiến độ Mốc M2
│   └── DEPLOY_MYS6ULX.md           # Hướng dẫn đấu nối & nạp code lên board MYIR MYS-6ULX-IND
├── requirements.txt
└── README.md
```

### Các thành phần kỹ thuật cốt lõi:

1. **Chuẩn hóa định dạng bản tin (Validator)**:
   - Tuân thủ chặt chẽ định dạng đã thống nhất tại Mốc M0/M1:
     ```json
     {
       "schema_version": 1,
       "node_id": "esp32_01",
       "message_id": "esp32_01-000001",
       "timestamp": "2026-11-07T13:19:11Z",
       "sensors": {
         "temperature_c": 28.4,
         "humidity_pct": 67.1,
         "pm25_ug_m3": 22.6,
         "co2_ppm": null
       }
     }
     ```
   - **Xử lý lỗi cảm biến**: Khi cảm biến bị hỏng hoặc mất kết nối phần cứng, node gửi giá trị `null`. Hệ thống **tuyệt đối không dùng giá trị 0** để biểu diễn lỗi (vì 0°C là một giá trị đo hoàn toàn hợp lệ trong thực tế).
   - Kiểm tra ngưỡng vật lý hợp lệ: Nhiệt độ (-40 đến 85°C), Độ ẩm (0 đến 100%), Bụi mịn PM2.5 (0 đến 1000 µg/m³), Khí CO2 (300 đến 10000 ppm).

2. **Cơ chế lưu trữ SQLite tối ưu cho bộ nhớ Flash i.MX6**:
   - Sử dụng **WAL Mode** (`PRAGMA journal_mode = WAL;`) và `PRAGMA synchronous = NORMAL;`. Cơ chế này cho phép đọc và ghi diễn ra đồng thời mà không bị khóa luồng (lock contention), đồng thời giảm tối đa số chu kỳ ghi đè lên các block flash của thẻ nhớ MicroSD/eMMC.
   - **Idempotency & Deduplication**: Khóa chính `message_id TEXT UNIQUE`. Khi node bị lỗi mạng cục bộ và phát lại bản tin cũ, Gateway lập tức nhận diện bản tin đã tồn tại, phản hồi mã HTTP `200 (duplicate_ignored)` và không ghi đè thêm bản ghi rác vào bộ nhớ.

3. **Cơ chế Lưu đệm và Gửi bù (Store-and-Forward)**:
   - Dữ liệu tiếp nhận từ các node được ghi vào bảng `telemetry` với trạng thái ban đầu là `PENDING`.
   - Một tiến trình nền (`CloudForwarder`) định kỳ kiểm tra trạng thái kết nối Internet đến Cloud MQTT (ThingsBoard):
     - **Khi có mạng (ONLINE)**: Lấy các bản tin `PENDING` theo thứ tự FIFO (First In First Out), đóng gói payload theo chuẩn ThingsBoard MQTT API (`{"ts": timestamp_ms, "values": {...}}`), gửi lên topic `v1/devices/me/telemetry` với mức QoS 1. Sau khi nhận được ACK thành công từ Broker, Gateway cập nhật trạng thái bản tin thành `SENT` kèm dấu thời gian `sent_at`.
     - **Khi mất mạng (OFFLINE)**: Gateway tạm dừng tiến trình gửi, giữ nguyên toàn bộ bản tin trong SQLite ở trạng thái `PENDING`.
     - **Khi mạng được khôi phục**: Gateway tự động phát hiện kết nối và gửi bù lần lượt toàn bộ bản tin đang chờ mà không làm xáo trộn thứ tự thời gian hay thất thoát dữ liệu.

---

## 3. KẾT QUẢ THỰC NGHIỆM VÀ KIỂM CHỨNG TẠI MỐC M2

Nhóm đã xây dựng bộ kiểm thử tự động (`pytest`/`unittest`) gồm 12 ca kiểm thử và 1 kịch bản demo đầu mối (`run_demo_m2.sh`).

### 3.1. Kết quả kiểm thử đơn vị (Unit Tests)
Chạy lệnh kiểm thử toàn diện trên hệ thống:
```bash
python3 -m unittest discover -s tests
```
**Kết quả**:
```
Ran 12 tests in 2.530s
OK (All 12 tests passed successfully)
```
- Đã kiểm tra thành công: Kiểm tra cấu trúc bản tin, loại bỏ các trường thiếu, kiểm tra ngưỡng cảm biến, kiểm tra ghi đệm SQLite, kiểm tra cơ chế chống lặp bản tin, kiểm tra chuyển trạng thái `PENDING` $\rightarrow$ `SENT`, và chính sách dọn dẹp dung lượng vòng lặp (Ring-Buffer).

### 3.2. Kết quả kịch bản thực nghiệm cốt lõi (M2 Core Demo)

Toàn bộ quá trình chạy thử nghiệm thông qua script `run_demo_m2.sh` ghi nhận các số liệu thực tế sau:

#### Giai đoạn 1: Khởi động dịch vụ và tiếp nhận bình thường (Online)
- Gateway khởi chạy trên cổng HTTP `8089`, SQLite database khởi tạo tại `data/demo_gateway.db`.
- Hai node ESP32 gửi 6 bản tin (3 chu kỳ):
  - **Node 1** (`esp32_01`): Nhiệt độ 28.4°C, Độ ẩm 67.1%, PM2.5 22.6 µg/m³.
  - **Node 2** (`esp32_02`): Nhiệt độ 28.6°C, Độ ẩm 66.6%, CO2 519.0 ppm.
- Phản hồi từ Gateway: HTTP `201 Created` (`action: stored`).
- Dịch vụ Cloud Forwarder lập tức chuyển tiếp lên Cloud và cập nhật trạng thái thành `SENT`.

#### Giai đoạn 2: Kiểm thử chống trùng lặp (Deduplication)
- Node 1 phát sinh bản tin thử nghiệm `esp32_01-dup-test-1794057556`.
- Lần 1: Gateway tiếp nhận và lưu trữ (HTTP 201).
- Lần 2 (gửi lại cùng ID): Gateway nhận diện trùng lặp, phản hồi HTTP `200 OK (duplicate_ignored)`. Không có bản tin dư thừa nào được chèn vào database.

#### Giai đoạn 3: Giả lập sự cố mất kết nối mạng (Network Outage)
- Kích hoạt trạng thái mất mạng: `mock_online = false`.
- Trong lúc mất mạng, Node 1 và Node 2 tiếp tục gửi 4 bản tin mới (ID từ 8 đến 11, chuỗi bắt đầu từ `000100`).
- **Trạng thái bộ đệm SQLite**:
  ```
  +----+-----------------+----------+----------+--------+-------+-------+---------+---------+
  | ID | Msg ID          | Node     | Temp(°C) | Hum(%) | PM2.5 | CO2   | Status  | Sent At |
  +----+-----------------+----------+----------+--------+-------+-------+---------+---------+
  | 11 | esp32_02-000101 | esp32_02 | 28.8     | 66.2   | --    | 657.0 | PENDING | --      |
  | 10 | esp32_01-000101 | esp32_01 | 28.9     | 63.3   | 24.4  | --    | PENDING | --      |
  | 9  | esp32_02-000100 | esp32_02 | 28.6     | 67.2   | --    | 651.0 | PENDING | --      |
  | 8  | esp32_01-000100 | esp32_01 | 28.5     | 63.1   | 24.2  | --    | PENDING | --      |
  +----+-----------------+----------+----------+--------+-------+-------+---------+---------+
  ```
  Toàn bộ 4 bản tin mới được lưu đệm an toàn với trạng thái `PENDING`. Không có lỗi crash hay tràn bộ nhớ.

#### Giai đoạn 4: Khôi phục kết nối và gửi bù (Store-and-Forward Recovery)
- Khôi phục mạng: `mock_online = true`.
- Sau 2 giây, tiến trình nền tự động quét thấy 4 bản tin `PENDING`, tiến hành gửi bù lên Cloud theo thứ tự FIFO và chuyển toàn bộ sang trạng thái `SENT`.
- **Bảng tổng kết cuối cùng**:
  ```
  ============================================================
         MYIR MYS-6ULX GATEWAY STATUS
  ============================================================
  Board Model        : MYIR MYS-6ULX-IND (i.MX 6ULL Cortex-A7)
  Gateway ID         : myir-mys6ulx-gw01
  Database Size      : 36.0 KB
  Total Records      : 11
  Pending (Buffer)   : 0
  Sent (Delivered)   : 11
  Active Nodes       : 2 (esp32_01, esp32_02)
  ============================================================
  ```
- **Tỉ lệ thất thoát bản tin**: **0%** (11/11 bản tin được lưu trữ và chuyển phát thành công).

---

## 4. KỊCH BẢN QUAY VIDEO DEMO M2 (1 – 3 PHÚT)

Sinh viên Mai Thế Hùng có thể thực hiện quay video màn hình theo kịch bản chuẩn bị sẵn sau:

1. **Phần 1: Giới thiệu (0:00 – 0:30)**:
   - Giới thiệu tên đề tài, nhóm N06, thành viên Mai Thế Hùng phụ trách Gateway Linux i.MX6.
   - Nêu model board mục tiêu: **MYIR MYS-6ULX-IND**.
   - Trình bày kiến trúc phần mềm trong thư mục `DO_AN_1`.
2. **Phần 2: Chạy demo kịch bản cốt lõi (0:30 – 2:00)**:
   - Mở terminal chạy lệnh:
     ```bash
     cd /home/hung/UIT/DO_AN_1
     ./scripts/run_demo_m2.sh
     ```
   - Thuyết minh theo các bước hiển thị trên terminal:
     - Dịch vụ khởi động và curl kiểm tra API `GET /api/v1/health`.
     - Hai node ESP32 gửi dữ liệu nhiệt độ, độ ẩm, bụi PM2.5, khí CO2.
     - Kiểm thử cơ chế loại bỏ tin trùng lặp (Idempotency).
     - Giả lập rớt mạng $\rightarrow$ xem các bản tin chuyển vào hàng đợi `PENDING`.
     - Phục hồi mạng $\rightarrow$ xem dịch vụ tự động gửi bù toàn bộ bản tin và chuyển sang `SENT`.
3. **Phần 3: Tổng kết & Kế hoạch tiếp theo (2:00 – 2:45)**:
   - Chỉ ra bảng thống kê: 0 bản tin bị mất, 2 node hoạt động liên tục.
   - Giới thiệu file dịch vụ `mys6ulx-gateway.service` và script triển khai `deploy_board.sh` đã sẵn sàng để nạp lên board thực tế ở các tuần tiếp theo.

---

## 5. KẾ HOẠCH CHO MỐC M3 VÀ CÁC TUẦN TIẾP THEO

- **Tuần 7 (09/11 – 15/11)**:
  - Hoàng: Hoàn thiện mạch tích hợp thêm cảm biến CO2 thực tế trên phần cứng ESP32 Node 2.
  - Hùng: Cấu hình tài khoản và thiết bị trên nền tảng ThingsBoard Cloud, kết nối trực tiếp tài khoản thật qua MQTT client.
- **Tuần 8 (16/11 – 22/11)**:
  - Nối mạng nội bộ giữa ESP32 phần cứng và Gateway phần cứng (cắm cáp Ethernet hoặc Wi-Fi dongle).
  - Tinh chỉnh tính năng tự kết nối lại (Auto-reconnect & exponential backoff) trên cả ESP32 và Linux Gateway.
- **Tuần 9 (Mốc M3 - hạn 30/11/2026)**:
  - Tích hợp toàn hệ thống end-to-end từ cảm biến ESP32 qua Gateway Linux i.MX6 lên ThingsBoard Dashboard.
  - Lập báo cáo M3 ghi nhận độ trễ và các lỗi còn tồn tại để hoàn thiện trước mốc đo đạc M4.
