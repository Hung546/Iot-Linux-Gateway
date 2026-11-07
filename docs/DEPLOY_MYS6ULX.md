# Hướng Dẫn Triển Khai Phần Mềm Lên Board MYIR MYS-6ULX-IND
**Đề tài**: Xây dựng mạng node thu thập dữ liệu môi trường trên nền tảng nhúng Linux i.MX6 (MYIR) truyền về nền tảng IoT  
**Thành viên phụ trách Linux Gateway**: Mai Thế Hùng (24520598)  
**Nhóm**: N06 – Đồ án 1  

---

## 1. Tổng Quan Phần Cứng MYIR MYS-6ULX-IND

- **Nhà sản xuất**: MYIR Tech Limited.
- **Tên board**: `MYS-6ULX-IND` (Phiên bản công nghiệp, chịu nhiệt -40°C đến +85°C).
- **Bộ vi xử lý (SoC)**: NXP i.MX 6ULL (hoặc i.MX 6UL) ARM Cortex-A7, xung nhịp 528 MHz – 792 MHz.
- **RAM**: 256 MB hoặc 512 MB DDR3.
- **Bộ nhớ Flash**: 256 MB / 512 MB NAND Flash hoặc 4 GB eMMC, khe cắm thẻ nhớ MicroSD.
- **Giao tiếp mạng**: 2 cổng Ethernet 10/100 Mbps (RJ45), cổng USB Host (hỗ trợ cắm USB Wi-Fi nếu cần).
- **Cổng Debug Console**: Micro-USB (tích hợp chip chuyển đổi USB-to-UART CP2102/FTDI).

---

## 2. Kết Nối Và Khởi Động Board (Khi Sẵn Sàng Thao Tác)

### 2.1. Cấu hình gạt switch boot (Boot Mode)
- **Boot từ thẻ nhớ MicroSD**: Gạt switch theo hướng dẫn của MYIR (thường là chế độ SD Card boot: `SW1: 01`, `SW2: 10`).
- **Nguồn cấp**: Adapter 5V / 2A (jack tròn DC hoặc micro USB theo thiết kế board).

### 2.2. Kết nối Debug UART qua máy tính Ubuntu
1. Cắm cáp Micro-USB từ cổng Debug UART của board vào máy tính Ubuntu.
2. Kiểm tra cổng ttyUSB trên máy:
   ```bash
   dmesg | grep ttyUSB
   # Thường sẽ nhận diện là /dev/ttyUSB0
   ```
3. Mở phần mềm kết nối UART (tốc độ Baud **115200**, 8 data bits, no parity, 1 stop bit):
   ```bash
   picocom -b 115200 /dev/ttyUSB0
   # Hoặc:
   screen /dev/ttyUSB0 115200
   ```
4. Cấp nguồn cho board, quan sát U-Boot và Linux Kernel nạp vào hệ thống.

---

## 3. Cấu Hình Mạng Trên Board

Khi Linux boot lên thành công và xuất hiện dấu nhắc login (user mặc định của BSP MYIR thường là `root`, password rỗng hoặc `root`):
1. Cắm dây mạng LAN vào cổng Ethernet (thường là `eth0`).
2. Kiểm tra IP nhận được qua DHCP:
   ```bash
   ifconfig eth0
   ```
3. Nếu chưa có IP, chạy lệnh xin IP:
   ```bash
   udhcpc -i eth0
   # hoặc:
   dhclient eth0
   ```
4. Kiểm tra kết nối từ board tới máy phát triển:
   ```bash
   ping -c 3 <IP_MAY_UBUNTU>
   ```

---

## 4. Triển Khai Mã Nguồn Gateway Lên Board

Trên máy tính Ubuntu (trong thư mục `DO_AN_1`), nhóm đã chuẩn bị sẵn script triển khai tự động qua mạng LAN bằng SCP/Rsync:

```bash
cd /home/hung/UIT/DO_AN_1
./scripts/deploy_board.sh <IP_CUA_BOARD> root
```

Ví dụ board có IP là `192.168.1.150`:
```bash
./scripts/deploy_board.sh 192.168.1.150 root
```

Script sẽ tự động:
1. Tạo thư mục `/opt/gateway` trên board.
2. Sao chép toàn bộ module `gateway/`, `scripts/`, `systemd/` lên board.
3. Cài đặt và kích hoạt dịch vụ chạy ngầm `systemd` (`mys6ulx-gateway.service`).

---

## 5. Quản Lý Dịch Vụ Systemd Trên Board

Đăng nhập vào console của board hoặc SSH:
```bash
ssh root@<IP_CUA_BOARD>
```

Các lệnh quản trị dịch vụ hệ thống:
- **Kiểm tra trạng thái dịch vụ**:
  ```bash
  systemctl status mys6ulx-gateway
  ```
- **Xem nhật ký hoạt động (Live Logs)**:
  ```bash
  journalctl -u mys6ulx-gateway -f
  ```
- **Dừng / Khởi động lại dịch vụ**:
  ```bash
  systemctl restart mys6ulx-gateway
  systemctl stop mys6ulx-gateway
  ```
- **Sử dụng công cụ CLI kiểm tra cơ sở dữ liệu trên board**:
  ```bash
  python3 /opt/gateway/gateway/gateway_cli.py status
  python3 /opt/gateway/gateway/gateway_cli.py nodes
  python3 /opt/gateway/gateway/gateway_cli.py recent
  ```

---

## 6. Lưu Ý Tối Ưu Cho Bộ Nhớ Flash Của Board Nhúng

1. **Chế độ ghi SQLite WAL (Write-Ahead Logging)**:
   - Dịch vụ đã được cấu hình sẵn `PRAGMA journal_mode = WAL;` và `PRAGMA synchronous = NORMAL;`.
   - Cơ chế này giảm thiểu số lần xóa/ghi trực tiếp lên block flash của thẻ nhớ SD/eMMC, giúp kéo dài tuổi thọ phần cứng và tăng tốc độ xử lý I/O trên vi xử lý ARM Cortex-A7.
2. **Chính sách xóa tự động vòng lặp (Ring-Buffer)**:
   - Khi dung lượng bản tin vượt quá ngưỡng cấu hình (`max_records = 50,000`), dịch vụ chỉ xóa các bản tin cũ nhất **đã gửi thành công lên cloud (status = 'SENT')**.
   - Tuyệt đối không xóa các bản tin chưa gửi (`PENDING`), đảm bảo không thất thoát dữ liệu quan trắc.
