# BÁO CÁO TIẾN ĐỘ THỰC HIỆN MỐC M2 – PHẦN GATEWAY LINUX i.MX6
**Đề tài**: Xây dựng mạng node thu thập dữ liệu môi trường trên nền tảng nhúng Linux i.MX6 (MYIR) truyền về nền tảng IoT  
**Môn học**: Đồ án 1 (CE201) – Khoa Kỹ thuật Máy tính, Trường ĐH Công nghệ Thông tin (ĐHQG-HCM)  
**Sinh viên phụ trách Gateway**: **Mai Thế Hùng** – MSSV: **24520598**  
**Nhóm**: N06  
**Mốc báo cáo**: Mốc M2 (Tuần 4 – Tuần 6 | Hạn nộp: 09/11/2026)  

---

## 1. MỤC TIÊU & NHIỆM VỤ ĐƯỢC PHÂN CÔNG ĐẾN MỐC M2

Căn cứ theo bản đặc tả kế hoạch 13 tuần đã duyệt ở Mốc M0/M1, nhiệm vụ của sinh viên **Mai Thế Hùng** (phụ trách phần Gateway Linux i.MX6) bao gồm:

1. **Tuần 4 (19/10 – 25/10)**:
   - Thiết kế và lập trình dịch vụ hệ thống Linux (`systemd`) chạy nền trên vi xử lý i.MX6 để luôn sẵn sàng tiếp nhận dữ liệu quan trắc từ các node cảm biến.
2. **Tuần 5 (26/10 – 01/11)**:
   - Hiện thực tầng giao tiếp tiếp nhận dữ liệu nội bộ từ $\ge 2$ node ESP32 theo đúng định dạng bản tin JSON đã thống nhất chuẩn hóa ở Mốc M0/M1.
3. **Tuần 6 – Hoàn thiện Mốc M2 (02/11 – 08/11)**:
   - Xây dựng **Module thử nghiệm cốt lõi (Core Prototype)**: Bộ lọc dữ liệu (Validator), cơ sở dữ liệu nhúng SQLite chế độ WAL chống hỏng bộ nhớ Flash, cơ chế chống trùng lặp bản tin (Idempotency & Deduplication), và cơ chế lưu đệm – gửi bù (Store-and-Forward) khi mất kết nối mạng.
   - Xây dựng bộ công cụ kiểm thử tự động và bộ mô phỏng $\ge 2$ node phục vụ kiểm chứng độc lập trên môi trường máy trạm Ubuntu trước khi nạp lên phần cứng thật.
   - Chuẩn hóa mã nguồn đưa lên Git repository và chuẩn bị kịch bản quay video demo (1–3 phút).

---

## 2. THIẾT KẾ & HIỆN THỰC KIẾN TRÚC PHẦN MỀM GATEWAY

Toàn bộ mã nguồn dịch vụ Gateway được đóng gói hoàn chỉnh trong thư mục `gateway/` với cấu trúc hướng module, đa luồng (multi-threaded), tối ưu hóa cho tài nguyên phần cứng của board nhúng **MYIR MYS-6ULX-IND (NXP i.MX 6ULL ARM Cortex-A7)**:

```
gateway/
├── __init__.py
├── config.py / config.json      # Quản lý cấu hình linh hoạt (Port, DB path, Cloud)
├── validator.py                 # Xác thực schema JSON M0/M1, xử lý ngưỡng & lỗi cảm biến
├── database.py                  # Động cơ SQLite WAL mode, chống trùng lặp (Idempotency)
├── ingestion_http.py            # REST API Server đa luồng (Port 8080)
├── ingestion_mqtt.py            # Subscriber nhận dữ liệu từ MQTT broker nội bộ
├── forwarder.py                 # Động cơ Store-and-Forward đẩy dữ liệu lên ThingsBoard
├── gateway_daemon.py            # Tiến trình nền chính điều phối hệ thống
└── gateway_cli.py               # Công cụ CLI giám sát trạng thái và dữ liệu thời gian thực
```

