# 🏭 Nestlé Packaging Copilot & Digital Twin (Nestlé Đồng Nai Factory)

> **Hệ sinh thái Công nghiệp Khép kín (Industrial AI & Digital Twin):** Kết nối IT - OT, Giám sát Cảm biến Thời gian thực, Phân tích Độ tin cậy Thiết bị (TPM / MTTR / MTBF), Chẩn đoán Sự cố Tự trị (Autonomous RCA Agent) và Thực thi An toàn LOTO.
> 
> **Ứng viên:** Nguyễn Doãn Hoàng (B.S. Computer Science - HCMUT, Data Analyst)  
> **Vị trí mục tiêu:** Digital Technical Specialist - Nhà máy Nestlé Đồng Nai (KCN Biên Hòa 2)  
> **Tuyến báo cáo:** Manufacturing Excellence Manager (TPM / Lean / OEE / Kaizen)

---

## 📐 Kiến trúc Tổng thể Hệ thống (IT-OT Convergence)

```text
       [ CẢM BIẾN DÂY CHUYỀN TETRA PAK / SIG ]
                          │
                          ▼
            scripts/etl_telemetry.py (Pha 1)
       (UCI AI4I Benchmark 10.000 records -> Feature Engineering)
                          │
                          ▼
             setup_database.py (Pha 2)
       (packaging_factory.db: SQLite Star Schema Data Warehouse)
                          │
     ┌────────────────────┴────────────────────┐
     ▼                                         ▼
factory_tools.py (Pha 3)              simulate_line.py (Pha 4.1)
- MTTR, MTBF, Availability           (IoT Edge Gateway Simulator)
- Phân tích Pareto 80/20 Lost Units            │ (Streaming live)
- Chốt chặn An toàn LOTO Guardrail              ▼
     │                                realtime_edge_buffer
     └────────────────────┬────────────────────┘
                          │
                          ▼
             agent_daemon.py & agent_core.py (Pha 4.2)
       (Autonomous Watchdog: Sense -> Think -> Act)
       - Google Gemini 3.6/3.8 Automatic Function Calling (AFC)
       - Tự động chẩn đoán RCA & Tạo Work Order cấp P1_URGENT
                          │
                          ▼
                    app.py (Pha 5)
       (Streamlit Industrial Operations Center & Interactive Copilot)
---

## 🚀 Tiến độ Kỹ thuật Đã Hoàn Thành

### ✅ Pha 1: Dữ liệu Công nghiệp & Feature Engineering (`scripts/etl_telemetry.py`)
- **Tập dữ liệu:** Tích hợp 10.000 bản ghi chuẩn AI4I 2020 (Stephan Matzka - IEEE), cơ chế Fail-safe chống sập mạng.
- **Ánh xạ vật lý vào Dây chuyền Đóng gói Nestlé Đồng Nai:**
  - `LINE_01`: Tetra Pak A3/Speed 115ml (Milo 115ml - Công suất 24,000 hộp/h)
  - `LINE_02`: Tetra Pak TBA/19 180ml (Milo 180ml - Công suất 7,500 hộp/h)
  - `LINE_03`: SIG Combibloc CFA 312 (Sữa 250ml - Công suất 12,000 hộp/h)
- **Công thức Vật lý & Cơ điện tử:**
  - $\Delta T = T_{\text{sonotrode}} - T_{\text{cleanroom}}$ (°C) – Phát hiện nghẽn nước làm mát Chiller cụm hàn.
  - $\frac{dT}{dt}$ (°C/min) – Đạo hàm biến thiên nhiệt đầu hàn theo thời gian.
  - $P_{\text{mech}} = \frac{\tau \times \omega}{1000} = \frac{\text{Torque} \times (2\pi \times \text{RPM})}{60.000}$ (kW) – Công suất cơ học trục kéo Servo.
  - $\text{Heat Strain Index (HSI)} = \frac{P_{\text{mech}} \times 100}{|\Delta T| + 0.1}$ – Tải nhiệt giải nhiệt.
- **Phân bổ:** 3 Ca sản xuất (Shift 1: 06h-14h, Shift 2: 14h-22h, Shift 3: 22h-06h). Xuất file `cleaned_telemetry.parquet` và `cleaned_telemetry.csv`.

### ✅ Pha 2: Relational Data Modeling Star Schema (`setup_database.py`)
- Kiến tạo `packaging_factory.db` chuẩn Kimball Star Schema, kích hoạt toàn vẹn khóa ngoại `PRAGMA foreign_keys = ON`:
  - `dim_machines`: Thông tin tài sản, công suất định danh (Cartons Per Hour - CPH).
  - `dim_error_catalog`: Chuẩn hóa 5 mã lỗi Nestlé (`E-105`, `E-401`, `E-204`, `E-302`, `E-999`) kèm quy chuẩn LOTO và đồ bảo hộ PPE.
  - `fact_sensor_telemetry`: Lưu 10.000 dòng cảm biến có Composite Index `(line_id, timestamp)`.
  - `fact_downtime_events`: 339 sự cố dừng máy, phân tách rõ Micro-stops (1-3 phút) và Major Breakdowns (20-45 phút). Tính sản lượng thất thoát:
    $$\text{Units Lost} = \frac{\text{CPH}}{60} \times \text{Downtime Minutes}$$
  - `fact_work_orders`: 339 phiếu bảo trì khép kín với các trạng thái an toàn LOTO (`PENDING_ISOLATION`, `VERIFIED_LOTO`, `RESTORED`).

### ✅ Pha 3: Analytics Engine & LOTO Guardrails (`factory_tools.py`)
- **Công thức TPM Reliability:**
  - $\text{MTBF} = \frac{T_{\text{run}}}{\text{Failures}} = 25.53\text{ phút}$ (Môi trường Stress-testing nén thời gian).
  - $\text{MTTR} = \frac{T_{\text{down}}}{\text{Failures}} = 10.09\text{ phút}$.
  - $\text{Availability} = 71.67\%$.
- **Phân tích Pareto 80/20:** Tự động phát hiện nhóm **Vital Few**: `E-401` (37.11%) và `E-302` (28.14%) chiếm 65.26% tổng sản lượng thất thoát.
- **LOTO Thermal Safety Guardrail:** Ngăn chặn tuyệt đối việc đóng phiếu bảo trì nếu $T_{\text{sonotrode}} > 40.0^\circ\text{C}$ (nguy cơ bỏng cấp 2).

### ✅ Pha 4: Telemetry Streaming & Autonomous Agent Core
- `simulate_line.py`: IoT Edge Gateway phát nhịp tim cảm biến thời gian thực vào bảng đệm `realtime_edge_buffer`.
- `agent_core.py`: Tích hợp Google Gemini với **Automatic Function Calling (AFC)** và cơ chế phục hồi đám mây (Cloud Resilience: Retry Exponential Backoff khi gặp 503/429, Failover đa tầng giữa 3.8 và 3.6).
- `agent_daemon.py`: **Autonomous Watchdog Agent (Sense – Think – Act)** chạy ngầm 24/7. Tự bắt sự kiện dị thường cảm biến ở Frame #024, tự gọi Gemini phân tích RCA cơ điện tử, và tự động tạo Work Order cấp `P1_URGENT` vào SQLite với đầy đủ ràng buộc khóa ngoại!

### ✅ Pha 5: Operations Dashboard Prototype (`app.py`)
- Xây dựng giao diện Streamlit giám sát trực quan: Top KPI Cards, biểu đồ Pareto 80/20, biểu đồ Telemetry thời gian thực, Form kiểm định chốt chặn an toàn LOTO, và khung chat tương tác với Copilot.

---

## 📌 Handoff Backlog (Nội dung cần thực hiện ở Thread tiếp theo)

1. **Giải quyết nghẽn Synchronous I/O ở High-throughput (> 300 frames):**
   - Refactor `agent_daemon.py` sang mô hình **Producer - Consumer (Async Worker Queue)** để Daemon không bị block trong lúc chờ LLM suy luận.
2. **Tối ưu hóa độ trễ phản hồi Gemini:**
   - Cố định Primary Model là `gemini-3.6-flash` để loại bỏ hoàn toàn độ trễ do lỗi 503 Retry của bản 3.8.
   - Thêm cơ chế Rate Throttling / Debouncing (chỉ kích hoạt RCA khi lỗi kéo dài $> N$ frames liên tục).
3. **Hoàn thiện UI/UX Pha 5 & Kịch bản Phỏng vấn:**
   - Hoàn thiện luồng hiển thị Live Stream tự động cập nhật (Auto-refresh) trên Streamlit khi chạy song song cùng Daemon.
   - Tập dượt kịch bản thuyết trình 4 bước thực chiến cùng Manufacturing Excellence Manager.