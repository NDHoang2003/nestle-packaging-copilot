# 🏭 Nestlé Packaging Copilot & Digital Twin (Nestlé Đồng Nai Factory)

> **Hệ sinh thái Công nghiệp Khép kín (Industrial AI & Cyber-Physical Digital Twin):** Kết nối IT - OT, Giám sát Cảm biến Thời gian thực, Chốt chặn An toàn LOTO Handshake, Chẩn đoán Sự cố Tự trị Tốc độ cao (Fast Single-Shot RCA Agent) và Trung tâm Điều hành Sản xuất (Industrial Operations Center).
> 
> **Ứng viên:** Nguyễn Doãn Hoàng (B.S. Computer Science - HCMUT, Data Analyst)  
> **Vị trí mục tiêu:** Digital Technical Specialist - Nhà máy Nestlé Đồng Nai (KCN Biên Hòa 2)  
> **Tuyến báo cáo:** Manufacturing Excellence Manager (TPM / Lean / OEE / Kaizen)

---

## 📐 Kiến trúc Tổng thể Hệ thống (IT-OT Convergence Architecture)


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
     ┌────────────────────┴──────────────────────────────────────┐
     ▼                                                           ▼
factory_tools.py (Pha 3)                                simulate_line.py (Pha 4.1)
- MTTR, MTBF, Availability Metrics                      (IoT Edge Gateway Simulator)
- Phân tích Pareto 80/20 Lost Units                              │
- Chốt chặn An toàn LOTO Guardrail                               ▼
     │                                                 realtime_edge_buffer
     │                                            (Bi-directional Interlock Latch)
     └────────────────────┬──────────────────────────────────────┘
                          │ (Hard Interlock Handshake)
                          ▼
             agent_daemon.py & agent_core.py (Pha 4.2)
       (Autonomous Watchdog: Sense -> Think -> Act)
       - Async Producer-Consumer Architecture (Thread-safe)
       - Fast Single-Shot RCA (Gemini 3.5/3.1 Flash-Lite, 1.2s response, Zero AFC Bloat)
       - Edge Heuristic Expert Engine Fallback (100% Offline-safe)
       - Mở Work Order OPEN (PENDING_ISOLATION) & Giữ khóa dừng máy an toàn
                          │
     ┌────────────────────┴──────────────────────────────────────┐
     ▼                                                           ▼
api_gateway.py (Pha 5.1)                                app.py (Pha 5.2)
(FastAPI Industrial Edge Gateway)                      (Streamlit Industrial Operations Center)
- Chuẩn OpenAPI 3.0 / Swagger                          - Live Telemetry Grid (LINE_01, 02, 03)
- Sẵn sàng tích hợp Microsoft Power Apps & Power BI     - Incident Ticker nhấp nháy đỏ khi TRIPPED
                                                       - Form Kiểm định LOTO (Nhiệt < 40°C)
                                                       - Interactive Copilot Chat

## 🚀 Tiến độ Kỹ thuật Đã Hoàn Thành (Pha 1 đến Pha 5)


### ✅ Pha 1: Dữ liệu Công nghiệp & Feature Engineering (scripts/etl_telemetry.py)

- Xử lý và làm sạch 10.000 bản ghi cảm biến công nghiệp theo chuẩn AI4I.

- Ánh xạ vào 3 dây chuyền Nestlé Đồng Nai:
  + LINE_01: Tetra Pak A3/Speed 115ml (Milo 115ml - Công suất: 24.000 hộp/h)
  + LINE_02: Tetra Pak TBA/19 180ml (Milo 180ml - Công suất: 7.500 hộp/h)
  + LINE_03: SIG Combibloc CFA 312 (Sữa 250ml - Công suất: 12.000 hộp/h)

- Tính toán tham số cơ điện tử:
  + Delta_T = T_sonotrode - T_cleanroom (Nhiệt chênh lệch phát hiện nghẽn Chiller)
  + dT/dt: Đạo hàm biến thiên nhiệt đầu hàn theo thời gian
  + P_mech = (Torque * 2 * pi * RPM) / 60.000 (Công suất cơ học động cơ Servo, kW)
  + HSI = (P_mech * 100) / (|Delta_T| + 0.1) (Chỉ số căng thẳng tải nhiệt)


### ✅ Pha 2: Relational Data Modeling Star Schema (setup_database.py)

- Xây dựng kho dữ liệu SQLite (packaging_factory.db) chuẩn Kimball.

- dim_machines: Thông tin tài sản thiết bị và công suất định danh CPH.

- dim_error_catalog: Chuẩn hóa 5 mã lỗi Nestlé (E-105, E-401, E-204, E-302, E-999) kèm quy chuẩn LOTO và PPE.

- fact_sensor_telemetry: Lưu 10.000 bản ghi cảm biến với Composite Index (line_id, timestamp).

- fact_downtime_events: Lưu 339 sự cố dừng máy, tính Units Lost = (CPH / 60) * Downtime_Minutes.

- fact_work_orders: Lưu 339 phiếu bảo trì với trạng thái an toàn LOTO (PENDING_ISOLATION, VERIFIED_LOTO, RESTORED).


### ✅ Pha 3: Analytics Engine & LOTO Guardrails (factory_tools.py)

- Bộ chỉ số TPM Reliability: MTTR = 10.09 phút, MTBF = 25.53 phút, Availability = 71.67%.

- Phân tích Pareto 80/20: Nhóm Vital Few gồm E-401 (37.11%) và E-302 (28.14%) chiếm 65.26% tổng sản lượng thất thoát.

- Chốt chặn an toàn nhiệt LOTO: Ngăn chặn tuyệt đối việc đóng phiếu nếu T_sonotrode > 40.0°C (Nguy cơ bỏng cấp 2).


### ✅ Pha 4: Closed-Loop Digital Twin & Fast-Path AI (simulate_line.py, agent_daemon.py, agent_core.py)

- Safety Interlock Handshake: Máy gặp sự cố sẽ dừng khẩn cấp (TRIPPED), khóa cứng dây chuyền và chỉ chạy tiếp sau khi Kỹ thuật viên nghiệm thu và đóng phiếu trên Dashboard.

- Async Producer-Consumer Daemon: Tách biệt luồng cảm biến khỏi luồng AI bằng hàng đợi queue.Queue, triệt tiêu nghẽn I/O và drop frame.

- Fast Single-Shot Zero-Tool RCA: Gemini phản hồi trong 1.2 giây, triệt tiêu 100% lỗi 429 Rate Limit và 503 Overload.

- Industrial Edge Expert Engine: Tự động suy luận vật lý cục bộ trong 0.01s khi mất mạng Internet.


### ✅ Pha 5: Operations Center & Integration Gateway (api_gateway.py, app.py)

- api_gateway.py: Cổng RESTful API chuẩn OpenAPI 3.0 / Swagger, sẵn sàng tích hợp Microsoft Power Apps và Power BI.

- app.py: Dashboard Streamlit giám sát trực quan 3 dây chuyền, còi báo động đỏ nhấp nháy khi TRIPPED, form kiểm định LOTO đóng phiếu mở khóa máy và khung chat Copilot tương tác.