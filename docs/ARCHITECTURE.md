# KIẾN TRÚC HỆ THỐNG GATEWAY LINUX i.MX6 (MYIR MYS-6ULX-IND)
**Đề tài**: Xây dựng mạng node thu thập dữ liệu môi trường trên nền tảng nhúng Linux i.MX6 (MYIR) truyền về nền tảng IoT  
**Mã nhóm**: N06 – Đồ án 1  
**Phụ trách Gateway**: Mai Thế Hùng (24520598)  

---

## 1. Sơ Đồ Khối Tổng Quan

```
+----------------------------------------------------------------------------------+
|                            MẠNG CẢM BIẾN NỘI BỘ (LAN)                            |
|                                                                                  |
|   +------------------------------------+   +---------------------------------+   |
|   |          ESP32 - Node 1            |   |          ESP32 - Node 2         |   |
|   |  - SHT3x: Nhiệt độ & Độ ẩm         |   |  - SHT3x: Nhiệt độ & Độ ẩm      |   |
|   |  - PMS5003: Nồng độ bụi PM2.5      |   |  - SCD4x/MH-Z19: Khí CO2        |   |
|   +-----------------+------------------+   +----------------+----------------+   |
+---------------------|---------------------------------------|--------------------+
                      | Wi-Fi / Ethernet                      | Wi-Fi / Ethernet
                      | (HTTP REST / MQTT)                    | (HTTP REST / MQTT)
                      v                                       v
+----------------------------------------------------------------------------------+
|                       GATEWAY NHÚNG LINUX i.MX6 (MYS-6ULX-IND)                   |
|                                                                                  |
|   +--------------------------------------------------------------------------+   |
|   |                    TẦNG TIẾP NHẬN BẢN TIN (INGESTION)                    |   |
|   |   - HTTP REST Server (Port 8080): Đa luồng, chuẩn RESTful                |   |
|   |   - MQTT Rx Subscriber (Optional): Topic 'devices/+/telemetry'           |   |
|   +-------------------------------------+------------------------------------+   |
|                                         |                                        |
|                                         v                                        |
|   +--------------------------------------------------------------------------+   |
|   |                   BỘ KIỂM TRA ĐỊNH DẠNG (VALIDATOR)                      |   |
|   |   - Kiểm tra Schema JSON M0/M1 (schema_version, node_id, message_id)     |   |
|   |   - Kiểm tra kiểu dữ liệu, ngưỡng vật lý, xử lý giá trị null             |   |
|   +-------------------------------------+------------------------------------+   |
|                                         |                                        |
|                                         v                                        |
|   +--------------------------------------------------------------------------+   |
|   |               ĐỘNG CƠ LƯU TRỮ VÀ XỬ LÝ TRÙNG LẶP (SQLITE)                |   |
|   |   - Tối ưu bộ nhớ Flash: PRAGMA journal_mode = WAL;                      |   |
|   |   - Chống ghi đè / Trùng lặp: UNIQUE(message_id)                         |   |
|   |   - Bảng 'telemetry' quản lý hàng đợi trạng thái: PENDING / SENT         |   |
|   |   - Quản lý giới hạn dung lượng (Ring-buffer purge oldest SENT)          |   |
|   +-------------------------------------+------------------------------------+   |
|                                         |                                        |
|                                         v                                        |
|   +--------------------------------------------------------------------------+   |
|   |            TIẾN TRÌNH LƯU ĐỆM & GỬI BÙ (STORE-AND-FORWARD WORKER)        |   |
|   |   - Quét bản tin PENDING theo thứ tự FIFO                                |   |
|   |   - Kiểm tra kết nối Internet / Cloud                                    |   |
|   |   - Đóng gói định dạng ThingsBoard Telemetry ({ts, values})              |   |
|   |   - Gửi MQTT QoS 1 và cập nhật SENT khi nhận phản hồi thành công         |   |
|   +-------------------------------------+------------------------------------+   |
+-----------------------------------------|----------------------------------------+
                                          | Internet (MQTT Uplink)
                                          v
+----------------------------------------------------------------------------------+
|                          NỀN TẢNG CLOUD (THINGSBOARD IoT)                        |
|   - Broker MQTT / Telemetry API: v1/devices/me/telemetry                         |
|   - Dashboard giám sát biểu đồ nhiệt độ, độ ẩm, bụi PM2.5, khí CO2               |
+----------------------------------------------------------------------------------+
```

---