### 2.1. Bộ kiểm tra và chuẩn hóa dữ liệu (`validator.py`)
- Kiểm tra tính hợp lệ của bản tin theo đúng cấu trúc đã thống nhất:
  * `schema_version`: Số nguyên dương (phiên bản hiện tại: 1).
  * `node_id`: Chuỗi định danh duy nhất của node (`esp32_01`, `esp32_02`).
  * `message_id`: Mã duy nhất của bản tin (`esp32_01-000001`...), phục vụ phát hiện trùng lặp khi node gửi lại.
  * `timestamp`: Thời gian đo theo chuẩn quốc tế ISO 8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`).
  * `sensors`: Đối tượng chứa giá trị đo của các cảm biến trong đề tài: SHT3x (`temperature_c`, `humidity_pct`), PMS5003 (`pm25_ug_m3`), SCD4x (`co2_ppm`).
- **Quy tắc xử lý lỗi cảm biến**: Khi phần cứng cảm biến bị lỏng dây hoặc lỗi đọc, giá trị được biểu diễn bằng `null`. Hệ thống **tuyệt đối không dùng số `0`** để báo lỗi vì 0°C là một giá trị nhiệt độ đo hoàn toàn hợp lệ.
- Kiểm tra ngưỡng vật lý: Nhiệt độ (-40°C đến 85°C), Độ ẩm (0% đến 100%), Bụi mịn PM2.5 (0 đến 1000 µg/m³), Khí CO2 (300 đến 10000 ppm).

### 2.2. Cơ sở dữ liệu SQLite tối ưu cho bộ nhớ Flash (`database.py`)
- Board nhúng sử dụng thẻ nhớ MicroSD hoặc chip Flash eMMC/NAND có số lần ghi xóa giới hạn. Do đó, hệ thống cấu hình SQLite với:
  * `PRAGMA journal_mode = WAL;` (Write-Ahead Logging): Cho phép đọc/ghi song song không khóa luồng, gom các thao tác ghi tuần tự để bảo vệ cell nhớ Flash.
  * `PRAGMA synchronous = NORMAL;`: Cân bằng giữa tốc độ I/O và an toàn dữ liệu khi sụt nguồn.
- **Cơ chế chống trùng lặp (Idempotency & Deduplication)**: Bảng `telemetry` định nghĩa trường `message_id TEXT UNIQUE NOT NULL`. Nếu ESP32 gửi lại bản tin cũ do chập chờn mạng, Gateway sẽ nhận diện bản tin đã tồn tại, lập tức phản hồi mã HTTP `200 (duplicate_ignored)` và không ghi đè dữ liệu rác vào bộ nhớ.
- **Cơ chế xoay vòng dung lượng (Ring-Buffer Policy)**: Khi tổng số bản tin đạt ngưỡng tối đa (`max_records = 50,000`), hệ thống tự động xóa các bản tin cũ nhất **đã gửi thành công lên cloud (`status = 'SENT'`)**. Tuyệt đối không xóa các bản tin đang chờ gửi (`PENDING`).

### 2.3. Tầng tiếp nhận dữ liệu Ingestion (`ingestion_http.py` & `ingestion_mqtt.py`)
- **HTTP REST Server**: Xây dựng bằng thư viện chuẩn Python (zero external dependencies), chạy đa luồng trên cổng `8080`, cung cấp các endpoint chuẩn RESTful:
  * `POST /api/v1/telemetry`: Nhận bản tin JSON từ ESP32, trả về HTTP 201 nếu hợp lệ, HTTP 200 nếu trùng lặp, HTTP 400 nếu sai định dạng.
  * `GET /api/v1/health`: Báo cáo tình trạng gateway, thời gian uptime, số lượng bản tin lưu trữ.
  * `GET /api/v1/nodes`: Danh sách các node ESP32 đang kết nối, thời điểm gửi gần nhất.
  * `GET /api/v1/telemetry/recent`: Truy vấn nhanh danh sách dữ liệu quan trắc gần nhất.
- **MQTT Local Subscriber**: Lắng nghe trên các topic nội bộ `devices/+/telemetry` dành cho các node gửi qua broker Mosquitto.

### 2.4. Động cơ Lưu đệm & Gửi bù Store-and-Forward (`forwarder.py`)
- Chạy như một luồng nền độc lập (background worker), liên tục kiểm tra hàng đợi bản tin có `status = 'PENDING'` theo thứ tự FIFO (vào trước ra trước).
- Đóng gói dữ liệu theo chuẩn Telemetry API của ThingsBoard: `{"ts": timestamp_ms, "values": {"temperature": ..., "humidity": ..., "pm25": ..., "co2": ...}}`.
- **Khi có mạng (Online)**: Đẩy bản tin lên Cloud qua MQTT QoS 1. Khi nhận được xác nhận chuyển phát thành công, cập nhật trạng thái bản tin thành `SENT` kèm dấu thời gian `sent_at`.
- **Khi mất mạng Internet (Offline)**: Giữ nguyên các bản tin trong bộ đệm SQLite với trạng thái `PENDING`. Khi mạng phục hồi, tự động gửi bù toàn bộ theo đúng thứ tự thời gian, đảm bảo tỉ lệ mất mát dữ liệu là **0%**.

### 2.5. Quản lý dịch vụ hệ thống Linux (`systemd/`)
- Đã cấu hình tệp dịch vụ [`systemd/mys6ulx-gateway.service`](file:///home/hung/UIT/DO_AN_1/systemd/mys6ulx-gateway.service) cho Linux i.MX6:
  * Tự động khởi chạy cùng hệ điều hành (`WantedBy=multi-user.target`).
  * Tự khởi động lại nếu xảy ra sự cố (`Restart=always`, `RestartSec=5s`).
  * Quản lý log tập trung qua `journald` và `syslog`.
- Viết sẵn script cài đặt dịch vụ tự động [`systemd/install_service.sh`](file:///home/hung/UIT/DO_AN_1/systemd/install_service.sh) và script nạp code từ xa qua mạng [`scripts/deploy_board.sh`](file:///home/hung/UIT/DO_AN_1/scripts/deploy_board.sh).

---

## 3. KẾT QUẢ THỰC NGHIỆM VÀ ĐO ĐẠC TẠI MỐC M2

Sinh viên Mai Thế Hùng đã triển khai bộ kiểm thử tự động và thực nghiệm kịch bản cốt lõi với các kết quả đo đạc thực tế như sau:

### 3.1. Kết quả kiểm thử tự động (Automated Test Suite)
Chạy bộ 12 test cases bao phủ toàn bộ chức năng:
```bash
python3 -m unittest discover -s tests
```
*Kết quả*: **12/12 ca kiểm thử đạt (PASS 100%)** trong thời gian thực thi 2.53 giây.
- `test_validator`: Xác thực chính xác các trường bắt buộc, phát hiện lỗi thiếu trường, kiểm tra giá trị cảm biến ngoài ngưỡng và giá trị `null`.
- `test_database`: Kiểm tra toàn vẹn dữ liệu SQLite, cơ chế chống ghi trùng lặp và chính sách giải phóng bộ nhớ.
- `test_store_and_forward`: Kiểm tra chu trình tích hợp giả lập ngắt mạng $\rightarrow$ tích lũy bản tin $\rightarrow$ khôi phục mạng $\rightarrow$ gửi bù thành công.

### 3.2. Kết quả kịch bản thực nghiệm cốt lõi (M2 Demo Script)
Thực thi kịch bản đo đạc tự động 6 bước qua script `scripts/run_demo_m2.sh`:

1. **Tiếp nhận dữ liệu từ 2 Node ESP32 trong điều kiện Online**:
   - Node 1 (`esp32_01`): Nhiệt độ 28.4°C, Độ ẩm 67.1%, Bụi PM2.5 22.6 µg/m³.
   - Node 2 (`esp32_02`): Nhiệt độ 28.6°C, Độ ẩm 66.6%, Khí CO2 519.0 ppm.
   - Gateway phản hồi HTTP 201 Created. Dữ liệu được chuyển tiếp ngay lên Cloud và đánh dấu `SENT`.

2. **Kiểm thử chống trùng lặp bản tin (Deduplication)**:
   - Gửi bản tin thử nghiệm `esp32_01-dup-test-1794057556`. Lần 1: Lưu thành công (HTTP 201).
   - Gửi lại lần 2 với cùng `message_id`: Gateway phản hồi HTTP 200 OK (`duplicate_ignored`). Database không phát sinh bản ghi trùng.

3. **Thực nghiệm Lưu đệm & Gửi bù khi mất kết nối mạng (Store-and-Forward)**:
   - *Giai đoạn mất mạng*: Kích hoạt ngắt kết nối Cloud (`mock_online = false`). Trong thời gian này, 2 Node ESP32 tiếp tục gửi 4 bản tin mới (ID từ 8 đến 11).
   - *Bảng trạng thái bộ đệm SQLite khi mất mạng*:
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
     Toàn bộ 4 bản tin được lưu trữ an toàn trong SQLite ở trạng thái `PENDING`.
   - *Giai đoạn khôi phục mạng*: Bật lại kết nối Cloud (`mock_online = true`). Gateway tự động phát hiện kết nối, lấy toàn bộ 4 bản tin theo thứ tự FIFO gửi bù lên Cloud và chuyển trạng thái sang `SENT`.

4. **Bảng tổng kết trạng thái Gateway sau thực nghiệm**:
   ```
   ============================================================
          MYIR MYS-6ULX GATEWAY STATUS (CE201 - NHÓM N06)
   ============================================================
   Phần cứng mục tiêu : MYIR MYS-6ULX-IND (i.MX 6ULL Cortex-A7)
   Mã Gateway         : myir-mys6ulx-gw01
   Cơ sở dữ liệu      : SQLite WAL Mode (36.0 KB)
   Tổng số bản tin    : 11
   Chờ gửi (Pending)  : 0
   Đã gửi (Sent)      : 11
   Node hoạt động     : 2 (esp32_01, esp32_02)
   Tỉ lệ mất dữ liệu  : 0.0% (100% dữ liệu được bảo toàn)
   ============================================================
   ```

---

## 4. QUẢN LÝ MÃ NGUỒN GIT & VIDEO DEMO M2

- **Quản lý mã nguồn**: Toàn bộ dự án đã được khởi tạo Git repository tại `/home/hung/UIT/DO_AN_1` với 25 files nguồn hoàn chỉnh, cấu trúc thư mục rõ ràng, tuân thủ chuẩn commit Convention (`feat(gateway): Complete milestone M2 core module...`).
- **Kịch bản Video Demo (1–3 phút)**: Đã đóng gói sẵn kịch bản chạy tự động hiển thị trực quan qua file [`scripts/run_demo_m2.sh`](file:///home/hung/UIT/DO_AN_1/scripts/run_demo_m2.sh), sẵn sàng để quay màn hình demo toàn diện các chức năng cốt lõi nộp giảng viên.

---

## 5. KẾ HOẠCH CHO MỐC M3 (TUẦN 7 – TUẦN 9)

1. **Tuần 7 (09/11 – 15/11)**:
   - Cấu hình tài khoản và device token thật trên nền tảng **ThingsBoard Cloud**.
   - Cập nhật thông số MQTT Client thật trong `config.json` của Gateway để đẩy telemetry trực tiếp lên Dashboard ThingsBoard.
2. **Tuần 8 (16/11 – 22/11)**:
   - Phối hợp với Phan Xuân Hoàng kết nối phần cứng mạng nội bộ: Cắm kit ESP32 thật và board MYIR thật vào cùng mạng Wi-Fi (hoặc switch LAN) để kiểm thử truyền nhận trực tiếp trên phần cứng.
   - Thử nghiệm rút dây mạng Internet của router trong 30 phút để kiểm tra độ bền của cơ chế Store-and-Forward trên thẻ nhớ của board i.MX6 thật.
3. **Tuần 9 – Mốc M3 (23/11 – 29/11 | Hạn 30/11)**:
   - Tích hợp toàn diện hệ thống end-to-end từ cảm biến ESP32 $\rightarrow$ Gateway Linux i.MX6 $\rightarrow$ ThingsBoard Dashboard.
   - Hoàn thiện báo cáo M3 ghi nhận độ trễ và các thông số ổn định của hệ thống.