## 2. Luồng Dữ Liệu Chi Tiết (Data Flow Sequence)

### 2.1. Tiếp nhận và gửi bình thường (Online)
```
ESP32 Node                Linux Gateway (MYS-6ULX)                   ThingsBoard Cloud
    |                                |                                       |
    |--- POST /api/v1/telemetry ---->|                                       |
    |    (JSON payload M0/M1)        |                                       |
    |                                |-- Validate Schema & Data              |
    |                                |-- Insert SQLite (status='PENDING')    |
    |<-- HTTP 201 (stored) ----------|                                       |
    |                                |                                       |
    |                                |-- [Forwarder Worker FIFO]             |
    |                                |-- Publish MQTT QoS 1 ---------------->|
    |                                |<-- PUBACK (Thành công) ---------------|
    |                                |-- Update SQLite (status='SENT')       |
```

### 2.2. Xử lý khi mất mạng Internet (Store-and-Forward Offline)
```
ESP32 Node                Linux Gateway (MYS-6ULX)                   ThingsBoard Cloud
    |                                |                                       |
    |--- POST /api/v1/telemetry ---->|                                       |
    |    (JSON payload M0/M1)        |                                       |
    |                                |-- Validate Schema & Data              |
    |                                |-- Insert SQLite (status='PENDING')    |
    |<-- HTTP 201 (stored) ----------|                                       |
    |                                |                                       |
    |                                |-- Check Cloud Connection: [OFFLINE]   |
    |                                |-- Giữ nguyên bản tin trạng thái PENDING
    |                                |   (Không phát sinh lỗi, không mất tin)
    |                                |                                       |
    |                                |   [KHI INTERNET PHỤC HỒI]             |
    |                                |-- Check Cloud Connection: [ONLINE]    |
    |                                |-- Quét toàn bộ bản tin PENDING (FIFO) |
    |                                |-- Publish MQTT QoS 1 ---------------->|
    |                                |<-- PUBACK (Thành công) ---------------|
    |                                |-- Update SQLite (status='SENT')       |
```

---

## 3. Cấu Trúc Bảng Dữ Liệu SQLite

### Bảng `telemetry`
| Cột | Kiểu | Mô tả |
| :--- | :--- | :--- |
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | Khóa chính tự tăng |
| `message_id` | TEXT UNIQUE NOT NULL | Mã bản tin duy nhất (phục vụ Idempotency) |
| `node_id` | TEXT NOT NULL | Mã định danh node (ví dụ: `esp32_01`, `esp32_02`) |
| `timestamp` | TEXT NOT NULL | Thời gian đo chuẩn ISO 8601 UTC |
| `schema_version` | INTEGER NOT NULL | Phiên bản định dạng (hiện tại là 1) |
| `temperature_c` | REAL | Nhiệt độ (°C) từ cảm biến SHT3x |
| `humidity_pct` | REAL | Độ ẩm (%) từ cảm biến SHT3x |
| `pm25_ug_m3` | REAL | Nồng độ bụi mịn PM2.5 (µg/m³) từ PMS5003 |
| `co2_ppm` | REAL | Nồng độ khí CO2 (ppm) từ SCD4x |
| `raw_payload` | TEXT NOT NULL | Nguyên văn chuỗi JSON nhận được từ Node |
| `status` | TEXT NOT NULL DEFAULT 'PENDING' | Trạng thái: `PENDING`, `SENT`, `FAILED` |
| `retry_count` | INTEGER DEFAULT 0 | Số lần thử gửi lại khi lỗi kết nối |
| `last_error` | TEXT | Ghi nhận lỗi gần nhất nếu có |
| `created_at` | TEXT NOT NULL | Thời điểm Gateway tiếp nhận |
| `sent_at` | TEXT | Thời điểm Gateway chuyển phát thành công lên Cloud |

### Bảng `node_registry`
| Cột | Kiểu | Mô tả |
| :--- | :--- | :--- |
| `node_id` | TEXT PRIMARY KEY | Mã định danh duy nhất của Node |
| `first_seen` | TEXT NOT NULL | Thời điểm Node gửi bản tin đầu tiên |
| `last_seen` | TEXT NOT NULL | Thời điểm bản tin mới nhất của Node |
| `total_messages`| INTEGER DEFAULT 0 | Tổng số bản tin hợp lệ đã tiếp nhận |
| `last_ip` | TEXT | Địa chỉ IP mạng nội bộ của Node |
